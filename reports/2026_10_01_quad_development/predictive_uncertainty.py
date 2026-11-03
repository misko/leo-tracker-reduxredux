"""Conditional design leverage and normalized Gaussian/t4 predictive mixtures."""
import math
import numpy as np
from trajectory_mixture import design

ARMS=('gaussian_fixed','gaussian_leverage','t4_matched_fixed','t4_matched_leverage','t4_same_fixed','t4_same_leverage')


def leverage(X,weights,Q):
    information=X.T@(weights[:,None]*X)
    eigen=np.linalg.eigvalsh(information)
    if eigen[0]<=0 or eigen[-1]/eigen[0]>1e12:raise ValueError('unsupported design information')
    h=np.sum(Q*np.linalg.solve(information,Q.T).T,axis=1)
    if np.any(h < -1e-10):raise ValueError('negative leverage')
    return np.maximum(h,0)


def setup(model,ttrain,ytrain,tquery,kind):
    X=design(ttrain,model['center'],model['scale']);Q=design(tquery,model['center'],model['scale'])
    sigma=model.get('sigma',model.get('sigma_hz'));v=np.asarray(ytrain)-model['offset']
    if kind=='robust':
        beta=np.asarray(model['beta'])[:,None];weights=np.ones(1)
        z=(v-X@beta[:,0])/sigma;R=(5/(4+z*z))[:,None]
    elif kind=='single':
        beta=np.asarray(model['single_beta']);weights=np.ones(1);R=np.ones((len(X),1))
    else:
        beta=np.asarray(model['beta']);weights=np.asarray(model['weights'])
        z=-.5*((v[:,None]-X@beta)/sigma)**2+np.log(weights)[None,:]
        z-=z.max(axis=1)[:,None];R=np.exp(z);R/=R.sum(axis=1)[:,None]
    means=Q@beta+model['offset'];h=None;error=None
    try:h=np.column_stack([leverage(X,R[:,k],Q) for k in range(len(weights))])
    except ValueError as exc:error=str(exc)
    return dict(means=means,weights=weights,sigma=sigma,leverage=h,error=error)


def score(prepared,y,arm):
    if arm not in ARMS:raise ValueError('unknown arm')
    if arm.endswith('leverage') and prepared['error']:raise ValueError(prepared['error'])
    h=prepared['leverage'] if arm.endswith('leverage') else np.zeros_like(prepared['means'])
    scale=prepared['sigma']*np.sqrt(1+h)
    if arm.startswith('t4_matched'):scale=scale/np.sqrt(2)
    z=(np.asarray(y)[:,None]-prepared['means'])/scale
    if arm.startswith('gaussian'):density=-.5*z*z-np.log(scale)-.5*np.log(2*np.pi)
    else:density=math.lgamma(2.5)-math.lgamma(2)-.5*np.log(4*np.pi)-np.log(scale)-2.5*np.log1p(z*z/4)
    density+=np.log(prepared['weights'])[None,:];maximum=density.max(axis=1)
    return maximum+np.log(np.exp(density-maximum[:,None]).sum(axis=1))
