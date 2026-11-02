"""Bounded solver-only phase fixed-point experiment; no production mutation.

Absolute phase coefficients and priors are untouched. Relinearization changes
the approximate likelihood, so objectives across references are not invariant.
Both refresh schedules target the SAME phase-posterior fixed-point equations;
neither is an exact nonlinear marginal likelihood optimizer.
"""
import time
import numpy as np
from scipy.optimize import minimize
from algo07_science import engine as e
from algo07_science.diagnose import objective
from phase_reference_checks import phase_refresh
from prototype_dsx01_continuous_position import latlon

def fit(d, z, arm, *, variant='damped_half', start=None, reference=None,
        max_rounds=15, maxiter=35, maxfun=140):
    if variant not in ('legacy', 'damped_half', 'damped_quarter'):
        raise ValueError('only preregistered refresh schedules')
    if max_rounds < 1:
        raise ValueError('positive round budget required')
    common=d['problems']['fitted_c']
    x=np.array(common[1] if start is None else start, dtype=float, copy=True)
    ref=np.array(common[0].reference if reference is None else reference, dtype=float, copy=True)
    damping={'legacy':1.,'damped_half':.5,'damped_quarter':.25}[variant]
    history=[];tic=time.monotonic()
    for epoch in range(max_rounds):
        round_tic=time.monotonic()
        p,dd=e.build(d,z,arm,ref)
        opt=minimize(lambda v:objective(p,dd,v),x,method='L-BFGS-B',
            bounds=[(-12.5,12.5)]*2,
            options=dict(maxiter=maxiter,maxfun=maxfun,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
        x=np.asarray(opt.x)
        actual=np.asarray(p.state(x)['phases'])[p.labels]
        clipped,check=phase_refresh(actual,ref,limit_s=30.)
        history.append(dict(epoch=epoch,x=x.copy(),reference=ref.copy(),
            posterior_phase=actual.copy(),objective=objective(p,dd,x),
            seconds=time.monotonic()-round_tic,
            success=bool(opt.success),message=str(opt.message),nfev=int(opt.nfev),**check))
        if check['phase_change_s']<=.01:break
        if epoch<max_rounds-1:ref=ref+damping*(clipped-ref)
    c=p.calculate(x)
    return dict(x=x,latlon=latlon(x),reference=p.reference.copy(),
        objective=objective(p,dd,x),rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        history=history,variant=variant,damping=damping,phase_closed=check['phase_change_s']<=.01,
        phase_change_s=check['phase_change_s'],optimizer_success=bool(opt.success),
        active_points=int(p.keep.sum()),boundary=bool(np.any(abs(x)>12.49)),
        seconds=time.monotonic()-tic,objective_scope='existing per-reference ELBO; no reference-invariance claim',
        total_position_evaluations=sum(h['nfev'] for h in history))
