"""Pure shared random-intercept likelihood for matched log-ratio residuals."""
from __future__ import annotations

import math

import numpy as np


def candidate_ratio_loglik(residuals, variance, tau) -> np.ndarray:
    """Return candidate log likelihoods under compound-symmetric covariance.

    Rows of ``residuals`` are candidates and columns are matched observations.
    A single v ~ Normal(0, tau**2) is shared by every observation in a row,
    while independent noise has the supplied ``variance``.
    """
    values = np.asarray(residuals, dtype=float)
    if values.ndim != 2 or not values.shape[0] or not np.all(np.isfinite(values)):
        raise ValueError("residuals must be a finite candidate-observation matrix")
    noise = float(variance); scale = float(tau)
    if not math.isfinite(noise) or noise <= 0:
        raise ValueError("variance must be positive and finite")
    if not math.isfinite(scale) or scale < 0:
        raise ValueError("tau must be finite and nonnegative")
    observations = values.shape[1]
    if observations == 0:
        return np.zeros(values.shape[0])
    normal_constant = math.log(2. * math.pi * noise)
    if scale == 0.:
        # Exact expression used by the existing independent Gaussian model.
        return np.sum(-.5 * (normal_constant + values**2 / noise), axis=1)

    mean = np.mean(values, axis=1)
    centered = values - mean[:, None]
    longitudinal_variance = noise + observations * scale**2
    log_determinant = ((observations - 1) * math.log(noise)
                       + math.log(longitudinal_variance))
    quadratic = (np.sum(centered**2, axis=1) / noise
                 + observations * mean**2 / longitudinal_variance)
    result = -.5 * (observations * math.log(2. * math.pi)
                    + log_determinant + quadratic)
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("ratio random-intercept likelihood is nonfinite")
    return result
