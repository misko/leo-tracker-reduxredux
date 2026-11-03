"""Exact Gaussian building blocks for a localization research prototype.

No association search, orbit approximation, or end-to-end estimator is implied.
All inputs are prewhitened where documented; densities include normalization.
"""
from __future__ import annotations

import numpy as np


def shared_shift_logpdf(shifts, epoch_variance, clock_variance):
    """log N(d; 0, epoch_variance I + clock_variance 11'), in O(M)."""
    d = np.asarray(shifts, dtype=float)
    if (d.ndim != 1 or not d.size or not np.all(np.isfinite(d))
            or not np.isfinite(epoch_variance) or epoch_variance <= 0
            or not np.isfinite(clock_variance) or clock_variance < 0):
        raise ValueError("finite vector and valid variances required")
    count = d.size
    mean = float(d.mean())
    common_variance = epoch_variance + count * clock_variance
    quadratic = float((d - mean) @ (d - mean)) / epoch_variance
    quadratic += count * mean**2 / common_variance
    logdet = (count - 1) * np.log(epoch_variance) + np.log(common_variance)
    return float(-0.5 * (quadratic + logdet + count * np.log(2 * np.pi)))


def collapsed_white_logpdf(residual, design):
    """log p(y) for y=U z+noise, independent z~N(0,I), noise~N(0,I).

    For raw covariance R and nuisance prior P, pass L_R^-1 residual and
    U=L_R^-1 B L_P, then subtract log|L_R| from the returned log density.
    The nuisance coordinates must be shared across all relevant track rows.
    """
    y, u = np.asarray(residual, dtype=float), np.asarray(design, dtype=float)
    if (y.ndim != 1 or not y.size or u.ndim != 2 or u.shape[0] != y.size
            or not np.all(np.isfinite(y)) or not np.all(np.isfinite(u))):
        raise ValueError("finite residual vector and matching design required")
    gram = np.eye(u.shape[1]) + u.T @ u
    chol = np.linalg.cholesky(gram)
    mean = np.linalg.solve(chol.T, np.linalg.solve(chol, u.T @ y))
    # Avoid subtracting two large near-equal Woodbury quadratic terms.
    remaining = y - u @ mean
    quadratic = float(remaining @ remaining + mean @ mean)
    logdet = float(2 * np.log(np.diag(chol)).sum())
    return float(-0.5 * (quadratic + logdet + y.size * np.log(2 * np.pi)))
