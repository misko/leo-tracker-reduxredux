"""Bounded two-variable Gauss–Newton with strictly contracting backtracking."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

STOP_KM = 0.020
TRIALS = 6
ARMIJO = 1e-4
MIN_DECREASE = 1e-9


def _step(normal, gradient, low, high):
    delta = np.linalg.solve(normal, -gradient)
    if np.all((low <= delta) & (delta <= high)):
        return delta
    best, cost = np.zeros(2), 0.0
    for fixed, free in ((0, 1), (1, 0)):
        for edge in (low[fixed], high[fixed]):
            delta[fixed] = edge
            delta[free] = np.clip(
                -(gradient[free] + normal[free, fixed] * edge) / normal[free, free],
                low[free],
                high[free],
            )
            value = delta @ (gradient + 0.5 * normal @ delta)
            if value < cost:
                best, cost = delta.copy(), value
    return best


def bounded_armijo(residual, initial, lower, upper, *, iterations=24, step=1e-3):
    x, lo, hi = (np.asarray(value, dtype=float) for value in (initial, lower, upper))
    if (
        any(v.shape != (2,) or not np.isfinite(v).all() for v in (x, lo, hi))
        or np.any(lo >= hi)
        or not np.isfinite(step)
        or step <= 0
        or iterations < 1
    ):
        raise ValueError("finite two-dimensional position and ordered bounds required")
    x = np.clip(x, lo, hi)
    r = residual(x)
    score = float(r @ r)
    history = [dict(parameters=x.copy(), score=score)]
    evaluations, jacobians, rejected = 1, 0, 0
    stopped = "iteration_budget"
    for _ in range(iterations):
        jacobian = np.empty((len(r), 2))
        for axis in range(2):
            nearby = x.copy()
            up, down = min(step, hi[axis] - x[axis]), min(step, x[axis] - lo[axis])
            nearby[axis] += up if up >= down else -down
            jacobian[:, axis] = (residual(nearby) - r) / (nearby[axis] - x[axis])
        evaluations += 2
        jacobians += 1
        normal, gradient = jacobian.T @ jacobian, jacobian.T @ r
        normal += 1e-8 * np.diag(np.maximum(np.diag(normal), 1e-6))
        delta = _step(normal, gradient, lo - x, hi - x)
        if np.linalg.norm(delta) <= STOP_KM:
            stopped = "small_bounded_step"
            break

        previous_size = np.inf
        for _trial in range(TRIALS):
            proposal = np.clip(x + delta, lo, hi)
            movement = proposal - x
            size = np.max(np.abs(movement))
            if not 0 < size < previous_size:
                stopped = "unrepresentable_armijo_step"
                break
            rr = residual(proposal)
            evaluations += 1
            candidate = float(rr @ rr)
            if candidate < score - MIN_DECREASE and candidate <= score + 2 * ARMIJO * (
                gradient @ movement
            ):
                x, r, score = proposal, rr, candidate
                history.append(dict(parameters=x.copy(), score=score))
                break
            previous_size = size
            delta *= 0.5
            rejected += 1
        else:
            stopped = "no_accepted_armijo_step"
        if stopped != "iteration_budget":
            break
    return dict(
        parameters=x,
        score=score,
        history=history,
        evaluations=evaluations,
        stopped=stopped,
        jacobian_refreshes=jacobians,
        rejected_trials=rejected,
    )


def worker(request, result, library):
    from leo.analysis.localization_v3 import position

    from tools.pipeline_eval.variants import v5_secant_fit

    with patch.object(position, "bounded_gauss_newton", bounded_armijo):
        v5_secant_fit.worker(request, result, library, "reference")


def run(case, work_dir):
    from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

    library = Path(work_dir) / "orbit_projector.so"
    library.parent.mkdir(parents=True, exist_ok=True)
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))
    result["boundary"] = v5_secant_fit.BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
