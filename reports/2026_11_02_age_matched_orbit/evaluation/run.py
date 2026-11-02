"""One prospective age-prior experiment; previous failed models stay immutable."""
import argparse
from collections import Counter
import copy
import importlib.util
import hashlib
import json
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

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parent
PREVIOUS=REPORT.parent/'2026_11_02_generalized_corrections'
ARMS=('c0','fitted_c')
AGE_MINIMUMS={'Age3':3,'Age2':2}


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n');temporary.replace(path)


def module(name,path):
    path=Path(path).resolve();existing=sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve()!=path:raise ValueError('Module name collision: '+name)
        return existing
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);sys.modules[name]=loaded
    spec.loader.exec_module(loaded);return loaded


numerical=module('age_prior_frozen_numerical',PREVIOUS/'solver/numerical.py')
evidence=module('age_prior_frozen_evidence',PREVIOUS/'evaluation/evidence.py')
nuisance=module('age_prior_nuisance',ROOT/'nuisance.py')


def timeout(*_):raise TimeoutError('Frozen age-prior preparation/model-arm time cap')


def initial(record,protocol_sha256):
    return dict(case=record['case'],dataset=record['dataset'],identities=record['identities'],
        input_sha256=record['input_sha256'],protocol_sha256=protocol_sha256,
        previous_row_sha256=record['previous_row_sha256'],target_family=record['target_family'],
        saved_nomination_sha256=record['saved_nomination_sha256'],status='pending',
        age_support=record.get('age_support_summary'),
        new_model_attempt_started=False,candidate_qualified=False,candidate_accepted=False,exploratory_accepted=False,raw_endpoints={},
        selected_output=copy.deepcopy(record['selected_A']),
        policies={label:dict(accepted=False,minimum_pairs=minimum,selected_output=copy.deepcopy(record['selected_A'])) for label,minimum in AGE_MINIMUMS.items()},
        immutable_comparators=dict(ALGO07=record['baseline'],A=record['selected_A'],B=record['selected_B']))


def choose(record,endpoints,receipt):
    qualified=bool(receipt.get('status')=='ready' and set(endpoints)==set(ARMS)
                   and all(endpoints[a].get('qualified') for a in ARMS))
    policies={}
    for label,minimum in AGE_MINIMUMS.items():
        accepted=bool(qualified and receipt.get('pair_count',0)>=minimum)
        selected={arm:dict(source=label+'_age_matched_covariance',x=endpoints[arm]['x'],reference=endpoints[arm]['reference'],
            objective=endpoints[arm]['objective'],rms_hz=endpoints[arm]['rms_hz'],associated=record['baseline'][arm]['associated']) for arm in ARMS} if accepted else copy.deepcopy(record['selected_A'])
        policies[label]=dict(accepted=accepted,minimum_pairs=minimum,selected_output=selected)
    return dict(candidate_qualified=qualified,candidate_accepted=policies['Age3']['accepted'],
                exploratory_accepted=policies['Age2']['accepted'],selected_output=policies['Age3']['selected_output'],policies=policies)


def scheduled(rows):
    groups={name:sorted((r for r in rows if r['dataset']==name),key=lambda r:r['case'])
            for name in sorted({r['dataset'] for r in rows})}
    return [group[i] for i in range(max((len(g) for g in groups.values()),default=0))
            for group in groups.values() if i<len(group)]


