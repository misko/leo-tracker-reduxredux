"""Test local offered-square containment under whole-orbit deletion."""

from collections import defaultdict

import numpy as np
from scipy.optimize import lsq_linear

try:
    from leo.analysis.localization_deletion_spread import deletion_spread
except ModuleNotFoundError:
    # The sealed deployment mounts the same helper alongside this variant.
    from .localization_deletion_spread import deletion_spread

METHOD = "native_smooth_orbit_influence"
BOUNDARY = "Complete native GLRT smooth fit filtered by whole-orbit local sensitivity"
CHI2_95_DF2 = 5.991464547107979


def _solve(normal, response, bounds):
    factor = np.linalg.cholesky(normal).T
    right = np.linalg.solve(factor.T, response)
    unconstrained = np.linalg.solve(factor, right)
    if np.all(unconstrained >= bounds[0]) and np.all(unconstrained <= bounds[1]):
        return unconstrained
    fit = lsq_linear(factor, right, bounds=bounds, method="bvls", max_iter=30)
    if not fit.success or not np.all(np.isfinite(fit.x)):
        raise ValueError("orbit-deletion bounded normal solve did not converge")
    return fit.x


def normal_deletions(matrix, response, labels, fit_bounds):
    """Delete each observation block while retaining the one common prior block."""
    matrix, response = np.asarray(matrix), np.asarray(response)
    n = len(labels)
    lower, upper = (np.array(limit, copy=True) for limit in fit_bounds)
    lower[:2], upper[:2] = -np.inf, np.inf
    bounds = lower, upper
    normal, rhs = matrix.T @ matrix, matrix.T @ response
    full = _solve(normal, rhs, bounds)[:2]
    covariance = np.linalg.solve(normal, np.eye(len(normal), 2))[:2]
    covariance = (covariance + covariance.T) / 2
    clusters = defaultdict(list)
    for index, label in enumerate(labels):
        clusters[label].append(index)
    if len(clusters) < 2 or n >= len(matrix):
        raise ValueError("whole-orbit influence needs independently assigned orbits and priors")
    shifts = {}
    for orbit, index in sorted(clusters.items()):
        x, y = matrix[index], response[index]
        shifts[orbit] = _solve(normal - x.T @ x, rhs - x.T @ y, bounds)[:2] - full
    return full, covariance, shifts


def containment(point, half, covariance, shifts):
    """The ellipse and every observed deletion point must lie in the offered square."""
    shifts = np.asarray(shifts, dtype=float)
    scatter = deletion_spread(shifts)
    combined = covariance + scatter
    axes = np.sqrt(CHI2_95_DF2 * np.diag(combined))
    ordinary = float(np.min(half - np.abs(point)))
    ellipse = float(np.min(half - np.abs(point) - axes))
    deleted = float(np.min(half - np.abs(point + shifts)))
    return dict(
        admitted=bool(min(ordinary, ellipse, deleted) > 0),
        ordinary_margin_km=ordinary,
        ellipse_margin_km=ellipse,
        deletion_margin_km=deleted,
        local_profile_covariance_km2=covariance.tolist(),
        deletion_covariance_km2=scatter.tolist(),
        nominal_projection_halfwidths_km=axes.tolist(),
        max_deletion_shift_km=float(np.max(np.linalg.norm(shifts, axis=1))),
    )
