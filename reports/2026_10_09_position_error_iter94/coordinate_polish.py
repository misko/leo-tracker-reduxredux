"""Bounded research-only coordinate polish of an unchanged exact objective."""

import numpy as np
from scipy.optimize import nnls

from leo.analysis.hard60_bounded_fit import _Problem

STEPS = tuple(10.0 ** (-exponent) for exponent in range(2, 9))


def projected_gradient(problem, vector, gradient):
    """Match the existing independently audited scaled KKT projection."""
    free, scales = problem.free, problem.scales
    derivative = (gradient * scales)[free]
    jacobian = (problem.jacobian(vector) * scales)[:, free]
    normals = list(jacobian[problem.constraints(vector) <= 1e-6])
    z, low, high = (
        (vector / scales)[free],
        (problem.lower / scales)[free],
        (problem.upper / scales)[free],
    )
    eye = np.eye(len(free))
    for i in range(len(free)):
        if z[i] <= low[i] + 1e-7:
            normals.append(eye[i])
        if z[i] >= high[i] - 1e-7:
            normals.append(-eye[i])
    if normals:
        active = np.asarray(normals).T
        multipliers, _ = nnls(active, derivative, maxiter=100 * active.shape[1])
        derivative = derivative - active @ multipliers
    return derivative


def polish(
    objective,
    start,
    *,
    maximum_rounds=10,
    maximum_evaluations=160,
    rf_arm="fitted-c",
    fixed_position=True,
    slope_half_width_hz_s=60,
):
    """Try feasible +/- fixed steps on one KKT-selected coordinate per round.

    Strict exact-objective decrease selects a step; qualification remains0.001.
    This can fail on coupled constraints or inadequate scalar steps. No optimizer
    success flag or absence of a tested descent direction establishes convergence.
    """
    if (
        isinstance(maximum_rounds, bool)
        or int(maximum_rounds) != maximum_rounds
        or not 1 <= maximum_rounds <= 10
    ):
        raise ValueError("maximum_rounds must be an integer in [1,10]")
    if (
        isinstance(maximum_evaluations, bool)
        or int(maximum_evaluations) != maximum_evaluations
        or not 1 <= maximum_evaluations <= 160
    ):
        raise ValueError("maximum_evaluations must be an integer in [1,160]")
    original = np.asarray(start, dtype=float)
    problem = _Problem(
        objective,
        original,
        rf_arm=rf_arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=slope_half_width_hz_s,
    )
    if not problem.feasible(original):
        raise ValueError(
            "Polish start must already satisfy unchanged physical constraints and RF locks"
        )
    helper_start_delta = problem.start - original
    evaluations, trials, accepted = 0, [], []

    def evaluate(vector):
        nonlocal evaluations
        evaluations += 1
        value, gradient, _ = objective.evaluate(vector)
        gradient = np.asarray(gradient, float)
        if (
            not np.isfinite(value)
            or gradient.shape != vector.shape
            or not np.isfinite(gradient).all()
        ):
            raise ValueError("Exact objective and gradient must be finite")
        return float(value), gradient.copy()

    vector = original.copy()
    value, gradient = evaluate(vector)
    initial_value = value
    reason = "round-budget"
    for round_index in range(maximum_rounds):
        stationarity = problem.stationarity(vector, gradient)
        if stationarity <= 0.001:
            reason = "independently-qualified"
            break
        if evaluations >= maximum_evaluations:
            reason = "evaluation-budget"
            break
        projected = projected_gradient(problem, vector, gradient)
        np.testing.assert_allclose(
            np.max(abs(projected), initial=0), stationarity, atol=1e-12, rtol=1e-12
        )
        coordinate = int(problem.free[int(np.argmax(abs(projected)))])
        before = value
        best_vector, best_value, best_gradient, best_trial = vector, value, gradient, None
        exhausted = False
        for step in STEPS:
            for sign in (1, -1):
                candidate = vector.copy()
                candidate[coordinate] += sign * step * problem.scales[coordinate]
                trial = dict(
                    round=round_index,
                    coordinate=coordinate,
                    scaled_step=sign * step,
                    vector=candidate.tolist(),
                    feasible=problem.feasible(candidate),
                    evaluated=False,
                    objective=None,
                )
                trials.append(trial)
                if not trial["feasible"]:
                    trial["reason"] = "outside unchanged physical constraints"
                    continue
                if evaluations >= maximum_evaluations:
                    trial["reason"] = "evaluation budget"
                    exhausted = True
                    break
                try:
                    candidate_value, candidate_gradient = evaluate(candidate)
                except Exception as error:
                    trial.update(
                        evaluated=True, error=repr(error), reason="objective evaluation failed"
                    )
                    continue
                trial.update(
                    evaluated=True, objective=candidate_value, gradient=candidate_gradient.tolist()
                )
                if candidate_value < best_value:
                    best_vector, best_value, best_gradient, best_trial = (
                        candidate,
                        candidate_value,
                        candidate_gradient,
                        len(trials) - 1,
                    )
            if exhausted:
                break
        if best_trial is None:
            reason = "evaluation-budget" if exhausted else "no-improving-feasible-step"
            break
        vector, value, gradient = best_vector.copy(), best_value, best_gradient.copy()
        accepted.append(
            dict(
                round=round_index,
                trial_index=best_trial,
                before_objective=before,
                after_objective=value,
                vector=vector.tolist(),
                stationarity=problem.stationarity(vector, gradient),
            )
        )
        if exhausted:
            reason = "evaluation-budget"
            break
    stationarity = problem.stationarity(vector, gradient)
    if stationarity <= 0.001:
        reason = "independently-qualified"
    return dict(
        vector=vector,
        objective=value,
        initial_objective=initial_value,
        gradient=gradient,
        stationarity=stationarity,
        converged=stationarity <= 0.001,
        stop_reason=reason,
        evaluations=evaluations,
        rounds=len(accepted),
        trials=trials,
        accepted=accepted,
        physical_constraints_minimum=float(problem.constraints(vector).min()),
        maximum_rounds=maximum_rounds,
        maximum_evaluations=maximum_evaluations,
        helper_start_delta=helper_start_delta,
        fixed_position=fixed_position,
        rf_arm=rf_arm,
        steps=list(STEPS),
    )