def baseline_parity(d,z,record,*,diagnostic_problems=None):
    checks={};control={}
    for arm,(p,x) in d['problems'].items():
        inv=evidence.native_inventory(p,d)
        delta=objective(p,d,x)-record['baseline'][arm]['objective']
        coordinate_delta=float(np.max(abs(np.asarray(x)-np.asarray(z['baseline_arms'][arm]['endpoint_east_north_km']))))
        old=record['previous_baseline_replay'][arm]
        if abs(delta)>1e-4 or coordinate_delta>1e-8:raise ValueError('Saved ALGO07 RF coordinate/objective parity differs')
        if (inv['owners']!=z['baseline_owners'][arm] or inv['native_ids_sha256']!=old['native_ids_sha256']
                or inv['fitted_owners_sha256']!=old['fitted_owners_sha256']):
            raise ValueError('Complete native input/owner parity differs')
        checks[arm]=dict(objective_difference=delta,coordinate_difference_km=coordinate_delta,
            native_ids_sha256=inv['native_ids_sha256'],fitted_owners_sha256=inv['fitted_owners_sha256'],
            native_counts=inv['counts'],owners_equal=True)
        selected=record['selected_A'][arm]
        if selected['source']=='exact_saved_ALGO07':
            control[arm]=dict(source=selected['source'],objective_difference=delta,
                             native_ids_sha256=inv['native_ids_sha256'],rms_hz=float(np.sqrt(np.mean(p.calculate(x)['conditional_residual_hz'][p.keep]**2))))
            if diagnostic_problems is not None:diagnostic_problems[arm]=(p,np.asarray(x))
        else:
            q,context=e.build(d,z,arm,np.asarray(selected['reference']))
            difference=objective(q,context,np.asarray(selected['x']))-selected['objective']
            qinv=evidence.native_inventory(q,context)
            if abs(difference)>1e-4 or qinv['owners']!=inv['owners']:raise ValueError('Immutable selectedA control replay differs')
            control[arm]=dict(source=selected['source'],objective_difference=difference,native_ids_sha256=qinv['native_ids_sha256'],
                             rms_hz=float(np.sqrt(np.mean(q.calculate(np.asarray(selected['x']))['conditional_residual_hz'][q.keep]**2))))
            if diagnostic_problems is not None:diagnostic_problems[arm]=(q,np.asarray(selected['x']))
    return checks,control


def check_support(receipt,expected):
    for key in ('pair_count','history_sha256','nominal_elements_sha256','temporal_extent_sha256'):
        if key in expected and receipt.get(key)!=expected[key]:raise ValueError('Frozen age-history support differs: '+key)
    if receipt.get('status')=='ready' and 'coefficient_covariance' in expected:
        if not np.allclose(receipt['coefficient_covariance'],expected['coefficient_covariance'],rtol=1e-12,atol=1e-12):
            raise ValueError('Frozen orbital covariance reconstruction differs')


def cell(d,z,arm,common,policy,folder,*,target_family=None,covariance=None):
    began=time.monotonic();path=folder/('age-'+arm+'.rf.json')
    signal.setitimer(signal.ITIMER_REAL,float(policy['cell_seconds']))
    try:
        fitted=numerical.fit(d,z,arm,start=common[1],reference=common[0].reference,**policy['solver'],
            checkpoint=lambda r:write(folder/('age-'+arm+'.checkpoint.json'),r))
        p,context=e.build(d,z,arm,np.asarray(fitted['reference']));x=np.asarray(fitted['x'])
        baseline_cost=objective(p,context,np.asarray(d['problems'][arm][1]))
        delta=objective(p,context,x)-fitted['objective']
        if abs(delta)>1e-4:raise ValueError('New endpoint RF objective replay differs')
        row=dict(fitted,**evidence.qualify(p,context,x,z,arm,fitted),status='complete',arm=arm,
                 objective_replay_difference=delta,
                 saved_arm_position_objective_at_final_reference=baseline_cost)
    except Exception as exc:
        row=dict(status='cell_cap' if isinstance(exc,TimeoutError) else 'failed',arm=arm,qualified=False,
                 reason=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0.)
    if row['status']=='complete':row['nuisance']=nuisance.optional_snapshot(p,x,target_family=target_family,covariance=covariance)
    row['wall_seconds']=time.monotonic()-began;write(path,row);return row


