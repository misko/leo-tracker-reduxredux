"""Bounded research polish using the original model and strict KKT audit."""
import time
import numpy as np
from scipy.optimize import minimize
from leo.analysis.hard60_bounded_fit import _Problem, _parameterization


def polish(model, fit, *, arm, local_center, local_radius_km, seconds=30., maximum=1999):
    v0, n0 = (np.asarray(fit[k], float) for k in ('vector', 'nuisance'))
    problem = _Problem(model, v0, rf_arm=arm, local_center=local_center,
                       local_radius_km=local_radius_km, slope_half_width_hz_s=60)
    initial, lower, upper, matrix, constant = _parameterization(problem)
    dimension = len(initial)
    scales = np.r_[np.full(model.clock_count, 50.), model.group_scales]
    limits = np.r_[np.full(model.clock_count, 2000.), model.group_limits]
    initial = np.r_[initial, n0/scales]
    lower = np.r_[lower, -limits/scales]; upper = np.r_[upper, limits/scales]
    begun = time.monotonic(); records = []; calls = 0
    initial_value = model.evaluate_joint(v0, n0)[0]

    class BudgetExpired(Exception):
        pass

    def physical(z):
        return constant+matrix@z[:dimension], z[dimension:]*scales

    def evaluate(z):
        nonlocal calls
        if calls >= maximum or time.monotonic()-begun >= seconds:
            raise BudgetExpired()
        calls += 1; v, n = physical(z)
        value, gradient, extra, terms = model.evaluate_joint(v, n)
        if problem.feasible(v) and np.all(abs(n) <= limits+1e-7):
            projected = scales*extra
            projected[(n <= -limits+1e-7) & (projected >= 0)] = 0
            projected[(n >= limits-1e-7) & (projected <= 0)] = 0
            kkt = max(problem.stationarity(v, gradient), float(np.max(abs(projected), initial=0)))
            records.append((float(value), v.copy(), n.copy(), float(terms.nll), kkt))
        # Centering changes neither the original objective nor its gradient.
        return value-initial_value, np.r_[matrix.T@gradient, scales*extra]

    def constraints(z):
        v, _ = physical(z)
        return np.r_[v[7]+10, 10-v[7], problem.constraints(v)]

    def jacobian(z):
        v, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(v)@matrix])
        return np.column_stack([core, np.zeros((len(core), len(scales)))])

    try:
        minimize(evaluate, initial, jac=True, method='SLSQP', bounds=list(zip(lower, upper)),
                 constraints=dict(type='ineq', fun=constraints, jac=jacobian),
                 options=dict(maxiter=600, ftol=1e-14))
    except BudgetExpired:
        pass
    accepted = [r for r in records if r[4] <= .001 and r[0] <= initial_value+1e-7]
    chosen = min(accepted or records, key=lambda r:r[0]) if records else None
    if chosen is None:
        return fit, dict(accepted=False, reason='No feasible polish evaluation', calls=calls)
    value, v, n, nll, kkt = chosen
    result = dict(vector=v, nuisance=n, objective=value, likelihood_nll=nll,
                  stationarity=kkt, converged=bool(accepted))
    return result, dict(accepted=bool(accepted), stationarity=kkt, calls=calls,
        elapsed_seconds=time.monotonic()-begun, objective_change=value-initial_value,
        optimizer_ftol=1e-14, strict_stationarity_threshold=.001,
        scope='Same model, priors and bounds; extra bounded optimizer allowance only')
