"""Prediction-only audit of discarded GLRT peaks under the saved fixed profile.

No peak substitution is credited to DSX01. A within-RX/channel time permutation
is a negative control for the extra opportunities introduced by several peaks.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
PREV=REPORTS/'2026_10_16_dsx01_iteration2'
sys.path[:0]=[str(REPORTS/'2026_10_16_dsx01_models'),str(PREV)]
from common import load_context, save_json
from bank_expansion import fixed_shift
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.cli.shared_fast_position import load_input
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.contracts.regional_position import PositionObservations
from leo.analysis.sequential_group_calibration import freeze_sequential_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.shared_scan_model import elevation_geometry, horizon_weight, density


def lane_permutation(obs):
    """Preserve each lane's measured frequency distribution, destroy time links."""
    measured=obs.measured_hz.copy()
    for rx,ch in sorted(set(zip(obs.receiver,obs.channel))):
        rows=np.flatnonzero((obs.receiver==rx)&(obs.channel==ch))
        # One fixed near-half-cycle rotation; no target/identity-dependent tuning.
        measured[rows]=np.roll(measured[rows],max(1,len(rows)//2))
    return replace(obs,measured_hz=measured)


def run(sid):
    import csv
    context=load_context(sid)
    source=context.source
    _,document,_,_=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2').plot_evidence(source['job_id'])
    candidates=project_scanner_candidates(load_input(document))
    candidates=sorted(candidates,key=lambda p:(p.support_center_utc_ns,p.source_group_id,p.candidate_rank))
    origin=source['first_sample_estimate_utc_ns']
    obs=PositionObservations(tuple(p.candidate_id for p in candidates),
        np.array([(p.support_center_utc_ns-origin)/1e9 for p in candidates]),
        np.array([p.measured_cfo_hz for p in candidates]),np.array([p.actual_rf_hz for p in candidates]),
        np.array([p.receiver_id for p in candidates]),np.array([p.channel for p in candidates]),
        np.array([p.margin for p in candidates]))
    fit=json.loads((PREV/'results'/f'{sid}-fitted-c-profile.json').read_text())
    vector,nuisance=np.asarray(fit['vector']),np.asarray(fit['nuisance'])
    model=context.model
    calibration=freeze_sequential_calibration(model.original,
        dict(vector=vector,nuisance=nuisance[:model.base_nuisance_count]),fixed_shift(model))
    tau=vector[7]+model.basis@vector[8:]
    predicted=predict_orbits(context.bank,obs,context.prior,vector[:2],tau,derivatives=False)[0]
    predicted+=calibration.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)[:,None]
    visible=horizon_weight(elevation_geometry(context.bank,obs,context.prior,vector[:2],tau)[0],
                           model.visibility_width)[0]
    q=model.hyperparameters(nuisance[model.base_nuisance_count:])[2]
    sigma=np.full(len(candidates),125.)
    groups={}
    for i,p in enumerate(candidates):groups.setdefault(p.source_group_id,[]).append(i)
    winner={key:min(rows,key=lambda i:(-candidates[i].margin,candidates[i].candidate_rank,candidates[i].candidate_id))
            for key,rows in groups.items()}
    order=[winner[key] for key in context.observations.window_ids]
    np.testing.assert_allclose(obs.times_s[order],context.observations.times_s,atol=1e-9,rtol=0)
    np.testing.assert_array_equal(obs.measured_hz[order],context.observations.measured_hz)
    states={}
    for label,observations in [('actual',obs),('within_lane_time_permutation',lane_permutation(obs))]:
        terms,_=density(observations.measured_hz,predicted,visible,sigma,q,model.score)
        best=terms.responsibilities.argmax(axis=1)
        associated=terms.responsibilities[np.arange(len(candidates)),best]>terms.clutter_probability
        states[label]=associated
        if label=='actual':
            with np.load(PREV/'results'/f'{sid}-fitted-c-profile.npz') as frozen:
                np.testing.assert_array_equal(associated[order],frozen['associated'])
                np.testing.assert_allclose(terms.residual_hz[np.array(order),best[order]],frozen['residual_hz'],atol=1e-6,rtol=0)
    data=REPORTS/'2026_10_16_dsx01_fast_association_losses'
    with (data/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']==sid]
    def summary(keys):
        result=dict(observations=len(keys),winner_associated=int(sum(states['actual'][winner[k]] for k in keys)))
        for label,a in states.items():
            result[label]=dict(any_peak_associated=int(sum(a[groups[k]].any() for k in keys)),
                winner_unassociated_with_associated_alternative=int(sum(not a[winner[k]] and a[groups[k]].any() for k in keys)))
        return result
    windows=[]
    for rid in sorted(set(r['region_id'] for r in members)):
        windows.append(dict(region_id=rid,**summary([r['observation_id'] for r in members if r['region_id']==rid])))
    result=dict(source_id=sid,input_sha256=source['tracking_input_sha256'],terminal_sha256=source['terminal_sha256'],
        model='saved exact fixed-bank fitted-c profile',candidate_peaks=len(candidates),
        full=summary(context.observations.window_ids),windows=windows,
        closure='All original winner IDs/times/CFO/associated flags and residuals exactly replayed; calibration transported through public frozen sequential function.',
        qualification='Any-peak association is an opportunity diagnostic, not recovery or identity truth. Multiple alternatives increase accidental matches; the permutation is a negative control, not a calibrated significance test. No fit or selection occurred.')
    save_json(HERE/'alternatives'/f'{sid}.json',result)
    print(json.dumps(dict(source_id=sid,**result['full'])),flush=True)


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=5) as pool:
        for future in as_completed([pool.submit(run,s) for s in ['S01','S02','S03','S04','S05']]):future.result()
