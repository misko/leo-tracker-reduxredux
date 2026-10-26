"""Matched original/refined retained position solves, no geographic reference."""
import time
STARTED=time.monotonic()
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import traceback
import numpy as np

REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import recovery as r
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary
from replacement import inject,digest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
INFLUENCE=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence')
OWN=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c');METHODS=('original','corrected')
CORRECTIONS=ROOT/'measurement/corrections.json'


def write(path,value):r.write_new(Path(path) if Path(path).is_absolute() else HERE/path,value)


def alarm(seconds):
    if seconds<=0:raise TimeoutError('frozen worker budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen fit/worker deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def selected():
    result={}
    for row in r.read(INFLUENCE/'results.json')['selection']:
        owners=[row[k] for k in ('target','control')]
        result[row['case']]=dict(owners=[o['owner'] for o in owners],
            native_IDs=sorted(oid for o in owners for oid in o['observation_ids']))
    if sum(len(x['native_IDs']) for x in result.values())!=159:raise ValueError('original159-ID panel differs')
    return result


def zero_rows(d,ids):
    obs={o['observation_id']:o for o in d['observations']}
    return [dict(case=d['case'],native_observation_id=i,original_cfo_hz=obs[i]['measured_cfo_hz'],
                 corrected_cfo_hz=obs[i]['measured_cfo_hz'],numerical_frequency_qualified=True) for i in ids]


def membership_ids(p,entries):
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
            for oid,on in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if on]
    predictive=[oid for e in entries for oid in e['observation_ids']]
    if len(curved+predictive)!=len(set(curved+predictive)):raise ValueError('duplicate/overlapping likelihood IDs')
    return dict(curved=curved,predictive=predictive,curved_count=len(curved),predictive_count=len(predictive),
                union_sha256=digest(sorted(curved+predictive)))


def prepare():
    if (HERE/'protocol.json').exists():raise FileExistsError('already frozen')
    results=[];panel=selected()
    for case in CASES:
        d=r.context(case);new,injection=inject(d,zero_rows(d,panel[case]['native_IDs']),panel[case]['native_IDs'])
        for arm in ARMS:
            saved=d['arms'][arm];x=np.asarray(saved['endpoint_east_north_km'])
            a=r.build(d,arm,saved['phase_reference']);b=r.build(new,arm,saved['phase_reference'])
            ca=a.calculate(x);cb=b.calculate(x)
            delta=float(ca['negative_twice_elbo']-saved['negative_twice_elbo'])
            errors={k:float(np.max(abs(np.asarray(ca[k])-np.asarray(cb[k])))) for k in
                    ('coefficient','noise_precision','conditional_residual_hz')}
            same=all(v==0 for v in errors.values()) and ca['negative_twice_elbo']==cb['negative_twice_elbo']
            if not same or abs(delta)>1e-3 or abs(delta)/max(1,abs(saved['negative_twice_elbo']))>1e-8:
                raise ValueError('original/zero-delta fixed-state control failed')
            ids=membership_ids(a,d['entries'])
            baseline=r.read(OWN/case/'parent.json')['coverage'][arm]
            if set(ids['curved'])!=set(baseline['curved_observation_ids']) or set(ids['predictive'])!=set(baseline['predictive_observation_ids']):raise ValueError('original likelihood membership differs')
            if not set(panel[case]['native_IDs'])<=set(ids['curved']):raise ValueError('complete selected owner not curved likelihood')
            if not np.array_equal(a.lower,[-12.5,-12.5]) or not np.array_equal(a.upper,[12.5,12.5]):raise ValueError('regional bounds changed')
            results.append(dict(case=case,arm=arm,original_saved_objective_replay_difference=delta,
                zero_delta_exact=same,zero_delta_errors=errors,likelihood_membership=ids,
                injection=injection,full_predictive_objective=ca.get('linear_predictive_objective',0.),
                maximum_graph_lift=max(abs(x['integer_graph_lift']) for x in injection['coordinate_rows'])))
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_replacement.py')],capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
    write('preparation.json',dict(all_passed=True,seconds=time.monotonic()-STARTED,records=results,
        test_stdout=proc.stdout,test_stderr=proc.stderr,selected=panel,GPS_used=False))
    print('PREPARATION_PASS',time.monotonic()-STARTED,flush=True)


