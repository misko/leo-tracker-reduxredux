"""Convex pseudo-Huber location profile for a future matched orbit experiment.

This primitive is not enabled by the current Gaussian joint estimator. It uses
training residuals only and returns normalized log density and its derivative.
"""

import numpy as np
from scipy.special import k1


def profile_pseudo_huber(residual_hz, training, sigma_hz, *, tolerance_hz=1e-7, max_iterations=100):
    """Profile a unique constant offset per row with safeguarded Newton steps.

    Brackets and convergence checks depend only on training columns. Failure to
    converge raises rather than silently using a Gaussian mean or partial fit.
    """
    residual = np.asarray(residual_hz, dtype=float)
    mask = np.asarray(training)
    if (
        residual.ndim != 2
        or mask.shape != (residual.shape[1],)
        or mask.dtype != bool
        or np.count_nonzero(mask) < 2
        or not np.all(np.isfinite(residual))
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or tolerance_hz <= 0
        or max_iterations < 1
    ):
        raise ValueError("finite residual matrix, training support and positive scale required")
    values = residual[:, mask]
    low, high = np.min(values, axis=1), np.max(values, axis=1)
    offset = np.mean(values, axis=1)
    done = high - low <= tolerance_hz
    for _ in range(max_iterations):
        if np.all(done):
            break
        z = (values - offset[:, None]) / sigma_hz
        root = np.hypot(1, z)
        score = np.mean(z / root, axis=1)
        curvature = np.mean(1 / root**3, axis=1)
        high = np.where((score < 0) & ~done, offset, high)
        low = np.where((score > 0) & ~done, offset, low)
        step = sigma_hz * score / np.maximum(curvature, np.finfo(float).tiny)
        converged = np.abs(step) <= tolerance_hz
        done |= converged | (high - low <= tolerance_hz)
        proposed = offset + step
        # Reject near-endpoint Newton steps: on nearly flat, widely separated
        # residual clusters they can shrink the bracket arbitrarily slowly.
        margin = 0.1 * (high - low)
        inside = (proposed > low + margin) & (proposed < high - margin) & np.isfinite(proposed)
        proposed = np.where(inside, proposed, low + (high - low) / 2)
        offset = np.where(done, offset, proposed)
    if not np.all(done):
        raise RuntimeError("pseudo-Huber offset profile did not converge")
    centered = residual - offset[:, None]
    z = centered / sigma_hz
    root = np.hypot(1, z)
    log_normalizer = np.log(2 * sigma_hz) + 1 + np.log(k1(1.0))
    log_density = -(root - 1) - log_normalizer
    negative_log_derivative = z / (sigma_hz * root)
    return offset, log_density, negative_log_derivative
