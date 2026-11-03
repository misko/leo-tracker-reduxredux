"""Bounded position optimization subject to unchanged RF residual gates.

This numerical helper has no catalogue, storage, receiver, or reference-position
authority. A caller supplies its RF objective and normalized gate slacks.
"""

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def noise_slacks(residual, times):
    """Positive iff every existing noise-screen inequality is satisfied."""
    r = np.asarray(residual, float)
    d = batch_noise_screen(r[None, :], times)
    return dict(mean=1-float(d['mean_z'][0])/3,
                slope=1-float(d['slope_z'][0])/3,
                quadratic=1-float(d['quadratic_bic_gain'][0])/10,
                step=1-float(d['maximum_step_z'][0])/4,
                lag1=1-abs(float(d['lag1_acf'][0]))/(4/np.sqrt(len(r))))


def residual_slacks(residual, times):
    r = np.asarray(residual, float)
    return dict(rms=1-float(np.sqrt(np.mean(r*r)))/450, **noise_slacks(r, times))


def feasible_fit(objective, slacks, start, lower, upper, *, iterations=40):
    """Minimize the RF objective with fixed gates and a small numerical interior.

    Solver success alone never establishes compatibility. The best feasible
    visited point is retained even if SLSQP stops on its budget, and the caller
    must independently replay all original gates at the final refreshed phase.
    """
    x0, lo, hi = (np.asarray(v, float) for v in (start, lower, upper))
    if x0.shape != lo.shape or x0.shape != hi.shape or np.any(lo >= hi):
        raise ValueError('matching finite position bounds required')
    if not all(np.isfinite(v).all() for v in (x0, lo, hi)) or iterations < 1:
        raise ValueError('finite position and positive iteration budget required')
    x0 = np.clip(x0, lo, hi)
    origin = float(objective(x0)); points = []
    cache = {}

    def evaluate(x):
        key = tuple(np.asarray(x, float))
        if key not in cache:
            score = float(objective(x))
            gate = np.asarray(slacks(x), float)
            if gate.ndim != 1 or not len(gate) or not np.isfinite(gate).all() or not np.isfinite(score):
                raise ValueError('finite objective and nonempty finite gate slacks required')
            cache[key] = score, gate
            if gate.min() >= 0:
                points.append((score, np.asarray(x, float).copy(), float(gate.min())))
        return cache[key]

    result = minimize(lambda x: evaluate(x)[0]-origin, x0, method='SLSQP',
                      bounds=list(zip(lo, hi, strict=True)),
                      constraints=[dict(type='ineq', fun=lambda x: evaluate(x)[1]-1e-6)],
                      options=dict(maxiter=iterations, ftol=1e-7, eps=1e-3))
    evaluate(result.x)
    chosen = min(points, key=lambda v: v[0]) if points else None
    endpoint = chosen[1] if chosen is not None else np.asarray(result.x)
    score, gate = evaluate(endpoint)
    return dict(parameters=endpoint, score=score, minimum_gate_slack=float(gate.min()),
                feasible=chosen is not None, solver_success=bool(result.success),
                solver_message=str(result.message), iterations=int(result.nit),
                evaluations=len(cache), numerical_interior=1e-6,
                finite_difference_step_km=1e-3)
