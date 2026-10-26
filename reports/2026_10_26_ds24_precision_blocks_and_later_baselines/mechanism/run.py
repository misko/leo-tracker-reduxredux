"""Eight original-CFO crossed-precision fits; no geographic inputs."""
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
import blocks
from blocks import r,model,OLD,CASES,ARMS,NEW_CELLS,key,mixed_packet,original_context
from investigate_dsx01_localization_failures import fit

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
TOL=dict(coefficient_absolute=1e-6,coefficient_relative=1e-8,residual_hz_absolute=1e-3,
    predictive_objective_absolute=1e-3,predictive_objective_relative=1e-8)


def write(name,value):r.write_new(HERE/name,value)
def alarm(seconds):
    if seconds<=0:raise TimeoutError('frozen cumulative budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen precision-block deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def check_files(path):
    for p,h in r.read(path)['files'].items():
        if r.sha(p)!=h:raise ValueError('bound source/input changed: '+p)


def prepare():
    if (HERE/'preparation.json').exists():raise FileExistsError('preparation already attempted')
    alarm(60-(time.monotonic()-STARTED));check_files(OLD/'protocol.json');check_files(OLD/'RF_seal.json')
    sources=r.read(OLD/'packets.json');controls=[];smokes=[];packets={}
    for case in CASES:
        original=original_context(case)
        for arm in ARMS:
            for origin in ('original','corrected'):
                packet=sources[key(case,arm,origin)];raw=r.read(packet['source_path'])
                # The prior eight controls include corrected-CFO diagonals.
                d=original
                if origin=='corrected':
                    rows=[x for x in r.read(model.PREVIOUS.parent/'measurement/corrections.json')['rows'] if x['case']==case]
                    d,_=model.inject(original,rows,model.previous.selected()[case]['native_IDs'])
                x=np.asarray(packet['source_endpoint']);reference=packet['final_phase_reference']
                vi=r.build(d,arm,reference);v=vi.calculate(x);p=model.build(d,arm,reference,packet);c=p.calculate(x)
                if model.layout(p)!=packet['layout'] or not np.array_equal(p.values,vi.values) or p.alias!=vi.alias:
                    raise ValueError('diagonal layout/value/alias mismatch')
                a=np.asarray(c['coefficient']);b=np.asarray(raw['coefficient']);res=np.asarray(c['conditional_residual_hz'])
                coef=float(np.max(abs(a-b)));rd=float(np.max(abs(res-raw['conditional_residual_hz'])))
                pr=float(np.max(abs(c['linear_raw_prediction_residual_hz']-v['linear_raw_prediction_residual_hz']))) if d['entries'] else 0.
                pd=float(c['linear_predictive_objective']-v['linear_predictive_objective']) if d['entries'] else 0.
                rel=abs(pd)/max(1,abs(v.get('linear_predictive_objective',0)))
                exact=bool(np.array_equal(c['noise_precision'],packet['noise_precision']) and np.array_equal(c['coefficient_prior_precision'],packet['coefficient_prior_precision']))
                passed=bool(exact and np.all(abs(a-b)<=1e-6+1e-8*abs(b)) and rd<=1e-3 and pr<=1e-3 and abs(pd)<=1e-3 and rel<=1e-8)
                arrays=HERE/'diagonal_arrays'/f'{key(case,arm,origin)}.npz';arrays.parent.mkdir(exist_ok=True)
                np.savez_compressed(arrays,coefficient=a,source_coefficient=b,residual_hz=res,source_residual_hz=raw['conditional_residual_hz'],
                    noise_precision=c['noise_precision'],prior_precision=c['coefficient_prior_precision'],values=p.values,
                    predictive_residual_hz=c.get('linear_raw_prediction_residual_hz',np.zeros(0)),
                    source_predictive_residual_hz=v.get('linear_raw_prediction_residual_hz',np.zeros(0)))
                controls.append(dict(case=case,arm=arm,origin=origin,passed=passed,max_coefficient_error=coef,max_residual_error_hz=rd,
                    max_predictive_residual_error_hz=pr,predictive_objective_difference=pd,predictive_relative_error=rel,packet_exact=exact,
                    array_path=str(arrays),array_sha256=r.sha(arrays),source_packet_sha256=model.digest(packet),
                    phase_reference=reference,source_endpoint=x,values_sha256=model.digest(p.values),aliases=p.alias,
                    curved_points=int(np.sum(p.keep)),predictive_points=sum(len(e['observation_ids']) for e in d['entries'])))
                if not passed:raise ValueError('same-reference diagonal failed: '+repr(controls[-1]))
            for cell,noise,prior in NEW_CELLS:
                packet=mixed_packet(sources[key(case,arm,noise)],sources[key(case,arm,prior)])
                packets[key(case,arm,cell)]=packet
    write('packets.json',packets)
    # Exercise the serialized packet path used by workers, at fixed old x/ref only.
    serialized=r.read(HERE/'packets.json')
    for case in CASES:
        d=original_context(case)
        for arm in ARMS:
            source=sources[key(case,arm,'original')]
            for cell,noise,prior in NEW_CELLS:
                packet=serialized[key(case,arm,cell)];p=model.build(d,arm,source['final_phase_reference'],packet)
                c=p.calculate(np.asarray(source['source_endpoint']))
                exact=bool(np.array_equal(c['noise_precision'],sources[key(case,arm,noise)]['noise_precision']) and
                    np.array_equal(c['coefficient_prior_precision'],sources[key(case,arm,prior)]['coefficient_prior_precision']))
                if not exact or not np.isfinite(c['negative_twice_elbo']):raise ValueError('mixed serialized input port failed')
                smokes.append(dict(case=case,arm=arm,cell=cell,passed=True,exact_selected_blocks=True,
                    packet_sha256=model.digest(packet),values_sha256=model.digest(p.values),aliases=p.alias,layout=model.layout(p)))
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_blocks.py')],capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
    signal.setitimer(signal.ITIMER_REAL,0)
    write('preparation.json',dict(all_passed=True,seconds=time.monotonic()-STARTED,diagonal_controls=controls,
        serialized_mixed_port_smokes=smokes,tolerances=TOL,test_stdout=proc.stdout,test_stderr=proc.stderr,
        GPS_used=False,new_endpoint_fits=0,old_CFO_original_contexts=True))
    print('PREPARATION_PASS',time.monotonic()-STARTED,flush=True)


def freeze():
    paths=[HERE/n for n in ('run.py','blocks.py','test_blocks.py','evaluate.py','PROTOCOL.md','packets.json','preparation.json')]
    paths +=[ROOT/'COORDINATOR_PLAN.md']
    paths +=[OLD/n for n in ('protocol.json','RF_seal.json','model.py','run.py','packets.json','preparation.json')]
    paths +=[Path(p) for p in r.read(OLD/'protocol.json')['files']]
    paths +=sorted((HERE/'diagonal_arrays').glob('*.npz'))
    for case in CASES:
        for arm in ARMS:
            for cell in ('00','01'):
                paths +=[OLD/case/arm/(cell+'_result.json'),OLD/case/arm/cell/'gates.json',OLD/case/arm/cell/'raw_endpoint.json']
    write('protocol.json',dict(schema='original-CFO-noise-prior-block-factorial/v1',files={str(p):r.sha(p) for p in sorted(set(paths))},
        cases=CASES,arms=ARMS,new_cells=NEW_CELLS,new_fit_count=8,reused_diagonal_count=8,
        diagonal_mapping={'00':'old_original_CFO_cell00','11':'old_original_CFO_cell01'},
        preparation_seconds=r.read(HERE/'preparation.json')['seconds'],preparation_cap_seconds=60,
        cap_seconds=360,workers=2,BLAS_threads=1,maximum_seconds_per_fit=30,cold_position=[0.,0.],cold_phase_reference='zero',
        phase_rounds=5,iterations=48,volume_weight=1,observations='original_CFO_only',
        diagnostics_membership='same actual conditional posterior; no VI rebuild',operational_policy='original_reference',
        evaluator_frozen_before_results=True,GPS_used=False))
    print('FROZEN',r.sha(HERE/'protocol.json'),flush=True)


def fit_cell(d,arm,cell,noise,prior,precision,deadline):
    began=time.monotonic();alarm(min(30,deadline-began));x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
    for epoch in range(5):
        p=model.build(d,arm,reference,precision);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=p.state(x)['phases'][p.labels];change=float(np.max(abs(np.clip(phase,-15,15)-reference)))
        history.append(dict(epoch=epoch,fit=result,reference=reference,unclipped_phase_s=phase,phase_change_s=change))
        write(Path(d['case'])/arm/cell/f'epoch{epoch}.json',history[-1]);reference=np.clip(phase,-15,15)
    c=p.calculate(x)
    if not np.array_equal(c['noise_precision'],precision['noise_precision']) or not np.array_equal(c['coefficient_prior_precision'],precision['coefficient_prior_precision']):
        raise ValueError('frozen mixed blocks changed during solve')
    record=model.summary(p,x,d['entries']);record.update(final_phase_change_s=change,history=history)
    write(Path(d['case'])/arm/cell/'raw_endpoint.json',dict(case=d['case'],arm=arm,cell=cell,CFO='original',noise_origin=noise,prior_origin=prior,
        summary=record,conditional_Gaussian_objective=c['negative_twice_elbo'],coefficient=c['coefficient'],
        noise_precision=c['noise_precision'],coefficient_prior_precision=c['coefficient_prior_precision'],
        conditional_residual_hz=c['conditional_residual_hz'],precision_packet_sha256=model.digest(precision),
        objective_kind='same_conditional_Gaussian_not_VI_ELBO',Gamma_updated=False,seconds=time.monotonic()-began))
    member,current=model.membership(p,x,d)
    old=r.read(model.previous.OWN/d['case']/'parent.json')['coverage'][arm]
    if set(member['curved_observation_ids'])!=set(old['curved_observation_ids']) or set(member['predictive_observation_ids'])!=set(old['predictive_observation_ids']):
        raise ValueError('fixed likelihood IDs changed')
    lost=sorted(set(old['accepted_observation_ids'])-set(member['accepted_observation_ids']))
    passed=bool(r.valid({a:record for a in ARMS}));maximum=float(np.max(abs(record['state']['phases'])))
    gates=dict(original_single_arm_valid=passed,final_phase_change_s=change,maximum_unclipped_phase_s=maximum,
        frozen_Gamma_no_convergence_claim=True,packet_exact=True,original_accepted_IDs_lost=lost,membership=member,
        posterior_kind='same_conditional_Gaussian',VI_rebuild=False,operational_policy='original_reference')
    write(Path(d['case'])/arm/cell/'gates.json',gates)
    return dict(case=d['case'],arm=arm,cell=cell,CFO='original',noise_origin=noise,prior_origin=prior,status='complete',
        endpoint_east_north_km=x,conditional_Gaussian_objective=c['negative_twice_elbo'],conditional_RMS_hz=current['RMS_hz'],
        original_single_arm_valid=passed,final_phase_change_s=change,maximum_unclipped_phase_s=maximum,
        original_accepted_IDs_lost=len(lost),associated_IDs=member['associated'],postfit_only_IDs=len(member['postfit_only_observation_ids']),
        fixed_likelihood_IDs=member['likelihood_points'],total_GLRT=member['total_GLRT'],packet_exact=True,
        objective_kind='same_conditional_Gaussian_not_VI_ELBO',seconds=time.monotonic()-began,operational_policy='original_reference')


def case_job(case,seconds):
    began=time.monotonic();deadline=began+seconds;rows=[];error=None
    try:
        alarm(deadline-time.monotonic());d=original_context(case);packets=r.read(HERE/'packets.json')
        for arm in ARMS:
            for cell,noise,prior in NEW_CELLS:
                try:row=fit_cell(d,arm,cell,noise,prior,packets[key(case,arm,cell)],deadline)
                except Exception as exc:row=dict(case=case,arm=arm,cell=cell,CFO='original',noise_origin=noise,prior_origin=prior,
                    status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc())
                finally:signal.setitimer(signal.ITIMER_REAL,0)
                rows.append(row);write(Path(case)/arm/(cell+'_result.json'),row);print(case,arm,cell,row['status'],flush=True)
    except Exception as exc:error=repr(exc)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    present={(r['arm'],r['cell']) for r in rows}
    for arm in ARMS:
        for cell,noise,prior in NEW_CELLS:
            if (arm,cell) not in present:
                row=dict(case=case,arm=arm,cell=cell,CFO='original',noise_origin=noise,prior_origin=prior,status='not_completed',error=error)
                rows.append(row);write(Path(case)/arm/(cell+'_result.json'),row)
    result=dict(case=case,rows=rows,error=error,seconds=time.monotonic()-began,operational_policy='original_reference',GPS_used=False)
    write(Path(case)/'result.json',result);return result


def run():
    if (HERE/'execution.json').exists():raise FileExistsError('no retries')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')
    check_files(HERE/'protocol.json');protocol=r.read(HERE/'protocol.json')
    audit=r.read(ROOT/'audit/mechanism_preflight.json');go=r.read(ROOT/'mechanism_go.json')
    if not audit['all_passed'] or not go['approved'] or any(v['protocol_sha256']!=r.sha(HERE/'protocol.json') for v in (audit,go)):
        raise ValueError('exact B preflight and root GO required')
    setup=time.monotonic()-STARTED;remaining=360-protocol['preparation_seconds']-setup;results=[]
    if remaining<=0:raise TimeoutError('preparation exhausted cap')
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(case_job,case,remaining/2):case for case in CASES}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],status='worker_failed',error=repr(exc),seconds=remaining/2))
    slots=[]
    for case in CASES:
        for arm in ARMS:
            for cell,noise,prior in NEW_CELLS:
                path=HERE/case/arm/(cell+'_result.json')
                slots.append(r.read(path) if path.exists() else dict(case=case,arm=arm,cell=cell,CFO='original',noise_origin=noise,prior_origin=prior,status='worker_failed'))
    write('execution.json',dict(cases=results,all8_slots=slots,all_selected_terminal=True,
        cumulative_worker_seconds=protocol['preparation_seconds']+setup+sum(x['seconds'] for x in results),
        cap_seconds=360,GPS_used=False,operational_policy='original_reference'))
    files={str(p):r.sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='RF_seal.json' and '.pytest_cache' not in p.parts and '__pycache__' not in p.parts}
    write('RF_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),files=files,all_selected_terminal=True,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','freeze','run'));a=parser.parse_args()
    try:{'prepare':prepare,'freeze':freeze,'run':run}[a.action]()
    except Exception as exc:
        if a.action=='prepare':write('preparation_failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-STARTED))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)
