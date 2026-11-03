"""Bounded BFGS with a fixed-metric stationarity check for mixed physical units."""
import time
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class JointSearchResult:
    mean: np.ndarray
    objectives: tuple[float, ...]
    converged: bool
    reason: str
    iterations: int
    decrement_squared: float


def fit_joint_objective(initial, value_gradient, information, support, *, deadline,
                        max_iterations=64, decrement_tolerance=1e-6, max_metric_step=10.):
    """Use BFGS for descent; use the original SPD metric to certify stationarity.

    The initial information matrix supplies physical scaling only, not a
    calibrated covariance. Inverse-BFGS collapse cannot itself trigger success.
    Domain support and Armijo descent are checked for every accepted step.
    """
    x = np.asarray(initial, dtype=float).copy()
    metric = np.asarray(information, dtype=float)
    if (x.ndim != 1 or metric.shape != (x.size, x.size)
            or not np.all(np.isfinite(x)) or not np.all(np.isfinite(metric))
            or not np.allclose(metric, metric.T) or not support(x)
            or max_iterations < 1 or not np.isfinite(decrement_tolerance)
            or not np.isfinite(max_metric_step)
            or decrement_tolerance <= 0 or max_metric_step <= 0
            or not np.isfinite(deadline)):
        raise ValueError('invalid joint search inputs')
    np.linalg.cholesky(metric)
    initial_inverse = np.linalg.solve(metric, np.eye(len(x)))
    inverse = initial_inverse.copy()
    history, reason, converged, iterations = [], 'iteration_limit', False, 0
    decrement = np.inf

    def evaluate(point):
        if time.monotonic() >= deadline:
            raise TimeoutError('joint objective deadline')
        value, gradient = value_gradient(point)
        gradient = np.asarray(gradient, dtype=float)
        if (gradient.shape != x.shape or not np.all(np.isfinite(gradient))
                or np.isnan(value) or np.isneginf(value)):
            raise ValueError('invalid objective gradient')
        return float(value), gradient

    try:
        value, gradient = evaluate(x)
        if not np.isfinite(value):
            raise ValueError('initial objective must be finite')
        history.append(value)
        for iteration in range(max_iterations):
            iterations = iteration+1
            decrement = float(gradient@initial_inverse@gradient)
            if decrement <= decrement_tolerance:
                reason, converged = 'scaled_stationary', True
                break
            direction = -inverse@gradient
            if gradient@direction >= 0:
                inverse = initial_inverse.copy()
                direction = -inverse@gradient
            norm = float(np.sqrt(max(0., direction@metric@direction)))
            direction *= min(1., max_metric_step/max(norm, 1e-30))
            for backtrack in range(20):
                step = direction*(.5**backtrack)
                trial = x+step
                if not support(trial):
                    continue
                trial_value, trial_gradient = evaluate(trial)
                if trial_value <= value+1e-4*float(gradient@step):
                    break
            else:
                reason = 'no_descent'
                break
            change = trial_gradient-gradient
            curvature = float(change@step)
            if curvature > 1e-10*np.linalg.norm(change)*np.linalg.norm(step):
                rho = 1./curvature
                transform = np.eye(len(x))-rho*np.outer(step, change)
                inverse = transform@inverse@transform.T+rho*np.outer(step, step)
                inverse = (inverse+inverse.T)*.5
            x, value, gradient = trial, trial_value, trial_gradient
            history.append(value)
    except TimeoutError:
        reason = 'wall_budget'
    return JointSearchResult(x, tuple(history), converged, reason, iterations, decrement)
