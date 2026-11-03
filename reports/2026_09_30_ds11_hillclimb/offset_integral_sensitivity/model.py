"""Posterior-expected score gradient for the independent-error CFO integral."""
import math
import numpy as np
from scipy.integrate import quad_vec
from scipy.special import gammaln

SIGMA=100.
PRIOR=1e6
LOG_C=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(SIGMA))


def value_gradient(residual, prediction_jacobian, offset, profile_score):
    r=np.asarray(residual,dtype=float);jac=np.asarray(prediction_jacobian,dtype=float)
    assert jac.shape[0]==len(r) and jac.ndim==2
    def integrand(z):
        b=offset+SIGMA*z;delta=r-b
        logp=len(r)*LOG_C-2.5*np.log1p((delta/SIGMA)**2/4).sum()-.5*(b/PRIOR)**2
        score=(5*delta/(4*SIGMA**2+delta**2))@jac
        return np.exp(logp-profile_score)*np.r_[1.,score]
    centers=(r-offset)/SIGMA
    points=np.unique(np.r_[centers-2,centers,centers+2,0.])
    total=np.zeros(1+jac.shape[1]);error=0.
    intervals=list(zip(np.r_[-np.inf,points],np.r_[points,np.inf]))
    for a,b in intervals:
        v,e,info=quad_vec(integrand,a,b,epsabs=1e-9/len(intervals),epsrel=1e-9,full_output=True)
        assert info.success
        total+=v;error+=e
    assert total[0]>0 and np.isfinite(total).all()
    value=profile_score+math.log(SIGMA*total[0])-math.log(PRIOR*math.sqrt(2*math.pi))
    return dict(value=float(value),gradient=(total[1:]/total[0]).tolist(),relative_error=float(error/total[0]))
