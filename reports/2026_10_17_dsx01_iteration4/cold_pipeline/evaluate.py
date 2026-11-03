"""Prediction-only held evaluation of an original TRAIN-discovered endpoint."""
from dataclasses import asdict
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from derive import digest,payload
from clock_transport import extend_frozen_clock
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views,plain
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.sequential_group_calibration import SequentialShift,freeze_sequential_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.shared_scan_model import density,elevation_geometry,horizon_weight
from leo.analysis.regional_position_score import coordinates
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionObservations,RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
ATTEMPT=HERE/'S03-early_to_late'


def save(path,value):
    with path.open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def stage_costs(terminal,stages):
    points=[v for k,v in stages.items() if k.startswith('discovery-point:')]
    fits=[f for p in points for f in p.get('fits',{}).values()]
    counted={k:v['result'] for k,v in stages.items() if isinstance(v.get('result'),dict) and
        'allocation' in v['result'] and 'actual_objective_calls' in v['result']}
    for name,value in counted.items():
        assert value['actual_objective_calls_exact']
        assert value['actual_objective_calls']<=value['allocation']['total_objectives']
        assert value['elapsed_seconds']<=value['allocation']['total_seconds']+.05
    if terminal.get('actual_objective_calls') is not None:
        assert sum(v['actual_objective_calls'] for v in counted.values())==terminal['actual_objective_calls']
        assert len(counted)==terminal['optimizer_calls']
    costs=dict(whole_pipeline_elapsed_seconds=terminal['elapsed_seconds'],
        actual_a_b_shared_objective_calls=terminal.get('actual_objective_calls'),
        a_b_shared_optimizer_calls=terminal.get('optimizer_calls'),
        prescreen_objective_calls=terminal.get('prescreen_objective_calls'),
        cost_exact=terminal.get('cost_exact'),unfinished_stages=terminal.get('unfinished_stages'),
        discovery_points=len(points),discovery_fit_receipts=len(fits),
        discovery_converged_fits=sum(bool(f.get('converged')) for f in fits),
        discovery_reported_solver_evaluations=sum(f.get('evaluations',0) for f in fits),
        discovery_summed_fit_elapsed_seconds=sum(f.get('elapsed_s',0.) for f in fits),
        counted_fit_receipts={name:dict(actual_objective_calls=v['actual_objective_calls'],
            accepted=v.get('audit',{}).get('accepted'),stationarity=v.get('audit',{}).get('stationarity'),
            allocation=v['allocation']) for name,v in counted.items()},
        shape_attempts=sum(len(v.get('result',{}).get('attempts',[])) for k,v in stages.items() if k.startswith('shape-') and not k.endswith('-launch')),
        bootstrap_stage_count=sum(k.startswith('bootstrap-') and not k.endswith('-launch') for k in stages),
        stage_elapsed_seconds={k:v['elapsed_seconds'] for k,v in stages.items() if 'elapsed_seconds' in v},
        scope='Terminal counters cover A/B/shared only; discovery solver counters, shape/bootstrap and stage wall receipts remain separately scoped.')
    return costs


def extend_bank(catalogue,numbers,origin,obs,prior):
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    if not set(numbers)<=set(lookup):raise ValueError('Train-selected ID absent from causal archive')
    bank,receipt=build_regional_bank(catalogue,[lookup[n] for n in numbers],origin,obs,prior,maximum_seconds=90)
    order={int(n):i for i,n in enumerate(bank.numbers)}
    if set(order)!=set(numbers):raise ValueError('Training-selected ID propagation unavailable; never silently drop held predictions')
    return bank.select([order[n] for n in numbers]),receipt


