"""Conditional complex-Gaussian pilot model with frequency and null uncertainty.

Noise scales are fixed from training energy. Signal amplitudes are integrated,
not profiled. This empirical-Bayes research model does not calibrate RF truth.
"""

import numpy as np


def logsumexp(values):
    values = np.asarray(values, dtype=float)
    maximum = np.max(values)
    return float(maximum + np.log(np.exp(values - maximum).sum()))


def fit(training, times, frequencies, *, gain_variance_ratio=1.0):
    training = np.asarray(training, dtype=complex)
    times = np.asarray(times, dtype=float)
    frequencies = np.asarray(frequencies, dtype=float)
    if (
        training.ndim != 2
        or times.shape != (len(training),)
        or frequencies.ndim != 1
        or len(frequencies) == 0
        or not np.all(np.isfinite(training))
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(frequencies))
        or gain_variance_ratio <= 0
        or not np.isfinite(gain_variance_ratio)
    ):
        raise ValueError("invalid pilot model inputs")
    variance = np.mean(np.abs(training) ** 2, axis=0)
    if np.any(variance <= 0) or not np.all(np.isfinite(variance)):
        raise ValueError("positive training power required for every tone")
    n, tones = training.shape
    kappa = gain_variance_ratio
    sums = np.exp(-2j * np.pi * frequencies[:, None] * times) @ training
    posterior_ratio = kappa / (1 + n * kappa)
    log_bf = -tones * np.log1p(n * kappa) + posterior_ratio * np.sum(
        np.abs(sums) ** 2 / variance, axis=1
    )
    evidence = logsumexp(log_bf) - np.log(len(frequencies))
    conditional_weights = np.exp(log_bf - logsumexp(log_bf))
    log_signal = evidence - np.logaddexp(0, evidence)
    log_null = -np.logaddexp(0, evidence)
    return {
        "frequencies": frequencies,
        "variance": variance,
        "mean": posterior_ratio * sums,
        "posterior_ratio": posterior_ratio,
        "log_bf": log_bf,
        "log_evidence_ratio": evidence,
        "weights": conditional_weights,
        "log_weights": log_bf - logsumexp(log_bf),
        "log_signal_probability": log_signal,
        "log_null_probability": log_null,
    }


def predict(model, held, times, *, include_null):
    held = np.asarray(held, dtype=complex)
    times = np.asarray(times, dtype=float)
    n, tones = held.shape
    if times.shape != (n,) or model["mean"].shape[1] != tones:
        raise ValueError("held pilot dimensions disagree")
    variance = model["variance"]
    sums = np.exp(-2j * np.pi * model["frequencies"][:, None] * times) @ held
    mean = model["mean"]
    ratio = model["posterior_ratio"]
    log_ratios = (
        -tones * np.log1p(n * ratio)
        + np.sum((2 * np.real(np.conj(mean) * sums) - n * np.abs(mean) ** 2) / variance, axis=1)
        + ratio / (1 + n * ratio) * np.sum(np.abs(sums - n * mean) ** 2 / variance, axis=1)
    )
    signal_ratio = logsumexp(model["log_weights"] + log_ratios)
    result = (
        np.logaddexp(model["log_null_probability"], model["log_signal_probability"] + signal_ratio)
        if include_null
        else signal_ratio
    )
    null_density = -n * np.log(np.pi * variance).sum() - np.sum(np.abs(held) ** 2 / variance)
    return {"log_density": float(null_density + result), "log_ratio_to_noise": float(result)}
