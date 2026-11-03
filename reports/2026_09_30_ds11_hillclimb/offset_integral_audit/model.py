"""Scalar CFO integral for independent Student-t4 observations and Gaussian CFO."""
import math
import numpy as np
from scipy.integrate import quad
from scipy.special import gammaln

SIGMA=100.
PRIOR=1e6
LOG_C=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(SIGMA))


def marginal(residual, offset, profile_score, tolerance=1e-8):
    residual=np.asarray(residual,dtype=float)
    if not len(residual) or not np.isfinite(residual).all():raise ValueError('finite nonempty residual required')
    def integrand(z):
        b=offset+SIGMA*z
        logp=len(residual)*LOG_C-2.5*np.log1p(((residual-b)/SIGMA)**2/4).sum()-.5*(b/PRIOR)**2
        return float(np.exp(logp-profile_score))
    centers=(residual-offset)/SIGMA
    # Split at each observation's center and flanks to expose separated modes.
    points=np.unique(np.r_[centers-2,centers,centers+2,0.])
    intervals=list(zip(np.r_[-np.inf,points],np.r_[points,np.inf]))
    values=[];errors=[]
    for lower,upper in intervals:
        value,error=quad(integrand,lower,upper,epsabs=tolerance/len(intervals),epsrel=tolerance,limit=150)
        values.append(value);errors.append(error)
    integral=math.fsum(values)
    if not integral>0 or not math.isfinite(integral):raise ValueError('invalid CFO integral')
    correction=math.log(SIGMA*integral)-math.log(PRIOR*math.sqrt(2*math.pi))
    return dict(log_marginal=float(profile_score+correction),log_correction=correction,
                relative_quadrature_error=math.fsum(errors)/integral)
