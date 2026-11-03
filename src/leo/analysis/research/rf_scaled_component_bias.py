"""Shared fractional carrier-bias hypothesis, referenced to 11.5 GHz.

One component coefficient b contributes q_fragment*b in native observed Hz.
The Gaussian zero-mean prior fixes the carrier/hardware offset gauge by
assumption. No component slope is permitted. Integer aliases remain native Hz.
"""

import numpy as np

from leo.analysis.research.component_frequency_bias import ComponentBiasTerms


def profile_rf_scaled_bias(stats, beta, *, bias_sigma_hz, period_hz=1 / 4.4e-6, noise_hz=150.0):
    if (
        not np.isfinite(bias_sigma_hz)
        or bias_sigma_hz < 0
        or not np.isfinite(noise_hz)
        or noise_hz <= 0
        or not np.isfinite(period_hz)
        or period_hz <= 0
    ):
        raise ValueError("finite nonnegative bias sigma and positive physical scales required")
    q = np.asarray(stats["q"], float)[:, None]
    if not np.isfinite(q).all() or np.any(q <= 0):
        raise ValueError("positive finite RF scale per original fragment required")
    ci, starts, n = stats["ci"], stats["starts"], stats["n"]
    b = beta[stats["g"], None]
    d = beta[stats["g"] + 4, None]
    if len(beta) == 9:
        b = b + beta[8] * (q * 11.5 - 11.5)
    expected = b + d * stats["mx"][:, None]
    aliases = np.rint((expected - stats["mean"]) / period_hz)
    precision_count = noise_hz**2 / bias_sigma_hz**2 if bias_sigma_hz else np.inf
    squared_rf_count = np.add.reduceat(n[:, None] * q * q, starts, axis=0)
    bias = np.zeros((len(starts), stats["mean"].shape[1]))
    for _ in range(3):
        means = stats["mean"] + aliases * period_hz - expected
        if bias_sigma_hz:
            total = np.add.reduceat(n[:, None] * q * means, starts, axis=0)
            bias = total / (squared_rf_count + precision_count)
        new = np.rint((expected + q * bias[ci] - stats["mean"]) / period_hz)
        if np.array_equal(new, aliases):
            break
        aliases = new
    means = stats["mean"] + aliases * period_hz - expected
    if bias_sigma_hz:
        bias = np.add.reduceat(n[:, None] * q * means, starts, axis=0) / (
            squared_rf_count + precision_count
        )
    centered = np.maximum(0.0, stats["rss"] - 2 * d * stats["xz"] + d * d * stats["xx"][:, None])
    rss = np.add.reduceat(centered + n[:, None] * (means - q * bias[ci]) ** 2, starts, axis=0)
    penalty = precision_count * bias * bias if bias_sigma_hz else np.zeros_like(bias)
    occam = noise_hz**2 * np.log1p(squared_rf_count * bias_sigma_hz**2 / noise_hz**2)
    score = (rss + penalty + occam) / stats["count"][:, None]
    score[~stats["component_visible"]] = 1e30
    best = np.argmin(score, axis=1)
    mse = rss / stats["count"][:, None]
    return ComponentBiasTerms(
        best, np.sqrt(mse[np.arange(len(best)), best]), aliases, score, bias, mse
    )
