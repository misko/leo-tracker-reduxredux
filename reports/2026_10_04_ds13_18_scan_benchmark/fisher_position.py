"""Damped Fisher/SQP steps for the unchanged independent-scan objective.

Use the existing likelihood Fisher matrix as a local quadratic model, with
explicit common+individual timing constraints and the exact 2 km disk. Every
accepted step must reduce the actual objective. This changes the optimizer,
not observations, likelihood, priors, gates or orbital model.
"""
import time
import numpy as np
from constrained_fit import kkt_residual
from position_direct import coordinate,coordinate_jacobian,disk_feasible


def fit(objective,start,point,budget_s=20.,fixed=False):
    from scipy.optimize import minimize,LinearConstraint
    from timing_model import DeadlineReached
    begun=time.monotonic()
    scale=np.asarray(objective.scale).copy();scale[:2]=1.
    z=np.asarray(start,float)/scale;z[:2]=point
    bounds=[(None if lo is None else lo/s,None if hi is None else hi/s)
            for (lo,hi),s in zip(objective.bounds,scale)]
    bounds[:2]=[(v,v) for v in point] if fixed else [(-2.,2.)]*2
    for i,(lo,hi) in enumerate(bounds):
        if lo is not None:z[i]=max(z[i],lo)
        if hi is not None:z[i]=min(z[i],hi)
    matrix=np.zeros((len(objective.base.satellites),len(z)))
    matrix[:,6]=1.;matrix[:,7:objective.size]=objective.base.basis;matrix*=scale
    lower,upper=objective.base.minimum_shift_s+1e-6,objective.base.maximum_shift_s-1e-6
    totals=matrix@z
    factor=min(1.,upper/max(float(np.max(totals)),upper),lower/min(float(np.min(totals)),lower))
    z[6:objective.size]*=factor
    if not disk_feasible(z[:2]):raise ValueError('initial position outside disk')
    objective.base.deadline=begun+budget_s
    def physical(z):
        vector=z*scale;vector[:2]=coordinate(z[:2]);return vector
    def transform(z):
        t=np.diag(scale);t[:2,:2]=coordinate_jacobian(z[:2]);return t
    def evaluate(z):
        value,g=objective.evaluate(physical(z));return value,transform(z).T@g
    def audit(z,g):
        m,lo,hi=matrix,np.full(len(matrix),lower),np.full(len(matrix),upper)
        if not fixed and np.linalg.norm(z[:2])>=2.-1e-5:
            normal=np.r_[-2*z[:2],np.zeros(len(z)-2)]
            m=np.vstack([m,normal]);lo=np.r_[lo,normal@z];hi=np.r_[hi,np.inf]
        return kkt_residual(g,z,bounds,m,lo,hi)
    trace=[];status='iteration_limit';damping=1e-6
    value,g=evaluate(z)
    if not np.isfinite(value) or value>1e25:raise ValueError('invalid initial objective')
    try:
        for iteration in range(200):
            if time.monotonic()>=begun+budget_s:raise DeadlineReached()
            norm=audit(z,g)
            trace.append(dict(iteration=iteration,objective=float(value),kkt_residual=norm))
            if norm<=1e-3:
                status='constrained_fisher_converged';break
            # Curvature reads the likelihood state at this same iterate.
            value,g=evaluate(z)
            t=transform(z);h=t.T@objective.curvature(physical(z))@t
            h=(h+h.T)/2
            diagonal=np.maximum(np.diag(h),1.)
            accepted=False
            for attempt in range(6):
                if time.monotonic()>=begun+budget_s:raise DeadlineReached()
                regularized=h+damping*np.diag(diagonal)
                factor=max(1.,float(np.max(abs(g))))
                delta_bounds=[(None if lo is None else lo-v,None if hi is None else hi-v) for (lo,hi),v in zip(bounds,z)]
                constraints=[LinearConstraint(matrix,lower-matrix@z,upper-matrix@z)]
                if not fixed:
                    constraints.append(dict(type='ineq',fun=lambda d:4.-np.dot(z[:2]+d[:2],z[:2]+d[:2]),
                                            jac=lambda d:np.r_[-2*(z[:2]+d[:2]),np.zeros(len(z)-2)]))
                def quadratic(d):
                    return (g@d+.5*d@regularized@d)/factor,(g+regularized@d)/factor
                # Exact reduced Newton solve avoids loss of precision in the
                # generic QP optimizer when no inequality is active. Retain
                # the constrained QP for steps that actually encounter bounds.
                free=np.array([lo!=hi or lo is None for lo,hi in bounds])
                direction=np.zeros(len(z))
                direction[free]=np.linalg.solve(regularized[np.ix_(free,free)],-g[free])
                candidate=z+direction
                feasible=(disk_feasible(candidate[:2]) and np.all(matrix@candidate>=lower)
                          and np.all(matrix@candidate<=upper)
                          and all((lo is None or v>=lo) and (hi is None or v<=hi)
                                  for v,(lo,hi) in zip(candidate,bounds)))
                if not feasible:
                    result=minimize(quadratic,np.zeros(len(z)),jac=True,method='SLSQP',bounds=delta_bounds,
                                    constraints=constraints,options=dict(maxiter=100,ftol=1e-11))
                    direction=np.asarray(result.x)
                if g@direction>=0:
                    damping*=10;continue
                for alpha in 2.**-np.arange(14):
                    candidate=z+alpha*direction
                    if not disk_feasible(candidate[:2]) or np.any(matrix@candidate<lower-1e-9) or np.any(matrix@candidate>upper+1e-9):
                        continue
                    trial,tg=evaluate(candidate)
                    if trial<=value+1e-4*alpha*(g@direction):
                        z,value,g=candidate,trial,tg;accepted=True;damping=max(1e-10,damping/5);break
                if accepted:break
                damping*=10
            if not accepted:
                status='no_descent_step';break
    except DeadlineReached:
        status='time_limit'
    objective.base.deadline=float('inf')
    value,g=evaluate(z);norm=audit(z,g);vector=physical(z)
    return dict(point_km=z[:2].tolist(),vector=vector.tolist(),objective=float(value),
                success=bool(norm<=1e-3),kkt_residual=norm,status=status,fixed_location=fixed,
                position_gradient_per_km=g[:2].tolist(),elapsed_s=time.monotonic()-begun,
                parameters=objective.base.state(vector[:objective.size])['parameters'].tolist(),
                coefficient=float(vector[-1]),trace=trace)
