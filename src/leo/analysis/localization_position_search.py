"""Bounded two-coordinate search for expensive marginalized location objectives."""
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PositionSearchResult:
    position: np.ndarray
    objectives: tuple[float, ...]
    converged: bool
    reason: str
    iterations: int


def fit_position_objective(
    initial: np.ndarray,
    objective: Callable[[np.ndarray], float],
    support: Callable[[np.ndarray], bool],
    *,
    deadline: float,
    max_iterations: int = 16,
    difference_step: float = .05,
    max_step: float = 10.,
    decrement_tolerance: float = 1e-6,
) -> PositionSearchResult:
    """Finite-difference Newton search with damping and checked descent.

    Coordinates are east/north kilometres. Finite differences include changes
    in covariance normalization, unlike a residual-only Gauss--Newton step.
    A positive Hessian and small quadratic decrement are required for success.
    This finds one local mode; it does not explore associations or certify a
    global optimum. Each objective evaluation must itself be bounded.
    """
    x = np.array(initial, dtype=float, copy=True)
    if (x.shape != (2,) or not np.all(np.isfinite(x)) or not support(x)
            or max_iterations < 1 or not np.isfinite(deadline)
            or any(not np.isfinite(v) or v <= 0 for v in
                   (difference_step, max_step, decrement_tolerance))):
        raise ValueError('invalid position search configuration')
    history = []
    reason, converged, iterations = 'iteration_limit', False, 0

    def evaluate(point):
        if time.monotonic() >= deadline:
            raise TimeoutError('position search deadline')
        if not support(point):
            return np.inf
        value = float(objective(point))
        if np.isnan(value) or np.isneginf(value):
            raise ValueError('invalid position objective')
        return value

    try:
        value = evaluate(x)
        if not np.isfinite(value):
            raise ValueError('initial position objective must be finite')
        history.append(value)
        for iteration in range(max_iterations):
            iterations = iteration+1
            h = difference_step
            basis = np.eye(2)*h
            plus = np.array([evaluate(x+d) for d in basis])
            minus = np.array([evaluate(x-d) for d in basis])
            corners = [evaluate(x+a*basis[0]+b*basis[1])
                       for a, b in [(1, 1), (1, -1), (-1, 1), (-1, -1)]]
            if not np.all(np.isfinite([*plus, *minus, *corners])):
                reason = 'infeasible_stencil'
                break
            gradient = (plus-minus)/(2*h)
            hessian = np.diag((plus+minus-2*value)/h**2)
            hessian[0, 1] = hessian[1, 0] = (
                corners[0]-corners[1]-corners[2]+corners[3])/(4*h**2)
            eigenvalues = np.linalg.eigvalsh(hessian)
            damped = hessian+np.eye(2)*max(0., 1e-6-eigenvalues[0])
            step = -np.linalg.solve(damped, gradient)
            decrement = float(-gradient@step)
            if eigenvalues[0] > 0 and decrement <= decrement_tolerance:
                reason, converged = 'scaled_stationary', True
                break
            step *= min(1., max_step/max(np.linalg.norm(step), 1e-30))
            for backtrack in range(10):
                trial = x+step*(.5**backtrack)
                trial_value = evaluate(trial)
                if trial_value < value:
                    x, value = trial, trial_value
                    history.append(value)
                    break
            else:
                reason = 'no_descent'
                break
    except TimeoutError:
        reason = 'wall_budget'
    return PositionSearchResult(x, tuple(history), converged, reason, iterations)
