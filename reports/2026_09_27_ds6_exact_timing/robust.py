"""Fixed Student-t4 research likelihood with training-only offset fitting."""
import numpy as np
from scipy.special import gammaln

def fit_offset(train,sigma=100.):
    train=np.asarray(train);offset=np.median(train,axis=-1)
    for _ in range(12):
        z=(train-offset[...,None])/sigma;weight=5/(4+z*z)
        offset=np.sum(weight*train,axis=-1)/np.sum(weight,axis=-1)
    return offset

def robust_scores(residual,mask,sigma=100.):
    """Student-t4 profile offset fit on train only; held offset is frozen."""
    offset=fit_offset(residual[...,mask],sigma)
    z=(residual-offset[...,None])/sigma
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(sigma)-2.5*np.log1p(z*z/4)
    score=density[...,mask].sum(axis=-1)-.5*offset**2/1e12
    return score,score+density[...,~mask].sum(axis=-1)
