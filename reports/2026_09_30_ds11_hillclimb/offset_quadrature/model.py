"""Vectorized piecewise Gauss-Legendre CFO integral including both infinite tails."""
from functools import lru_cache
import math
import numpy as np
from scipy.special import gammaln,logsumexp

SIGMA=100.
PRIOR=1e6
LOG_C=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(SIGMA))


@lru_cache(None)
def rule(order):
    return np.polynomial.legendre.leggauss(order)


def integrate(residual,jacobian,offset,order=32):
    r=np.asarray(residual,dtype=float);jac=np.asarray(jacobian,dtype=float)
    assert len(r)>0 and jac.shape[0]==len(r) and np.isfinite(r).all()
    centers=(r-offset)/SIGMA
    knots=np.unique(np.r_[centers-2,centers,centers+2,0.])
    nodes,weights=rule(order)
    mid=(knots[1:]+knots[:-1])/2;half=np.diff(knots)/2
    z=(mid[:,None]+half[:,None]*nodes).ravel()
    w=(half[:,None]*np.broadcast_to(weights,(len(half),order))).ravel()
    u=(nodes+1)/2;tail=u/(1-u);tail_weights=weights/2/(1-u)**2
    z=np.r_[knots[0]-tail,z,knots[-1]+tail]
    w=np.r_[tail_weights,w,tail_weights]
    b=offset+SIGMA*z
    delta=r[None,:]-b[:,None]
    logp=len(r)*LOG_C-2.5*np.log1p((delta/SIGMA)**2/4).sum(axis=1)-.5*(b/PRIOR)**2
    logweight=logp+np.log(w)
    normal=float(logsumexp(logweight))
    posterior=np.exp(logweight-normal)
    expected_score=posterior@(5*delta/(4*SIGMA**2+delta**2))
    return dict(value=normal+math.log(SIGMA)-math.log(PRIOR*math.sqrt(2*math.pi)),
                gradient=(expected_score@jac).tolist(),nodes=len(z))
