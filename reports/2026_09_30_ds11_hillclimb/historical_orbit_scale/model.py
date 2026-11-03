"""Normalized isotropic t4 state-revision uncertainty, with optional age scale."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln


def scores(parameters,ages_days,vectors,age_model):
    ages=np.asarray(ages_days,float);v=np.asarray(vectors,float);p=np.asarray(parameters,float)
    if ages.ndim!=1 or v.shape!=(len(ages),3) or np.any(ages<0) or not np.isfinite(v).all() or not np.isfinite(ages).all():
        raise ValueError('invalid ages or state vectors')
    x=np.column_stack((np.ones(len(ages)),np.log1p(ages))) if age_model else np.ones((len(ages),1))
    eta=x@p
    q=np.sum(v*v,axis=1)*np.exp(-2*eta)/4
    value=gammaln(3.5)-gammaln(2)-1.5*np.log(4*np.pi)-3*eta-3.5*np.log1p(q)
    derivative=(-3+7*q/(1+q))[:,None]*x
    return value,derivative


def fit(ages,vectors,weights,age_model):
    weights=np.asarray(weights,float);weights=weights/weights.sum()
    def objective(p):
        s,g=scores(p,ages,vectors,age_model)
        return -float(weights@s),-weights@g
    bounds=[(-6.,8.)]+([(0.,4.)] if age_model else [])
    starts=[[0.,0.],[0.,1.]] if age_model else [[0.]]
    rows=[]
    for start in starts:
        r=minimize(objective,start,jac=True,method='L-BFGS-B',bounds=bounds,
                   options=dict(maxiter=500,ftol=1e-14,gtol=1e-9,maxls=40))
        value,g=objective(r.x);projected=g.copy();fd=[]
        for j,(low,high) in enumerate(bounds):
            if r.x[j]<=low+1e-8 and g[j]>=0:projected[j]=0
            if r.x[j]>=high-1e-8 and g[j]<=0:projected[j]=0
            plus=r.x.copy();minus=r.x.copy();plus[j]+=1e-5;minus[j]-=1e-5
            fd.append((objective(plus)[0]-objective(minus)[0])/2e-5)
        error=float(np.max(abs(np.array(fd)-g)));pg=float(np.max(abs(projected)))
        boundary=any(r.x[j]>=hi-1e-5 or (j==0 and r.x[j]<=lo+1e-5) for j,(lo,hi) in enumerate(bounds))
        rows.append(dict(parameters=r.x.tolist(),score=-value,projected_gradient=pg,
                         derivative_discrepancy=error,success=bool(r.success),
                         qualified=bool(r.success and pg<1e-5 and error<1e-5 and not boundary)))
    qualified=[r for r in rows if r['qualified']]
    return dict(starts=rows,selected=max(qualified,key=lambda r:r['score']) if qualified else None)
