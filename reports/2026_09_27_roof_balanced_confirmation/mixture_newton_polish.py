"""Bounded damped-Newton polish for frozen mixture-calibration runs."""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

import mixture_reception_core as core


def newton_polish(
    theta: object,
    value_gradient_fn: Callable[[np.ndarray], tuple[float, np.ndarray]],
    hessian_fn: Callable[[np.ndarray], np.ndarray],
    *, max_steps: int = 8, target_gradient: float = 1e-8,
    acceptance_gradient: float = core.DEFAULT_GRADIENT_TOLERANCE,
    curvature_tolerance: float = core.DEFAULT_CURVATURE_TOLERANCE,
    armijo: float = 1e-4, max_line_search_steps: int = 30,
) -> dict[str, object]:
    """Polish one existing theta without changing its objective or thresholds."""
    current = np.asarray(theta, dtype=float).copy()
    if current.ndim != 1 or not len(current) or not np.all(np.isfinite(current)):
        raise ValueError("initial theta must be a nonempty finite vector")
    if (max_steps < 0 or max_line_search_steps <= 0 or target_gradient <= 0 or
            acceptance_gradient <= 0 or curvature_tolerance < 0 or
            not 0 < armijo < 1):
        raise ValueError("invalid polish configuration")
    initial_value, initial_gradient = value_gradient_fn(current)
    initial_gradient = np.asarray(initial_gradient, dtype=float)
    if (not math.isfinite(float(initial_value)) or
            initial_gradient.shape != current.shape or
            not np.all(np.isfinite(initial_gradient))):
        raise ValueError("initial objective or gradient is nonfinite")
    history = []
    stop_reason = "maximum_steps"
    for step in range(max_steps):
        value, gradient = value_gradient_fn(current)
        gradient = np.asarray(gradient, dtype=float)
        if (not math.isfinite(float(value)) or gradient.shape != current.shape or
                not np.all(np.isfinite(gradient))):
            stop_reason = "nonfinite_objective_or_gradient"
            break
        gradient_max = float(np.max(np.abs(gradient)))
        if gradient_max <= target_gradient:
            stop_reason = "target_gradient"
            break
        hessian = np.asarray(hessian_fn(current), dtype=float)
        if (hessian.shape != (current.size, current.size) or
                not np.all(np.isfinite(hessian))):
            stop_reason = "nonfinite_hessian"
            break
        hessian = (hessian + hessian.T) / 2.
        eigenvalues = np.linalg.eigvalsh(hessian)
        if eigenvalues[0] <= curvature_tolerance:
            stop_reason = "nonpositive_or_weak_curvature"
            break
        try:
            direction = -np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            stop_reason = "singular_hessian"
            break
        directional_derivative = float(gradient @ direction)
        if not math.isfinite(directional_derivative) or directional_derivative >= 0:
            stop_reason = "non_descent_newton_direction"
            break
        accepted = False
        scale = 1.
        candidate_value = math.inf
        for line_step in range(max_line_search_steps):
            candidate = current + scale * direction
            try:
                candidate_value = float(value_gradient_fn(candidate)[0])
            except (FloatingPointError, OverflowError, ValueError):
                candidate_value = math.inf
            if (math.isfinite(candidate_value) and
                    candidate_value <= value + armijo * scale * directional_derivative):
                accepted = True
                break
            scale *= .5
        history.append({
            "step": step + 1, "objective_before": float(value),
            "gradient_max_abs_before": gradient_max,
            "minimum_hessian_eigenvalue": float(eigenvalues[0]),
            "step_scale": float(scale), "line_search_steps": line_step + 1,
            "accepted": accepted,
            "objective_after": float(candidate_value) if math.isfinite(candidate_value) else None,
        })
        if not accepted:
            stop_reason = "line_search_failed"
            break
        current = candidate
    try:
        final_value, final_gradient = value_gradient_fn(current)
        final_hessian = np.asarray(hessian_fn(current), dtype=float)
    except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError) as error:
        raise FloatingPointError("nonfinite or invalid final polish evaluation") from error
    final_gradient = np.asarray(final_gradient, dtype=float)
    objective_gradient_finite = (math.isfinite(float(final_value)) and
                                 final_gradient.shape == current.shape and
                                 np.all(np.isfinite(final_gradient)))
    if not objective_gradient_finite:
        raise FloatingPointError("nonfinite final objective or gradient")
    gradient_max = float(np.max(np.abs(final_gradient)))
    finite = (final_hessian.shape == (current.size, current.size) and
              np.all(np.isfinite(final_hessian)))
    if finite:
        final_hessian = (final_hessian + final_hessian.T) / 2.
        final_eigenvalues = np.linalg.eigvalsh(final_hessian)
        minimum_eigenvalue = float(final_eigenvalues[0])
        maximum_eigenvalue = float(final_eigenvalues[-1])
    else:
        minimum_eigenvalue = None
        maximum_eigenvalue = None
    fatal_stop_reasons = {
        "nonfinite_objective_or_gradient", "nonfinite_hessian",
        "nonpositive_or_weak_curvature", "singular_hessian",
        "non_descent_newton_direction", "line_search_failed",
    }
    fatal_stop = stop_reason in fatal_stop_reasons
    return {
        "input_theta": np.asarray(theta, float).tolist(),
        "input_objective": float(initial_value),
        "input_gradient_max_abs": float(np.max(np.abs(initial_gradient))),
        "theta": current.tolist(), "objective": float(final_value),
        "gradient_max_abs": gradient_max, "steps_attempted": len(history),
        "accepted_steps": sum(row["accepted"] for row in history),
        "stop_reason": stop_reason, "history": history,
        "curvature": {
            "minimum_eigenvalue": minimum_eigenvalue,
            "maximum_eigenvalue": maximum_eigenvalue,
            "tolerance": curvature_tolerance,
            "identifiable": bool(finite and minimum_eigenvalue is not None and
                                 minimum_eigenvalue > curvature_tolerance),
        },
        "finite": bool(finite),
        "fatal_stop": bool(fatal_stop),
        "gradient_accepted": bool(finite and gradient_max <= acceptance_gradient),
        "accepted": bool(finite and not fatal_stop and
                         gradient_max <= acceptance_gradient and
                         minimum_eigenvalue is not None and
                         minimum_eigenvalue > curvature_tolerance),
    }


