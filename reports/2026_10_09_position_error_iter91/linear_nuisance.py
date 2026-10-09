"""Bounded linear nuisance update for a frozen-responsibility Gaussian surrogate."""

import time

import numpy as np
from scipy.optimize import lsq_linear


def collapse_mixture(residual_hz, responsibilities, sigma_hz):
    """Collapse candidate rows for a receiver correction shared across candidates.

    Windings and responsibilities must already be frozen by the caller. The
    returned constant preserves the complete quadratic surrogate value.
    """
    residual = np.asarray(residual_hz, float)
    probability = np.asarray(responsibilities, float)
    if (
        residual.ndim != 2
        or probability.shape != residual.shape
        or not np.isfinite(residual).all()
        or not np.isfinite(probability).all()
        or np.any(probability < 0)
        or np.any(probability.sum(axis=1) > 1 + 1e-10)
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
    ):
        raise ValueError("invalid frozen mixture arrays or Gaussian width")
    mass = probability.sum(axis=1)
    target = np.divide(
        np.sum(probability * residual, axis=1),
        mass,
        out=np.zeros(len(mass)),
        where=mass > 0,
    )
    weight = mass / sigma_hz**2
    constant = 0.5 * np.sum(probability * residual**2) / sigma_hz**2
    constant -= 0.5 * np.dot(weight, target**2)
    return dict(residual_hz=target, weights=weight, constant=float(constant))


def receiver_clock_bounds(current, smooth_clock_count, arm, *, fixed_rf=False):
    """Physical B7 bounds; freeze every satellite coefficient at its current value."""
    current = np.asarray(current, float)
    if (
        current.ndim != 1
        or not np.isfinite(current).all()
        or not 0 <= smooth_clock_count <= len(current) - 2
        or arm not in ("fitted-c", "zero-c")
    ):
        raise ValueError("invalid existing-clock coefficient layout")
    lower, upper = current.copy(), current.copy()
    lower[:smooth_clock_count], upper[:smooth_clock_count] = -2000.0, 2000.0
    lower[-2:], upper[-2:] = (0.0, 0.0) if arm == "zero-c" or fixed_rf else (-1000.0, 1000.0)
    return lower, upper


