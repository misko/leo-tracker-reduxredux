"""Sixteen cold conditional-Gaussian fits; no geographic inputs."""
import time
STARTED=time.monotonic()
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import os
import signal
import subprocess
import sys
import traceback
import numpy as np
import model
from model import r,previous,inject,layout,digest,summary
from investigate_dsx01_localization_failures import fit

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
OLD=model.PREVIOUS;CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c')
CELLS=(('00','original','original'),('10','corrected','original'),('01','original','corrected'),('11','corrected','corrected'))
CORRECTIONS=OLD.parent/'measurement/corrections.json'
TOL=dict(coefficient_absolute=1e-6,coefficient_relative=1e-8,residual_hz_absolute=1e-3,
         predictive_objective_absolute=1e-3,predictive_objective_relative=1e-8)


def write(name,value):r.write_new(HERE/name,value)
def alarm(seconds):
    if seconds<=0:raise TimeoutError('original cumulative budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen factorial deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def data_context(case):
    d=r.context(case);rows=[x for x in r.read(CORRECTIONS)['rows'] if x['case']==case]
    refined,receipt=inject(d,rows,previous.selected()[case]['native_IDs'])
    return {'original':d,'corrected':refined},receipt


def packet_key(case,arm,origin):return case+'_'+arm+'_'+origin


def prepare():
    if (HERE/'protocol.json').exists():raise FileExistsError('already frozen')
    controls=[];packets={};comparisons=[]
    for case in CASES:
        data,injection=data_context(case)
        zero,zero_receipt=inject(data['original'],previous.zero_rows(data['original'],previous.selected()[case]['native_IDs']),previous.selected()[case]['native_IDs'])
        zero_exact=all(np.array_equal(a['values'],b['values']) for a,b in zip(data['original']['scan'].tracks,zero['scan'].tracks,strict=True))
        if not zero_exact:raise ValueError('zero-CFO-delta graph contract differs')
        for arm in ARMS:
            for origin in ('original','corrected'):
                key=packet_key(case,arm,origin);packet=model.packet(case,arm,origin)
                d=data[origin];raw=r.read(packet['source_path']);x=np.asarray(packet['source_endpoint']);reference=packet['final_phase_reference']
                vi=r.build(d,arm,reference);old=vi.calculate(x)
                packet['layout']=layout(vi);conditional=model.build(d,arm,reference,packet);c=conditional.calculate(x)
                full=np.asarray(packet['coefficient_prior_precision']);tau=np.asarray(packet['noise_precision'])
                if not np.array_equal(c['coefficient_prior_precision'],full) or not np.array_equal(c['noise_precision'],tau):raise ValueError('full same-arm precision packet not exact')
                if layout(conditional)!=layout(vi) or not np.array_equal(conditional.values,vi.values) or conditional.alias!=vi.alias:raise ValueError('original layout/value/alias identity differs')
                a=np.asarray(c['coefficient']);b=np.asarray(raw['coefficient'])
                coef=float(np.max(abs(a-b)));coef_ok=bool(np.all(abs(a-b)<=TOL['coefficient_absolute']+TOL['coefficient_relative']*abs(b)))
                residual=float(np.max(abs(np.asarray(c['conditional_residual_hz'])-raw['conditional_residual_hz'])))
                if d['entries']:
                    pred_res=float(np.max(abs(c['linear_raw_prediction_residual_hz']-old['linear_raw_prediction_residual_hz'])))
                    pred_delta=float(c['linear_predictive_objective']-old['linear_predictive_objective'])
                    pred_relative=abs(pred_delta)/max(1,abs(old['linear_predictive_objective']))
                else:pred_res=0.;pred_delta=0.;pred_relative=0.
                passed=bool(coef_ok and residual<=TOL['residual_hz_absolute'] and pred_res<=TOL['residual_hz_absolute'] and
                    abs(pred_delta)<=TOL['predictive_objective_absolute'] and pred_relative<=TOL['predictive_objective_relative'])
                if not passed:raise ValueError('diagonal posterior replay failed '+key+': '+repr((coef,residual,pred_res,pred_delta)))
                curved=conditional.curved_calculate(x) if d['entries'] else c
                gamma_groups=np.unique(conditional.noise_groups[conditional.keep]);active=np.zeros(len(tau),bool);active[gamma_groups]=True
                arr=HERE/'diagonal_arrays'/(key+'.npz');arr.parent.mkdir(exist_ok=True)
                np.savez_compressed(arr,coefficient=a,old_coefficient=b,conditional_residual_hz=c['conditional_residual_hz'],
                    old_conditional_residual_hz=raw['conditional_residual_hz'],features=c['features'],
                    keep=conditional.keep,point_noise=conditional.point_noise,noise_groups=conditional.noise_groups,
                    powers=d['powers'],noise_precision=tau,prior_precision=full,
                    predictive_residual_hz=c.get('linear_raw_prediction_residual_hz',np.zeros(0)),
                    old_predictive_residual_hz=old.get('linear_raw_prediction_residual_hz',np.zeros(0)))
                controls.append(dict(case=case,arm=arm,packet_origin=origin,passed=passed,
                    max_coefficient_error=coef,max_conditional_residual_error_hz=residual,
                    max_predictive_raw_residual_error_hz=pred_res,predictive_objective_difference=pred_delta,
                    predictive_objective_relative_difference=pred_relative,full_prior_exact=True,noise_packet_exact=True,
                    packet_layout=packet['layout'],inactive_noise_zeros=int(np.sum(tau==0)),active_noise_groups=np.flatnonzero(active),
                    values_sha256=digest(conditional.values),aliases=conditional.alias,
                    full_conditional_objective=c['negative_twice_elbo'],curved_conditional_objective=curved['negative_twice_elbo'],
                    original_VI_objective=raw['full_objective'],objectives_are_different=True,
                    predictive_IDs=sum(len(e['observation_ids']) for e in d['entries']),
                    array_path=str(arr),array_sha256=r.sha(arr),injection_receipt=injection))
                controls[-1]['zero_CFO_delta_all_graph_arrays_exact']=zero_exact
                packets[key]=packet
            aa=packets[packet_key(case,arm,'original')];bb=packets[packet_key(case,arm,'corrected')]
            ta=np.asarray(aa['noise_precision']);tb=np.asarray(bb['noise_precision']);use=ta>0
            ratio=tb[use]/ta[use];pr=np.asarray(bb['coefficient_prior_precision'])/aa['coefficient_prior_precision']
            comparisons.append(dict(case=case,arm=arm,active_noise_count=int(use.sum()),inactive_noise_zeros_unchanged=bool(np.array_equal(ta[~use],tb[~use])),
                active_noise_ratio_min=float(ratio.min()),active_noise_ratio_median=float(np.median(ratio)),active_noise_ratio_max=float(ratio.max()),
                full_prior_ratio_min=float(pr.min()),full_prior_ratio_max=float(pr.max()),packet_changes_both_noise_and_prior=True))
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_model.py'),str(HERE/'test_evaluate.py')],capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
    write('packets.json',packets)
    write('preparation.json',dict(all_passed=True,seconds=time.monotonic()-STARTED,controls=controls,packet_comparisons=comparisons,
        tolerances=TOL,test_stdout=proc.stdout,test_stderr=proc.stderr,GPS_used=False))
    print('PREPARATION_PASS',time.monotonic()-STARTED,flush=True)


def freeze():
    paths=[HERE/n for n in ('run.py','model.py','test_model.py','evaluate.py','test_evaluate.py','PROTOCOL.md','packets.json','preparation.json')]
    paths +=[ROOT/'COORDINATOR_PLAN.md',OLD/'protocol.json',OLD/'RF_seal.json',OLD/'run.py',OLD/'replacement.py',CORRECTIONS]
    paths +=[Path(p['source_path']) for p in r.read(HERE/'packets.json').values()]
    paths +=[Path(p) for p in r.read(OLD/'protocol.json')['files']]
    paths +=[previous.REPO/'tools'/n for n in ('ds23_frozen_precision.py','probe_ds23_refined_precision.py','ds23_height_problem.py','ds23_predictive_linear.py')]
    paths +=sorted((HERE/'diagonal_arrays').glob('*.npz'))
    write('protocol.json',dict(schema='same-arm-CFO-precision-factorial/v1',files={str(p):r.sha(p) for p in sorted(set(paths))},
        cases=CASES,arms=ARMS,cells=CELLS,preparation_seconds=r.read(HERE/'preparation.json')['seconds'],
        cap_seconds=600,workers=2,BLAS_threads=1,maximum_seconds_per_fit=30,fit_count=16,
        cold_position=[0.,0.],cold_phase_reference='zero',phase_rounds=5,iterations=48,volume_weight=1,
        predictor_sigma_multiplier='sqrt(2), unchanged',packet='full_same_arm_noise_and_coefficient_prior_precision',
        fitted_c_mapping='require fullslot8==1; delete then reinsert exactly, never overwrite',
        diagnostics_membership='same actual conditional posterior; no VI rebuild',
        evaluator_frozen_before_results=True,operational_policy='original_reference',GPS_used=False))
    print('FROZEN',r.sha(HERE/'protocol.json'),flush=True)


def fit_cell(d,arm,cell,cfo_origin,packet_origin,precision,deadline):
    began=time.monotonic();alarm(min(30,deadline-began));x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
    for epoch in range(5):
        p=model.build(d,arm,reference,precision);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=p.state(x)['phases'][p.labels];change=float(np.max(abs(np.clip(phase,-15,15)-reference)))
        history.append(dict(epoch=epoch,fit=result,reference=reference,unclipped_phase_s=phase,phase_change_s=change))
        write(Path(d['case'])/arm/cell/f'epoch{epoch}.json',history[-1]);reference=np.clip(phase,-15,15)
    c=p.calculate(x)
    if not np.array_equal(c['noise_precision'],precision['noise_precision']) or not np.array_equal(c['coefficient_prior_precision'],precision['coefficient_prior_precision']):raise ValueError('precision packet changed during solve')
    record=summary(p,x,d['entries']);record.update(final_phase_change_s=change,history=history)
    write(Path(d['case'])/arm/cell/'raw_endpoint.json',dict(case=d['case'],arm=arm,cell=cell,CFO=cfo_origin,packet=packet_origin,
        summary=record,conditional_Gaussian_objective=c['negative_twice_elbo'],coefficient=c['coefficient'],
        noise_precision=c['noise_precision'],coefficient_prior_precision=c['coefficient_prior_precision'],
        conditional_residual_hz=c['conditional_residual_hz'],precision_packet_sha256=digest(precision),
        objective_kind='conditional_Gaussian_with_volume1_not_VI_ELBO',Gamma_updated=False,seconds=time.monotonic()-began))
    member,current=model.membership(p,x,d)
    old=r.read(previous.OWN/d['case']/'parent.json')['coverage'][arm]
    if set(member['curved_observation_ids'])!=set(old['curved_observation_ids']) or set(member['predictive_observation_ids'])!=set(old['predictive_observation_ids']):raise ValueError('likelihood IDs changed')
    lost=sorted(set(old['accepted_observation_ids'])-set(member['accepted_observation_ids']))
    passed=bool(r.valid({a:record for a in ARMS}));maximum=float(np.max(abs(record['state']['phases'])))
    gates=dict(original_single_arm_valid=passed,final_phase_change_s=change,maximum_unclipped_phase_s=maximum,
        frozen_Gamma_no_convergence_claim=True,packet_exact=True,original_accepted_IDs_lost=lost,
        membership=member,posterior_kind='conditional_Gaussian',VI_rebuild=False,operational_policy='original_reference')
    write(Path(d['case'])/arm/cell/'gates.json',gates)
    return dict(case=d['case'],arm=arm,cell=cell,CFO=cfo_origin,packet=packet_origin,status='complete',
        endpoint_east_north_km=x,conditional_Gaussian_objective=c['negative_twice_elbo'],conditional_RMS_hz=current['RMS_hz'],
        original_single_arm_valid=passed,final_phase_change_s=change,maximum_unclipped_phase_s=maximum,
        original_accepted_IDs_lost=len(lost),associated_IDs=member['associated'],postfit_only_IDs=len(member['postfit_only_observation_ids']),
        fixed_likelihood_IDs=member['likelihood_points'],total_GLRT=member['total_GLRT'],packet_exact=True,
        objective_kind='conditional_Gaussian_not_VI_ELBO',seconds=time.monotonic()-began,operational_policy='original_reference')


def case_job(case,seconds):
    began=time.monotonic();deadline=began+seconds;rows=[];error=None
    try:
        alarm(deadline-time.monotonic());data,injection=data_context(case);packets=r.read(HERE/'packets.json')
        write(Path(case)/'injection.json',injection)
        for arm in ARMS:
            for cell,cfo,origin in CELLS:
                try:row=fit_cell(data[cfo],arm,cell,cfo,origin,packets[packet_key(case,arm,origin)],deadline)
                except Exception as exc:row=dict(case=case,arm=arm,cell=cell,CFO=cfo,packet=origin,status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc())
                finally:signal.setitimer(signal.ITIMER_REAL,0)
                rows.append(row);write(Path(case)/arm/(cell+'_result.json'),row);print(case,arm,cell,row['status'],flush=True)
    except Exception as exc:error=repr(exc)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    present={(r['arm'],r['cell']) for r in rows}
    for arm in ARMS:
        for cell,cfo,origin in CELLS:
            if (arm,cell) not in present:
                row=dict(case=case,arm=arm,cell=cell,CFO=cfo,packet=origin,status='not_completed',error=error)
                rows.append(row);write(Path(case)/arm/(cell+'_result.json'),row)
    result=dict(case=case,rows=rows,error=error,seconds=time.monotonic()-began,operational_policy='original_reference',GPS_used=False)
    write(Path(case)/'result.json',result);return result


def run():
    if (HERE/'execution.json').exists():raise FileExistsError('no retries')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')
    protocol=r.read(HERE/'protocol.json')
    for path,h in protocol['files'].items():
        if r.sha(path)!=h:raise ValueError('frozen source/input changed: '+path)
    audit=r.read(ROOT/'audit/preflight.json');go=r.read(ROOT/'solver_go.json')
    if not audit['all_passed'] or not go['approved'] or any(v['protocol_sha256']!=r.sha(HERE/'protocol.json') for v in (audit,go)):raise ValueError('B exact preflight and root GO required')
    setup=time.monotonic()-STARTED;remaining=600-protocol['preparation_seconds']-setup;results=[]
    if remaining<=0:raise TimeoutError('preparation exhausted cap')
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(case_job,case,remaining/2):case for case in CASES}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],status='worker_failed',error=repr(exc),seconds=remaining/2))
    slots=[]
    for case in CASES:
        for arm in ARMS:
            for cell,cfo,origin in CELLS:
                path=HERE/case/arm/(cell+'_result.json')
                slots.append(r.read(path) if path.exists() else dict(case=case,arm=arm,cell=cell,status='worker_failed'))
    write('execution.json',dict(cases=results,all16_slots=slots,all_selected_terminal=True,
        cumulative_worker_seconds=protocol['preparation_seconds']+setup+sum(x['seconds'] for x in results),
        cap_seconds=600,GPS_used=False,operational_policy='original_reference'))
    files={str(p):r.sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='RF_seal.json' and '.pytest_cache' not in p.parts and '__pycache__' not in p.parts}
    write('RF_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),files=files,all_selected_terminal=True,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','freeze','run'));args=parser.parse_args()
    {'prepare':prepare,'freeze':freeze,'run':run}[args.action]()