def polish_multistart(
    raw_runs: Sequence[dict[str, object]], tracks: Sequence[core.TrackData],
    layout: core.ParameterLayout, ridge: float = 1.0, *, max_steps: int = 8,
    target_gradient: float = 1e-8,
    input_objective_tolerance: float = 1e-8,
) -> dict[str, object]:
    """Polish saved multistart thetas and reapply the frozen aggregate gates."""
    if len(raw_runs) < 2:
        raise ValueError("at least two raw optimizer runs are required")
    value_gradient = lambda value: core.objective_gradient(
        value, tracks, layout, ridge)
    hessian = lambda value: core.numerical_hessian(
        value, tracks, layout, ridge)
    polished = []
    for raw in raw_runs:
        if "theta" not in raw or "objective" not in raw:
            raise ValueError("raw run lacks theta or objective")
        recomputed_objective = float(value_gradient(raw["theta"])[0])
        saved_objective = float(raw["objective"])
        if (not math.isfinite(saved_objective) or
                abs(recomputed_objective - saved_objective) > input_objective_tolerance):
            raise ValueError("saved run objective differs from reconstructed objective")
        result = newton_polish(
            raw["theta"], value_gradient, hessian, max_steps=max_steps,
            target_gradient=target_gradient)
        result["input_run"] = dict(raw)
        result["input_objective_absolute_difference"] = abs(
            recomputed_objective - saved_objective)
        polished.append(result)
    objectives = np.asarray([run["objective"] for run in polished], float)
    if not np.all(np.isfinite(objectives)):
        raise FloatingPointError("polished objectives are nonfinite")
    stable, objective_range, per_track_range = core.objective_stability(
        objectives, len(tracks), core.DEFAULT_OBJECTIVE_STABILITY_TOLERANCE)
    best_index = int(np.argmin(objectives))
    predictions = [core.prediction_vector(run["theta"], tracks, layout)
                   for run in polished]
    prediction_difference = max(float(np.max(np.abs(value - predictions[best_index])))
                                for value in predictions)
    predictions_stable = (
        prediction_difference <= core.DEFAULT_PREDICTION_STABILITY_TOLERANCE)
    gradients_ok = all(run["gradient_accepted"] for run in polished)
    curvature_ok = all(run["curvature"]["identifiable"] for run in polished)
    finite = all(run["finite"] for run in polished)
    runs_accepted = all(run["accepted"] for run in polished)
    numerical_failures = []
    if not finite:
        numerical_failures.append("one_or_more_polished_runs_nonfinite")
    if not gradients_ok:
        numerical_failures.append("one_or_more_gradient_norms_exceed_threshold")
    if not runs_accepted:
        numerical_failures.append("one_or_more_runs_has_fatal_stop_or_failed_gate")
    identifiability_concerns = []
    if finite and gradients_ok:
        if not stable:
            identifiability_concerns.append("polished_multistart_objectives_disagree")
        if not predictions_stable:
            identifiability_concerns.append("polished_multistart_predictions_disagree")
        if not curvature_ok:
            identifiability_concerns.append("near_zero_or_negative_local_curvature")
    return {
        "theta": polished[best_index]["theta"],
        "objective": polished[best_index]["objective"],
        "best_start_index": best_index, "runs": polished,
        "configuration": {
            "max_steps": max_steps, "target_gradient": target_gradient,
            "input_objective_tolerance": input_objective_tolerance,
            "acceptance_gradient": core.DEFAULT_GRADIENT_TOLERANCE,
            "objective_stability_tolerance": core.DEFAULT_OBJECTIVE_STABILITY_TOLERANCE,
            "prediction_stability_tolerance": core.DEFAULT_PREDICTION_STABILITY_TOLERANCE,
            "curvature_tolerance": core.DEFAULT_CURVATURE_TOLERANCE,
        },
        "objective_range": objective_range,
        "objective_per_track_range": per_track_range,
        "stable_objective": bool(stable),
        "prediction_max_absolute_difference": prediction_difference,
        "stable_predictions": bool(predictions_stable),
        "all_gradients_within_tolerance": bool(gradients_ok),
        "all_curvature_accepted": bool(curvature_ok),
        "all_runs_accepted": bool(runs_accepted),
        "failure_reasons": {
            "numerical_inconclusive": numerical_failures,
            "identifiability_concerns": identifiability_concerns,
        },
        "accepted": bool(finite and runs_accepted and gradients_ok and curvature_ok and stable and
                         predictions_stable),
    }
