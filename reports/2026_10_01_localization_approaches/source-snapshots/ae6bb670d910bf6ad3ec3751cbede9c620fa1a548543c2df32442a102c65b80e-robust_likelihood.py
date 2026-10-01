"""Normalized multivariate Student-t likelihood for robust experiments."""
from __future__ import annotations

from math import lgamma, log, pi

import numpy as np


def student_t_logpdf(residual: object, covariance: object, nu: float) -> float:
    """Return a normalized multivariate Student-t log density with fixed scale."""
    value = np.asarray(residual, dtype=float)
    scale = np.asarray(covariance, dtype=float)
    nu = float(nu)
    if value.ndim != 1 or np.any(~np.isfinite(value)):
        raise ValueError("residual must be a finite vector")
    if scale.shape != (value.size, value.size) or np.any(~np.isfinite(scale)):
        raise ValueError("covariance has invalid shape or values")
    if not np.allclose(scale, scale.T, rtol=1e-10, atol=1e-12):
        raise ValueError("covariance must be symmetric")
    if not np.isfinite(nu) or nu <= 0:
        raise ValueError("nu must be finite and positive")
    try:
        chol = np.linalg.cholesky(scale)
    except np.linalg.LinAlgError as error:
        raise ValueError("covariance must be positive definite") from error
    solved = np.linalg.solve(chol, value)
    mahalanobis = float(solved @ solved)
    dimension = value.size
    return float(
        lgamma((nu + dimension) / 2)
        - lgamma(nu / 2)
        - 0.5 * (dimension * log(nu * pi) + 2 * np.log(np.diag(chol)).sum())
        - 0.5 * (nu + dimension) * np.log1p(mahalanobis / nu)
    )


def student_t_weight(mahalanobis_squared: float, dimension: int, nu: float) -> float:
    """Return the Student-t IRLS weight for a fixed scale matrix."""
    distance = float(mahalanobis_squared)
    nu = float(nu)
    if not np.isfinite(distance) or distance < 0:
        raise ValueError("mahalanobis_squared must be finite and nonnegative")
    if not isinstance(dimension, (int, np.integer)) or dimension < 1:
        raise ValueError("dimension must be a positive integer")
    if not np.isfinite(nu) or nu <= 0:
        raise ValueError("nu must be finite and positive")
    return float((nu + dimension) / (nu + distance))
