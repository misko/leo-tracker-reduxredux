"""Pre-forecast amendment: remove whole D from inherited noise estimation."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import traceback

START = time.monotonic()
import numpy as np
import predict as first
import conditional
import ds23_radio_noise as noise

OWN = Path(__file__).resolve().parent
HERE = OWN / 'run02'
ROOT = OWN.parent
base, r, w, k, sr = first.base, first.r, first.w, first.k, first.sr
ARMS, MODELS, ORDERS, CAP = first.ARMS, first.MODELS, first.ORDERS, first.CAP


def read(path): return first.read(path)
def sha(path): return first.sha(path)
def write(name, value): r.write_new(HERE/name, value)
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, default=r.encode).encode()).hexdigest()


def save_arrays(name, **arrays):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: np.savez_compressed(stream,**arrays)


def exclude_target(tracks, key):
    if sum(track['key']==key for track in tracks)!=1:
        raise ValueError('Exactly one complete D owner required')
    return [track for track in tracks if track['key']!=key]


def replace_noise(scan, model):
    changed=copy.copy(scan)
    changed.fixed_window_noise=model
    changed.radio_sigma_hz=float(model['constant_radio_sigma_hz'])
    changed.fixed_window_noise_sha256=digest(model)
    return changed


def rebuilt(d, entry, arm, x):
    model=noise.estimate(exclude_target(d['scan'].tracks,entry['component']),d['observations'])
    changed=dict(d,scan=replace_noise(d['scan'],model))
    changed['base']=r.build(changed,'c0',changed['arms']['c0']['phase_reference'])
    refreshed,info=k.cavity(changed,[],arm)
    if not w.hard_parent(info): raise ValueError('Leave-D-out parent hard prerequisite failed')
    parent=r.build(refreshed,arm,info['phase_reference'])
    ids=[oid for i in parent.members for oid in parent.scan.tracks[i]['observation_ids']]
    expected=np.array([model['per_observation_noise_sigma_hz'][oid]
        if model['extra_parameter_BIC_gain']>0 else model['constant_radio_sigma_hz'] for oid in ids])
    if parent.point_noise.shape!=expected.shape or not np.array_equal(parent.point_noise,expected):
        raise ValueError('Actual parent point noise did not use regenerated noise model')
    comp=w.background(refreshed,arm,x,[entry])
    minimum=min(model['per_observation_noise_sigma_hz'][oid] if model['extra_parameter_BIC_gain']>0
        else model['constant_radio_sigma_hz'] for oid in entry['observation_ids'])*np.sqrt(2)
    if np.linalg.eigvalsh(comp['covariance']-300.**2*np.ones((29,29))).min()<=0:
        raise ValueError('One shared constant / positive remaining covariance prerequisite failed')
    return model,info,comp,float(np.max(abs(parent.point_noise-expected))),minimum


def redacted_context(d, entry, held, delta):
    changed=dict(d);scan=copy.copy(d['scan']);scan.tracks=list(scan.tracks)
    track=dict(scan.tracks[entry['track_index']]);values=np.asarray(track['values']).copy()
    values[held]+=delta;track['values']=values;scan.tracks[entry['track_index']]=track;changed['scan']=scan
    ids={entry['observation_ids'][i] for i in held}
    changed['observations']=[dict(row,measured_cfo_hz=row['measured_cfo_hz']+delta)
        if row['observation_id'] in ids else row for row in d['observations']]
    return changed


def prepare():
    base.threads();sr.alarm(90.)
    if (OWN/'execution_started.json').exists(): raise ValueError('Initial exposed-noise forecasts must remain unexecuted')
    prior=read(OWN/'protocol.json')
    for path,expected in prior['bindings'].items():
        if sha(path)!=expected:raise ValueError('Preserved preparation changed: '+path)
    d,x,family,target,entry=base.input_context()
    old=read(base.r.SOURCE/base.CASE/'radio_noise.json')
    if sha(Path(noise.__file__))!=old['code_sha256']:
        raise ValueError('Original noise estimator source changed')
    target_track=d['scan'].tracks[entry['track_index']]
    pieces=[dict(degree=piece['degree'],points=int(np.sum((target_track['times']>=piece['start_s'])&(target_track['times']<=piece['end_s']))),
                 start_s=piece['start_s'],end_s=piece['end_s']) for piece in target_track['pieces']]
    frozen=dict(np.load(OWN/'c0_input.npz'));folds=conditional.split_indices(frozen['times'],frozen['native_ids'])
    records=[];redactions=[]
    for arm in ARMS:
        model,info,comp,point_error,minimum=rebuilt(d,entry,arm,x)
        if old['noise_samples']-model['noise_samples']!=29:
            raise ValueError('Whole D noise exclusion did not remove exactly29 residual samples')
        if not np.array_equal(comp['q'],frozen['q']):raise ValueError('Cached q-scaled geometry no longer applies')
        save_arrays(arm+'_input.npz',raw=comp['raw'],covariance=comp['covariance'],q=comp['q'],x=x,
            values=frozen['values'],times=frozen['times'],native_ids=frozen['native_ids'],
            parent_coefficients=comp['parent_coefficients'],parent_noise=comp['parent_noise'])
        write(arm+'_parent.json',info);write(arm+'_noise.json',model)
        records.append(dict(arm=arm,noise_hash=digest(model),noise_samples=model['noise_samples'],
            actual_point_noise_max_error=point_error,target_minimum_noise_SD=minimum,
            original_parent_gates_pass=info['original_remaining_gates_pass'],parent_phase_reference=info['phase_reference']))
        for fold,train,held in folds:
            for delta in (-1000.,1000.):
                other,other_info,test,err,_=rebuilt(redacted_context(d,entry,held,delta),entry,arm,x)
                expected_shift=np.zeros(29);expected_shift[held]=delta
                errors={key:float(np.max(abs(test[key]-comp[key]))) for key in ('covariance','parent_coefficients','parent_noise')}
                errors['raw_shift']=float(np.max(abs(test['raw']-comp['raw']-expected_shift)))
                errors['parent_phase_reference']=float(np.max(abs(np.asarray(other_info['phase_reference'])-info['phase_reference'])))
                if digest(other)!=digest(model) or max(errors.values())>1e-8:
                    raise ValueError('Held CFO influenced regenerated noise/parent background')
                redactions.append(dict(arm=arm,fold=fold,held_CFO_shift_Hz=delta,noise_model_exact=True,errors=errors,actual_point_noise_max_error=err))
    signal.setitimer(signal.ITIMER_REAL,0)
    write('preparation.json',dict(seconds=time.monotonic()-START,original_noise_samples=old['noise_samples'],
        excluded_noise_samples=29,new_noise_samples=old['noise_samples']-29,original_D_pieces=pieces,
        estimator_source_sha256=sha(Path(noise.__file__)),records=records,entire_pipeline_redactions=redactions,
        geometry_and_split_unchanged=True,no_primary_forecasts_yet=True,
        remaining_exposure='Fixed RF position, identity and graph/quality/margin covariates were selected or measured on all D; this is not independent identity or full end-to-end holdout validation'))
    bindings=dict(prior['bindings'])
    for path in [OWN/'protocol.json',OWN/'preparation.json',OWN/'geometry_GL32.npz',OWN/'geometry_GL64.npz',OWN/'AMENDMENT02.md',
                 OWN/'predict02.py',OWN/'test_noise02.py',OWN/'test_receipt02.json',OWN/'test_receipt03.json',
                 OWN/'preparation02_failed/failure.json',ROOT/'COORDINATOR_PLAN.md']:
        bindings[str(path)]=sha(path)
    for path in HERE.iterdir():
        if path.is_file():bindings[str(path)]=sha(path)
    write('protocol.json',dict(prior,bindings=bindings,schema='same-owner-chronological-prediction/v2',
        preparation_seconds=prior['preparation_seconds']+read(HERE/'preparation.json')['seconds']+read(OWN/'preparation02_failed/failure.json')['charged_worker_seconds_upper_bound'],
        test_seconds=prior['test_seconds']+read(OWN/'test_receipt02.json')['seconds']+read(OWN/'test_receipt03.json')['seconds'],
        initial_protocol_sha256=sha(OWN/'protocol.json'),noise_training_excludes_whole_D=True,
        initial_preparation_preserved_unexecuted=True,failed_noise_preparation_exact_wall_unknown=True,
        failed_noise_preparation_charged_upper_bound_seconds=90.))
    print('PREPARED02',sha(HERE/'protocol.json'),flush=True)


def verify():
    protocol=read(HERE/'protocol.json')
    for path,expected in protocol['bindings'].items():
        if sha(path)!=expected:raise ValueError('Frozen source/input changed: '+path)
    receipt=read(ROOT/'audit/prediction_preflight02.json')
    if not receipt['all_passed'] or receipt['protocol_sha256']!=sha(HERE/'protocol.json'):
        raise ValueError('Exact amended independent preflight required')
    return protocol


def run():
    base.threads();protocol=verify();prefix=protocol['preparation_seconds']+protocol['test_seconds']
    began=time.monotonic();sr.alarm(CAP-prefix)
    write('execution_started.json',dict(protocol_sha256=sha(HERE/'protocol.json'),prefix_worker_seconds=prefix))
    slots=[]
    try:
        for arm in ARMS:
            raw=dict(np.load(HERE/(arm+'_input.npz')))
            for fold,train,held in conditional.split_indices(raw['times'],raw['native_ids']):
                for model in MODELS:
                    start=time.monotonic();values={};name=arm+'_'+fold+'_'+model
                    for order in ORDERS:
                        geometry=dict(np.load(OWN/('geometry_GL'+str(order)+'.npz')))
                        value=conditional.evaluate(raw['raw'],raw['covariance'],geometry,train,held,model=='three_modes',k.PERIOD)
                        arrays={key:value.pop(key) for key in ('prediction_mean','prediction_covariance','prediction_SD','posterior_node_alias_mass','held_raw_residual')}
                        save_arrays(name+'_GL'+str(order)+'.npz',**arrays);write(name+'_GL'+str(order)+'.json',value)
                        values[order]=dict(value,**arrays)
                    checks=first.check(values[32],values[64],protocol['tolerances'])
                    result=dict(arm=arm,fold=fold,model=model,status='complete',train_indices=train,held_indices=held,
                        orders={str(order):{key:val for key,val in v.items() if key not in ('prediction_mean','prediction_covariance','prediction_SD','posterior_node_alias_mass','held_raw_residual')} for order,v in values.items()},
                        checks=checks,numerically_qualified=all(checks.values()),seconds=time.monotonic()-start,
                        independent_identity_validation=False,position_fit=False,held_values_used_for_training=False,
                        inherited_noise_training_excludes_whole_D=True)
                    write(name+'_result.json',result);slots.append(dict(arm=arm,fold=fold,model=model,status='complete',qualified=result['numerically_qualified'],seconds=result['seconds']))
                    print(arm,fold,model,result['numerically_qualified'],flush=True)
    except Exception as exc:write('failure.json',dict(error=repr(exc),traceback=traceback.format_exc()))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    complete={(q['arm'],q['fold'],q['model']) for q in slots}
    slots += [dict(arm=a,fold=f,model=m,status='unavailable') for a in ARMS for f in protocol['folds'] for m in MODELS if (a,f,m) not in complete]
    write('execution.json',dict(slots=slots,cumulative_worker_seconds=prefix+time.monotonic()-began,
        run_wall_seconds=time.monotonic()-began,position_fits=0,GPS_used=False,identity_admissions=0))
    verify();write('RF_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),files={str(p):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file()}))
    print('TERMINAL02',read(HERE/'execution.json')['cumulative_worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run'])
    globals()[parser.parse_args().action]()