def solve_nuisance_delta(
    design,
    residual_hz,
    weights,
    current,
    precision,
    lower,
    upper,
    *,
    prior_mean=None,
    constant=0.0,
    kkt_tolerance=1e-7,
    maximum_iterations=500,
):
    """Solve a convex bounded quadratic, with its prior on actual coefficients.

    Q(delta)=.5||sqrt(W)(A delta-r)||²
             +.5(current+delta-mean)'P(current+delta-mean)+constant.
    Equal lower/upper bounds lock coefficients exactly, including c0 RF terms.
    """
    begun = time.monotonic()
    design, residual = np.asarray(design, float), np.asarray(residual_hz, float)
    weights, current = np.asarray(weights, float), np.asarray(current, float)
    precision = np.asarray(precision, float)
    lower, upper = np.asarray(lower, float), np.asarray(upper, float)
    mean = np.zeros_like(current) if prior_mean is None else np.asarray(prior_mean, float)
    n = len(current) if current.ndim == 1 else -1
    arrays = (design, residual, weights, current, precision, lower, upper, mean)
    if (
        n <= 0
        or design.ndim != 2
        or design.shape[0] == 0
        or design.shape[1] != n
        or residual.shape != (len(design),)
        or weights.shape != residual.shape
        or precision.shape != (n, n)
        or any(x.shape != (n,) for x in (lower, upper, mean))
        or any(not np.isfinite(x).all() for x in arrays)
        or np.any(weights < 0)
        or np.any(lower > upper)
        or np.any(current < lower)
        or np.any(current > upper)
        or not np.isfinite(constant)
        or not np.isfinite(kkt_tolerance)
        or kkt_tolerance <= 0
        or maximum_iterations < 1
        or int(maximum_iterations) != maximum_iterations
    ):
        raise ValueError("invalid bounded quadratic inputs or infeasible current coefficients")
    scale = max(float(np.linalg.norm(precision, ord=2)), 1.0)
    if not np.allclose(precision, precision.T, atol=1e-12 * scale, rtol=0):
        raise ValueError("precision must be symmetric")
    precision = (precision + precision.T) / 2
    eigenvalues, eigenvectors = np.linalg.eigh(precision)
    tolerance = 64 * np.finfo(float).eps * n * scale
    if eigenvalues.min() < -tolerance:
        raise ValueError("precision must be positive semidefinite")
    positive = eigenvalues > 0
    root_precision = (
        np.sqrt(np.maximum(eigenvalues[positive], 0))[:, None] * eigenvectors[:, positive].T
    )
    # Tiny negative eigenvalues allowed by the roundoff tolerance are projected
    # to zero consistently in both the solved objective and its KKT check.
    precision = root_precision.T @ root_precision
    augmented = np.vstack([np.sqrt(weights)[:, None] * design, root_precision])
    target = np.r_[np.sqrt(weights) * residual, root_precision @ (mean - current)]
    free = lower < upper
    delta = np.zeros(n)
    # Locked coefficients equal their already-feasible current values.
    solver_status, solver_success, iterations = 0, True, 0
    if np.any(free):
        result = lsq_linear(
            augmented[:, free],
            target,
            bounds=(lower[free] - current[free], upper[free] - current[free]),
            method="bvls",
            tol=1e-12,
            max_iter=int(maximum_iterations),
        )
        delta[free] = result.x
        solver_status, solver_success, iterations = (
            int(result.status),
            bool(result.success),
            int(result.nit),
        )
    coefficients = current + delta
    gradient = design.T @ (weights * (design @ delta - residual)) + precision @ (
        coefficients - mean
    )
    projected_gradient = gradient.copy()
    projected_gradient[~free] = 0
    bound_tolerance = 1e-9 * np.maximum(1, np.maximum(np.abs(lower), np.abs(upper)))
    projected_gradient[(coefficients <= lower + bound_tolerance) & (gradient >= 0)] = 0
    projected_gradient[(coefficients >= upper - bound_tolerance) & (gradient <= 0)] = 0
    stationarity = float(np.max(np.abs(projected_gradient)))
    before = 0.5 * np.dot(weights, residual**2)
    before += 0.5 * (current - mean) @ precision @ (current - mean) + constant
    after = 0.5 * np.dot(weights, (design @ delta - residual) ** 2)
    after += 0.5 * (coefficients - mean) @ precision @ (coefficients - mean) + constant
    feasible = bool(
        np.all(coefficients >= lower - bound_tolerance)
        and np.all(coefficients <= upper + bound_tolerance)
    )
    return dict(
        coefficients=coefficients,
        delta=delta,
        gradient=gradient,
        projected_gradient=projected_gradient,
        stationarity=stationarity,
        qualified=feasible and stationarity <= kkt_tolerance and after <= before + 1e-8,
        objective_before=float(before),
        objective_after=float(after),
        data_rank=int(np.linalg.matrix_rank(np.sqrt(weights)[:, None] * design[:, free]))
        if np.any(free)
        else 0,
        regularized_rank=int(np.linalg.matrix_rank(augmented[:, free])) if np.any(free) else 0,
        free_dimensions=int(free.sum()),
        locked_dimensions=int((~free).sum()),
        active_lower=(coefficients <= lower + bound_tolerance) & free,
        active_upper=(coefficients >= upper - bound_tolerance) & free,
        solver_success=solver_success,
        solver_status=solver_status,
        iterations=iterations,
        elapsed_s=time.monotonic() - begun,
        dimensions=dict(observations=len(design), coefficients=n, augmented_rows=len(augmented)),
    )
