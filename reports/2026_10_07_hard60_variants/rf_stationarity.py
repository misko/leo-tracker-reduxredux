"""Bounded diagnostic of N64 RF-offset stationarity; no benchmark mutation."""
import numpy as np
from scipy.optimize import nnls
import run_variants as run
import rf_model


def main():
    run.engine.CONTEXT['N64']=run.data.load('N64')
    _,obs,bank,prior,score=run.engine.context('N64','rf_offsets')
    path=run.HERE/'results'/'N64'/'rf_offsets'/'regions'/'-102.5_-77.5_25.json'
    region=run.read(path);xy=region['point'];radius=region['local_radius_km']
    bank=bank.select(region['association']['selected_indices'])
    obj=rf_model.RFObjective(run.engine.NativeObjective(obs,bank,prior,score,
        receiver_baseline_hz=region['calibration']['receiver_baseline_hz']))
    pool=[c for c in region['candidates'] if c['arm']=='zero-c' and c['feasible']]
    v=np.asarray(min(pool,key=lambda c:c['selection_score'])['vector'])
    domain=rf_model.Domain(obj,v,'zero-c',xy,radius)
    value,g,_=obj.evaluate(v);slacks,jac=domain.slacks_jac(v)
    f,s=domain.free,domain.scales
    normals=list((jac[slacks<=1e-6]*s)[:,f])
    for i in f:
        if (v[i]-domain.lo[i])/s[i]<=1e-7:normals.append(np.eye(domain.n)[i,f])
        if (domain.hi[i]-v[i])/s[i]<=1e-7:normals.append(-np.eye(domain.n)[i,f])
    a=np.asarray(normals).T
    beta,_=nnls(a,(g*s)[f],maxiter=100*a.shape[1])
    residual=(g*s)[f]-a@beta
    direction=np.zeros(domain.n);direction[f]=-residual/np.linalg.norm(residual)
    physical=s*direction
    profile=[]
    for step in (-1e-3,-1e-4,-1e-5,-1e-6,-1e-7,-1e-8,0.,1e-8,1e-7,1e-6,1e-5,1e-4,1e-3):
        candidate=v+step*physical
        feasible=domain.audit(candidate,obj.evaluate(candidate)[1])['feasible']
        delta=obj.evaluate(candidate)[0]-value
        profile.append(dict(step_scaled=step,value_change=delta,feasible=feasible))
    captured=[];original=rf_model.minimize
    def capture(*args,**kwargs):
        result=original(*args,**kwargs);captured.append(result);return result
    rf_model.minimize=capture
    fit=rf_model.fit_rf(obj,v,rf_arm='zero-c',local_center=xy,local_radius_km=radius)
    rf_model.minimize=original
    terminal=None
    if captured:
        result=captured[0]
        scaled=domain.start/s;scaled[f]=result.x;last=scaled*s
        last_value,last_gradient,_=obj.evaluate(last)
        terminal=dict(vector=last,value=last_value,optimizer_success=bool(result.success),
            optimizer_message=str(result.message),**domain.audit(last,last_gradient))
    out=dict(scope=__doc__,value=value,stationarity=float(abs(residual).max()),
        scaled_residual_by_index={str(int(i)):float(r) for i,r in zip(f,residual)},
        analytic_directional_derivative=float(g@physical),profile=profile,
        returned=dict(vector=fit.vector,value=fit.objective,stationarity=fit.stationarity,
                      converged=fit.converged,stop_reason=fit.stop_reason),terminal=terminal,
        sources={str(p):run.data.digest(p) for p in (run.HERE/'rf_stationarity.py',run.HERE/'rf_model.py',path)})
    run.engine.write(run.HERE/'rf_stationarity.json',out)
    print('RETURNED',fit.stationarity,fit.converged,fit.stop_reason)
    print('TERMINAL',None if terminal is None else {k:v for k,v in terminal.items() if k!='vector'})


if __name__=='__main__':main()