def worker(spec):
    record,policy,protocol_sha256=spec
    began=time.monotonic();case=record['case'];folder=ROOT/'cases'/case
    result=initial(record,protocol_sha256)
    result.update(status='running',new_model_attempt_started=True,attempt_started_utc_ns=time.time_ns())
    signal.signal(signal.SIGALRM,timeout);write(folder/'result.json',result)
    try:
        if record['target_family'] is None:raise ValueError('New fit attempted without prior frozen nomination')
        if sha(record['input_path'])!=record['input_sha256']:raise ValueError('Frozen RF input changed')
        signal.setitimer(signal.ITIMER_REAL,float(policy['preparation_seconds']))
        root=Path(record['input_path']).parent.parent;e.configure(root,folder/'engine');e.ROOTS[case[:4]]=root
        d,z,replay=e.load_case(case)
        diagnostic_problems={};parity,control=baseline_parity(d,z,record,diagnostic_problems=diagnostic_problems)
        result.update(baseline_replay=parity,selected_A_control_replay=control,reconstruction=replay)
        covariance=module('age_matched_covariance',REPORT/policy['covariance_module'])
        dd,receipt=covariance.candidate_context(d,z,dict(case=case,input_path=record['input_path'],selected_family=record['target_family']))
        check_support(receipt,record['expected_age_support'])
        result['age_prior_receipt']=receipt
        signal.setitimer(signal.ITIMER_REAL,0.)
        for arm,(p,x) in diagnostic_problems.items():control[arm]['nuisance']=nuisance.optional_snapshot(p,x,target_family=record['target_family'])
        write(folder/'result.json',result)
        if receipt.get('status')!='ready':result['status']='age_prior_unavailable';return result
        common=d['problems']['fitted_c'];endpoints={}
        for arm in ARMS:
            endpoints[arm]=cell(dd,z,arm,common,policy,folder,target_family=record['target_family'],covariance=receipt['coefficient_covariance'])
            result['raw_endpoints']=endpoints
            if set(endpoints)==set(ARMS):
                result.update(choose(record,endpoints,receipt));result['status']='qualified' if result['candidate_qualified'] else 'qualification_rejected'
            write(folder/'result.json',result)
        result['objective_gains_diagnostic']={a:record['selected_A'][a]['objective']-endpoints[a]['objective']
            if 'objective' in endpoints[a] else None for a in ARMS}
    except Exception as exc:
        result.update(status='preparation_cap' if isinstance(exc,TimeoutError) else 'failed',reason=repr(exc),traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL,0.);result['wall_seconds']=time.monotonic()-began
        write(folder/'result.json',result)
    return result


