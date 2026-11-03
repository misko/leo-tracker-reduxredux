"""Local position quadrature for conditional family nomination, not confidence."""

import numpy as np
from scipy.special import logsumexp


def normal_grid(mean,covariance,lower,upper):
    mean,cov,lo,hi=map(np.asarray,(mean,covariance,lower,upper))
    if mean.shape!=(2,) or cov.shape!=(2,2) or lo.shape!=(2,) or hi.shape!=(2,) or np.any(lo>=hi):
        raise ValueError('two-dimensional mean, covariance and ordered bounds required')
    if not all(np.isfinite(v).all() for v in (mean,cov,lo,hi)) or not np.allclose(cov,cov.T):
        raise ValueError('finite symmetric position covariance required')
    root=np.linalg.cholesky(cov);knots,weights=np.polynomial.hermite.hermgauss(3)
    nodes=[];mass=[]
    for a in range(3):
        for b in range(3):
            x=mean+np.sqrt(2)*root@np.array([knots[a],knots[b]])
            if np.all((x>=lo-1e-10)&(x<=hi+1e-10)):
                nodes.append(np.clip(x,lo,hi));mass.append(weights[a]*weights[b]/np.pi)
    if not nodes:raise ValueError('no quadrature nodes inside the regional box')
    mass=np.asarray(mass)
    return dict(positions=np.asarray(nodes),log_weights=np.log(mass/mass.sum()),retained_Gaussian_mass=float(mass.sum()))


def reweight_nodes(positions,mean,covariance,log_weights,loss):
    """Correct local Gaussian proposal weights using other-family RF evidence."""
    x,mu,c,w,l=map(np.asarray,(positions,mean,covariance,log_weights,loss))
    if x.shape!=(len(w),2) or l.shape!=w.shape or not np.isfinite(l).all():
        raise ValueError('one finite other-family loss per position node required')
    z=x-mu;quadratic=np.einsum('ni,ij,nj->n',z,np.linalg.inv(c),z)
    score=w-.5*(l-l.min())+.5*quadratic
    return score-logsumexp(score)


def mixture_score(component_scores,log_weights):
    """Normalized -2 log density of a fixed finite mixture, along the node axis."""
    scores,w=np.asarray(component_scores,float),np.asarray(log_weights,float)
    if scores.ndim<1 or scores.shape[0]!=len(w) or w.ndim!=1 or not np.isfinite(w).all() or np.isnan(scores).any():
        raise ValueError('matching finite mixture weights and non-NaN component scores required')
    w=w-logsumexp(w)
    return -2*logsumexp(w.reshape((len(w),)+(1,)*(scores.ndim-1))-.5*scores,axis=0)
