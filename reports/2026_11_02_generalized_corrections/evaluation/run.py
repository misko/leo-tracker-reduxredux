"""One bounded, no-retry paired population evaluation. No geography is read."""
import argparse
from collections import Counter
import importlib.util
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time
import traceback
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo07_science.validation import clean
from evidence import native_inventory, qualify

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parent
sys.path.insert(0,str(REPORT/'solver'))
import numerical
ARMS=('c0','fitted_c')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    return loaded


def timeout(*_):raise TimeoutError('Frozen model-arm or preload time cap')


def fallback(record):
    return {arm:dict(source='exact_saved_ALGO07',objective=record['baseline'][arm]['objective'],
                     associated=record['baseline'][arm]['associated'],
                     selected_replacement=record['selected']) for arm in ARMS}


def initial(record,protocol_sha256):
    base=fallback(record)
    return dict(case=record['case'],dataset=record['dataset'],identities=record['identities'],
                input_sha256=record['input_sha256'],protocol_sha256=protocol_sha256,
                baseline=record['baseline'],status='running',
                variants={name:dict(accepted=False,status='unattempted',selected_output=base)
                          for name in ('A','A+B','A+B+C')})


def selection(record,rows,source):
    return {arm:dict(source=source,x=rows[arm]['x'],reference=rows[arm]['reference'],
                     objective=rows[arm]['objective'],rms_hz=rows[arm]['rms_hz'],
                     associated=record['baseline'][arm]['associated']) for arm in ARMS}


def pair_qualified(rows):
    return bool(set(rows)==set(ARMS) and all(rows[arm].get('qualified') for arm in ARMS))


def choose_A(record,rows,diagnostics,tolerance):
    triggered=any(diagnostics[a]['trigger'] for a in ARMS)
    gain={a:record['baseline'][a]['objective']-rows[a]['objective'] for a in ARMS} if set(rows)==set(ARMS) and all('objective' in rows[a] for a in ARMS) else {}
    common_reference_gain={a:rows[a]['saved_arm_position_objective_at_final_reference']-rows[a]['objective'] for a in ARMS} if set(rows)==set(ARMS) and all('saved_arm_position_objective_at_final_reference' in rows[a] for a in ARMS) else {}
    accepted=bool(triggered and pair_qualified(rows) and common_reference_gain and all(common_reference_gain[a]>=-tolerance for a in ARMS))
    return dict(accepted=accepted,status='accepted' if accepted else 'no_numerical_trigger' if not triggered else 'qualified_or_objective_guard_rejected',
                raw_endpoints=rows,objective_gains_diagnostic=gain,
                common_final_reference_position_gains=common_reference_gain,
                selected_output=selection(record,rows,'A_numerical_repair') if accepted else fallback(record))


def choose_B(record,rows,prior_receipt,selected_A):
    # Covariance choice is entirely causal-history based, never fitted-score based.
    accepted=bool(prior_receipt.get('status')=='ready' and pair_qualified(rows))
    return dict(accepted=accepted,status='accepted' if accepted else 'prior_or_qualification_fallback',
                raw_endpoints=rows,prior_receipt=prior_receipt,
                selected_output=selection(record,rows,'A+B_causal_covariance') if accepted else selected_A)


def terminal_fallback(result,status,reason):
    result.update(status=status,reason=reason)
    for label in ('A','A+B','A+B+C'):
        if result['variants'][label]['status']=='unattempted':
            result['variants'][label]['status']=status
    return result


def one_cell(d,z,arm,label,common,policy,folder):
    began=time.monotonic();path=folder/(label+'-'+arm+'.rf.json')
    checkpoint=folder/(label+'-'+arm+'.checkpoint.json')
    signal.setitimer(signal.ITIMER_REAL,float(policy['cell_seconds']))
    try:
        fitted=numerical.fit(d,z,arm,start=common[1],reference=common[0].reference,
                             **policy['solver'],checkpoint=lambda r:write(checkpoint,r))
        p,ctx=e.build(d,z,arm,np.asarray(fitted['reference']))
        replay_difference=objective(p,ctx,np.asarray(fitted['x']))-fitted['objective']
        if abs(replay_difference)>1e-4:raise ValueError('Sealed endpoint objective replay mismatch')
        row=dict(fitted,**qualify(p,ctx,np.asarray(fitted['x']),z,arm,fitted),
                 status='complete',arm=arm,model=label,objective_replay_difference=replay_difference,
                 saved_arm_position_objective_at_final_reference=objective(p,ctx,np.asarray(d['problems'][arm][1])))
    except Exception as exc:
        row=dict(status='cell_cap' if isinstance(exc,TimeoutError) else 'failed',arm=arm,
                 model=label,qualified=False,reason=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0.)
    row['wall_seconds']=time.monotonic()-began;write(path,row)
    return row


