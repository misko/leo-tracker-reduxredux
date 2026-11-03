"""Conditional Student-t residuals for disjoint fitting and checking contrasts."""
import math

import numpy as np


def conditional_student_logpdf(residual, scale, training_dimension, degrees_of_freedom=4.):
    """Return log p(check residual | training residual) for a joint multivariate t.

    Scale is the Student-t scale matrix, not its covariance. Parameters and
    contrast construction belong to the caller; no claim of independent data
    selection or calibrated predictive coverage is made here.
    """
    r = np.asarray(residual, dtype=float)
    c = np.asarray(scale, dtype=float)
    k, nu = training_dimension, float(degrees_of_freedom)
    if (r.ndim != 1 or c.shape != (r.size, r.size) or not isinstance(k, int)
            or not 0 < k < r.size or not np.isfinite(nu) or nu <= 0
            or not np.all(np.isfinite(r)) or not np.all(np.isfinite(c))
            or not np.allclose(c, c.T, atol=1e-10, rtol=1e-10)):
        raise ValueError('invalid conditional Student-t inputs')
    np.linalg.cholesky(c)
    train_solution = np.linalg.solve(c[:k, :k], r[:k])
    q = float(r[:k] @ train_solution)
    conditional = r[k:] - c[k:, :k] @ train_solution
    schur = c[k:, k:] - c[k:, :k] @ np.linalg.solve(c[:k, :k], c[:k, k:])
    conditional_scale = (nu+q)/(nu+k)*schur
    chol = np.linalg.cholesky(conditional_scale)
    whitened = np.linalg.solve(chol, conditional)
    dimension, conditional_nu = r.size-k, nu+k
    return float(math.lgamma((conditional_nu+dimension)/2)-math.lgamma(conditional_nu/2)
                 - .5*dimension*math.log(conditional_nu*math.pi)
                 - np.log(np.diag(chol)).sum()
                 - .5*(conditional_nu+dimension)*math.log1p(
                     float(whitened @ whitened)/conditional_nu))
