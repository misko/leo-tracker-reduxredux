"""Conditional Doppler information and training-only nuisance projection.

No orbit, storage, or acquisition dependencies. Bounds assume the supplied
Jacobian and white Gaussian errors are correct; they are not absolute accuracy.
"""

import numpy as np


def profile(value, group, training, time=None):
    """Remove each group's fitted constant, optionally its unconstrained drift.

    Fits use training rows exclusively and apply unchanged to evaluation rows.
    Matrices project each column using the same nuisance design.
    """
    value = np.asarray(value, float)
    group, training = np.asarray(group), np.asarray(training, bool)
    if value.shape[0] != len(group) or group.shape != training.shape:
        raise ValueError("incompatible nuisance arrays")
    if not np.all(np.isfinite(value)):
        raise ValueError("finite values required")
    _, g = np.unique(group, return_inverse=True)
    count = np.bincount(g[training], minlength=g.max() + 1)
    if np.any(count == 0):
        raise ValueError("each group needs training observations")
    matrix = value[:, None] if value.ndim == 1 else value
    mean = np.stack(
        [np.bincount(g[training], weights=c[training]) / count for c in matrix.T], axis=1
    )
    result = matrix - mean[g]
    if time is not None:
        t = np.asarray(time, float)
        t = t - (np.bincount(g[training], weights=t[training]) / count)[g]
        denom = np.bincount(g[training], weights=t[training] ** 2)
        if np.any(denom <= 0):
            raise ValueError("drift needs distinct training times")
        slope = np.stack(
            [np.bincount(g[training], weights=t[training] * c[training]) / denom for c in result.T],
            axis=1,
        )
        result -= t[:, None] * slope[g]
    return result[:, 0] if value.ndim == 1 else result


def information(jacobian_hz_per_km, sigma_hz):
    """Gaussian local bound after nuisance projection; singular means unbounded."""
    j = np.asarray(jacobian_hz_per_km, float)
    if j.ndim != 2 or not np.all(np.isfinite(j)) or sigma_hz <= 0:
        raise ValueError("finite Jacobian and positive noise required")
    normal = j.T @ j / sigma_hz**2
    rank = int(np.linalg.matrix_rank(normal))
    result = {
        "rank": rank,
        "parameters": j.shape[1],
        "sigma_hz": float(sigma_hz),
        "covariance_m2": None,
        "horizontal_rms_m": None,
        "major_95_m": None,
    }
    if rank == j.shape[1]:
        covariance = np.linalg.inv(normal) * 1e6
        result.update(
            covariance_m2=covariance.tolist(),
            horizontal_rms_m=float(np.sqrt(np.trace(covariance[:2, :2]))),
            major_95_m=float(np.sqrt(5.991464547 * np.linalg.eigvalsh(covariance[:2, :2])[-1])),
        )
    return result


def nuisance_project(jacobian, nuisance):
    """Remove sensitivities reproducible by free nuisance parameters.

    Inputs must already be whitened using the same observation noise model.
    Call with fitting rows only when estimating fitting-data information.
    Column normalization makes the rank decision independent of parameter units.
    """
    j, a = np.asarray(jacobian, float), np.asarray(nuisance, float)
    if j.ndim != 2 or a.ndim != 2 or len(j) != len(a):
        raise ValueError("compatible two-dimensional Jacobians required")
    if not np.all(np.isfinite(j)) or not np.all(np.isfinite(a)):
        raise ValueError("finite Jacobians required")
    scale = np.linalg.norm(a, axis=0)
    a = a[:, scale > 0] / scale[scale > 0]
    if not a.shape[1]:
        return j.copy()
    return j - a @ np.linalg.lstsq(a, j, rcond=None)[0]


def profile_shared_drift(value, segment, session, training, time):
    """Segment offsets plus one source-balanced linear drift per session."""
    residual = profile(value, segment, training)
    t = profile(time, segment, training)
    _, g = np.unique(segment, return_inverse=True)
    _, s = np.unique(session, return_inverse=True)
    counts = np.bincount(g[training])
    weight = 1 / counts[g]
    denom = np.bincount(s[training], weights=weight[training] * t[training] ** 2)
    if np.any(denom <= 0):
        raise ValueError("shared drift needs distinct training times")
    slope = (
        np.bincount(s[training], weights=weight[training] * t[training] * residual[training])
        / denom
    )
    return residual - t * slope[s]
