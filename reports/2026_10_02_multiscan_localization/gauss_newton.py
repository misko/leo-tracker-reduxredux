"""Bounded damped Gauss-Newton refinement for grouped localization likelihoods."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from prediction_plan import SharedPredictionPlan


@dataclass
class _State:
    vector: np.ndarray
    parameters: np.ndarray
    objective: float
    gradient: np.ndarray
    hessian: np.ndarray
    likelihood: dict


def _project(vector, bounds):
    projected = np.asarray(vector, dtype=float).copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None:
            projected[index] = max(projected[index], lower)
        if upper is not None:
            projected[index] = min(projected[index], upper)
    return projected


def _projected_gradient(vector, gradient, bounds):
    projected = np.asarray(gradient, dtype=float).copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and upper is not None and lower == upper:
            projected[index] = 0.0
            continue
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            projected[index] = 0.0
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            projected[index] = 0.0
    return projected


def _free_variables(vector, gradient, bounds):
    free = np.ones(len(vector), dtype=bool)
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and upper is not None and lower == upper:
            free[index] = False
            continue
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            free[index] = False
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            free[index] = False
    return free


def _newton_stationarity(objective, gradient, hessian, free, damping):
    diagnostics = {
        "free_curvature_min_eigenvalue": None,
        "free_curvature_max_eigenvalue": None,
        "damping_to_free_min_eigenvalue": None,
        "undamped_newton_step_inf_norm": None,
        "modeled_newton_loss_decrease": None,
        "modeled_newton_relative_loss_decrease": None,
        "low_damping_positive_newton_converged": False,
    }
    if not np.any(free):
        return diagnostics
    free_hessian = hessian[np.ix_(free, free)]
    eigenvalues = np.linalg.eigvalsh(free_hessian)
    minimum = float(eigenvalues[0])
    maximum = float(eigenvalues[-1])
    diagnostics["free_curvature_min_eigenvalue"] = minimum
    diagnostics["free_curvature_max_eigenvalue"] = maximum
    if not np.isfinite(minimum) or minimum <= 0:
        return diagnostics
    damping_ratio = float(damping / minimum)
    diagnostics["damping_to_free_min_eigenvalue"] = damping_ratio
    try:
        step = np.linalg.solve(free_hessian, -gradient[free])
    except np.linalg.LinAlgError:
        return diagnostics
    if np.any(~np.isfinite(step)):
        return diagnostics
    modeled_decrease = float(
        -(gradient[free] @ step + 0.5 * step @ free_hessian @ step)
    )
    relative_decrease = modeled_decrease / max(1.0, abs(float(objective)))
    step_norm = float(np.max(np.abs(step)))
    diagnostics.update(
        {
            "undamped_newton_step_inf_norm": step_norm,
            "modeled_newton_loss_decrease": modeled_decrease,
            "modeled_newton_relative_loss_decrease": relative_decrease,
            "low_damping_positive_newton_converged": bool(
                damping_ratio <= 1e-6
                and step_norm <= 1e-5
                and 0.0 <= relative_decrease <= 1e-10
            ),
        }
    )
    return diagnostics


def refine_gauss_newton(
    data,
    initial,
    satellites,
    support,
    prepared,
    *,
    sigma_hz=200.0,
    tau_sigma_s=1.0,
    tau_bound_s=3.0,
    slope_bound=50.0,
    budget_s=45.0,
    fixed_position_km=None,
):
    """Refine one frozen bank with complete-data/Fisher Gauss-Newton steps.

    Visibility and mixture responsibilities are fixed within each local
    quadratic model. Every proposed step is nevertheless accepted only after
    evaluating the actual grouped likelihood objective.
    """

    initial = np.asarray(initial, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    support = np.asarray(support, dtype=float)
    candidate_count = len(data.numbers)
    if initial.shape != (6 + candidate_count,) or np.any(~np.isfinite(initial)):
        raise ValueError("initial parameters do not match the candidate bank")
    initial = initial.copy()
    if fixed_position_km is not None:
        fixed_position_km = np.asarray(fixed_position_km, dtype=float)
        if fixed_position_km.shape != (2,) or np.any(~np.isfinite(fixed_position_km)):
            raise ValueError("fixed_position_km must contain two finite coordinates")
        if np.any(np.abs(fixed_position_km) > 200.0):
            raise ValueError("fixed_position_km lies outside the position bounds")
        initial[:2] = fixed_position_km
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if len(np.unique(satellites)) != len(satellites) or np.any(satellites < 0) or np.any(
        satellites >= candidate_count
    ):
        raise ValueError("satellites must be unique valid candidate indices")
    if support.shape != satellites.shape or np.any(~np.isfinite(support)) or np.any(support <= 0):
        raise ValueError("support must be positive and match satellites")
    for value, name in (
        (sigma_hz, "sigma_hz"),
        (tau_sigma_s, "tau_sigma_s"),
        (tau_bound_s, "tau_bound_s"),
        (slope_bound, "slope_bound"),
        (budget_s, "budget_s"),
    ):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")

    active = np.r_[np.arange(6), 6 + satellites]
    scales = np.r_[20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, np.ones(len(satellites))]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-slope_bound / 10.0, slope_bound / 10.0),
        (None, None),
        (-slope_bound / 10.0, slope_bound / 10.0),
    ]
    bounds += [(-tau_bound_s, tau_bound_s)] * len(satellites)
    if fixed_position_km is not None:
        fixed_scaled_position = fixed_position_km / scales[:2]
        bounds[:2] = [
            (float(fixed_scaled_position[index]), float(fixed_scaled_position[index]))
            for index in range(2)
        ]
    weights = support / np.sum(support)
    plan = SharedPredictionPlan(data, satellites)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(vector, *, check_time=True):
        nonlocal best, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("Gauss-Newton refinement budget exhausted")
        parameters = initial.copy()
        parameters[active] = vector * scales
        if fixed_position_km is not None:
            parameters[:2] = fixed_position_km
        predicted, visible, jacobian = plan.predict(parameters)
        predicted = predicted.reshape(len(data.times), len(satellites))
        visible = visible.reshape(predicted.shape)
        evaluations += 1
        result = prepared.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            satellite_weights=weights,
            background_mass=0.2,
            return_gradient=True,
            return_precision=True,
        )
        prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
        prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
        if (
            prediction_gradient.shape != predicted.shape
            or prediction_precision.shape != predicted.shape
        ):
            raise ValueError("prepared derivatives must match prediction shape")
        if np.any(~np.isfinite(prediction_gradient)) or np.any(~np.isfinite(prediction_precision)):
            raise FloatingPointError("prepared derivatives must be finite")
        if np.any(prediction_precision < 0):
            raise ValueError("prediction precision must be non-negative")

        physical_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
        physical_hessian = np.asarray(
            jacobian.normal_matrix(prediction_precision.ravel()), dtype=float
        )
        expected_shape = (6 + candidate_count, 6 + candidate_count)
        if physical_gradient.shape != (6 + candidate_count,):
            raise ValueError("prediction Jacobian gradient has the wrong shape")
        if physical_hessian.shape != expected_shape:
            raise ValueError("prediction Jacobian normal matrix has the wrong shape")
        tau_indices = 6 + satellites
        tau = parameters[tau_indices]
        prior = 0.5 * np.sum((tau / tau_sigma_s) ** 2)
        physical_gradient[tau_indices] += tau / tau_sigma_s**2
        physical_hessian[tau_indices, tau_indices] += 1.0 / tau_sigma_s**2
        objective = float(-result["total_log_likelihood"] + prior)
        gradient = physical_gradient[active] * scales
        hessian = physical_hessian[np.ix_(active, active)] * scales[:, None] * scales[None, :]
        hessian = 0.5 * (hessian + hessian.T)
        if not np.isfinite(objective) or np.any(~np.isfinite(gradient)) or np.any(
            ~np.isfinite(hessian)
        ):
            raise FloatingPointError("objective derivatives must be finite")
        likelihood = dict(result)
        likelihood.pop("prediction_gradient", None)
        likelihood.pop("prediction_precision", None)
        state = _State(
            vector=np.asarray(vector, dtype=float).copy(),
            parameters=parameters,
            objective=objective,
            gradient=gradient,
            hessian=hessian,
            likelihood=likelihood,
        )
        if best is None or objective < best.objective:
            best = state
        return state

    vector = _project(initial[active] / scales, bounds)
    current = evaluate(vector, check_time=False)
    initial_objective = current.objective
    positive_diagonal = np.diag(current.hessian)
    positive_diagonal = positive_diagonal[positive_diagonal > 0]
    damping = max(
        1e-6,
        1e-3 * (float(np.median(positive_diagonal)) if len(positive_diagonal) else 1.0),
    )
    iterations = 0
    accepted_steps = 0
    rejected_steps = 0
    last_accepted_step_inf_norm = None
    last_accepted_loss_decrease = None
    success = False
    reason = "iteration_limit"

    try:
        while iterations < 200:
            if time.monotonic() > deadline:
                raise TimeoutError("Gauss-Newton refinement budget exhausted")
            projected_gradient = _projected_gradient(
                current.vector, current.gradient, bounds
            )
            if np.max(np.abs(projected_gradient)) <= 1e-4:
                success = True
                reason = "projected_gradient"
                break
            free = _free_variables(current.vector, current.gradient, bounds)
            newton_stationarity = _newton_stationarity(
                current.objective,
                current.gradient,
                current.hessian,
                free,
                damping,
            )
            if newton_stationarity["low_damping_positive_newton_converged"]:
                success = True
                reason = "low_damping_positive_newton_decrement"
                break
            iterations += 1
            system = current.hessian[np.ix_(free, free)] + damping * np.eye(np.sum(free))
            try:
                step = np.zeros_like(current.vector)
                step[free] = np.linalg.solve(system, -current.gradient[free])
            except np.linalg.LinAlgError:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "singular_curvature"
                    break
                continue
            if np.any(~np.isfinite(step)):
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "nonfinite_step"
                    break
                continue
            maximum = float(np.max(np.abs(step)))
            if maximum > 1.0:
                step /= maximum

            accepted = None
            accepted_step = None
            for fraction in (1.0, 0.5, 0.25, 0.125):
                candidate_vector = _project(current.vector + fraction * step, bounds)
                actual_step = candidate_vector - current.vector
                if not np.any(actual_step):
                    continue
                candidate = evaluate(candidate_vector)
                if candidate.objective < current.objective:
                    accepted = candidate
                    accepted_step = actual_step
                    break
            if accepted is None:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "no_acceptable_step"
                    break
                continue

            previous_objective = current.objective
            current = accepted
            accepted_steps += 1
            damping = max(damping / 3.0, 1e-12)
            step_norm = float(np.max(np.abs(accepted_step)))
            improvement = previous_objective - current.objective
            last_accepted_step_inf_norm = step_norm
            last_accepted_loss_decrease = float(improvement)
            if step_norm <= 1e-6 and improvement <= 1e-8 * (1.0 + abs(previous_objective)):
                accepted_projected_gradient = _projected_gradient(
                    current.vector, current.gradient, bounds
                )
                if np.max(np.abs(accepted_projected_gradient)) <= 1e-4:
                    success = True
                    reason = "projected_gradient_after_tiny_step"
                else:
                    accepted_free = _free_variables(
                        current.vector, current.gradient, bounds
                    )
                    accepted_stationarity = _newton_stationarity(
                        current.objective,
                        current.gradient,
                        current.hessian,
                        accepted_free,
                        damping,
                    )
                    if accepted_stationarity["low_damping_positive_newton_converged"]:
                        success = True
                        reason = "low_damping_positive_newton_decrement_after_tiny_step"
                    else:
                        reason = "tiny_accepted_step_without_gradient_convergence"
                break
    except TimeoutError:
        reason = "budget_exhausted"
    except Exception as error:
        reason = f"evaluation_error:{type(error).__name__}:{error}"

    final_evaluation_error = None
    try:
        evaluate(best.vector, check_time=False)
        final = best
    except Exception as error:
        final = best
        success = False
        final_evaluation_error = f"{type(error).__name__}:{error}"
        if reason in ("projected_gradient", "projected_gradient_after_tiny_step"):
            reason = "final_evaluation_failed_after_convergence"
        if hasattr(prepared, "last_result"):
            prepared.last_result = dict(best.likelihood)
    projected_gradient = _projected_gradient(final.vector, final.gradient, bounds)
    final_free = _free_variables(final.vector, final.gradient, bounds)
    stationarity = _newton_stationarity(
        final.objective,
        final.gradient,
        final.hessian,
        final_free,
        damping,
    )
    likelihood = final.likelihood
    penalty = 0.5 * len(satellites) * np.log(len(likelihood["group_values"]))
    return {
        "parameters": final.parameters,
        "success": success,
        "message": reason,
        "status": "converged" if success else "nonconverged",
        "convergence_reason": reason,
        "algorithm_version": "complete-data-fisher-gn/v2",
        "final_evaluation_error": final_evaluation_error,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "selection_score": final.objective + penalty,
        "entry_penalty": float(penalty),
        "satellite_weights": weights,
        "satellite_support": likelihood["satellite_support"],
        "null_support": likelihood["null_support"],
        "groups": len(likelihood["group_values"]),
        "tau_sigma_s": float(tau_sigma_s),
        "tau_bound_s": float(tau_bound_s),
        "elapsed_s": time.monotonic() - started,
        "evaluations": evaluations,
        "iterations": iterations,
        "accepted_steps": accepted_steps,
        "rejected_steps": rejected_steps,
        "last_accepted_step_inf_norm": last_accepted_step_inf_norm,
        "last_accepted_loss_decrease": last_accepted_loss_decrease,
        "damping": float(damping),
        "free_parameter_count": int(np.sum(final_free)),
        "position_fixed": fixed_position_km is not None,
        "fixed_position_km": None
        if fixed_position_km is None
        else fixed_position_km.copy(),
        "zero_width_bound_count": int(
            sum(
                lower is not None and upper is not None and lower == upper
                for lower, upper in bounds
            )
        ),
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "stationarity_thresholds": {
            "projected_gradient_inf_norm": 1e-4,
            "modeled_newton_relative_loss_decrease": 1e-10,
            "undamped_newton_step_inf_norm": 1e-5,
            "damping_to_free_min_eigenvalue": 1e-6,
            "positive_free_curvature_required": True,
        },
        **stationarity,
        "gradient_method": "Analytic likelihood and orbit derivatives; observer ECEF central 1m",
        "curvature_method": "Complete-data/Fisher JtWJ plus Gaussian tau prior",
        "shared_predictions": True,
        "best_finite_preserved": True,
    }


__all__ = ["refine_gauss_newton"]
