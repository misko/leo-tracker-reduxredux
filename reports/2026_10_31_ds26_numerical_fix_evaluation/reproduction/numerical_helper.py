"""Opt-in numerical patches for isolated ALGO03 research stage processes.

Importing this module changes nothing. Use ``patched_stages`` before importing
or executing an existing stage. Candidate selection, physical priors, target
phase integration, RF/owner gates, and stage schedules are not modified.
"""
from contextlib import contextmanager
import hashlib
import inspect
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import OptimizeResult


def bounded_position_call(method,x0,bounds,jac=None,constraints=()):
    if str(method).upper()!='L-BFGS-B' or jac is not None or constraints:
        return False
    try:
        x=np.asarray(x0,float);b=np.asarray(bounds,float)
        return bool(x.shape==(2,) and b.shape==(2,2) and np.isfinite(x).all()
            and np.array_equal(b,np.array([[-12.5,12.5],[-12.5,12.5]])))
    except (TypeError,ValueError):return False


def centered_minimize(original,fun,x0,*,args=(),bounds,options=None,callback=None,tol=None):
    """Same initial point/box; count all derivative calls under the original cap."""
    options=dict(options or {})
    cap=min(240,int(options.get('maxfun',240)))
    if cap<1:raise ValueError('positive objective-evaluation cap required')
    options.update(maxfun=cap,maxiter=min(48,int(options.get('maxiter',48))),maxls=40)
    options.pop('eps',None);options.pop('finite_diff_rel_step',None)
    b=np.asarray(bounds,float);x0=np.asarray(x0,float)
    memo={};gradients={};last=np.clip(x0,b[:,0],b[:,1]);iteration_count=0;gradient_calls=0
    class Budget(Exception):pass
    def evaluated(x):
        key=tuple(np.asarray(x,float))
        if key not in memo:
            if len(memo)>=cap:raise Budget('counted physical objective evaluation cap reached')
            value=float(fun(np.asarray(x,float),*args))
            if not np.isfinite(value):raise ValueError('finite physical objective required')
            memo[key]=value
        return memo[key]
    def jacobian(x):
        nonlocal gradient_calls
        gradient_calls+=1;gradient=[];h=.001
        for k in range(2):
            direction=np.eye(2)[k]*h
            if x[k]-h>=b[k,0] and x[k]+h<=b[k,1]:
                value=(evaluated(x+direction)-evaluated(x-direction))/(2*h)
            elif x[k]+2*h<=b[k,1]:
                value=(-3*evaluated(x)+4*evaluated(x+direction)-evaluated(x+2*direction))/(2*h)
            else:
                value=(3*evaluated(x)-4*evaluated(x-direction)+evaluated(x-2*direction))/(2*h)
            gradient.append(value)
        value=np.asarray(gradient);gradients[tuple(x)]=value;return value
    def accepted(x):
        nonlocal last,iteration_count
        last=np.asarray(x,float).copy();iteration_count+=1
        if callback is not None:
            if set(inspect.signature(callback).parameters)=={'intermediate_result'}:
                callback(intermediate_result=OptimizeResult(x=last.copy(),fun=evaluated(last)))
            else:callback(last.copy())
    try:
        result=original(evaluated,x0,method='L-BFGS-B',jac=jacobian,bounds=bounds,
            options=options,callback=accepted,tol=tol)
        scipy_nfev=int(result.nfev)
    except Budget as exc:
        key=tuple(last);value=memo.get(key)
        if value is None:
            # SciPy evaluates the initial point before its Jacobian. This path
            # protects a custom optimizer adapter without exceeding the cap.
            key=next(iter(memo));last=np.asarray(key,float);value=memo[key]
        gradient=gradients.get(key)
        result=OptimizeResult(x=last,fun=value,success=False,status=1,message=str(exc),
            nit=iteration_count,nfev=len(memo),njev=gradient_calls,
            jac=np.zeros(2) if gradient is None else gradient,hess_inv=np.eye(2),
            jac_available=gradient is not None)
        scipy_nfev=None
    result.scipy_nfev=scipy_nfev
    result.nfev=len(memo)
    result.total_physical_objective_evaluations=len(memo)
    result.objective_evaluation_cap=cap
    result.centered_gradient_step_km=.001
    result.numerical_maxls=40
    return result


