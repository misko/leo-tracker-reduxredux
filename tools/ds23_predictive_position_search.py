"""Bounded scalar predictive-score descent with deterministic differences."""

from functools import lru_cache
import numpy as np
from scipy.optimize import minimize


def search(score,*,half_width_km=12.5,step_km=.05,maxiter=20):
    if half_width_km<=step_km or step_km<=0:raise ValueError('positive regional box and smaller gradient step required')
    @lru_cache(maxsize=512)
    def cached(point):
        value=float(score(np.asarray(point,float)))
        if not np.isfinite(value):raise ValueError('predictive position objective is not finite')
        return value
    def value_and_gradient(position):
        x=np.asarray(position,float);value=cached(tuple(x));gradient=np.empty(2)
        for k in [0,1]:
            lower=x.copy();upper=x.copy()
            lower[k]=max(-half_width_km,x[k]-step_km);upper[k]=min(half_width_km,x[k]+step_km)
            gradient[k]=(cached(tuple(upper))-cached(tuple(lower)))/(upper[k]-lower[k])
        return value,gradient
    history=[]
    def record(x):history.append(dict(position=np.asarray(x).copy(),objective=cached(tuple(x))))
    result=minimize(value_and_gradient,np.zeros(2),jac=True,method='L-BFGS-B',
        bounds=[(-half_width_km,half_width_km)]*2,callback=record,
        options=dict(maxiter=maxiter,ftol=1e-10,gtol=.01,maxls=20))
    return dict(position=result.x,objective=float(result.fun),converged=bool(result.success),
        message=str(result.message),iterations=int(result.nit),score_evaluations=cached.cache_info().misses,
        maximum_gradient=float(max(abs(result.jac))),history=history,cold_start=[0.,0.],
        regional_box_width_km=2*half_width_km,gradient_step_km=step_km)
