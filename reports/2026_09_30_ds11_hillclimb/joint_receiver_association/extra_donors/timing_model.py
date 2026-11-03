"""Train-only scalar timing optimization at immutable horizontal coordinates."""
import numpy as np
from scipy.optimize import minimize


def solve(engine,horizontal):
    horizontal=np.asarray(horizontal,float)
    if horizontal.shape!=(2,) or not np.isfinite(horizontal).all():raise ValueError('finite fixed horizontal coordinates required')
    def state(t):return np.r_[horizontal,float(t[0])]
    def objective(t):
        score,gradient=engine.evaluate(state(t),True)
        return -score,np.array([-gradient[2]])
    rows=[]
    for seed in (0.,-2.,2.):
        fit=minimize(objective,[seed],method='L-BFGS-B',jac=True,bounds=[(-5.,5.)],
                     options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
        x=state(fit.x);score,gradient=engine.evaluate(x,True)
        delta=np.array([0.,0.,1e-4])
        fd=(engine.evaluate(x+delta,False)[0]-engine.evaluate(x-delta,False)[0])/2e-4
        error=abs(float(fd-gradient[2]));margin=5-abs(float(fit.x[0]))
        qualified=bool(fit.success and np.isfinite(score) and np.isfinite(x).all() and margin>=.001 and abs(gradient[2])<=.01 and error<=.02)
        rows.append(dict(seed_s=seed,x=x.tolist(),score=float(score),timing_gradient=float(gradient[2]),
                         derivative_discrepancy=error,bound_margin_s=margin,qualified=qualified,
                         success=bool(fit.success),message=str(fit.message),evaluations=int(fit.nfev)))
    good=[r for r in rows if r['qualified']]
    return dict(starts=rows,selected=max(good,key=lambda r:r['score']) if good else None)
