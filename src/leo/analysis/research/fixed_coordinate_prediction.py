"""Gaussian prediction conditional on other coefficients fixed at their means.

This is a diagnostic conditional model, not marginalization of the frozen
coordinates' uncertainty. Callers must retain that distinction when comparing
it with a full posterior predictive model.
"""
import numpy as np
from scipy.linalg import cho_solve
from leo.analysis.research.predictive_track import gaussian_log_density


def fixed_coordinate_prediction(mean, precision, design, residual, noise, allowed):
    a,g,h,r,n=(np.asarray(v,float) for v in (mean,precision,design,residual,noise))
    indices=np.asarray(allowed)
    if (a.ndim!=1 or g.shape!=(len(a),len(a)) or r.ndim!=1 or not len(r)
            or h.shape!=(len(r),len(a)) or n.shape!=(len(r),len(r))):
        raise ValueError('matching nonempty coefficient and observation geometry required')
    if (indices.ndim!=1 or not np.issubdtype(indices.dtype,np.integer) or len(indices)==0
            or len(set(indices))!=len(indices) or np.any(indices<0) or np.any(indices>=len(a))):
        raise ValueError('nonempty unique integer coordinate indices required')
    if not all(np.isfinite(v).all() for v in (a,g,h,r,n)) or not np.allclose(g,g.T) or not np.allclose(n,n.T):
        raise ValueError('finite geometry and symmetric covariance/precision required')
    np.linalg.cholesky(g);np.linalg.cholesky(n)
    # Principal precision block is conditional precision. A principal block of
    # inverse(g) would instead marginalize the coordinates claimed to be fixed.
    root=np.linalg.cholesky(g[np.ix_(indices,indices)])
    covariance=cho_solve((root,True),np.eye(len(indices)))
    local=h[:,indices];cross=covariance@local.T;predictive=n+local@cross
    predictive=(predictive+predictive.T)/2;chol=np.linalg.cholesky(predictive)
    delta=cross@cho_solve((chol,True),r);updated=a.copy();updated[indices]+=delta
    posterior=covariance-cross@cho_solve((chol,True),cross.T)
    return dict(coefficient=updated,conditional_prior_covariance=covariance,
        posterior_covariance=(posterior+posterior.T)/2,predictive_covariance=predictive,
        negative_twice_log_density=-2*gaussian_log_density(r,predictive),
        shift_mahalanobis=float(np.sqrt(max(0.,delta@g[np.ix_(indices,indices)]@delta))),
        frozen_coordinates_conditioned_not_integrated=True)
