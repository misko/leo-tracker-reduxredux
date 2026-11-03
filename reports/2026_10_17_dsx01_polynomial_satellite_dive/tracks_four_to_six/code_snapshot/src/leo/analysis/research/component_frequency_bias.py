"""Gaussian constant-bias profiling for whole merged carrier components.

Aliases are discrete native-Hz profile branches. This branch-profiled robust
research score is not a normalized wrapped multivariate probability density.
There is no component slope parameter, geographic seed or storage dependency.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ComponentBiasTerms:
    best: np.ndarray
    rms_hz: np.ndarray
    aliases: np.ndarray
    score: np.ndarray
    bias_hz: np.ndarray
    residual_mse: np.ndarray


def profile_component_bias(stats, beta, *, bias_sigma_hz, period_hz=1 / 4.4e-6, noise_hz=150.0):
    if not np.isfinite(bias_sigma_hz) or bias_sigma_hz < 0:
        raise ValueError("finite nonnegative bias sigma required")
    if not np.isfinite(noise_hz) or noise_hz <= 0 or period_hz <= 0:
        raise ValueError("positive physical scales required")
    ci, starts, n = stats["ci"], stats["starts"], stats["n"]
    b = beta[stats["g"], None]
    d = beta[stats["g"] + 4, None]
    if len(beta) == 9:
        b = b + beta[8] * (stats["q"][:, None] * 11.5 - 11.5)
    expected = b + d * stats["mx"][:, None]
    aliases = np.rint((expected - stats["mean"]) / period_hz)
    prior_count = noise_hz**2 / bias_sigma_hz**2 if bias_sigma_hz else np.inf
    bias = np.zeros((len(starts), stats["mean"].shape[1]))
    # Small Gaussian biases do not grant free alias changes. The bounded
    # coordinate profile retains one integer for an entire original fragment.
    for _ in range(3):
        means = stats["mean"] + aliases * period_hz - expected
        if bias_sigma_hz:
            total = np.add.reduceat(n[:, None] * means, starts, axis=0)
            bias = total / (stats["count"][:, None] + prior_count)
        new_aliases = np.rint((expected + bias[ci] - stats["mean"]) / period_hz)
        if np.array_equal(new_aliases, aliases):
            break
        aliases = new_aliases
    means = stats["mean"] + aliases * period_hz - expected
    if bias_sigma_hz:
        bias = np.add.reduceat(n[:, None] * means, starts, axis=0) / (
            stats["count"][:, None] + prior_count
        )
    centered = np.maximum(0.0, stats["rss"] - 2 * d * stats["xz"] + d * d * stats["xx"][:, None])
    rss = np.add.reduceat(centered + n[:, None] * (means - bias[ci]) ** 2, starts, axis=0)
    penalty = prior_count * bias * bias if bias_sigma_hz else np.zeros_like(bias)
    occam = noise_hz**2 * np.log1p(stats["count"][:, None] * bias_sigma_hz**2 / noise_hz**2)
    score = (rss + penalty + occam) / stats["count"][:, None]
    score[~stats["component_visible"]] = 1e30
    best = np.argmin(score, axis=1)
    mse = rss / stats["count"][:, None]
    rms = np.sqrt(mse[np.arange(len(best)), best])
    return ComponentBiasTerms(best, rms, aliases, score, bias, mse)
