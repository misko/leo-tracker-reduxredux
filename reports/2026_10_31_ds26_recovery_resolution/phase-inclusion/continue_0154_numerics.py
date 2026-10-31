"""One matched derivative/line-search continuation of frozen DS26-0154 fits."""
import copy
import hashlib
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.optimize import minimize

from run_inclusion import REPO,check_domains,source_receipt
from debug_fast_graph_unassociated import read,write,memberships
from annotate_predictive_only import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from predictive_new_family import NewFamily,resolution_audit
from phase_reference_checks import phase_refresh
from algo02_scan import pair_passes
import audit_predictive_family_inclusion as audit

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'cases/DS26-0154/reference30/inclusion'
OUT=ROOT/'DS26-0154-numerical-continuation'


def objective_for(p,family,d,include):
    def objective(x):
        c=p.calculate(x);penalty=float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)
        return float(c['negative_twice_elbo']+penalty+(family.evaluate(p,x,d['powers'],d['entries']) if include else 0.))
    return objective


def gradient_audit(objective,x):
    origin=objective(x);rows=[]
    for h in (.01,.001,.0001):
        forward=[];central=[];second=[]
        for k in range(2):
            delta=np.eye(2)[k]*h;plus=objective(x+delta);minus=objective(x-delta)
            forward.append(float((plus-origin)/h));central.append(float((plus-minus)/(2*h)))
            second.append(float((plus-2*origin+minus)/h**2))
        rows.append(dict(step_km=h,forward_gradient=forward,centered_gradient=central,diagonal_curvature=second))
    return dict(objective=origin,finite=bool(np.isfinite(origin) and np.isfinite([v for r in rows for v in r['centered_gradient']]).all()),rows=rows)


def centered_fit(objective,start):
    # Count every physical objective evaluation, including the four centered
    # derivative calls. This retains the original 240-evaluation round cap.
    memo={};last=np.asarray(start,float).copy();best=(float('inf'),last.copy())
    class Budget(Exception):pass
    def evaluated(x):
        nonlocal best
        key=tuple(np.asarray(x,float))
        if key not in memo:
            if len(memo)>=240:raise Budget('240 total physical objective evaluations')
            memo[key]=objective(np.asarray(x,float))
            if memo[key]<best[0]:best=(memo[key],np.asarray(x,float).copy())
        return memo[key]
    def jacobian(x):
        h=.001
        return np.array([(evaluated(x+np.eye(2)[k]*h)-evaluated(x-np.eye(2)[k]*h))/(2*h) for k in range(2)])
    def callback(x):
        nonlocal last
        last=np.asarray(x,float).copy()
    try:
        opt=minimize(evaluated,last,jac=jacobian,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
            callback=callback,options=dict(maxiter=48,maxfun=240,ftol=1e-10,gtol=1e-4,maxls=40))
        row=dict(endpoint_east_north_km=np.asarray(opt.x),objective=float(opt.fun),success=bool(opt.success),
            message=str(opt.message),nfev=int(opt.nfev),nit=int(opt.nit),gradient=np.asarray(opt.jac))
    except Budget as exc:
        row=dict(endpoint_east_north_km=last,objective=evaluated(last),success=False,message=str(exc),nfev=None,nit=None)
    row.update(total_objective_evaluations=len(memo),best_visited_objective=best[0],
        endpoint_movement_km=float(np.linalg.norm(np.asarray(row['endpoint_east_north_km'])-start)))
    return row