def freeze():
    if (HERE/'protocol.json').exists():raise FileExistsError('already frozen')
    paths=[HERE/n for n in ('run.py','replacement.py','test_replacement.py','PROTOCOL.md','preparation.json')]
    paths +=[ROOT/'COORDINATOR_PLAN.md',ROOT/'EVALUATION_SCOPE.md',INFLUENCE/'protocol.json',INFLUENCE/'results.json',RECOVERY/'recovery.py']
    paths +=[REPO/'tools'/n for n in ('algo02_scan.py','probe_ds23_frequency_events.py','ds23_frequency_events.py',
        'investigate_dsx01_localization_failures.py','run_ds23_combined_recovery_full.py','audit_ds23_algo01_coverage.py',
        'evaluate_ds23_phase_refreshed.py','dsx01_joint_marginal.py','dsx01_hierarchical_bound.py',
        'ds23_predictive_linear.py','ds23_height_problem.py','probe_ds23_history_calibrated_phase.py',
        'probe_ds23_receiver_smooth_prior.py')]
    paths +=[REPO/'src/leo/analysis/research/public_tracking_points.py',REPO/'src/leo/analysis/graph_tracklets.py']
    paths +=[REPO/'src/leo/analysis/research'/n for n in ('continuous_curve_fit.py','orbit_uncertainty.py','retained_track_likelihood.py')]
    for case in CASES:
        paths +=[r.SOURCE/'family_cavity/position'/(case+'.json'),OWN/case/'parent.json']
        paths +=[r.SOURCE/case/n for n in ('observations.json','tracks.json','tracking.json','radio_noise.json','bank.npz','nominal_elements.json','receipt.json')]
    measurement=ROOT/'measurement/protocol.json'
    if not measurement.exists():raise FileNotFoundError('wait for frozen measurement protocol')
    paths.append(measurement)
    write('protocol.json',dict(schema='matched-complete-owner-position/v1',files={str(p):r.sha(p) for p in paths},
        cases=CASES,arms=ARMS,methods=METHODS,selected=selected(),total_fits=8,
        preparation_seconds=r.read(HERE/'preparation.json')['seconds'],cap_seconds=600.,workers=2,BLAS_threads=1,
        maximum_seconds_per_fit=60.,outer_refresh_rounds=5,iterations_per_round=48,start_km=[0.,0.],initial_phase_reference='all_zero',
        phase_reference_update='clip actual posterior phase to[-15,15] between fits; final guard uses unclipped phases',
        baseline_reproduction={'endpoint_km':.001,'objective_absolute':1e-3,'objective_relative':1e-8},
        original_Gamma_precision_stop=1e-5,final_phase_change_limit_s=.01,absolute_phase_limit_s=15.000001,
        corrections_path=str(CORRECTIONS),launch_receipt=str(ROOT/'position_go.json'),
        unresolved_correction_policy='exact original CFO per native ID; never drop or rewrap',
        qualification='original paired residual/owner gates+unclipped phase+Gamma+final refresh+all original accepted IDs; baseline reproduction required',
        operational_policy='original_reference',GPS_used=False))
    print('FROZEN',r.sha(HERE/'protocol.json'),flush=True)


