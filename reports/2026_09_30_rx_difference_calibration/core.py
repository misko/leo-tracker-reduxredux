import math
import numpy as np
from scipy.optimize import minimize


def pair(a,b):
    if (a['session_id'],a['rf_hz'],a['number'])!=(b['session_id'],b['rf_hz'],b['number']):
        return None
    if (a['receiver_id'],b['receiver_id'])!=(0,1):
        return None
    ta,tb=np.asarray(a['times']),np.asarray(b['times'])
    distances=abs(ta[:,None]-tb[None,:])
    ab=distances.argmin(axis=1);ba=distances.argmin(axis=0)
    ia=np.array([i for i,j in enumerate(ab) if ba[j]==i and distances[i,j]<=1e-6],dtype=int)
    ib=ab[ia]
    ma,mb=np.asarray(a['mask'],bool)[ia],np.asarray(b['mask'],bool)[ib]
    train=ma&mb;held=~ma&~mb
    if train.sum()<8 or held.sum()<3 or np.ptp(ta[ia][train])<5:
        return None
    delta=np.asarray(a['residual'])[ia]-np.asarray(b['residual'])[ib]
    center=float(np.median(delta[train]))
    scale=max(1.,1.4826*float(np.median(abs(delta[train]-center))))
    return dict(center=center,feature=scale,held=(delta[held]-center).tolist(),
                training_pairs=int(train.sum()),held_pairs=int(held.sum()),mixed_pairs=int((ma!=mb).sum()))


def density(params,errors,features):
    design=np.column_stack([np.ones(len(errors)),np.log(features)])[:,:len(params)]
    logscale=design@params
    r2=(np.asarray(errors)*np.exp(-logscale))**2
    values=math.lgamma(2.5)-math.lgamma(2)-.5*math.log(4*math.pi)-logscale-2.5*np.log1p(r2/4)
    derivative=(-1+5*r2/(4+r2))[:,None]*design
    return values,derivative


def fit(errors,features,weights,variable):
    initial=[math.log(50),0.] if variable else [math.log(50)]
    bounds=[(-5.,10.),(-2.,2.)][:len(initial)]
    def objective(p):
        values,derivative=density(p,errors,features)
        return -float(weights@values),-weights@derivative
    result=minimize(objective,initial,jac=True,bounds=bounds,method='L-BFGS-B',
                    options=dict(maxiter=200,ftol=1e-12,gtol=1e-7))
    audits=[]
    for i in range(len(initial)):
        delta=np.zeros(len(initial));delta[i]=1e-5
        fd=(objective(result.x+delta)[0]-objective(result.x-delta)[0])/2e-5
        audits.append(abs(fd-result.jac[i]))
    boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(result.x,bounds))
    gradient=float(max(abs(result.jac)))
    audit=float(max(audits))
    return dict(params=result.x.tolist(),success=bool(result.success),message=str(result.message),
                gradient=gradient,gradient_audit=audit,boundary=boundary,
                qualified=bool(result.success and not boundary and gradient<=1e-5 and audit<=1e-5))
