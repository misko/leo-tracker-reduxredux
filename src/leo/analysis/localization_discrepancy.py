"""Track-specific slope discrepancy in contrast-space residual scale.

For Student-t residuals this defines a joint scale mixture: conditional on
one track precision lambda, both ordinary noise and the random slope have
covariance divided by lambda. It is not Gaussian noise added to a Student-t.
"""
import numpy as np


def slope_discrepancy_scale(covariance, slope_design, sigma, *, isotropic_control=False):
    """Add a slope scale, or a trace-matched isotropic comparison scale."""
    c = np.asarray(covariance, dtype=float)
    v = np.asarray(slope_design, dtype=float)
    if (v.ndim != 1 or v.size == 0 or c.shape != (v.size, v.size)
            or not np.all(np.isfinite(c)) or not np.all(np.isfinite(v))
            or not np.isfinite(sigma) or sigma < 0
            or not np.allclose(c, c.T, atol=1e-12, rtol=1e-12)):
        raise ValueError('invalid residual scale or slope design')
    np.linalg.cholesky(c)
    addition = np.outer(v, v)*sigma**2
    if isotropic_control:
        addition = np.eye(v.size)*np.trace(addition)/v.size
    return c+addition