def worker(spec):
    record,policy,protocol_sha256=spec
    case=record['case'];folder=ROOT/'cases'/case
    began=time.monotonic();result=initial(record,protocol_sha256)
    signal.signal(signal.SIGALRM,timeout)
    write(folder/'result.json',result)
    try:
        if sha(record['input_path'])!=record['input_sha256']:raise ValueError('Native input hash changed')
        if record['selected']:
            terminal_fallback(result,'preserved_existing_ALGO07','Exact accepted ALGO07 replacement preserved; no reconstruction as ALGO06')
            return result
        signal.setitimer(signal.ITIMER_REAL,float(policy['preload_case_seconds']))
        input_root=Path(record['input_path']).parent.parent
        e.configure(input_root,folder/'engine');e.ROOTS[case[:4]]=input_root
        d,z,replay=e.load_case(case)
        checks={}
        for arm,(p,x) in d['problems'].items():
            inv=native_inventory(p,d)
            coordinate_delta=float(np.max(abs(np.asarray(x)-np.asarray(z['baseline_arms'][arm]['endpoint_east_north_km']))))
            objective_delta=objective(p,d,x)-record['baseline'][arm]['objective']
            if abs(objective_delta)>1e-4 or coordinate_delta>1e-8:raise ValueError('Saved ALGO07 RF comparator mismatch')
            checks[arm]=dict(objective_difference=objective_delta,coordinate_difference_km=coordinate_delta,
                             native_counts=inv['counts'],native_ids_sha256=inv['native_ids_sha256'],
                             fitted_owners_sha256=inv['fitted_owners_sha256'],
                             owners_equal=inv['owners']==z['baseline_owners'][arm],
                             missing_owned_ids=len(set(z['baseline_owners'][arm])-set(inv['owners'])))
        result.update(baseline_replay=checks,reconstruction=replay)
        if not all(r['owners_equal'] for r in checks.values()):
            terminal_fallback(result,'unsupported_baseline_evidence_union','Published owners differ from complete fitted likelihood')
            return result
        diagnostics={arm:numerical.baseline_diagnostic(d,arm) for arm in ARMS}
        result['numerical_trigger_diagnostics']=diagnostics
        signal.setitimer(signal.ITIMER_REAL,0.)
        common=d['problems']['fitted_c'];rows_A={}
        if any(diagnostics[a]['trigger'] for a in ARMS):
            for arm in ARMS:rows_A[arm]=one_cell(d,z,arm,'A',common,policy,folder)
        result['variants']['A']=choose_A(record,rows_A,diagnostics,policy['A_objective_nondegradation_tolerance'])
        selected_A=result['variants']['A']['selected_output']
        for label in ('A+B','A+B+C'):result['variants'][label]['selected_output']=selected_A
        write(folder/'result.json',result)
        signal.setitimer(signal.ITIMER_REAL,float(policy['preload_case_seconds']))
        ranking,eligible=e.rank_families(d,z)
        result.update(family_ranking=ranking,eligible_families=eligible)
        if not eligible:
            for label in ('A+B','A+B+C'):result['variants'][label].update(status='no_RF_family_trigger')
            result['status']='complete';return result
        target=int(eligible[0]);result['target_family']=target
        covariance=module('generalized_causal_covariance',REPORT/'covariance/causal_covariance.py')
        dd,receipt=covariance.candidate_context(d,z,dict(case=case,input_path=record['input_path'],selected_family=target))
        result['prior_receipt']=receipt
        signal.setitimer(signal.ITIMER_REAL,0.)
        rows_B={}
        if receipt.get('status')=='ready':
            for arm in ARMS:rows_B[arm]=one_cell(dd,z,arm,'B',common,policy,folder)
        result['variants']['A+B']=choose_B(record,rows_B,receipt,selected_A)
        write(folder/'result.json',result)
        guards={}
        if pair_qualified(rows_B):
            guard_module=module('generalized_identifiability',REPORT/'identifiability/guard.py')
            for arm in ARMS:
                selected_control=selected_A[arm]
                if selected_control['source']=='exact_saved_ALGO07':
                    p,x=d['problems'][arm]
                    selected_control=dict(x=x,reference=p.reference)
                signal.setitimer(signal.ITIMER_REAL,float(policy['guard_arm_seconds']))
                guards[arm]=guard_module.evaluate_guard(d,dd,selected_control,rows_B[arm],arm=arm,target_family=target,z=z)
                signal.setitimer(signal.ITIMER_REAL,0.)
        accepted_C=bool(result['variants']['A+B']['accepted'] and set(guards)==set(ARMS)
                        and all(guards[a]['guard_pass'] for a in ARMS))
        result['variants']['A+B+C']=dict(accepted=accepted_C,status='accepted' if accepted_C else 'geometry_or_B_qualification_fallback',
                geometry_guards=guards,selected_output=selection(record,rows_B,'A+B+C_guarded_causal_covariance') if accepted_C else selected_A)
        result['status']='complete'
    except Exception as exc:
        terminal_fallback(result,'preload_or_guard_cap' if isinstance(exc,TimeoutError) else 'failed',repr(exc))
        result['traceback']=traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0.)
        result['wall_seconds']=time.monotonic()-began
        write(folder/'result.json',result)
    return result