def run():
    began=time.monotonic();pr=read(SOURCE/'protocol.json');batchpr=read(ROOT/'cases/DS26-0154/protocol.json')
    inventory=Path(batchpr['inventory']);inv=read(inventory);d=context(inv);targets=pr['targets']
    family=NewFamily(d['scan'],targets,d['model'],phase_step=pr['phase_step_s'],allow_uncalibrated_label=pr['uncalibrated_label'])
    oldaudit=read(SOURCE/'exact_owner_replay.json')
    if not oldaudit['all_verified']:raise ValueError('continuation requires every frozen physical gate to pass')
    family_domains=[]
    from phase_reference_checks import reference_domain
    for phase in (-15.,15.):
        domain=reference_domain(d['scan'].sky['time_s'],family.times,np.zeros(len(family.times),int),[phase])
        if not domain['in_domain']:raise ValueError('target integration outside existing bank')
        family_domains.append(domain)
    protocol=copy.deepcopy(pr)
    protocol.update(numerical_continuation=True,reference_limit_s=30,start='corresponding frozen role/c-arm endpoint',
        source=str(SOURCE),matched_roles_and_c_arms=True,numerical_derivative='centered finite difference; h=0.001km',
        maxls=40,phase_rounds=5,maxiter=48,total_objective_evaluation_cap_per_round=240,
        maximum_seconds=590,causal_priors_candidates_aliases_masks_unchanged=True,GPS_used=False,
        original_control_failure='fitted_c final L-BFGS-B ABNORMAL; physical gates all passed',
        target_phase_bank_domains=family_domains,
        source_sha256=source_receipt([Path(__file__),SOURCE/'control.json',SOURCE/'new_family.json',SOURCE/'protocol.json',SOURCE/'exact_owner_replay.json',inventory]))
    write(OUT/'protocol.json',protocol)
    contexts=[];pre=[]
    for role,include in (('control',False),('new_family',True)):
        saved=read(SOURCE/(role+'.json'))
        for arm,v in saved['arms'].items():
            reference=np.asarray(v['phase_reference']);x=np.asarray(v['endpoint_east_north_km'])
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
            attach_event_predictive(p,d['entries'],d['powers']);cached(p)
            domains=check_domains(p,p.state(x)['phases'][p.labels],d['entries'])
            obj=objective_for(p,family,d,include);grad=gradient_audit(obj,x)
            difference=grad['objective']-v['negative_twice_elbo']
            if abs(difference)>1e-5 or not grad['finite']:raise ValueError('pre-continuation objective/gradient replay failed')
            row=dict(role=role,arm=arm,endpoint=x,objective_replay_difference=difference,
                last_optimizer=v['history'][-1],phase_check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)[1],
                all_physical_checks_pass=next(r for r in oldaudit['rows'] if r['role']==role and r['arm']==arm)['verified'],
                domains=domains,gradient=grad)
            pre.append(row);contexts.append(dict(role=role,include=include,arm=arm,x=x,reference=reference))
    write(OUT/'pre_continuation_audit.json',dict(rows=pre,selection='sole matched-control optimizer status blocker; no GPS criterion'))
    for role,include in (('control',False),('new_family',True)):
        pair={}
        for context_ in [c for c in contexts if c['role']==role]:
            arm=context_['arm'];x=context_['x'].copy();reference=context_['reference'].copy();history=[]
            for epoch in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                check_domains(p,reference,d['entries']);objective=objective_for(p,family,d,include)
                before=objective(x);f=centered_fit(objective,x);x=np.asarray(f['endpoint_east_north_km'])
                phase,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
                check['next_reference_domain']=check_domains(p,phase,d['entries']);reference=phase
                history.append(dict(f,objective_before=before,objective_change=float(f['objective']-before),**check))
            row=summary(p,x,d['entries']);_,_,ids,_=memberships(p,x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            if include:
                detail=family.evaluate(p,x,d['powers'],d['entries'],details=True);row['family']=detail
                row['incumbent_objective']=row['negative_twice_elbo'];row['negative_twice_elbo']+=detail['negative_twice_log_density']
                row['linear_gates']+=detail['gates'];ids.update(o for e in targets for o in e['observation_ids'])
                row['phase_resolution_audit']=resolution_audit(family,p,x,d['powers'],d['entries'],d['model'])
            row.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],proposed_associated_ids=sorted(ids),
                added_points=len(ids-old),lost_points=len(old-ids),post_gradient_audit=gradient_audit(objective_for(p,family,d,include),x),
                continuation_endpoint_movement_km=float(np.linalg.norm(x-context_['x'])))
            pair[arm]=row
            print(role,arm,'success',history[-1]['success'],'phase',history[-1]['phase_change_s'],'step',row['continuation_endpoint_movement_km'],flush=True)
        valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 and v['history'][-1]['success'] and v['final_phase_change_s']<=.01 for v in pair.values())
        if include:valid=valid and all(v['family']['phase_boundary_mass']<.01 and v['phase_resolution_audit']['local_agreement'] for v in pair.values())
        write(OUT/(role+'.json'),dict(job=inv['job'],arms=pair,baseline=inv['policy'],paired_valid=valid,target_entries=targets if include else [],
            no_production_change=True,receiver_calibration_from_target=False,shared_predictive_uncertainty=True,phase_resolution_checked=include))
    old_refresh,old_exact=audit.phase_refresh,audit.exact_gate_replay
    audit.phase_refresh=lambda actual,reference:phase_refresh(actual,reference,limit_s=30)
    def checked_exact(p,x,entries):
        check_domains(p,p.state(x)['phases'][p.labels],entries);return old_exact(p,x,entries)
    audit.exact_gate_replay=checked_exact
    try:audit.run(SimpleNamespace(trial=OUT,study=inventory.parents[2],output=OUT/'exact_owner_replay.json'))
    finally:audit.phase_refresh,audit.exact_gate_replay=old_refresh,old_exact
    paths=list(OUT.glob('*.json'))+[Path(__file__)]
    write(OUT/'inference_seal.json',dict(GPS_used=False,artifacts_sha256=source_receipt(paths),seconds=time.monotonic()-began))
    write(OUT/'terminal.json',dict(completed=True,seconds=time.monotonic()-began,budget_seconds=590))


if __name__=='__main__':
    OUT.mkdir(exist_ok=False)
    def timeout(*unused):raise TimeoutError('590-second continuation bound')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(590)
    try:run()
    except Exception as exc:
        write(OUT/'failure.json',dict(type=type(exc).__name__,message=str(exc)));raise