def checked_domains(p,phases):
    from phase_reference_checks import reference_domain
    domains=dict(curved=reference_domain(p.sky['time_s'],p.flat_times,p.flat_labels,phases))
    entries=getattr(p,'linear_entries',[])
    if entries:
        from ds23_predictive_linear import linear_geometry
        view,*_=linear_geometry(p,entries)
        domains['predictive']=reference_domain(p.sky['time_s'],view.flat_times,view.flat_labels,phases)
    if not all(v['in_domain'] for v in domains.values()):
        raise ValueError('numerical reference leaves frozen causal orbit bank; no extrapolation')
    return domains


def replace_aliases(pairs):
    """Cover aliases imported before installation as well as future imports."""
    lookup={id(old):(old,new) for old,new in pairs}
    count=0
    for module in list(sys.modules.values()):
        if module is None or getattr(module,'__name__',None)==__name__:continue
        for name,value in list(vars(module).items()):
            pair=lookup.get(id(value))
            if pair is not None and value is pair[0]:
                setattr(module,name,pair[1]);count+=1
    return count


@contextmanager
def patched_stages(*,reference_limit_s,centered_lbfgsb=False):
    """Temporarily activate explicit experiment policy; always restore aliases."""
    if reference_limit_s not in (15,30):raise ValueError('explicit reference limit must be 15 or 30 s')
    import phase_reference_checks as phase_module
    import ds23_frequency_events as event_module
    import scipy.optimize as optimize
    original_phase=phase_module.phase_refresh;original_problem=event_module.make_event_problem;original_minimize=optimize.minimize
    state=dict(reference_limit_s=reference_limit_s,centered_lbfgsb=bool(centered_lbfgsb),
        extra_optimizer_rounds=0,physical_priors_and_target_phase_support_unchanged=True,
        reference_updates=[],optimizer_calls=[],problem_count=0,
        helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    current={}
    def make_problem(*args,**kwargs):
        p=original_problem(*args,**kwargs);checked_domains(p,p.reference)
        current['problem']=p;state['problem_count']+=1;return p
    def refresh(phases,reference,limit_s=15.):
        p=current.get('problem')
        if p is None:raise ValueError('phase refresh has no captured event problem for bank validation')
        if len(p.labels)!=len(np.asarray(reference)):raise ValueError('captured problem/reference shape mismatch')
        if not np.array_equal(np.asarray(p.reference),np.asarray(reference)):
            raise ValueError('captured problem is not the phase-refresh reference owner')
        updated,check=original_phase(phases,reference,limit_s=reference_limit_s)
        check['next_reference_domain']=checked_domains(p,updated)
        check['actual_posterior_domain']=checked_domains(p,np.asarray(phases))
        check['numerical_reference_limit_s']=reference_limit_s
        state['reference_updates'].append(dict(caller_limit_s=float(limit_s),**check))
        return updated,check
    def minimize(fun,x0,args=(),method=None,jac=None,hess=None,hessp=None,bounds=None,
                 constraints=(),tol=None,callback=None,options=None):
        if not bounded_position_call(method,x0,bounds,jac,constraints):
            return original_minimize(fun,x0,args=args,method=method,jac=jac,hess=hess,hessp=hessp,
                bounds=bounds,constraints=constraints,tol=tol,callback=callback,options=options)
        result=centered_minimize(original_minimize,fun,x0,args=args,bounds=bounds,options=options,callback=callback,tol=tol)
        state['optimizer_calls'].append(dict(start=np.asarray(x0,float).tolist(),endpoint=np.asarray(result.x).tolist(),
            success=bool(result.success),status=int(result.status),message=str(result.message),
            total_physical_objective_evaluations=int(result.nfev),cap=int(result.objective_evaluation_cap),
            gradient=np.asarray(result.jac).tolist(),gradient_available=bool(result.get('jac_available',True)),
            maxls=40,step_km=.001))
        return result
    pairs=[(original_problem,make_problem),(original_phase,refresh)]
    if centered_lbfgsb:pairs.append((original_minimize,minimize))
    state['patched_aliases']=replace_aliases(pairs)
    try:yield state
    finally:state['restored_aliases']=replace_aliases([(new,old) for old,new in pairs])
