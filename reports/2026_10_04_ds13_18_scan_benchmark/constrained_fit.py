"""Explicit total-satellite-timing constraints for the unchanged likelihood.

The timing model uses common plus zero-sum relative coordinates. Bounding only
the common coordinate misses active limits on their sums. This solver exposes
those linear inequalities and audits their KKT residual instead of treating a
nonzero outward gradient at a timing boundary as automatic nonconvergence.
"""
import time
import numpy as np


def kkt_residual(gradient,point,bounds,matrix,lower,upper,active_tolerance=2e-5):
    from scipy.optimize import nnls
    gradient,point=np.asarray(gradient,float),np.asarray(point,float)
    free=np.array([lo!=hi or lo is None for lo,hi in bounds])
    normals=[]
    for i,(lo,hi) in enumerate(bounds):
        if not free[i]:
            continue
        axis=np.eye(len(point))[i]
        if lo is not None and point[i]-lo<=active_tolerance:
            normals.append(axis)
        if hi is not None and hi-point[i]<=active_tolerance:
            normals.append(-axis)
    values=matrix@point
    for row,value,lo,hi in zip(matrix,values,np.broadcast_to(lower,len(values)),np.broadcast_to(upper,len(values))):
        if value-lo<=active_tolerance:
            normals.append(row)
        if hi-value<=active_tolerance:
            normals.append(-row)
    residual=gradient[free].copy()
    if normals and np.any(free):
        design=np.asarray(normals)[:,free].T
        keep=np.linalg.norm(design,axis=0)>1e-14
        if np.any(keep):
            design=design[:,keep]
            multiplier,_=nnls(design,residual,maxiter=2000)
            residual-=design@multiplier
    return float(np.max(abs(residual),initial=0.))


def optimize(objective,start,bounds,budget_s=20.):
    from scipy.optimize import minimize,LinearConstraint
    from timing_model import DeadlineReached
    begun=time.monotonic()
    scale=np.asarray(objective.scale)
    initial=np.asarray(start).copy()
    matrix=np.zeros((len(objective.base.satellites),len(initial)))
    matrix[:,6]=1.
    matrix[:,7:objective.size]=objective.base.basis
    lower,upper=objective.base.minimum_shift_s+1e-6,objective.base.maximum_shift_s-1e-6
    total=np.clip(matrix@initial,lower,upper)
    initial[6]=np.mean(total)
    initial[7:objective.size]=objective.base.basis.T@(total-initial[6])
    scaled_bounds=[(None if lo is None else lo/s,None if hi is None else hi/s) for (lo,hi),s in zip(bounds,scale)]
    for i,(lo,hi) in enumerate(scaled_bounds):
        if lo is not None:
            initial[i]=max(initial[i],lo*scale[i])
        if hi is not None:
            initial[i]=min(initial[i],hi*scale[i])
    constraint=LinearConstraint(matrix*scale[None,:],lower,upper)
    best=None
    objective.base.deadline=begun+budget_s
    def evaluate(z):
        nonlocal best
        v,g=objective.evaluate(z*scale)
        if v<1e25 and (best is None or v<best[0]):
            best=(float(v),z.copy())
        return v,g*scale
    message='not_started'
    try:
        result=minimize(evaluate,initial/scale,jac=True,method='SLSQP',bounds=scaled_bounds,
                        constraints=[constraint],options=dict(maxiter=300,ftol=1e-10))
        message=str(result.message)
    except DeadlineReached:
        message='time_limit'
    if best is None:
        raise ValueError('no feasible finite constrained objective')
    value,z=best
    objective.base.deadline=float('inf')
    value,gradient=objective.evaluate(z*scale)
    kkt=kkt_residual(gradient*scale,z,scaled_bounds,matrix*scale[None,:],lower,upper)
    remaining=budget_s-(time.monotonic()-begun)
    if kkt>1e-3 and remaining>.5:
        from truth_start_diagnostic import optimize as gauss_newton
        polished=gauss_newton(objective,z*scale,bounds,budget_s=min(8.,remaining))
        if polished['objective']<=value and objective.base.state(polished['vector'][:objective.size])['ephemeris_valid']:
            z=np.asarray(polished['vector'])/scale
            objective.base.deadline=float('inf')
            value,gradient=objective.evaluate(z*scale)
            kkt=kkt_residual(gradient*scale,z,scaled_bounds,matrix*scale[None,:],lower,upper)
    feasible=objective.base.state((z*scale)[:objective.size])['ephemeris_valid']
    return dict(vector=z*scale,objective=float(value),success=bool(feasible and kkt<=1e-3),
                status='constrained_kkt_converged' if feasible and kkt<=1e-3 else message,
                projected_gradient_inf_norm=kkt,elapsed_s=time.monotonic()-begun,budget_s=budget_s,
                active_total_timing_bounds=int(sum((matrix@(z*scale)-lower<2e-5)|(upper-matrix@(z*scale)<2e-5))),
                validation='First-order KKT residual including box and total-timing constraints; not a certificate across visibility discontinuities.')
