"""Five-refresh compact v5 position optimizer, without the evaluation worker."""

import numpy as np

STOP_KM = 0.020
TRIALS = 3
SECANT_LIMIT = 4
INITIAL_RADIUS_KM = 5.0
MAX_RADIUS_KM = 10.0
MIN_DECREASE = 1e-9


def _forward_points(x, lo, hi, step):
    for axis in range(2):
        up, down = hi[axis] - x[axis], x[axis] - lo[axis]
        signed = min(step, up) if up >= step or up >= down else -min(step, down)
        nearby = x.copy()
        nearby[axis] += signed
        yield axis, nearby, nearby[axis] - x[axis]


def _box_step(normal, gradient, lower, upper):
    """Minimize the regularized two-dimensional quadratic on a box containing zero."""
    delta = np.linalg.solve(normal, -gradient)
    if np.all((delta >= lower) & (delta <= upper)):
        return delta
    best, best_cost = np.zeros(2), 0.0
    for fixed in range(2):
        free = 1 - fixed
        for bound in (lower[fixed], upper[fixed]):
            delta = np.empty(2)
            delta[fixed] = bound
            delta[free] = np.clip(
                -(gradient[free] + normal[free, fixed] * bound) / normal[free, free],
                lower[free],
                upper[free],
            )
            cost = delta @ (gradient + 0.5 * normal @ delta)
            if cost < best_cost:
                best, best_cost = delta, cost
    return best


def bounded_secant(residual, initial, lower, upper, *, iterations=24, step=1e-3):
    """Preserve the stock objective and fit history in a km-scaled two-dimensional box."""
    x, lo, hi = (np.asarray(a, dtype=float) for a in (initial, lower, upper))
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
    evaluations, refreshes, total_updates, rejected = 1, 0, 0, 0
    jacobian, updates = None, 0
    radius, stopped = INITIAL_RADIUS_KM, "iteration_budget"

    def linearize():
        nonlocal evaluations, refreshes
        columns = [
            (residual(nearby) - r) / delta for _, nearby, delta in _forward_points(x, lo, hi, step)
        ]
        evaluations += 2
        refreshes += 1
        return np.column_stack(columns)

    def system(jacobian):
        normal = jacobian.T @ jacobian
        normal += 1e-8 * np.diag(np.maximum(np.diag(normal), 1e-6))
        return normal, jacobian.T @ r

    for _ in range(iterations):
        fresh = jacobian is None
        if fresh:
            jacobian, updates = linearize(), 0
        normal, gradient = system(jacobian)
        full = _box_step(normal, gradient, lo - x, hi - x)
        if np.linalg.norm(full) <= STOP_KM and not fresh:
            jacobian, updates, fresh = linearize(), 0, True
            normal, gradient = system(jacobian)
            full = _box_step(normal, gradient, lo - x, hi - x)
        if np.linalg.norm(full) <= STOP_KM:
            stopped = "small_bounded_step"
            break

        for _trial in range(TRIALS):
            delta = _box_step(
                normal, gradient, np.maximum(lo - x, -radius), np.minimum(hi - x, radius)
            )
            proposal = np.clip(x + delta, lo, hi)
            delta = proposal - x
            predicted_residual = r + jacobian @ delta
            predicted = score - float(predicted_residual @ predicted_residual)
            rr = residual(proposal)
            evaluations += 1
            candidate = float(rr @ rr)
            if not candidate < score - MIN_DECREASE:
                rejected += 1
                radius *= 0.5
                continue

            ratio = (score - candidate) / predicted if predicted > 0 else 0.0
            if ratio < 0.25:
                radius *= 0.5
                jacobian = None
            else:
                if ratio > 0.75 and np.max(np.abs(delta)) >= 0.8 * radius:
                    radius = min(MAX_RADIUS_KM, 2 * radius)
                jacobian += np.outer(rr - predicted_residual, delta) / (delta @ delta)
                updates += 1
                total_updates += 1
                if updates == SECANT_LIMIT:
                    jacobian = None
            x, r, score = proposal, rr, candidate
            history.append(dict(parameters=x.copy(), score=score))
            break
        else:
            if fresh:
                stopped = "no_accepted_trust_step"
                break
            jacobian = None
    return dict(
        parameters=x,
        score=score,
        history=history,
        evaluations=evaluations,
        stopped=stopped,
        jacobian_refreshes=refreshes,
        secant_updates=total_updates,
        rejected_trials=rejected,
    )
