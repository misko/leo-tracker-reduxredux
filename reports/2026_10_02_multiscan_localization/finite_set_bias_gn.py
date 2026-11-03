"""Complete-data/Fisher Gauss-Newton refinement for satellite frequency bias."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from finite_set_satellite_bias import (
    MEASUREMENT_SIGMA_HZ,
    OMEGA_SIGMA_HZ,
    RX_SLOPE_BOUND_HZ_S,
    TAU_BOUND_S,
    TAU_SIGMA_S,
    _trial_specification,
    receiver_satellite_topology,
)
from gauss_newton import (
    _free_variables,
    _newton_stationarity,
    _project,
    _projected_gradient,
)
from prediction_plan import SharedPredictionPlan


@dataclass(frozen=True)
class BiasFisherState:
    vector: np.ndarray
    parameters: np.ndarray
    omega_hz: np.ndarray
    objective: float
    gradient: np.ndarray
    hessian: np.ndarray
    likelihood: dict
    visible: np.ndarray
    topology: dict
    tau_prior: float
    omega_prior: float


def bias_trial_specification(data, source_trial):
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    specification = _trial_specification(data, source_trial["parameters"], satellites)
    vector = specification["vector"].copy()
    omega = source_trial.get("omega_hz")
    if omega is None:
        omega = np.zeros(len(satellites))
        source = "zero_default"
    else:
        omega = np.asarray(omega, dtype=float)
        if omega.shape != satellites.shape or np.any(~np.isfinite(omega)):
            raise ValueError("source omega_hz must be finite and match selected satellites")
        source = "source_trial_continuation"
    vector[-len(satellites) :] = omega / OMEGA_SIGMA_HZ
    return {
        **specification,
        "vector": vector,
        "initial_omega_hz": omega.copy(),
        "omega_initialization": source,
    }


def _physical_parameters(vector, specification):
    vector = np.asarray(vector, dtype=float)
    physical_count = len(specification["active"])
    parameters = specification["initial_parameters"].copy()
    physical_scales = specification["physical_scales"]
    parameters[specification["active"]] = vector[:physical_count] * physical_scales
    return parameters


def _candidate_topology(data, satellites, visible):
    try:
        return receiver_satellite_topology(
            data,
            satellites,
            visible,
            require_connected=False,
        )
    except ValueError as error:
        if "has no visible prediction support" not in str(error):
            raise
        return {
            "connected": False,
            "component_count": None,
            "likelihood_identifiable_omega_contrasts": None,
            "error": str(error),
            "limitation": "At least one selected satellite has no visible prediction support.",
        }


def _omega_cross_block(jacobian, precision):
    precision = np.asarray(precision, dtype=float)
    if precision.ndim != 2:
        raise ValueError("prediction precision must be a row-by-satellite matrix")
    columns = []
    for satellite_column in range(precision.shape[1]):
        weights = np.zeros_like(precision)
        weights[:, satellite_column] = precision[:, satellite_column]
        columns.append(jacobian.transpose_multiply(weights.ravel()))
    return np.column_stack(columns)


def evaluate_bias_fisher_state(
    vector,
    *,
    data,
    specification,
    satellites,
    likelihood,
    plan,
):
    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(specification["scales"], dtype=float)
    if vector.shape != scales.shape or np.any(~np.isfinite(vector)):
        raise ValueError("satellite-bias vector has the wrong shape or non-finite values")
    physical_count = len(specification["active"])
    parameters = _physical_parameters(vector, specification)
    omega_scaled = vector[physical_count:]
    omega_hz = omega_scaled * OMEGA_SIGMA_HZ
    predicted, visible, jacobian = plan.predict(parameters)
    predicted = np.asarray(predicted, dtype=float).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible, dtype=bool).reshape(predicted.shape)
    predicted = predicted + omega_hz[None, :]
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=MEASUREMENT_SIGMA_HZ,
        satellite_weights=likelihood.frozen_masses["raw_satellite_mass"],
        background_mass=likelihood.frozen_masses["raw_background_mass"],
        return_gradient=True,
        return_precision=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
    if (
        prediction_gradient.shape != predicted.shape
        or prediction_precision.shape != predicted.shape
    ):
        raise ValueError("finite-set derivatives must match the prediction matrix")
    if np.any(~np.isfinite(prediction_gradient)) or np.any(~np.isfinite(prediction_precision)):
        raise FloatingPointError("finite-set derivatives must be finite")
    if np.any(prediction_precision < 0):
        raise ValueError("prediction precision must be nonnegative")

    candidate_count = len(data.numbers)
    full_size = 6 + candidate_count
    physical_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
    physical_hessian = np.asarray(jacobian.normal_matrix(prediction_precision.ravel()), dtype=float)
    if physical_gradient.shape != (full_size,):
        raise ValueError("prediction Jacobian gradient has the wrong shape")
    if physical_hessian.shape != (full_size, full_size):
        raise ValueError("prediction Jacobian normal matrix has the wrong shape")

    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    physical_hessian[tau_indices, tau_indices] += 1.0 / TAU_SIGMA_S**2
    omega_prior = 0.5 * float(np.sum(omega_scaled**2))
    omega_gradient = -np.sum(prediction_gradient, axis=0) + omega_hz / OMEGA_SIGMA_HZ**2

    cross = _omega_cross_block(jacobian, prediction_precision)
    omega_hessian = np.diag(np.sum(prediction_precision, axis=0) + 1.0 / OMEGA_SIGMA_HZ**2)
    active = specification["active"]
    unscaled_hessian = np.block(
        [
            [physical_hessian[np.ix_(active, active)], cross[active]],
            [cross[active].T, omega_hessian],
        ]
    )
    unscaled_gradient = np.r_[physical_gradient[active], omega_gradient]
    gradient = unscaled_gradient * scales
    hessian = unscaled_hessian * scales[:, None] * scales[None, :]
    hessian = 0.5 * (hessian + hessian.T)
    objective = float(-result["total_log_likelihood"] + tau_prior + omega_prior)
    if (
        not np.isfinite(objective)
        or np.any(~np.isfinite(gradient))
        or np.any(~np.isfinite(hessian))
    ):
        raise FloatingPointError("satellite-bias objective derivatives must be finite")
    diagnostics = dict(result)
    diagnostics.pop("prediction_gradient", None)
    diagnostics.pop("prediction_precision", None)
    return BiasFisherState(
        vector=vector.copy(),
        parameters=parameters,
        omega_hz=omega_hz,
        objective=objective,
        gradient=gradient,
        hessian=hessian,
        likelihood=diagnostics,
        visible=visible.copy(),
        topology=_candidate_topology(data, satellites, visible),
        tau_prior=tau_prior,
        omega_prior=omega_prior,
    )


def fit_satellite_bias_trial(
    data,
    source_trial,
    likelihood,
    *,
    budget_s=15.0,
    plan_factory=SharedPredictionPlan,
):
    """Refine one frozen finite-set bank with satellite-bias Fisher GN."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("budget_s must lie in (0, 15]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    specification = bias_trial_specification(data, source_trial)
    bounds = specification["bounds"]
    plan = plan_factory(data, satellites)
    _, initial_visible, _ = plan.predict(specification["initial_parameters"])
    initial_topology = receiver_satellite_topology(data, satellites, initial_visible)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None
    disconnected_topology_evaluations = 0

    def evaluate(vector, *, check_time=True):
        nonlocal best, disconnected_topology_evaluations, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("finite-set satellite-bias GN budget exhausted")
        state = evaluate_bias_fisher_state(
            vector,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        )
        evaluations += 1
        if not state.topology["connected"]:
            disconnected_topology_evaluations += 1
        elif best is None or state.objective < best.objective:
            best = state
        return state

    vector = _project(specification["vector"], bounds)
    current = evaluate(vector, check_time=False)
    if not current.topology["connected"]:
        raise ValueError("initial satellite-bias visibility topology is disconnected")
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
                raise TimeoutError("finite-set satellite-bias GN budget exhausted")
            projected_gradient = _projected_gradient(
                current.vector,
                current.gradient,
                bounds,
            )
            if np.max(np.abs(projected_gradient)) <= 1e-4:
                success = True
                reason = "projected_gradient"
                break
            free = _free_variables(current.vector, current.gradient, bounds)
            stationarity = _newton_stationarity(
                current.objective,
                current.gradient,
                current.hessian,
                free,
                damping,
            )
            if stationarity["low_damping_positive_newton_converged"]:
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
                if candidate.topology["connected"] and candidate.objective < current.objective:
                    accepted = candidate
                    accepted_step = actual_step
                    break
            if accepted is None:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "no_acceptable_connected_step"
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
                    current.vector,
                    current.gradient,
                    bounds,
                )
                if np.max(np.abs(accepted_projected_gradient)) <= 1e-4:
                    success = True
                    reason = "projected_gradient_after_tiny_step"
                else:
                    accepted_free = _free_variables(
                        current.vector,
                        current.gradient,
                        bounds,
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
        final = evaluate(best.vector, check_time=False)
    except Exception as error:
        final = best
        success = False
        final_evaluation_error = f"{type(error).__name__}:{error}"
        reason = f"final_evaluation_failed:{final_evaluation_error}"
        if hasattr(likelihood, "last_result"):
            likelihood.last_result = dict(best.likelihood)
    if final is None:
        raise RuntimeError("satellite-bias GN produced no connected finite state")
    _, retained_visible, _ = plan.predict(final.parameters)
    final_topology = receiver_satellite_topology(data, satellites, retained_visible)
    retained_matches_current = bool(
        final.vector.shape == current.vector.shape
        and np.allclose(final.vector, current.vector, rtol=0, atol=1e-10)
    )
    if success and not retained_matches_current:
        success = False
        reason = "converged_state_differs_from_retained_connected_incumbent"

    projected_gradient = _projected_gradient(final.vector, final.gradient, bounds)
    final_free = _free_variables(final.vector, final.gradient, bounds)
    stationarity = _newton_stationarity(
        final.objective,
        final.gradient,
        final.hessian,
        final_free,
        damping,
    )
    groups = len(final.likelihood["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(groups)
    omega_parameter_count = len(satellites) - final_topology["component_count"]
    omega_penalty = 0.5 * omega_parameter_count * np.log(groups)
    return {
        "model": "finite_set_satellite_bias_gn",
        "parameters": final.parameters,
        "omega_hz": final.omega_hz,
        "omega_sigma_hz": OMEGA_SIGMA_HZ,
        "omega_hard_bound_hz": None,
        "omega_initialization": specification["omega_initialization"],
        "initial_omega_hz": specification["initial_omega_hz"],
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "selection_score": float(final.objective + entry_penalty + omega_penalty),
        "entry_penalty": float(entry_penalty),
        "omega_identifiable_parameter_count": omega_parameter_count,
        "omega_parameter_penalty": float(omega_penalty),
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": reason,
        "convergence_reason": reason,
        "algorithm_version": "finite-set-satellite-bias-complete-data-fisher-gn/v1",
        "optimizer_status": None,
        "final_evaluation_error": final_evaluation_error,
        "evaluations": evaluations,
        "iterations": iterations,
        "accepted_steps": accepted_steps,
        "rejected_steps": rejected_steps,
        "elapsed_s": time.monotonic() - started,
        "groups": groups,
        "sigma_hz": MEASUREMENT_SIGMA_HZ,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "rx_slope_bound_hz_s": RX_SLOPE_BOUND_HZ_S,
        "tau_prior": final.tau_prior,
        "omega_prior": final.omega_prior,
        "gradient_inf_norm": float(np.max(np.abs(final.gradient))),
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "omega_mean_hz": float(np.mean(final.omega_hz)),
        "last_accepted_step_inf_norm": last_accepted_step_inf_norm,
        "last_accepted_loss_decrease": last_accepted_loss_decrease,
        "damping": float(damping),
        "free_parameter_count": int(np.sum(final_free)),
        "zero_width_bound_count": int(
            sum(
                lower is not None and upper is not None and lower == upper
                for lower, upper in bounds
            )
        ),
        "stationarity_thresholds": {
            "projected_gradient_inf_norm": 1e-4,
            "modeled_newton_relative_loss_decrease": 1e-10,
            "undamped_newton_step_inf_norm": 1e-5,
            "damping_to_free_min_eigenvalue": 1e-6,
            "positive_free_curvature_required": True,
        },
        **stationarity,
        "gradient_method": "Analytic finite-set prediction gradient plus omega column sums",
        "curvature_method": (
            "Complete-data/Fisher base JtWJ, exact physical-omega cross block, omega diagonal, "
            "and Gaussian tau/omega priors"
        ),
        "initial_topology": initial_topology,
        "final_topology": final_topology,
        "optimizer_terminal_topology": final_topology,
        "optimizer_terminal_matches_retained": retained_matches_current,
        "disconnected_topology_evaluation_count": disconnected_topology_evaluations,
        "retained_matches_current": retained_matches_current,
        "best_finite_preserved": True,
        "best_connected_finite_preserved": True,
        "omega_shared_across_receivers_and_channels": True,
        "omega_gauge_resolution": (
            "The proper zero-mean Gaussian prior assigns the common omega mode to the free RX "
            "intercepts; the connected likelihood identifies K-1 omega contrasts."
        ),
        "satellite_support": final.likelihood["satellite_support"],
        "null_support": final.likelihood["null_support"],
    }


__all__ = [
    "BiasFisherState",
    "bias_trial_specification",
    "evaluate_bias_fisher_state",
    "fit_satellite_bias_trial",
]