def run(protocol_path):
    protocol=read(protocol_path);policy=protocol['evaluation'];digest=sha(protocol_path)
    if not protocol.get('source_sha256'):raise ValueError('Frozen source seal required')
    for path,expected in protocol['source_sha256'].items():
        if sha(path)!=expected:raise ValueError('Frozen source changed: '+path)
    if sha(policy['roster_path'])!=policy['roster_sha256']:raise ValueError('RF comparator roster changed')
    if sha(policy['support_inventory_path'])!=policy['support_inventory_sha256']:raise ValueError('Frozen orbital support inventory changed')
    for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(variable)!='1':raise ValueError('Launch requires '+variable+'=1')
    if int(policy['workers'])!=8 or float(policy['total_seconds'])>1200 or float(policy['cell_seconds'])>120:
        raise ValueError('Frozen prospective execution ceiling exceeded')
    if policy['age_policy_minimum_pairs']!=AGE_MINIMUMS:raise ValueError('Frozen primary/exploratory age support rules differ')
    if (ROOT/'execution_started.json').exists() or (ROOT/'results.json').exists():raise FileExistsError('Single new-model attempt only; no retries/extensions')
    roster=read(policy['roster_path']);cases={r['case']:r for r in roster['cases']};eligible=policy['candidate_cases']
    inventory=read(policy['support_inventory_path']);support={r['case']:r for r in inventory['rows']}
    if len(cases)!=205 or len(eligible)!=len(set(eligible)) or not set(eligible)<=set(cases):raise ValueError('Frozen candidate/whole205 roster differs')
    if len(support)!=len(inventory['rows']) or set(support)!=set(cases) or inventory['roster_sha256']!=policy['roster_sha256']:
        raise ValueError('Whole205 orbital support inventory differs from RF roster')
    if inventory['covariance_source_sha256']!=sha(REPORT/policy['covariance_module']):raise ValueError('Inventory covariance source binding differs')
    if any(cases[c]['target_family'] is None for c in eligible):raise ValueError('Candidate case lacks old nomination')
    ready={r['case'] for r in support.values() if r['status']=='ready' and r.get('pair_count',0)>=2}
    if set(eligible)!=ready:raise ValueError('Frozen candidate subset differs from all supported age priors')
    for case,record in cases.items():
        row=support[case]
        if row.get('target_family')!=record['target_family']:raise ValueError('Support inventory changed old target nomination')
        record['age_support_summary']={k:row[k] for k in ('status','pair_count','history_sha256','primary_history_eligible','exploratory_history_eligible') if k in row}
        if case in eligible:
            record['expected_age_support']={k:row[k] for k in ('pair_count','history_sha256','nominal_elements_sha256','temporal_extent_sha256','coefficient_covariance') if k in row}
    records=scheduled([cases[c] for c in eligible]);write(ROOT/'execution_started.json',dict(protocol_sha256=digest,
        wall_utc_ns=time.time_ns(),candidate_cases=[r['case'] for r in records],all_policy_cases=205))
    began=time.monotonic();deadline=began+float(policy['total_seconds']);capped=False;errors=[]
    if records:
        pool=multiprocessing.get_context('fork').Pool(processes=int(policy['workers']))
        futures=[pool.apply_async(worker,((record,policy,digest),)) for record in records]
        try:
            pool.close()
            for future in futures:
                remaining=deadline-time.monotonic()
                if remaining<=0:capped=True;break
                try:future.get(timeout=remaining)
                except multiprocessing.TimeoutError:capped=True;break
                except Exception as exc:errors.append(repr(exc))
        finally:
            if capped:pool.terminate()
            pool.join()
    results=[]
    for case,record in sorted(cases.items()):
        path=ROOT/'cases'/case/'result.json'
        result=read(path) if path.exists() else initial(record,digest)
        if result['status'] in ('pending','running'):
            if result['new_model_attempt_started']:write(path.with_name('checkpoint_at_total_deadline.json'),result)
            result['status']='global_deadline_partial' if result['new_model_attempt_started'] else 'global_deadline_unattempted' if case in eligible else 'not_in_frozen_candidate_subset' if record['target_family'] is not None else 'no_prior_nomination'
            result['selected_output']=copy.deepcopy(record['selected_A']);result['candidate_accepted']=False
            result['policies']={label:dict(accepted=False,minimum_pairs=minimum,selected_output=copy.deepcopy(record['selected_A'])) for label,minimum in AGE_MINIMUMS.items()}
            write(path,result)
        results.append(result)
    output=dict(protocol_sha256=digest,roster_sha256=policy['roster_sha256'],available=205,
        total_source_members=roster['total_source_members'],unavailable_source_members=roster['unavailable_source_members'],
        candidate_subset=len(eligible),wall_seconds=time.monotonic()-began,workers_joined=True,
        workers_terminated_at_deadline=capped,worker_errors=errors,
        status_counts=dict(Counter(r['status'] for r in results)),candidate_accepted=sum(r['candidate_accepted'] for r in results),
        policy_accepted={label:sum(r['policies'][label]['accepted'] for r in results) for label in AGE_MINIMUMS},rows=results)
    write(ROOT/'results.json',output);print(json.dumps({k:v for k,v in output.items() if k!='rows'},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',type=Path,required=True)
    run(ap.parse_args().protocol)
