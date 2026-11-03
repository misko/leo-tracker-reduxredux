"""Independent constrained training optimizer with explicit scientific gates."""
import numpy as np
from scipy.optimize import minimize


def fit_model(model, initial):
    initial=np.asarray(initial,dtype=float)
    bounds=[(-12.,12.)]*2+[(-5.,5.)]*(len(initial)-2)
    offset=model.evaluate(initial,gradient=False)['score']
    def objective(x):
        out=model.evaluate(x)
        return offset-out['score'],-np.asarray(out['gradient'])
    fit=minimize(objective,initial,jac=True,method='SLSQP',bounds=bounds,
                 options=dict(maxiter=100,ftol=1e-10))
    out=model.evaluate(fit.x)
    gradient=np.asarray(out['gradient'])
    errors=[]
    for i,step in enumerate([1e-4,1e-4]+[1e-5]*(len(initial)-2)):
        plus,minus=fit.x.copy(),fit.x.copy()
        plus[i]+=step
        minus[i]-=step
        fd=(model.evaluate(plus,gradient=False)['score']-model.evaluate(minus,gradient=False)['score'])/(2*step)
        errors.append(abs(fd-gradient[i]))
    boundary=any(min(v-lo,hi-v)<.001 for v,(lo,hi) in zip(fit.x,bounds,strict=True))
    pg=float(np.max(np.abs(gradient)))
    audit=float(max(errors))
    replay=abs(float(offset-fit.fun)-out['score'])
    assert replay<1e-7
    return dict(x=fit.x.tolist(),score=float(out['score']),success=bool(fit.success),message=str(fit.message),
                boundary=bool(boundary),projected_gradient=pg,gradient_audit=audit,score_replay_error=replay,
                iterations=int(fit.nit),evaluations=int(fit.nfev),
                qualified=bool(fit.success and not boundary and pg<=.01 and audit<=.02))
