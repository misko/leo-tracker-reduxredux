"""Reusable TRAIN-only original context and metadata-only frozen prediction port."""
import json
from pathlib import Path
import sys
import numpy as np
from numpy.testing import assert_allclose
from derive_blocks import digest
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.sequential_group_calibration import SequentialShift,freeze_sequential_calibration
from leo.analysis.shared_scan_model import SharedScanObjective,elevation_geometry,horizon_weight
from leo.analysis.hard60_score import predict_orbits
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
sys.path.append(str(REPORTS/'2026_10_16_dsx01_models'))
sys.path.append(str(REPORTS/'2026_10_17_dsx01_iteration4'/'cold_pipeline'))
from common import Context
from evaluate import extend_bank


def load_training_context(attempt=HERE/'S03-block20-parity0'):
    """Load only the derived training export, its causal archive and fit receipts."""
    attempt=Path(attempt);d=json.loads((attempt/'derivation.json').read_text())
    terminal=json.loads((attempt/'output'/'terminal.json').read_text())
    if terminal['state']!='complete':raise ValueError('Complete strict original training endpoint required')
    encoded=(attempt/'training-input.json').read_bytes();assert digest(encoded)==d['derived_input_sha256']==terminal['input_sha256']
    source=load_input(json.loads(encoded));prepared,nodes=prepare_views(source)
    assert prepared['all'].evidence_sha256==terminal['provenance']['evidence_sha256']
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots=[s for s in archive.list_snapshots() if s.digest==d['causal_tle']['sha256'] and
        s.provider==d['causal_tle']['provider'] and s.collected_utc_ns==d['causal_tle']['collected_utc_ns']]
    if len(snapshots)!=1:raise ValueError('Unique pinned causal snapshot required')
    assert snapshots[0].collected_utc_ns<prepared['all'].start_utc_ns-505_000_000_000
    filtered,_=exclude_labelled_starlink_debris(archive.read(snapshots[0]));catalogue=parse_element_sets(filtered)
    prior=RegionalPrior(**terminal['provenance']['prior'])
    bank,_=extend_bank(catalogue,list(map(int,terminal['candidate_numbers'])),prepared['all'].start_utc_ns,
        prepared['all'].observations,prior)
    stages={p.stem:json.loads(p.read_text()) for p in (attempt/'output'/'stages').glob('*.json')}
    model,fit,audit=selected_model(prepared,bank,prior,nodes,terminal,stages)
    assert audit['accepted']
    obs=prepared['all'].observations
    return Context('S03-block20-parity0',model,model,np.array(fit['vector']),np.array(fit['nuisance']),
        obs,bank,prior,np.ones(len(obs.times_s),bool),np.asarray(nodes),
        dict(derived_input_sha256=d['derived_input_sha256'],attempt=str(attempt),source_generation_policy=terminal['source_generation_policy']))


def predict_original(context,vector,nuisance,metadata):
    """Return base predictions/visibility/q without reading metadata.measured_hz.

    For a future changed model, callers must explicitly add and disclose its
    residual correction before scoring. This port never silently drops terms.
    """
    model=context.model
    if type(model) is not SharedScanObjective:raise ValueError('Explicit original shared prediction port; declare changed-model corrections separately')
    v,n=np.asarray(vector),np.asarray(nuisance);model.split(n)
    train=model.observations;raw=model.original
    receivers=tuple(map(int,np.unique(train.receiver[train.channel>=5])))
    shift=SequentialShift(receivers,[raw.baseline[(train.receiver==rx)&(train.channel>=5)][0] for rx in receivers])
    assert_allclose(shift.predict(train.receiver,train.channel>=5),raw.baseline,atol=1e-10,rtol=0)
    calibration=freeze_sequential_calibration(raw,dict(vector=v,nuisance=n[:model.base_nuisance_count]),shift)
    correction=calibration.predict(metadata.times_s,metadata.rf_hz,metadata.receiver,metadata.channel>=5)
    tau=v[7]+model.basis@v[8:]
    prediction=predict_orbits(context.bank,metadata,context.prior,v[:2],tau,derivatives=False)[0]+correction[:,None]
    visibility=horizon_weight(elevation_geometry(context.bank,metadata,context.prior,v[:2],tau)[0],model.visibility_width)[0]
    q=model.hyperparameters(n[model.base_nuisance_count:])[2]
    return dict(prediction_hz=prediction,visibility_weight=visibility,correction_hz=correction,
        detection_probability=q,number=context.bank.numbers.copy())
