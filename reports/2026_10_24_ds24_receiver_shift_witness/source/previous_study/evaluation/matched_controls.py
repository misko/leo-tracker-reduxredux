"""Cold, paired DS24 model controls; no geographic reference is read here.

Adapter contract: build(d, arm, reference, case) returns an event/predictive
problem supporting the existing fit/summary interfaces. An adapter may replace
declared noise or nuisance-prior/features, but never observations, assignments,
aliases, masks, powers, candidate set, bounds, or predictive membership.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
FULL=Path('/srv/bulk/leo/research/ds25-20261024')
HALF=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
ARMS=('c0','fitted_c')


def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value,default=encode,sort_keys=True,separators=(',',':')).encode()


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,default=encode,indent=2)+'\n')


def cohort():return read(HALF/'summary.json')['baseline']['c0']['common_cases']


def load_baseline(case):
    import algo02_scan as algo
    saved_path=FULL/'family_cavity/position'/(case+'.json')
    saved=read(saved_path)
    if saved['status']!='complete':raise ValueError('baseline incomplete')
    selected=saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(FULL)
    return dict(case=case,scan=algo.load_scan(FULL,case),
        node=copy.deepcopy(selected['node'] if selected else saved['baseline_node']),
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),
        model=copy.deepcopy(saved['model']),
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=copy.deepcopy(selected['entries'] if selected else saved['baseline_entries']),
        arms=saved['policy_arms'],baseline_path=str(saved_path),baseline_sha256=digest(saved_path))


def measurement_binding(d):
    tracks=[dict(key=t['key'],receiver=t['receiver'],channel=t['channel'],rf_hz=t['rf_hz'],
        times=t['times'],values=t['values'],observation_ids=t['observation_ids']) for t in d['scan'].tracks]
    rows=[dict(component=r['component'],candidate_index=r['candidate_index'],candidate_norad=r['candidate_norad'])
        for r in d['node']['seed']['rows']]
    data=dict(tracks=tracks,rows=rows,aliases=d['node']['aliases'],keep=d['keep'],powers=d['powers'],
        model=d['model'],means=d['means'],entries=d['entries'],norads=d['scan'].norads,
        causal_receipt=d['scan'].receipt)
    return hashlib.sha256(canonical(data)).hexdigest()


def factor_contract(p,entries):
    # Noise/features and their covariance may change; these physical factors may not.
    data=dict(rows=[(r['component'],int(r['candidate_index'])) for r in p.rows],
        members=p.members,labels=p.labels,aliases=p.alias,keep=p.keep,
        values=p.values,times=p.flat_times,RF_ratio=p.q,
        lower=p.lower,upper=p.upper,entries=entries)
    return hashlib.sha256(canonical(data)).hexdigest()


def assert_factor_contract(p,entries,expected):
    if factor_contract(p,entries)!=expected:
        raise ValueError('adapter changed physical observations, labels, aliases, mask, bounds or predictive membership')
    np.testing.assert_array_equal(p.lower,[-12.5,-12.5])
    np.testing.assert_array_equal(p.upper,[12.5,12.5])
    if entries and canonical(getattr(p,'linear_entries',None))!=canonical(entries):
        raise ValueError('adapter omitted or changed predictive factors')


def phase_pair_valid(arms):
    from algo02_scan import pair_passes
    if not pair_passes(arms,include_linear=True):return False
    return all(np.max(abs(np.asarray(r['state']['phases'])))<=15.000001 for r in arms.values())


def policy_source(eligible,paired_valid):
    # Model qualification is external and frozen before any position evaluation.
    return 'trial' if eligible and paired_valid else 'baseline'


def cold_refit(build,arm,means_count,entries,expected_contract,*,fit_function=None,summary_function=None):
    if fit_function is None:
        from investigate_dsx01_localization_failures import fit as fit_function
    if summary_function is None:
        from probe_ds23_frequency_events import summary as summary_function
    reference=np.zeros(means_count);x=np.zeros(2);history=[]
    for epoch in range(5):
        p=build(arm,reference)
        assert_factor_contract(p,entries,expected_contract)
        result=fit_function(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        change=float(np.max(abs(phase-reference)))
        history.append(dict(epoch=epoch,fit=result,phase_change_s=change))
        reference=phase
    saved=summary_function(p,x,entries)
    saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    if saved.get('linear_calibration_max_difference',0)>1e-10:
        raise ValueError('predictive factors fed back into calibration')
    return saved


def load_protocol(path):
    protocol=read(path)
    if protocol.get('schema_version')!=1:raise ValueError('protocol schema_version must be 1')
    if protocol['cases']!=cohort():raise ValueError('protocol must retain exact 24-case cohort')
    if protocol['phase_rounds']!=5 or protocol['position_steps']!=48:raise ValueError('unmatched fitting budget')
    if protocol['start_east_north_km']!=[0,0]:raise ValueError('cold regional start required')
    if protocol['adoption']!='RF_qualified_and_original_paired_gates_else_baseline':raise ValueError('unexpected adoption policy')
    if protocol.get('GPS_used') is not False:raise ValueError('explicit no-GPS qualification required')
    if not set(protocol['eligible_cases'])<=set(protocol['cases']):raise ValueError('unknown eligible case')
    bindings=[protocol['adapter'],protocol['qualification']]+protocol.get('source_bindings',[])
    for item in bindings:
        if digest(item['path'])!=item['sha256'].removeprefix('sha256:'):
            raise ValueError('frozen proposal dependency changed: '+item['path'])
    return protocol,bindings


def load_adapter(path):
    path=Path(path)
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('frozen_ds24_model_adapter',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def baseline_metrics(arms):
    keys=('endpoint_east_north_km','endpoint_latlon','negative_twice_elbo','curved_negative_twice_elbo',
        'RMS_hz','active_points','predictive_points','additional_predictive_points','final_phase_change_s')
    return {a:{k:r[k] for k in keys if k in r} for a,r in arms.items()}


def one(case,protocol_path):
    from probe_ds23_graph_seeded_paths import build as baseline_build
    protocol,bindings=load_protocol(protocol_path)
    if case not in protocol['cases']:raise ValueError('case outside sealed cohort')
    destination=HERE/'models'/protocol['model_id']/(case+'.json')
    if destination.exists():
        saved=read(destination)
        if saved['protocol_sha256']!=digest(protocol_path):raise ValueError('preserve previous differently sealed result')
        return saved
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s case cap')));signal.alarm(240)
    result=dict(case=case,model_id=protocol['model_id'],protocol_path=str(protocol_path),protocol_sha256=digest(protocol_path),
        source_sha256=digest(Path(__file__)),GPS_used=False,adopted=False,policy_source='baseline')
    try:
        d=load_baseline(case);binding=measurement_binding(d)
        result.update(baseline_path=d['baseline_path'],baseline_sha256=d['baseline_sha256'],baseline=baseline_metrics(d['arms']),
            input_binding_sha256=binding,eligible=case in protocol['eligible_cases'])
        replay={};contracts={}
        for arm,saved in d['arms'].items():
            p=baseline_build(d,'default',arm,saved['phase_reference'])
            delta=float(p.calculate(saved['endpoint_east_north_km'])['negative_twice_elbo']-saved['negative_twice_elbo'])
            if abs(delta)>min(1e-3,1e-8*max(abs(saved['negative_twice_elbo']),1)):
                raise ValueError('baseline objective replay failed')
            replay[arm]=delta;contracts[arm]=factor_contract(p,d['entries'])
        result['baseline_objective_replay_difference']=replay
        if not result['eligible']:
            result.update(status='RF_unqualified',fallback_reason='frozen predictive qualification did not permit this model')
        else:
            module=load_adapter(protocol['adapter']['path'])
            build=lambda arm,ref:module.build(d,arm,ref,case)
            arms={a:cold_refit(build,a,len(d['means']),d['entries'],contracts[a]) for a in ARMS}
            if measurement_binding(d)!=binding:raise ValueError('adapter mutated frozen scan inputs or priors')
            for item in bindings:
                if digest(item['path'])!=item['sha256'].removeprefix('sha256:'):raise ValueError('proposal dependency changed during fit')
            valid=phase_pair_valid(arms)
            result.update(status='complete',arms=arms,paired_valid=valid,adopted=valid,
                policy_source=policy_source(True,valid),fallback_reason=None if valid else 'original paired residual/phase gates failed',
                normalized_loss_change={a:r['negative_twice_elbo']-d['arms'][a]['negative_twice_elbo'] for a,r in arms.items()},
                RMS_change_hz={a:r['RMS_hz']-d['arms'][a]['RMS_hz'] for a,r in arms.items()},
                original_measurements_assignments_masks_and_powers_preserved=True,
                other_priors_preserved_except_declared_intervention=True)
    except Exception as exc:
        import traceback
        result.update(status='failed',error=repr(exc),traceback=traceback.format_exc(),fallback_reason='bounded scientific trial failed')
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(destination,result)
    print(case,protocol['model_id'],result['status'],'policy',result['policy_source'],'seconds',round(result['seconds'],2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--case',required=True)
    args=parser.parse_args();one(args.case,args.protocol)
