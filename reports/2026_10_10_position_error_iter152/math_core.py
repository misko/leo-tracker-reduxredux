"""Analytic finite Gaussian-mixture identities only; no recording/model adapter."""

import numpy as np
from scipy.special import logsumexp


def observed_block(b, measured, means, design, masses, clutter_density, sigma, precision):
    """Return NLL, gradient, observed Hessian, and complete-component curvature.

    Gaussian means are means[n,k] + design[n,k,:] @ b. Masses are fixed
    nonnegative component weights; clutter_density already includes its mass.
    A wrapped likelihood can expand satellite/winding components explicitly.
    This function does not approximate geometry-dependent detection terms.
    """
    b, measured, means, design, masses, precision = map(
        lambda value: np.asarray(value, float),
        (b, measured, means, design, masses, precision),
    )
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("positive finite sigma required")
    n, k = means.shape
    d = len(b)
    clutter = np.broadcast_to(np.asarray(clutter_density, float), (n,))
    if (measured.shape != (n,) or design.shape != (n, k, d)
            or masses.shape != (n, k) or precision.shape != (d, d)):
        raise ValueError("incompatible dimensions")
    if not all(np.isfinite(a).all() for a in (b, measured, means, design, masses, precision, clutter)):
        raise ValueError("nonfinite input")
    if np.any(masses < 0) or np.any(clutter < 0):
        raise ValueError("negative mixture mass/density")
    if not np.allclose(precision, precision.T, rtol=0, atol=1e-12):
        raise ValueError("symmetric precision required")
    np.linalg.cholesky(precision)  # No arbitrary ridge or pseudodeterminant.
    residual = measured[:, None] - means - np.einsum("nkd,d->nk", design, b)
    with np.errstate(divide="ignore"):
        log_gaussian = np.log(masses) - np.log(sigma * np.sqrt(2 * np.pi))
        log_gaussian -= 0.5 * (residual / sigma) ** 2
        log_components = np.column_stack([log_gaussian, np.log(clutter)])
    log_density = logsumexp(log_components, axis=1)
    if not np.isfinite(log_density).all():
        raise ValueError("zero/nonfinite mixture density")
    responsibilities = np.exp(log_gaussian - log_density[:, None])
    component_score = residual[:, :, None] * design / sigma**2
    expected_score = np.einsum("nk,nkd->nd", responsibilities, component_score)
    complete = np.einsum("nk,nkd,nke->de", responsibilities, design, design) / sigma**2
    covariance = np.einsum(
        "nk,nkd,nke->de", responsibilities, component_score, component_score
    ) - expected_score.T @ expected_score
    value = -log_density.sum() + 0.5 * b @ precision @ b
    return dict(
        value=float(value), gradient=-expected_score.sum(axis=0) + precision @ b,
        hessian=complete - covariance + precision,
        complete_curvature=complete, responsibility_covariance=covariance,
    )


def interior_laplace(map_value, hessian, precision):
    """Normalized proper-block correction; interior, unimodal approximation only."""
    matrices = [np.asarray(a, float) for a in (hessian, precision)]
    logs = []
    for matrix in matrices:
        if not np.isfinite(matrix).all() or not np.allclose(matrix, matrix.T, rtol=0, atol=1e-12):
            raise ValueError("finite symmetric curvature required")
        factor = np.linalg.cholesky(matrix)
        logs.append(2 * np.log(np.diag(factor)).sum())
    return float(map_value + 0.5 * (logs[0] - logs[1]))


def amplitude_interval(direction, remaining, bound=2000.0):
    """Exact intersection preserving original coefficient boxes, not a new prior."""
    direction, remaining = np.asarray(direction, float), np.asarray(remaining, float)
    if direction.shape != remaining.shape or not np.isfinite(direction).all() or not np.isfinite(remaining).all():
        raise ValueError("invalid slice")
    if not np.isfinite(bound) or bound <= 0 or not np.any(direction):
        raise ValueError("invalid bound/direction")
    lower, upper = -np.inf, np.inf
    for q, r in zip(direction, remaining, strict=True):
        if q == 0:
            if abs(r) > bound:
                raise ValueError("empty coefficient slice")
            continue
        a, b = (-bound-r)/q, (bound-r)/q
        lower, upper = max(lower, min(a, b)), min(upper, max(a, b))
    if not lower < upper:
        raise ValueError("empty or zero-measure coefficient slice")
    return float(lower), float(upper)
