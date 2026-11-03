"""Tight RF profile optimization and observed carrier/rate response.

The finite-difference Hessian retains residual-dependent curvature omitted by
the Gauss-Newton matrix. All coordinates remain the original six physical RF
parameters; this helper does not introduce a position or orbital timing prior.
"""

import copy
import numpy as np
from scipy.optimize import minimize

from ds23_differential_rf_epoch import inject_component_rates


def tight_fit(workspace, start, parity=None, *, iterations=160):
    p=workspace;scale=np.asarray(p.scale,float);native=np.asarray(p.start,float)
    start=np.asarray(start,float)
    if start.shape!=(6,) or not np.isfinite(start).all():
        raise ValueError('six finite physical RF coordinates required')
    lower=native.copy();upper=native.copy()
    lower[[0,3]]-=120;upper[[0,3]]+=120
    lower[[1,4]]=-.75;upper[[1,4]]=.75
    lower[[2,5]]=-40;upper[[2,5]]=40
    initial=p.statistics(start,parity)
    variance=initial['squared_error']/max(1,initial['samples']-17*len(p.segments)-6)

    def objective(u):
        result=p.statistics(u*scale,parity)
        return result['squared_error']/variance,-2*result['rhs']/variance

    result=minimize(objective,start/scale,jac=True,method='L-BFGS-B',
        bounds=list(zip(lower/scale,upper/scale,strict=True)),
        options=dict(maxiter=iterations,maxls=30,ftol=2e-15,gtol=1e-7,maxcor=12))
    physical=result.x*scale;stats=p.statistics(physical,parity)
    standardized=float(np.max(abs(stats['rhs'])/
        np.sqrt(np.maximum(np.diag(stats['normal'])*variance/2,1e-20))))
    return dict(parameters=physical,score=stats['score'],squared_error=stats['squared_error'],
        noise_variance=variance,maximum_standardized_score=standardized,
        difference_hz=float(physical[0]-physical[3]),iterations=int(result.nit),calls=int(result.nfev),
        optimizer_success=bool(result.success),optimizer_message=str(result.message),
        boundary=bool(np.any(physical<=lower+1e-5) or np.any(physical>=upper-1e-5)))


def observed_rate_response(workspace, parameters, *, coordinate_step=1e-7, rate_step=50.):
    """Derivative of the fitted contrast to injected component frequency ramps.

    At a stationary fit, 0 = d(rhs) = -H du + B dr. Compute H and B
    from the actual profiled score, including refitted channel coefficients.
    The returned response is Hz / (Hz/s), i.e. seconds.
    """
    p=workspace;parameters=np.asarray(parameters,float);scale=np.asarray(p.scale,float)
    if parameters.shape!=(6,) or coordinate_step<=0 or rate_step<=0:
        raise ValueError('six RF coordinates and positive derivative steps required')
    columns=[]
    for k in range(6):
        delta=np.zeros(6);delta[k]=coordinate_step*scale[k]
        plus=p.statistics(parameters+delta)['rhs'];minus=p.statistics(parameters-delta)['rhs']
        columns.append(-(plus-minus)/(2*coordinate_step))
    hessian=np.column_stack(columns);cross=[]
    for k in range(2):
        values=[]
        for sign in [-1,1]:
            rates=np.zeros(2);rates[k]=sign*rate_step
            view=copy.copy(p);view.y=inject_component_rates(p,parameters,rates)
            values.append(view.statistics(parameters)['rhs'])
        cross.append((values[1]-values[0])/(2*rate_step))
    cross=np.column_stack(cross)
    contrast=np.array([1.,0.,0.,-1.,0.,0.])*scale
    response=contrast@np.linalg.solve(hessian,cross)
    symmetric=(hessian+hessian.T)/2
    return dict(response_s=response,hessian=hessian,cross=cross,
        hessian_asymmetry=float(np.max(abs(hessian-hessian.T))/max(1.,np.max(abs(hessian)))),
        minimum_eigenvalue=float(np.linalg.eigvalsh(symmetric).min()),
        coordinate_step=coordinate_step,rate_step_hz_s=rate_step)