def evaluate(*,verify=False):
    derivation=json.loads((ATTEMPT/'derivation.json').read_text())
    terminal=json.loads((ATTEMPT/'output'/'terminal.json').read_text())
    assert terminal['elapsed_seconds']<=480.1
    for path,sha in derivation['source_code_sha256'].items():assert digest(Path(path).read_bytes())==sha
    for name,sha in derivation['research_code_sha256'].items():assert digest((HERE/name).read_bytes())==sha
    stages={p.stem:json.loads(p.read_text()) for p in (ATTEMPT/'output'/'stages').glob('*.json')}
    report=dict(source_id='S03',direction='early_to_late',state=terminal['state'],
        reason=terminal.get('reason'),derivation_sha256=digest((ATTEMPT/'derivation.json').read_bytes()),
        terminal_sha256=digest((ATTEMPT/'output'/'terminal.json').read_bytes()),
        cost=stage_costs(terminal,stages),
        qualification='Single full-data-derived measurement export restricted before inference to whole probes in the first capture half. '
        'The bank, source proposals, location and calibration are newly training-derived; no target full-fit state is used. '
        'This is fitted-c production discovery, not whole-pipeline c0. Different data split and bank from fixed full-bank median-timestamp stresses.')
    if terminal['state']!='complete':
        save(ATTEMPT/'evaluation.json',report);return report
    data=(ATTEMPT/'training-input.json').read_bytes()
    assert digest(data)==derivation['derived_input_sha256']==terminal['input_sha256']
    source=load_input(json.loads(data));prepared,nodes=prepare_views(source)
    assert_array_equal(nodes,terminal['provenance']['clock_nodes_s'])
    assert prepared['all'].evidence_sha256==terminal['provenance']['evidence_sha256']
    prior=RegionalPrior(**terminal['provenance']['prior'])
    origin=prepared['all'].start_utc_ns;numbers=list(map(int,terminal['candidate_numbers']))
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots=[s for s in archive.list_snapshots() if s.digest==derivation['causal_tle']['sha256'] and
        s.provider==derivation['causal_tle']['provider'] and s.collected_utc_ns==derivation['causal_tle']['collected_utc_ns']]
    if len(snapshots)!=1:raise ValueError('Unique causal training snapshot required')
    snapshot=snapshots[0]
    assert snapshot.digest==terminal['provenance']['tle_sha256']
    assert snapshot.collected_utc_ns<origin-505_000_000_000
    filtered,_=exclude_labelled_starlink_debris(archive.read(snapshot));catalogue=parse_element_sets(filtered)
    train_bank,train_receipt=extend_bank(catalogue,numbers,origin,prepared['all'].observations,prior)
    model,fit,audit=selected_model(prepared,train_bank,prior,nodes,terminal,stages)
    if not audit['accepted']:raise ValueError('Training selected endpoint failed original strict audit')
    v,n=np.asarray(fit['vector']),np.asarray(fit['nuisance'])
    raw=model.original;obs=model.observations
    receivers=tuple(map(int,np.unique(obs.receiver[obs.channel>=5])))
    shift=SequentialShift(receivers,[raw.baseline[(obs.receiver==r)&(obs.channel>=5)][0] for r in receivers])
    assert_allclose(shift.predict(obs.receiver,obs.channel>=5),raw.baseline,atol=1e-10,rtol=0)
    frozen=freeze_sequential_calibration(raw,dict(vector=v,nuisance=n[:model.base_nuisance_count]),shift)
    # Only timing/RF/receiver/channel/IDs enter prediction metadata. CFO is read
    # below, after all predictions and the extrapolated function are fixed.
    fields=('observation_id','time_s','receiver','channel','actual_rf_hz')
    metadata=[]
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['source_id']=='S03':
            selected={k:row[k] for k in fields}
            if selected['receiver'] not in (1,2):raise ValueError('Frozen report requires declared one-based receiver labels')
            selected['receiver']-=1  # Frozen report display RX1/RX2 -> contract receiver0/1.
            metadata.append(selected)
    full=PositionObservations(tuple(r['observation_id'] for r in metadata),
        np.array([r['time_s'] for r in metadata]),np.zeros(len(metadata)),
        np.array([r['actual_rf_hz'] for r in metadata]),np.array([r['receiver'] for r in metadata]),
        np.array([r['channel'] for r in metadata]),np.ones(len(metadata)))
    capture=derivation['preserved_authorities']['input_manifest_sha256']
    ids=lambda keys:{canonical_digest(dict(capture=capture,visit=k[0],rx=k[1],probe=k[2])) for k in keys}
    train_ids=ids(derivation['training_keys']);held_ids=ids(derivation['held_keys']);boundary_ids=ids(derivation['boundary_keys'])
    train=np.array([key in train_ids for key in full.window_ids]);held=np.array([key in held_ids for key in full.window_ids])
    boundary=np.array([key in boundary_ids for key in full.window_ids])
    assert_array_equal(train.astype(int)+held.astype(int)+boundary.astype(int),np.ones(len(metadata),int))
    assert set(obs.window_ids)==set(np.array(full.window_ids)[train])
    lookup={key:i for i,key in enumerate(full.window_ids)}
    original_train=np.array([lookup[key] for key in obs.window_ids])
    for name in ['times_s','rf_hz','receiver','channel']:
        assert_array_equal(getattr(full,name)[original_train],getattr(obs,name))
    assert held.any() and train.any()
    extended=extend_frozen_clock(frozen,float(np.floor(full.times_s.min())),float(np.ceil(full.times_s.max())))
    actual=extended.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
    expected=raw.correction(v,n[:model.base_nuisance_count])
    closure=float(np.max(abs(actual-expected),initial=0));assert closure<=1e-6
    full_bank,full_receipt=extend_bank(catalogue,numbers,origin,full,prior)
    indices=np.searchsorted(full_bank.nodes_s,train_bank.nodes_s)
    assert_array_equal(full_bank.nodes_s[indices],train_bank.nodes_s)
    assert_allclose(full_bank.position_km[:,indices],train_bank.position_km,atol=1e-9,rtol=0)
    assert_allclose(full_bank.velocity_km_s[:,indices],train_bank.velocity_km_s,atol=1e-12,rtol=0)
    tau=v[7]+model.basis@v[8:]
    prediction=predict_orbits(full_bank,full,prior,v[:2],tau,derivatives=False)[0]
    correction=extended.predict(full.times_s,full.rf_hz,full.receiver,full.channel>=5)
    prediction+=correction[:,None]
    visibility=horizon_weight(elevation_geometry(full_bank,full,prior,v[:2],tau)[0],model.visibility_width)[0]
    q=model.hyperparameters(n[model.base_nuisance_count:])[2]
    prediction_path=ATTEMPT/'held-predictions.npz'
    prediction_arrays=dict(prediction_hz=prediction,visibility_weight=visibility,
        correction_hz=correction,number=full_bank.numbers,times_s=full.times_s,
        train_mask=train,held_mask=held,boundary_mask=boundary,detection_probability=q)
    if prediction_path.exists():
        if not verify:raise FileExistsError('Prediction receipt exists; never overwrite')
        with np.load(prediction_path) as saved:
            for name,value in prediction_arrays.items():assert_array_equal(saved[name],value)
    else:
        if verify:raise FileNotFoundError('Missing original prediction receipt')
        np.savez_compressed(prediction_path,**prediction_arrays)
    # Evaluation begins here. No fitted state may change after this point.
    evaluation_rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    evaluation_rows=[r for r in evaluation_rows if r['source_id']=='S03']
    assert [r['observation_id'] for r in evaluation_rows]==list(full.window_ids)
    measured=np.array([r['measured_cfo_hz'] for r in evaluation_rows])
    terms,details=density(measured,prediction,visibility,np.full(len(measured),125.),q,model.score)
    best=terms.responsibilities.argmax(1);assigned=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    residual=terms.residual_hz[np.arange(len(best)),best]
    def metric(mask):
        use=mask&assigned
        original=np.array([r['original_associated'] for r in evaluation_rows])
        return dict(observations=int(mask.sum()),associated=int(use.sum()),
            associated_rms_hz=float(np.sqrt(np.mean(residual[use]**2))) if use.any() else None,
            conditional_cfo_nll=float(details['row_nll'][mask].sum()),
            original_full_fit_associated=int((mask&original).sum()),
            new_vs_original_full_fit=int((mask&assigned&~original).sum()),
            lost_vs_original_full_fit=int((mask&~assigned&original).sum()))
    train_eval=model.evaluate_joint(v,n)
    assert_allclose(terms.nll if train.all() else details['row_nll'][train].sum(),train_eval[3].nll,atol=1e-6,rtol=0)
    with (DATA/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']=='S03']
    windows=[]
    for rid in sorted(set(r['region_id'] for r in members)):
        selected={r['observation_id'] for r in members if r['region_id']==rid}
        mask=np.array([key in selected for key in full.window_ids])
        windows.append(dict(region_id=rid,full=metric(mask),train=metric(mask&train),held=metric(mask&held)))
    lat,lon=coordinates(prior,v[:2])
    report.update(training_audit=audit,position=dict(latitude_deg=float(lat),longitude_deg=float(lon)),
        training_selected_numbers=numbers,training_full_regional_candidates=len(terminal['provenance']['full_candidate_numbers']),
        propagation=dict(train=asdict(train_receipt),full_evaluation=asdict(full_receipt),
            exact_selected_order_preserved=True,training_overlap_position_max_error_km=float(np.max(abs(full_bank.position_km[:,indices]-train_bank.position_km))),
            no_held_discovery=True),
        clock_transport=dict(training_nodes_s=frozen.common.clock_nodes_s,evaluation_nodes_s=extended.common.clock_nodes_s,
            training_closure_max_error_hz=closure,policy='Constant residual-clock boundary extension, learned affine slopes retained; no new fitted knots'),
        full=metric(np.ones(len(measured),bool)),train=metric(train),held=metric(held),boundary=metric(boundary),
        windows=windows,cut_s=derivation['cut_s'],original_median_timestamp_s=float(np.median(full.times_s)),
        prediction_artifact_sha256=digest(prediction_path.read_bytes()),
        common_timing_s=float(v[7]),relative_timing_rms_s=float(np.sqrt(np.mean((model.basis@v[8:])**2))),
        total_timing_s={str(k):float(t) for k,t in zip(numbers,tau)},c=float(v[6]),
        learned_band_offsets_hz=shift.offsets_hz,bank_conditioning='TRAIN-discovered selected IDs; not full-bank conditioned',
        winner_association_rule='Maximum satellite posterior exceeds clutter, original125Hz density',
        identity_claimed=False)
    evaluation_arrays=dict(associated=assigned,residual_hz=residual,
        satellite_number=full_bank.numbers[best],times_s=full.times_s,train_mask=train,held_mask=held,boundary_mask=boundary)
    if verify:
        with np.load(ATTEMPT/'evaluation.npz') as saved:
            for name,value in evaluation_arrays.items():assert_array_equal(saved[name],value)
        previous=json.loads((ATTEMPT/'evaluation.json').read_text())
        for name in ['train','held','windows','position','training_audit','clock_transport']:
            assert plain(report[name])==previous[name]
        for name in ['train','full_evaluation']:
            stable=lambda value:{k:v for k,v in value.items() if k!='elapsed_s'}
            assert plain(stable(report['propagation'][name]))==stable(previous['propagation'][name])
        report.update(replayed_original_evaluation_sha256=digest((ATTEMPT/'evaluation.json').read_bytes()),
            exact_prediction_and_evaluation_arrays_replayed=True,
            evaluation_code_sha256=digest(Path(__file__).read_bytes()),
            replay_scope='Read-only repeat of saved predictions, arrays, metrics, strict endpoint and stronger cost audits; no fit or state change')
        save(ATTEMPT/'evaluation-replay.json',report)
    else:
        np.savez_compressed(ATTEMPT/'evaluation.npz',**evaluation_arrays)
        save(ATTEMPT/'evaluation.json',report)
    print(json.dumps(dict(state='evaluated',train=report['train'],held=report['held'],windows=windows)),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();evaluate(verify=args.verify)
