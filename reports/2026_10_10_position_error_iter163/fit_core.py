"""Explicit161 successor: fixed position and arm-correct nonzero RF starts.

The audit is copied from immutable161 with only seed admission and fixed-position
constraints changed. No optimizer is copied; callers inject the unchanged fitter.
"""

import copy
import math
import time

import numpy as np


def plain(value):
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def audit_state(objective, seed, vector, coefficients, reported_objective, *,
                arm, problem_type, clock=time.monotonic):
    """Audit one retained control with one fresh callback, never an optimizer.

    Reuse the exact execute_cell admission/constraint/audit path through a local
    identity port that returns the supplied state. No production fit port is
    accepted or invoked. The seed fixes the hypothesis position; coefficients
    supply both the feasible clock admission state and returned control state.
    """
    raw = dict(vector=np.array(vector, dtype=float, copy=True),
               clock_coefficients=np.array(coefficients, dtype=float, copy=True),
               objective=reported_objective)

    def retained_state(*args, **kwargs):
        return copy.deepcopy(raw)

    result = execute_cell(objective, seed, coefficients, arm=arm,
                          fit_port=retained_state, problem_type=problem_type, clock=clock)
    result['solver'] = plain(raw)
    result['origin'] = 'retained-control-audit'
    result['fit_called'] = False
    result['fit_elapsed_s'] = None
    result['fit_exceeded_soft_budget'] = None
    return result


def execute_cell(objective, common_vector, common_clock, *, arm, fit_port,
                 problem_type, clock=time.monotonic):
    """Fit/audit only. Caller owns input identity, held scoring and sealing.

    Original constraints apply at the supplied hypothesis position. Fitted-c
    permits nonzero source RF coefficients; zero-c must be projected by caller.
    Optimizer success never substitutes for independent KKT.
    Solver output survives all later audit failures; unavailable costs are null.
    """
    begun = clock()
    result = dict(status="failed", arm=arm, solver=None, audit=None, error=None,
                  fit_called=False, audit_called=False, fit_elapsed_s=None,
                  audit_elapsed_s=None, total_elapsed_s=None)
    try:
        seed = np.array(common_vector, dtype=float, copy=True)
        initial = np.array(common_clock, dtype=float, copy=True)
        if arm not in ("zero-c", "fitted-c"):
            raise ValueError("Unknown RF arm")
        if (seed.shape != (objective.size,) or initial.shape != objective.initial_clock.shape
                or len(initial) < 2 or not np.isfinite(seed).all() or not np.isfinite(initial).all()):
            raise ValueError("Invalid common starting state")
        if arm == "zero-c" and (seed[6] != 0 or np.any(initial[-2:] != 0)):
            raise ValueError("Caller must apply exact zero-c start locks")
        lower, upper = np.full(len(initial), -2000.), np.full(len(initial), 2000.)
        locked = arm == "zero-c" or bool(getattr(objective, "fixed_rf_drift", False))
        lower[-2:], upper[-2:] = (0., 0.) if locked else (-1000., 1000.)
        problem = problem_type(objective, seed.copy(), rf_arm=arm, fixed_position=True,
                               local_center=seed[:2].copy(), local_radius_km=25.,
                               slope_half_width_hz_s=60.)
        if not problem.feasible(seed) or np.any(initial < lower) or np.any(initial > upper):
            raise ValueError("Original common seed is infeasible; helper projection not adopted")
        result["start"] = dict(vector=seed.copy(), clock_coefficients=initial.copy(),
                               local_center=seed[:2].copy(), local_radius_km=25.)
        start = clock(); result["fit_called"] = True
        try:
            fitted = fit_port(objective, seed.copy(), arm=arm, clock_seed=initial.copy(),
                              maximum_seconds=90, maximum_iterations=600,
                              timing_half_width_s=20, fixed_position=True)
            result["solver"] = copy.deepcopy(fitted)
        finally:
            result["fit_elapsed_s"] = clock() - start
        start = clock()
        try:
            vector = np.array(fitted["vector"], dtype=float, copy=True)
            coefficients = np.array(fitted["clock_coefficients"], dtype=float, copy=True)
            if (vector.shape != seed.shape or coefficients.shape != initial.shape
                    or not np.isfinite(vector).all() or not np.isfinite(coefficients).all()):
                raise ValueError("Invalid returned state")
            saved = float(fitted["objective"])
            if not math.isfinite(saved):
                raise ValueError("Nonfinite reported objective")
            position_locked = bool(np.array_equal(vector[:2], seed[:2]))
            feasible = bool(problem.feasible(vector))
            boxes = bool(np.all(coefficients >= lower) and np.all(coefficients <= upper))
            locks = bool((arm != "zero-c" or vector[6] == 0)
                         and (not locked or np.all(coefficients[-2:] == 0)))
            result["audit"] = dict(feasible=feasible, clock_boxes=boxes, locks=locks,
                                   position_locked=position_locked, qualified=False)
            if not (feasible and boxes and locks and position_locked):
                raise ValueError("Returned physical state/clock boxes/RF locks invalid")
            result["audit_called"] = True
            value, gradient, nuisance_gradient, terms = objective.evaluate_joint(vector.copy(), coefficients.copy())
            gradient, nuisance_gradient = np.asarray(gradient), np.asarray(nuisance_gradient)
            if (not np.isfinite(value) or gradient.shape != seed.shape
                    or nuisance_gradient.shape != initial.shape
                    or not np.isfinite(gradient).all() or not np.isfinite(nuisance_gradient).all()):
                raise ValueError("Nonfinite or malformed fresh objective/gradients")
            nll = float(terms.nll)
            if not math.isfinite(nll):
                raise ValueError("Nonfinite likelihood")
            scaled = 50 * nuisance_gradient.copy()
            scaled[(coefficients <= lower + 1e-7) & (scaled >= 0)] = 0
            scaled[(coefficients >= upper - 1e-7) & (scaled <= 0)] = 0
            physical = float(problem.stationarity(vector, gradient))
            nuisance = float(np.max(abs(scaled), initial=0.))
            if not math.isfinite(physical) or not math.isfinite(nuisance):
                raise ValueError("Nonfinite independent stationarity")
            delta = float(value - saved)
            qualified = abs(delta) <= 1e-6 and max(physical, nuisance) <= .001
            result["audit"].update(objective=float(value), reported_objective=saved,
                objective_delta=delta, likelihood_nll=nll, prior_penalty=float(value-nll),
                physical_stationarity=physical, clock_stationarity=nuisance,
                stationarity=max(physical, nuisance), qualified=qualified)
            result["status"] = "qualified" if qualified else "unqualified"
        finally:
            result["audit_elapsed_s"] = clock() - start
    except Exception as error:
        result["error"] = repr(error)
    finally:
        result["total_elapsed_s"] = clock() - begun
        result["fixed_position"] = True
        result["fit_exceeded_soft_budget"] = (
            None if result["fit_elapsed_s"] is None else result["fit_elapsed_s"] > 90)
    return plain(result)
