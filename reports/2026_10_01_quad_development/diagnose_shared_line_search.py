"""Fixed-state reconstruction of the failed DS11 pilot line search; no refit."""
import math
import time
from pathlib import Path
import numpy as np
from run_shared_visibility_pilot import HERE, baseline, sealed, setup, digest, verify_sources, save


def main():
    begun=time.monotonic();unit='DS11-B01-S1'
    directory=HERE/'shared-visibility-pilot-v1'/unit
    frozen=sealed(directory/'sources.json')
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    receipt=sealed(directory/(unit+'.json'));best=receipt['best']
    assert best['reason']=='line_search_failed' and best['iterations']==1
    original,_,_=baseline(unit);model=setup(unit,original)
    x0=np.asarray(receipt['initial_state']);x=np.asarray(best['mean'])
    v0,g0,l0=model.evaluate(x0);v,g,labels=model.evaluate(x)
    scale=np.ones_like(x);mask=model.precision>0
    scale[mask]=1/np.sqrt(model.precision[mask]);scale[:2]=10
    # There is exactly one accepted step, so reconstruct the only history pair.
    s=(x-x0)/scale;y=(g-g0)*scale;sy=float(s@y)
    used=labels==l0 and sy>1e-12*np.linalg.norm(s)*np.linalg.norm(y)
    q=g*scale
    if used:
        rho=1/sy;a=rho*float(s@q);q=q-a*y
        gamma=sy/float(y@y);direction=gamma*q
        direction+=s*(a-rho*float(y@direction));direction=-direction
    else:
        gamma=1.;direction=-q
    if float((g*scale)@direction)>=0:direction=-g*scale
    physical=scale*direction;norm=np.linalg.norm(physical[:2])
    if norm>5:direction*=5/norm;physical=scale*direction
    slope=float(g@physical)
    initial_scores=[p.score_selected(x[c],i) for p,c,i in zip(model.ports,model.columns,labels,strict=True)]
    rows=[]
    for k in range(24):
        alpha=2.**(-k);trial=x+alpha*physical
        tv,_,tl=model.evaluate(trial,gradient=False)
        differences=[p.score_selected(trial[c],i)-old for p,c,i,old in
                     zip(model.ports,model.columns,tl,initial_scores,strict=True)]
        delta=trial-x
        stable=float((model.precision*x)@delta+.5*(model.precision*delta)@delta)-math.fsum(differences)
        rows.append(dict(backtrack=k,alpha=alpha,actual_delta=tv-v,termwise_delta=stable,
            linear_prediction=alpha*slope,armijo_bound=1e-4*alpha*slope,
            accepted=bool(tv<=v+1e-4*alpha*slope),label_changes=sum(a!=b for a,b in zip(tl,labels,strict=True)),
            physical_step_norm=float(np.linalg.norm(delta))))
    d=physical/np.linalg.norm(physical);direction_checks=[]
    for h in [.01,.001,.0001,.00001,.000001]:
        plus=model.evaluate(x+h*d,labels,False)[0];minus=model.evaluate(x-h*d,labels,False)[0]
        direction_checks.append(dict(step=h,numeric=(plus-minus)/(2*h),analytic=float(g@d)))
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    save(HERE/'shared-line-search-diagnostic-v1.json',dict(unit=unit,rows=rows,
        history_used=bool(used),history_curvature=sy,initial_inverse_hessian_scale=gamma,
        slope=slope,direction_norm=float(np.linalg.norm(physical)),direction_checks=direction_checks,
        objective=v,objective_ulp=float(np.spacing(v)),seconds=time.monotonic()-begun,
        input_sha256={str(directory/(unit+'.json')):digest(directory/(unit+'.json'))},
        source_sha256={str(Path(__file__).resolve()):digest(__file__),**frozen['source_sha256']},
        qualification='Failure-selected fixed-state diagnostic; same 24 candidate steps, no optimizer run, no new location estimate or geographic scoring. Termwise differences reduce aggregate subtraction loss but retain per-track floating-point arithmetic.'))
    print('history',used,'gamma',gamma,'slope',slope,'norm',np.linalg.norm(physical))
    print('accepted',sum(r['accepted'] for r in rows),'labels',max(r['label_changes'] for r in rows))
    print('delta range',min(r['actual_delta'] for r in rows),max(r['actual_delta'] for r in rows))
    print(direction_checks)


if __name__=='__main__':main()
