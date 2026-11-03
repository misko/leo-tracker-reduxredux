"""One bounded L-BFGS-B numerical continuation from an unchanged raw endpoint."""

import math
import time

import numpy as np
from scipy.optimize import minimize


def solve(evaluate, initial, lower, upper, feasible, *, maximum=134, seconds=78,
          expected_objective=None):
    """Never evaluate invalid physical points; cache best feasible actual state."""
    if (type(maximum) is not int or not 1 <= maximum <= 134
            or not math.isfinite(seconds) or not 0 < seconds <= 78):
        raise ValueError('bounded <=134 evaluations / <=78 seconds required')
    initial = np.asarray(initial, float)
    if not feasible(initial):
        raise ValueError('raw endpoint must be feasible')
    begun = time.monotonic()
    calls, attempts, invalid = 0, 0, 0
    best = None

    class Exhausted(Exception):
        pass

    def objective(point):
        nonlocal calls, attempts, invalid, best
        if attempts >= maximum or calls >= maximum or time.monotonic()-begun >= seconds:
            raise Exhausted
        attempts += 1
        if not feasible(point):
            invalid += 1
            # Only an infeasible extension to guide the line search back to
            # the source. This is never a model score or eligible endpoint.
            offset = point-initial
            return best[0]+1+1e6*float(offset@offset), 2e6*offset
        calls += 1
        value, gradient = evaluate(point)
        value, gradient = float(value), np.asarray(gradient, float)
        if not math.isfinite(value) or not np.isfinite(gradient).all():
            raise ValueError('nonfinite feasible model evaluation')
        if best is None or value < best[0]:
            best = (value, np.asarray(point).copy(), gradient.copy())
        return value, gradient

    reason = 'evaluation-or-wall-budget'
    try:
        source_value = objective(initial)[0]
        if expected_objective is not None and abs(source_value-expected_objective) > 1e-7:
            raise ValueError('raw source objective differs from immutable parent')
        result = minimize(objective, initial, jac=True, method='L-BFGS-B',
            bounds=list(zip(lower, upper, strict=True)),
            options=dict(maxiter=maximum, maxfun=maximum, maxls=30,
                         ftol=1e-15, gtol=1e-8, maxcor=20))
        reason = str(result.message)
    except Exhausted:
        pass
    if best is None:
        raise RuntimeError('no feasible endpoint evaluation')
    return dict(point=best[1], objective=best[0], gradient=best[2],
        diagnostics=dict(evaluations=calls, attempted_chart_calls=attempts,
            invalid_points_excluded=invalid, maximum_evaluations=maximum,
            maximum_seconds=seconds, elapsed_seconds=time.monotonic()-begun,
            reason=reason, solver='L-BFGS-B', raw_endpoint_first=True,
            initial_objective=source_value))


def polish(context, vector, nuisance, *, max_evaluations=134, max_seconds=78,
           expected_objective=None):
    """Original direct-total-tau chart; no domain widening or model changes."""
    from leo.analysis.hard60_bounded_fit import _parameterization, _Problem

    begun = time.monotonic()
    v, n = np.asarray(vector, float).copy(), np.asarray(nuisance, float).copy()
    model = context.model
    problem = _Problem(model, v, rf_arm='zero-c' if context.fixed_c else 'fitted-c')
    if not problem.feasible(v):
        raise ValueError('raw source endpoint outside original physical bounds')
    # The constructor's initializer margin is not an endpoint transformation.
    # Retain the raw endpoint as the chart origin and all original constraints.
    problem.start = v.copy()
    initial, lower, upper, matrix, _ = _parameterization(problem)
    dimension = len(initial)
    scales = np.r_[np.full(model.clock_count, 50.), model.group_scales]
    limits = np.r_[np.full(model.clock_count, 2000.), model.group_limits]
    if n.shape != scales.shape or not np.isfinite(n).all() or np.any(abs(n) > limits+1e-7):
        raise ValueError('raw source nuisance outside original bounds')
    initial = np.r_[initial, n/scales]
    lower, upper = np.r_[lower, -limits/scales], np.r_[upper, limits/scales]

    def physical(point):
        return (v+matrix@(point[:dimension]-initial[:dimension]),
                n+scales*(point[dimension:]-initial[dimension:]))

    def feasible(point):
        pv, pn = physical(point)
        return bool(problem.feasible(pv) and np.all(abs(pn) <= limits+1e-7))

    def evaluate(point):
        pv, pn = physical(point)
        value, grad, extra, _ = model.evaluate_joint(pv, pn)
        return value, np.r_[matrix.T@grad, scales*extra]

    seconds = min(max_seconds, getattr(context, 'deadline', math.inf)-time.monotonic(),
                  max_seconds-(time.monotonic()-begun))
    result = solve(evaluate, initial, lower, upper, feasible,
                   maximum=max_evaluations, seconds=seconds,
                   expected_objective=expected_objective)
    vector, nuisance = physical(result['point'])
    return dict(vector=vector, nuisance=nuisance, diagnostics=dict(result['diagnostics'],
        objective=result['objective'], total_elapsed_seconds=time.monotonic()-begun,
        scope='same raw endpoint, exact original regional/physical/nuisance bounds',
        independent_audit_calls_outside_inference=1))
