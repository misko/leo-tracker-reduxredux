"""No-fit interpolation scoring; native training clock covers all held gaps."""
import argparse
import csv
import json
from pathlib import Path
import sys
import numpy as np
from numpy.testing import assert_array_equal,assert_allclose
from derive_blocks import digest
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views,plain
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.sequential_group_calibration import SequentialShift,freeze_sequential_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.shared_scan_model import density,elevation_geometry,horizon_weight
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import PositionObservations,RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
ATTEMPT=HERE/'S03-block20-parity0'
HELPERS=REPORTS/'2026_10_17_dsx01_iteration4'/'cold_pipeline'
sys.path.append(str(HELPERS))
from evaluate import stage_costs,extend_bank
from support_diagnostics import support


def save(path,value):
    with path.open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def score(*,verify=False):
    sealed=json.loads((HELPERS/'manifest.json').read_text())
    for name in ['evaluate.py','support_diagnostics.py']:
        bound=next(r for r in sealed['files'] if r['path']==name)
        assert digest((HELPERS/name).read_bytes())==bound['sha256']
    d=json.loads((ATTEMPT/'derivation.json').read_text());terminal=json.loads((ATTEMPT/'output'/'terminal.json').read_text())
    for path,sha in d['source_code_sha256'].items():assert digest(Path(path).read_bytes())==sha
    for name,sha in d['research_code_sha256'].items():assert digest((HERE/name).read_bytes())==sha
    stages={p.stem:json.loads(p.read_text()) for p in (ATTEMPT/'output'/'stages').glob('*.json')}
    report=dict(source_id='S03',protocol='Alternating20s whole-probe parity0 gap interpolation',state=terminal['state'],
        reason=terminal.get('reason'),cost=stage_costs(terminal,stages),evaluation_denominators=d['evaluation_denominators'],
        derivation_sha256=digest((ATTEMPT/'derivation.json').read_bytes()),terminal_sha256=digest((ATTEMPT/'output'/'terminal.json').read_bytes()))
    if terminal['state']!='complete':save(ATTEMPT/'evaluation.json',report);return report
    encoded=(ATTEMPT/'training-input.json').read_bytes();assert digest(encoded)==d['derived_input_sha256']==terminal['input_sha256']
    source=load_input(json.loads(encoded));prepared,nodes=prepare_views(source)
    assert_array_equal(nodes,terminal['provenance']['clock_nodes_s'])
    assert prepared['all'].evidence_sha256==terminal['provenance']['evidence_sha256']
    prior=RegionalPrior(**terminal['provenance']['prior']);origin=prepared['all'].start_utc_ns
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots=[s for s in archive.list_snapshots() if s.digest==d['causal_tle']['sha256'] and
        s.provider==d['causal_tle']['provider'] and s.collected_utc_ns==d['causal_tle']['collected_utc_ns']]
    assert len(snapshots)==1;snapshot=snapshots[0]
    assert snapshot.digest==terminal['provenance']['tle_sha256'] and snapshot.collected_utc_ns<origin-505_000_000_000
    filtered,_=exclude_labelled_starlink_debris(archive.read(snapshot));catalogue=parse_element_sets(filtered)
    numbers=list(map(int,terminal['candidate_numbers']))
    bank,bank_receipt=extend_bank(catalogue,numbers,origin,prepared['all'].observations,prior)
    model,fit,audit=selected_model(prepared,bank,prior,nodes,terminal,stages)
    assert audit['accepted'];v,n=np.asarray(fit['vector']),np.asarray(fit['nuisance'])
    obs=model.observations;raw=model.original;receivers=tuple(map(int,np.unique(obs.receiver[obs.channel>=5])))
    shift=SequentialShift(receivers,[raw.baseline[(obs.receiver==rx)&(obs.channel>=5)][0] for rx in receivers])
    assert_allclose(shift.predict(obs.receiver,obs.channel>=5),raw.baseline,atol=1e-10,rtol=0)
    calibration=freeze_sequential_calibration(raw,dict(vector=v,nuisance=n[:model.base_nuisance_count]),shift)
    fields=['observation_id','time_s','actual_rf_hz','receiver','channel']
    metadata=[]
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['source_id']=='S03':
            point={name:row[name] for name in fields};assert point['receiver'] in (1,2);point['receiver']-=1;metadata.append(point)
    full=PositionObservations(tuple(r['observation_id'] for r in metadata),np.array([r['time_s'] for r in metadata]),
        np.zeros(len(metadata)),np.array([r['actual_rf_hz'] for r in metadata]),np.array([r['receiver'] for r in metadata]),
        np.array([r['channel'] for r in metadata]),np.ones(len(metadata)))
    roles={r['global_group_id']:r['role'] for r in d['membership']}
    masks={role:np.array([roles[k]==role for k in full.window_ids]) for role in ['train','held','boundary']}
    assert_array_equal(sum(m.astype(int) for m in masks.values()),np.ones(len(metadata),int))
    assert set(obs.window_ids)==set(np.array(full.window_ids)[masks['train']])
    index={key:i for i,key in enumerate(full.window_ids)};train_indices=np.array([index[k] for k in obs.window_ids])
    for name in ['times_s','rf_hz','receiver','channel']:assert_array_equal(getattr(full,name)[train_indices],getattr(obs,name))
    assert full.times_s.min()>=nodes[0] and full.times_s.max()<=nodes[-1]
    correction=calibration.predict(full.times_s,full.rf_hz,full.receiver,full.channel>=5)
    closure=float(np.max(abs(correction[train_indices]-raw.correction(v,n[:model.base_nuisance_count])),initial=0));assert closure<=1e-6
    tau=v[7]+model.basis@v[8:]
    prediction=predict_orbits(bank,full,prior,v[:2],tau,derivatives=False)[0]+correction[:,None]
    visibility=horizon_weight(elevation_geometry(bank,full,prior,v[:2],tau)[0],model.visibility_width)[0]
    q=model.hyperparameters(n[model.base_nuisance_count:])[2]
    arrays=dict(prediction_hz=prediction,visibility_weight=visibility,correction_hz=correction,
        number=bank.numbers,times_s=full.times_s,detection_probability=q,
        **{role+'_mask':mask for role,mask in masks.items()})
    prediction_path=ATTEMPT/'predictions.npz'
    if verify:
        with np.load(prediction_path) as frozen:
            for name,value in arrays.items():assert_array_equal(frozen[name],value)
    else:
        if prediction_path.exists():raise FileExistsError('Prediction receipt exists; no overwrite')
        np.savez_compressed(prediction_path,**arrays)
    # CFO and full-fit descriptive labels enter evaluation only after freeze.
    rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']=='S03'];assert [r['observation_id'] for r in rows]==list(full.window_ids)
    terms,details=density(np.array([r['measured_cfo_hz'] for r in rows]),prediction,visibility,np.full(len(rows),125.),q,model.score)
    best=terms.responsibilities.argmax(1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    residual=terms.residual_hz[np.arange(len(best)),best]
    original=np.array([r['original_associated'] for r in rows]);present=np.array([r['original_best_satellite'] in numbers for r in rows])
    def metric(mask):
        chosen=mask&associated;intersection=mask&associated&original
        return dict(observations=int(mask.sum()),associated=int(chosen.sum()),
            associated_rms_hz=float(np.sqrt(np.mean(residual[chosen]**2))) if chosen.any() else None,
            frequency_nll=float(details['row_nll'][mask].sum()),original_full_fit_associated=int((mask&original).sum()),
            new_vs_original_full_fit=int((mask&associated&~original).sum()),lost_vs_original_full_fit=int((mask&~associated&original).sum()),
            retained_vs_original_full_fit=int(intersection.sum()),
            original_winner_ids_absent_from_train_bank=int((mask&original&~present).sum()),
            lost_original_rows_with_absent_original_winner=int((mask&original&~associated&~present).sum()))
    assert_allclose(details['row_nll'][masks['train']].sum(),model.evaluate_joint(v,n)[3].nll,atol=1e-6,rtol=0)
    with (DATA/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']=='S03']
    windows=[]
    for rid in sorted(set(r['region_id'] for r in members)):
        ids={r['observation_id'] for r in members if r['region_id']==rid};use=np.array([key in ids for key in full.window_ids])
        windows.append(dict(region_id=rid,full=metric(use),**{role:metric(use&mask) for role,mask in masks.items()}))
    lat,lon=coordinates(prior,v[:2])
    report.update(training_audit=audit,position=dict(latitude_deg=float(lat),longitude_deg=float(lon)),
        full=metric(np.ones(len(rows),bool)),**{role:metric(mask) for role,mask in masks.items()},windows=windows,
        visibility_frequency={role:support(terms,visibility,q,mask) for role,mask in masks.items()},
        training_selected_ids=numbers,training_regional_bank_count=len(terminal['provenance']['full_candidate_numbers']),
        clock=dict(nodes_s=nodes,held_times_inside_native_training_clock_support=True,
            training_correction_closure_hz=closure,extrapolation='none; unchanged trained function interpolates held gaps'),
        learned_band_offsets_hz=shift.offsets_hz,common_timing_s=float(v[7]),
        relative_timing_rms_s=float(np.sqrt(np.mean((model.basis@v[8:])**2))),
        total_timing_s={str(k):float(t) for k,t in zip(numbers,tau)},c=float(v[6]),
        prediction_sha256=digest(prediction_path.read_bytes()),evaluation_code_sha256=digest(Path(__file__).read_bytes()),
        helper_source_sha256={name:digest((HELPERS/name).read_bytes()) for name in ['evaluate.py','support_diagnostics.py']},
        qualification='One predeclaredS03 parity0 interpolation pilot with TRAIN-only public production discovery. '
        'Original125Hz winner classifier, unchanged observation IDs/values. No held fit, bank addition, calibration or timing adjustment. '
        'Full-fit IDs are descriptive oracle labels only, not verified identities and never used for training. '
        'Production source generation fitsc throughout; no whole-pipelinec0 claim. Different split/bank from half-forecast baseline; no new-position generalization claim.')
    output=dict(associated=associated,residual_hz=residual,satellite_number=bank.numbers[best],times_s=full.times_s,
        **{role+'_mask':mask for role,mask in masks.items()})
    if verify:
        with np.load(ATTEMPT/'evaluation.npz') as frozen:
            for name,value in output.items():assert_array_equal(frozen[name],value)
        previous=json.loads((ATTEMPT/'evaluation.json').read_text())
        for name in ['train','held','boundary','windows','training_audit','clock','visibility_frequency']:
            assert plain(report[name])==previous[name]
        report.update(exact_saved_prediction_and_score_replay=True,original_evaluation_sha256=digest((ATTEMPT/'evaluation.json').read_bytes()))
        save(ATTEMPT/'verification.json',report)
    else:
        np.savez_compressed(ATTEMPT/'evaluation.npz',**output);save(ATTEMPT/'evaluation.json',report)
    print(json.dumps(dict(state='scored',train=report['train'],held=report['held'],boundary=report['boundary'],
        selected_ids=len(numbers),strict_kkt=audit['stationarity'],windows=windows)),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();score(verify=args.verify)