def fit_one(d,arm,method,deadline):
    began=time.monotonic();alarm(min(60.,deadline-began));reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
    for epoch in range(5):
        p=r.build(d,arm,reference);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=p.state(x)['phases'][p.labels];change=float(np.max(abs(np.clip(phase,-15,15)-reference)))
        history.append(dict(epoch=epoch,fit=result,phase_change_s=change,reference=reference,unclipped_phase_s=phase))
        write(Path(d['case'])/method/arm/f'epoch{epoch}.json',history[-1]);reference=np.clip(phase,-15,15)
    record=summary(p,x,d['entries']);record.update(history=history,final_phase_change_s=change)
    c=p.calculate(x);ids=membership_ids(p,d['entries'])
    raw=dict(case=d['case'],arm=arm,method=method,summary=record,
        full_objective=c['negative_twice_elbo'],predictive_objective=c.get('linear_predictive_objective',0.),
        normalization_constant=c['normalization_constant'],
        conditional_residual_hz=c['conditional_residual_hz'],noise_precision=c['noise_precision'],
        coefficient=c['coefficient'],coefficient_prior_precision=c['coefficient_prior_precision'],
        final_log_precision_change=c['final_log_precision_change'],likelihood_membership=ids,seconds=time.monotonic()-began)
    write(Path(d['case'])/method/arm/'raw_endpoint.json',raw)
    alarm(deadline-time.monotonic())
    member=r.membership(d,arm,record)
    original=r.read(OWN/d['case']/'parent.json')['coverage'][arm]
    lost=sorted(set(original['accepted_observation_ids'])-set(member['accepted_observation_ids']))
    old_likelihood=set(original['curved_observation_ids']+original['predictive_observation_ids'])
    if old_likelihood!=set(ids['curved']+ids['predictive']):raise ValueError('fixed likelihood membership changed')
    reproduction=None
    if method=='original':
        saved=d['arms'][arm];dx=float(np.linalg.norm(x-saved['endpoint_east_north_km']));df=float(c['negative_twice_elbo']-saved['negative_twice_elbo'])
        reproduction=dict(endpoint_difference_km=dx,objective_difference=df,objective_relative_difference=abs(df)/max(1,abs(saved['negative_twice_elbo'])),
            passed=bool(dx<=.001 and abs(df)<=1e-3 and abs(df)/max(1,abs(saved['negative_twice_elbo']))<=1e-8))
    single=bool(r.valid({a:record for a in ARMS}));gamma=bool(c['final_log_precision_change']<=1e-5)
    gated=dict(original_single_arm_valid=single,Gamma_converged=gamma,final_phase_change_s=change,
        maximum_unclipped_phase_s=float(np.max(abs(record['state']['phases']))),
        original_accepted_IDs_lost=lost,membership=member,baseline_reproduction=reproduction,
        likelihood_IDs_exact=True,all_gates_recomputed_from_current_graph_values=True,
        original_graph_quality_metadata_unchanged=True,operational_policy='original_reference')
    write(Path(d['case'])/method/arm/'gates.json',gated)
    return dict(case=d['case'],arm=arm,method=method,status='complete',endpoint_east_north_km=x,
        full_objective=c['negative_twice_elbo'],conditional_RMS_hz=record['RMS_hz'],
        original_single_arm_valid=single,Gamma_converged=gamma,final_phase_change_s=change,
        all_original_accepted_IDs_preserved=not lost,postfit_IDs_lost=len(lost),
        baseline_reproduction=reproduction,seconds=time.monotonic()-began,operational_policy='original_reference')


