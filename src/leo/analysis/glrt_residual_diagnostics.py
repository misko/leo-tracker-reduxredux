"""Conditional residual diagnostics retaining signal/candidate uncertainty.

These responsibilities are conditional on the declared GLRT mark model and the
fitted satellite mixture. They do not establish physical satellite identities or
an independently calibrated measurement-error distribution.
"""

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import circular, wrapped_ratios


def signal_candidate_residuals(evidence, prediction, opportunity, design, beta, config, weights):
    """Return N×K×S residuals/masses and the N-dimensional clutter mass."""
    ratio = wrapped_ratios(evidence, prediction, opportunity, design, beta, config)
    weights = np.asarray(weights, dtype=float)
    if (
        weights.shape != (ratio.shape[1] + 1,)
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.isclose(weights.sum(), 1, atol=1e-9, rtol=0)
    ):
        raise ValueError("normalized finite activity weights required")
    mean = np.asarray(prediction) + (np.asarray(design) @ np.asarray(beta))[:, None]
    residual = circular(evidence.frequency_hz[:, :, None] - mean[:, None, :], config.period_hz)
    a = 2 * np.pi * config.scale_hz / config.period_hz
    rho = np.exp(-a)
    kernel = -np.expm1(-2 * a) / (
        np.expm1(-a) ** 2 + 4 * rho * np.sin(np.pi * residual / config.period_hz) ** 2
    )
    q = evidence.signal_probability[:, None] * opportunity
    mixture = weights[0] + ratio @ weights[1:]
    mass = (
        evidence.candidate_weight[:, :, None]
        * kernel
        * q[:, None, :]
        * weights[None, None, 1:]
        / mixture[:, None, None]
    )
    clutter = (weights[0] + (1 - q) @ weights[1:]) / mixture
    if not np.allclose(mass.sum(axis=(1, 2)) + clutter, 1, atol=1e-9, rtol=0):
        raise ValueError("candidate responsibilities disagree with the fitted density")
    return residual, mass, clutter


def weighted_median(values, weights):
    values, weights = np.asarray(values).ravel(), np.asarray(weights).ravel()
    if (
        values.shape != weights.shape
        or not np.isfinite(values).all()
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
    ):
        raise ValueError("finite samples with nonnegative weights required")
    if not weights.sum():
        return None
    order = np.argsort(values)
    index = np.searchsorted(np.cumsum(weights[order]), weights.sum() / 2)
    return float(values[order[index]])