def scheduled(rows):
    """Round-robin cohorts, lexical IDs inside each cohort; no geography ranks."""
    groups={name:sorted([r for r in rows if r['dataset']==name],key=lambda r:r['case'])
            for name in sorted({r['dataset'] for r in rows})}
    out=[]
    for index in range(max(map(len,groups.values()))):
        for group in groups.values():
            if index<len(group):out.append(group[index])
    return out


def run(protocol_path):
    protocol=read(protocol_path);configuration=protocol['evaluation']
    roster_path=Path(configuration['roster_path'])
    if sha(roster_path)!=configuration['roster_sha256']:raise ValueError('RF roster hash mismatch')
    for path,digest in protocol['source_sha256'].items():
        if sha(path)!=digest:raise ValueError('Frozen source changed: '+path)
    if not protocol.get('source_sha256'):raise ValueError('Frozen source seal required')
    for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(variable)!='1':raise ValueError('Launch requires '+variable+'=1 before importing numerical libraries')
    completion=ROOT/'results.json'
    if completion.exists() or (ROOT/'execution_started.json').exists():
        raise FileExistsError('Single attempt only; existing execution is terminal and cannot be retried')
    roster=read(roster_path);rows=scheduled(roster['cases']);digest=sha(protocol_path)
    write(ROOT/'execution_started.json',dict(protocol_sha256=digest,cases=len(rows),wall_utc_ns=time.time_ns()))
    began=time.monotonic();deadline=began+float(configuration['total_seconds'])
    pool=multiprocessing.get_context('fork').Pool(processes=int(configuration['workers']))
    futures=[pool.apply_async(worker,((r,configuration,digest),)) for r in rows]
    capped=False;worker_errors=[]
    try:
        pool.close()
        for future in futures:
            remaining=deadline-time.monotonic()
            if remaining<=0:capped=True;break
            try:future.get(timeout=remaining)
            except multiprocessing.TimeoutError:capped=True;break
            except Exception as exc:worker_errors.append(repr(exc))
    finally:
        if capped:pool.terminate()
        pool.join()
    results=[]
    for record in rows:
        path=ROOT/'cases'/record['case']/'result.json'
        result=read(path) if path.exists() else initial(record,digest)
        if result['status']=='running':
            if path.exists():write(path.with_name('checkpoint_at_total_deadline.json'),result)
            terminal_fallback(result,'total_deadline_fallback','Original 1200s execution window exhausted; no retry')
            write(path,result)
        results.append(result)
    output=dict(protocol_sha256=digest,roster_sha256=sha(roster_path),available=len(rows),
                unavailable_source_members=roster['unavailable_source_members'],total_source_members=roster['total_source_members'],
                wall_seconds=time.monotonic()-began,workers_joined=True,workers_terminated_at_deadline=capped,
                worker_errors=worker_errors,status_counts=dict(Counter(r['status'] for r in results)),rows=results)
    write(completion,output)
    print(json.dumps({k:v for k,v in output.items() if k!='rows'},indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',required=True,type=Path)
    run(ap.parse_args().protocol)