def case_job(case,seconds,correction_rows):
    began=time.monotonic();deadline=began+seconds;rows=[];failure=None
    try:
        alarm(deadline-time.monotonic());d=r.context(case)
        replaced,injection=inject(d,correction_rows,selected()[case]['native_IDs'])
        write(Path(case)/'injection.json',injection)
        for method in METHODS:
            data=d if method=='original' else replaced
            for arm in ARMS:
                try:row=fit_one(data,arm,method,deadline)
                except Exception as exc:row=dict(case=case,arm=arm,method=method,status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc(),operational_policy='original_reference')
                finally:signal.setitimer(signal.ITIMER_REAL,0)
                rows.append(row);write(Path(case)/method/(arm+'_result.json'),row)
                print(case,method,arm,row['status'],flush=True)
    except Exception as exc:failure=repr(exc)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    present={(x['method'],x['arm']) for x in rows}
    for method in METHODS:
        for arm in ARMS:
            if (method,arm) not in present:
                row=dict(case=case,method=method,arm=arm,status='not_completed',error=failure,operational_policy='original_reference')
                rows.append(row);write(Path(case)/method/(arm+'_result.json'),row)
    original_ok=all(x['status']=='complete' and x['baseline_reproduction']['passed'] for x in rows if x['method']=='original')
    corrected_ok=all(x['status']=='complete' and x['original_single_arm_valid'] and x['Gamma_converged'] and x['final_phase_change_s']<=.01 and x['all_original_accepted_IDs_preserved'] for x in rows if x['method']=='corrected')
    result=dict(case=case,rows=rows,seconds=time.monotonic()-began,failure=failure,
        original_baseline_reproduced_both_arms=original_ok,corrected_research_paired_qualified=bool(original_ok and corrected_ok),
        operational_policy='original_reference',GPS_used=False)
    write(Path(case)/'result.json',result);return result


def run():
    if (HERE/'execution.json').exists():raise FileExistsError('no scientific retries')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')
    protocol=r.read(HERE/'protocol.json')
    for path,digest_value in protocol['files'].items():
        if r.sha(path)!=digest_value:raise ValueError('frozen source/input changed: '+path)
    audit=r.read(ROOT/'audit/position_preflight.json');go=r.read(ROOT/'position_go.json')
    for receipt in (audit,go):
        if receipt.get('protocol_sha256')!=r.sha(HERE/'protocol.json'):raise ValueError('exact frozen protocol receipt required')
    if not audit['all_passed'] or not go['approved']:raise ValueError('B preflight/rootGO required')
    corrections=r.read(CORRECTIONS)
    if not corrections['coverage_complete'] or r.sha(CORRECTIONS)!=go['corrections_sha256']:raise ValueError('complete sealed correction vector required')
    measurement_seal=ROOT/'measurement/RF_seal.json'
    if r.sha(measurement_seal)!=go['measurement_RF_seal_sha256']:raise ValueError('measurement seal differs')
    for path,h in r.read(measurement_seal)['files'].items():
        if r.sha(path)!=h:raise ValueError('measurement artifact changed: '+path)
    expected=selected();rows=corrections['rows']
    if len(rows)!=159 or len({x['native_observation_id'] for x in rows})!=159:raise ValueError('159 unique correction slots required')
    for case in CASES:
        if {x['native_observation_id'] for x in rows if x['case']==case}!=set(expected[case]['native_IDs']):raise ValueError('correction case panel differs')
    setup=time.monotonic()-STARTED;remaining=600-protocol['preparation_seconds']-setup
    if remaining<=0:raise TimeoutError('setup exhausted original cap')
    results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(case_job,case,remaining/2,[x for x in rows if x['case']==case]):case for case in CASES}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],status='worker_failed',error=repr(exc),seconds=remaining/2))
    slots=[]
    for case in CASES:
        for method in METHODS:
            for arm in ARMS:
                path=HERE/case/method/(arm+'_result.json')
                slots.append(r.read(path) if path.exists() else dict(case=case,method=method,arm=arm,status='worker_failed'))
    write('execution.json',dict(cases=results,all8_slots=slots,all_selected_terminal=True,
        corrections_sha256=r.sha(CORRECTIONS),measurement_RF_seal_sha256=r.sha(measurement_seal),
        cumulative_worker_seconds=protocol['preparation_seconds']+setup+sum(x['seconds'] for x in results),
        cap_seconds=600,operational_policy='original_reference',GPS_used=False))
    files={str(p):r.sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='RF_seal.json' and '.pytest_cache' not in p.parts and '__pycache__' not in p.parts}
    write('RF_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),files=files,all_selected_terminal=True,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','freeze','run'));args=parser.parse_args()
    {'prepare':prepare,'freeze':freeze,'run':run}[args.action]()
