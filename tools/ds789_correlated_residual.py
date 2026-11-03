"""Fixed-offset multivariate-t covariance scores for a bounded model shadow."""

import math

import numpy as np


def kernel(times, decay_s, nugget=0.2):
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or not len(times) or not np.isfinite(times).all():
        raise ValueError("finite nonempty time vector required")
    if decay_s < 0 or not 0 < nugget <= 1:
        raise ValueError("invalid covariance parameters")
    if decay_s == 0:
        return np.eye(len(times))
    return (1 - nugget) * np.exp(-abs(times[:, None] - times[None, :]) / decay_s) + nugget * np.eye(
        len(times)
    )


def quadratic(residual, covariance):
    residual = np.asarray(residual, dtype=float)
    chol = np.linalg.cholesky(covariance)
    whitened = np.linalg.solve(chol, residual.T)
    return (whitened**2).sum(axis=0), float(2 * np.log(np.diag(chol)).sum())


def multivariate_t(q, logdet, count, scale, df=4):
    if scale <= 0 or df <= 0 or count < 1:
        raise ValueError("positive scale, degrees of freedom and count required")
    return (
        math.lgamma((df + count) / 2)
        - math.lgamma(df / 2)
        - count / 2 * math.log(df * math.pi)
        - count * math.log(scale)
        - logdet / 2
        - (df + count) / 2 * np.log1p(np.asarray(q) / (df * scale**2))
    )


def independent_t(residual, scale):
    r = np.asarray(residual)
    return (
        math.lgamma(2.5)
        - math.lgamma(2)
        - 0.5 * math.log(4 * math.pi)
        - math.log(scale)
        - 2.5 * np.log1p((r / scale) ** 2 / 4)
    ).sum(axis=-1)
