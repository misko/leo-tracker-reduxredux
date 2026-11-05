"""Owned causal residual recovery mathematics extracted from the frozen policy."""

import numpy as np
from scipy.special import logsumexp


def age_penalty(age_h, half_life_h=24.0):
    """-2 log relative prior weight; odds halve per day beyond the old cutoff."""
    if not np.isfinite(age_h) or age_h < 0 or not np.isfinite(half_life_h) or half_life_h <= 0:
        raise ValueError("Finite nonnegative age and positive half-life required")
    return 2 * np.log(2) * max(0.0, age_h - 48.0) / half_life_h


def phase_prior(phases, sigma):
    phases = np.asarray(phases, float)
    if (
        sigma <= 0
        or not np.isfinite(sigma)
        or len(phases) < 3
        or not np.allclose(np.diff(phases), np.diff(phases)[0])
    ):
        raise ValueError("Positive scale and regular phase grid required")
    logp = -0.5 * (phases / sigma) ** 2 - np.log(sigma * np.sqrt(2 * np.pi))
    logp[[0, -1]] -= np.log(2)  # Trapezoidal endpoint weights.
    return logp - logsumexp(logp)


def components(
    y,
    predictions,
    visible,
    times,
    aliases,
    period,
    mask=None,
    noise_hz=150.0,
    bias_hz=300.0,
    rate_hz_s=0.5,
):
    y, predictions, times = (
        np.asarray(y, float),
        np.asarray(predictions, float),
        np.asarray(times, float),
    )
    if (
        y.ndim != 1
        or predictions.ndim != 2
        or predictions.shape[1:] != y.shape
        or times.shape != y.shape
    ):
        raise ValueError("Matching phase-by-native-point geometry required")
    if (
        not all(np.isfinite(z).all() for z in (y, predictions, times))
        or min(noise_hz, bias_hz, rate_hz_s) <= 0
    ):
        raise ValueError("Finite data and positive scales required")
    mask = np.ones(len(y), bool) if mask is None else np.asarray(mask, bool)
    if mask.shape != y.shape or mask.sum() < 3:
        raise ValueError("At least three selected native points required")
    x = np.column_stack([np.ones(len(y)), times - times.mean()])
    prior = np.diag([bias_hz**2, rate_hz_s**2])
    precision = np.linalg.inv(prior) + x[mask].T @ x[mask] / noise_hz**2
    covariance = np.linalg.inv(precision)
    raw = y[None, None, :] + np.asarray(aliases)[:, None, None] * period - predictions[None, :, :]
    selected = raw[:, :, mask]
    rhs = selected @ x[mask] / noise_hz**2
    beta = rhs @ covariance
    quadratic = np.sum(selected**2, axis=-1) / noise_hz**2 - np.sum(rhs * beta, axis=-1)
    logdet = (
        mask.sum() * np.log(noise_hz**2)
        + np.linalg.slogdet(prior)[1]
        + np.linalg.slogdet(precision)[1]
    )
    loglik = -0.5 * (quadratic + logdet + mask.sum() * np.log(2 * np.pi))
    loglik = np.where(np.asarray(visible)[None, :], loglik, -np.inf)
    return dict(
        loglik=loglik,
        beta=beta,
        design=x,
        coefficient_covariance=covariance,
        quadratic=quadratic,
        logdet=float(logdet),
        raw=raw,
    )


def marginal(component, phases, sigma):
    logphase = phase_prior(phases, sigma)
    joint = component["loglik"] + logphase[None, :] - np.log(component["loglik"].shape[0])
    logz = float(logsumexp(joint))
    weights = np.exp(joint - logz) if np.isfinite(logz) else np.zeros_like(joint)
    alias, k = np.unravel_index(np.argmax(joint), joint.shape)
    residual = component["raw"][alias, k] - component["design"] @ component["beta"][alias, k]
    return dict(
        score=-2 * logz,
        weights=weights,
        alias_index=int(alias),
        phase_index=int(k),
        beta=component["beta"][alias, k],
        residual=residual,
        rms_hz=float(np.sqrt(np.mean(residual**2))),
        phase_s=float(phases[k]),
        phase_mean_s=float(weights.sum(axis=0) @ phases),
        phase_boundary_mass=float(weights[:, abs(phases) >= max(abs(phases)) - 0.1].sum()),
        maximum_component_score=float(-2 * np.max(component["loglik"])),
        integration_penalty=float(-2 * logz + 2 * np.max(component["loglik"])),
    )
