"""Explicit whole-curve Gaussian likelihoods for bounded retention experiments."""

import numpy as np

PERIOD = 1 / 4.4e-6
NOISE = 150.0
BIAS = 1000.0


def whitening(times, *, correlated_sigma_hz=0.0, correlation_seconds=10.0):
    """Return inverse Cholesky and covariance log-volume relative to white noise."""
    t = np.asarray(times, float)
    if t.ndim != 1 or not len(t) or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("finite strictly increasing times required")
    if correlated_sigma_hz < 0 or correlation_seconds <= 0:
        raise ValueError("nonnegative correlated scale and positive correlation time required")
    if correlated_sigma_hz == 0:
        return np.eye(len(t)) / NOISE, 0.0
    covariance = np.eye(len(t)) * NOISE**2
    covariance += correlated_sigma_hz**2 * np.exp(-abs(t[:, None] - t) / correlation_seconds)
    lower = np.linalg.cholesky(covariance)
    inverse = np.linalg.solve(lower, np.eye(len(t)))
    logvolume = 2 * np.log(np.diag(lower) / NOISE).sum()
    return inverse, float(logvolume)


def profile(observed, predicted, inverse, logvolume=0.0):
    """One native alias and Gaussian constant per curve; retain every observation."""
    y, f, w = np.asarray(observed), np.atleast_2d(predicted), np.asarray(inverse)
    if y.ndim != 1 or f.shape[1] != len(y) or w.shape != (len(y), len(y)):
        raise ValueError("matching observations, predictions and whitening matrix required")
    raw = y - f
    alias = np.rint(-raw.mean(axis=1) / PERIOD)
    raw += alias[:, None] * PERIOD
    if np.count_nonzero(w) == len(y):
        diagonal = np.diag(w)
        z, one = raw * diagonal, diagonal
    else:
        z = raw @ w.T
        one = w @ np.ones(len(y))
    information = one @ one
    bias = z @ one / (information + 1 / BIAS**2)
    innovations = z - bias[:, None] * one
    residual = raw - bias[:, None]
    cost = np.sum(innovations**2, axis=1) + (bias / BIAS) ** 2
    cost += logvolume + np.log1p(BIAS**2 * information)
    return dict(
        alias=alias,
        bias=bias,
        residual=residual,
        innovations=NOISE * innovations,
        rms=np.sqrt(np.mean(residual**2, axis=1)),
        cost=cost,
    )


def add_curve(normal, rhs, design, values, inverse, weight=1.0):
    """Eliminate one Gaussian curve constant; add a weighted dense normal block."""
    x, y = inverse @ design, inverse @ values
    one = inverse @ np.ones(len(values))
    cross = x.T @ one
    denominator = one @ one + 1 / BIAS**2
    normal += weight * (x.T @ x - np.outer(cross, cross) / denominator)
    rhs += weight * (x.T @ y - cross * (one @ y) / denominator)


def projected_receiver_basis(times, *, spacing_s=30.0, width_s=20.0):
    """Smooth scan-wide columns with no constant or linear component on [0,300]."""
    t = np.asarray(times, float)
    grid = np.linspace(0, 300, 301)
    centers = np.arange(0, 300.001, spacing_s)
    raw = np.exp(-0.5 * ((t[:, None] - centers) / width_s) ** 2)
    reference = np.exp(-0.5 * ((grid[:, None] - centers) / width_s) ** 2)
    affine = np.column_stack((np.ones(len(grid)), (grid - 150) / 150))
    coefficients = np.linalg.lstsq(affine, reference, rcond=None)[0]
    return raw - np.column_stack((np.ones(len(t)), (t - 150) / 150)) @ coefficients
