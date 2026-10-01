"""Exact conditional multivariate Student density in nested contrast coordinates."""
from math import lgamma, log, pi
import numpy as np


def log_student(residual, scale, degrees):
    residual, scale = np.asarray(residual), np.asarray(scale)
    d = len(residual)
    chol = np.linalg.cholesky(scale)
    whitened = np.linalg.solve(chol, residual)
    return float(lgamma((degrees+d)/2)-lgamma(degrees/2)-d/2*log(degrees*pi)
                 -np.log(np.diag(chol)).sum()-(degrees+d)/2*np.log1p(whitened@whitened/degrees))


def nested_transform(base_ids, dense_ids, base_contrasts, dense_contrasts):
    if len(set(base_ids)) != len(base_ids) or len(set(dense_ids)) != len(dense_ids):
        raise ValueError('Observation IDs must be unique')
    if not set(base_ids) <= set(dense_ids) or not base_ids:
        raise ValueError('Dense evidence must contain baseline evidence')
    base_contrasts, dense_contrasts = np.asarray(base_contrasts), np.asarray(dense_contrasts)
    if base_contrasts.shape != (len(base_ids)-1, len(base_ids)) or dense_contrasts.shape != (len(dense_ids)-1, len(dense_ids)):
        raise ValueError('Expected one removed constant offset per track')
    positions = {identifier: i for i, identifier in enumerate(dense_ids)}
    old = [positions[i] for i in base_ids]
    added = [i for i, identifier in enumerate(dense_ids) if identifier not in set(base_ids)]
    if not added:
        raise ValueError('No added observations')
    combined = np.zeros((len(dense_ids)-1, len(dense_ids)))
    combined[:len(base_ids)-1, old] = base_contrasts
    for row, index in enumerate(added, start=len(base_ids)-1):
        combined[row, index] = 1.
        combined[row, old[0]] = -1.
    transform = np.linalg.solve(dense_contrasts@dense_contrasts.T,
                                dense_contrasts@combined.T).T
    if not np.allclose(transform@dense_contrasts, combined, rtol=0, atol=1e-10):
        raise ValueError('Contrast spaces do not match')
    np.linalg.cholesky(transform@transform.T)
    return transform, np.asarray(added)


def conditional_student(residual, scale, original_dimension, degrees=4.):
    residual, scale = np.asarray(residual), np.asarray(scale)
    p = original_dimension
    if not 0 < p < len(residual) or scale.shape != (len(residual), len(residual)) or degrees <= 0:
        raise ValueError('Invalid conditional dimensions/degrees')
    a, b, c = scale[:p, :p], scale[p:, :p], scale[p:, p:]
    solved = np.linalg.solve(a, residual[:p])
    quadratic = float(residual[:p]@solved)
    innovation = residual[p:]-b@solved
    schur = c-b@np.linalg.solve(a, b.T)
    schur = (schur+schur.T)/2
    conditional_degrees = degrees+p
    conditional_scale = (degrees+quadratic)/conditional_degrees*schur
    density = log_student(innovation, conditional_scale, conditional_degrees)
    ratio = log_student(residual, scale, degrees)-log_student(residual[:p], a, degrees)
    return dict(innovation=innovation, scale=conditional_scale, degrees=conditional_degrees,
                log_density=density, log_ratio=ratio, original_quadratic=quadratic)
