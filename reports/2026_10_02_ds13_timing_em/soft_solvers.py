from __future__ import annotations

import copy
import time

import numpy as np
from solvers import (
    TERMINAL_ATOL,
    TERMINAL_RTOL,
    _make_objective,
    _minimizer,
    _observed_details,
    _optimizer_scale,
    _result,
    _scaled_minimize,
)
from timing_model import DeadlineReached

MAX_BUDGET_S = 90.0
DEFAULT_MAX_ITERATIONS = 500
PROJECTED_GRADIENT_GTOL = 1.0e-3
NORMALIZED_PROJECTED_GRADIENT_GTOL = 1.0e-4
NORMALIZED_NEWTON_DECREMENT_TOL = 1.0e-3
ARMIJO_COEFFICIENT = 1.0e-4
MIN_STEP_FRACTION = 2.0**-12
INITIAL_DAMPING = 1.0e-6
MIN_DAMPING = 1.0e-12
MAX_DAMPING = 1.0e8


def _budget(budget_s):
    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_BUDGET_S:
        raise ValueError("budget_s must lie in (0, 90]")
    return float(budget_s)


def _parameter_map(objective):
    vector_size = len(objective.initial_vector)
    mapping = np.zeros((6 + objective.candidate_count, vector_size))
    mapping[:6, :6] = np.eye(6)
    mapping[6 + objective.satellites, 6] = 1.0
    mapping[6 + objective.satellites, 7:] = objective.basis
    return mapping


def _normal_matrix(jacobian, weights):
    weights = np.asarray(weights, dtype=float).ravel()
    if hasattr(jacobian, "normal_matrix"):
        matrix = np.asarray(jacobian.normal_matrix(weights), dtype=float)
    elif hasattr(jacobian, "matrix"):
        dense = np.asarray(jacobian.matrix, dtype=float)
        matrix = dense.T @ (weights[:, None] * dense)
    else:
        raise TypeError("prediction Jacobian must provide normal_matrix")
    return 0.5 * (matrix + matrix.T)


def _fisher_system(objective, vector, details):
    posterior = np.asarray(
        details["likelihood"]["row_association_probability"],
        dtype=float,
    )
    predicted, visible, jacobian = objective.predict(vector, with_jacobian=True)
    if posterior.shape != predicted.shape:
        raise ValueError("row_association_probability has the wrong shape")
    if np.any(~np.isfinite(posterior)) or np.any(posterior < 0):
        raise ValueError("row_association_probability must be finite and nonnegative")
    weights = posterior * visible / objective.sigma_hz**2
    mapping = _parameter_map(objective)
    physical = _normal_matrix(jacobian, weights)
    hessian = mapping.T @ physical @ mapping
    if objective.common_prior:
        hessian[6, 6] += 1.0 / 100.0
    hessian[7:, 7:] += np.eye(len(vector) - 7)
    return 0.5 * (hessian + hessian.T), visible


def _project_bounds(vector, bounds):
    projected = np.asarray(vector, dtype=float).copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None:
            projected[index] = max(projected[index], lower)
        if upper is not None:
            projected[index] = min(projected[index], upper)
    return projected


def _scaled_projected_gradient(vector, gradient, bounds, scale):
    vector = np.asarray(vector, dtype=float)
    gradient = np.asarray(gradient, dtype=float)
    projected = gradient * scale
    free = np.ones(len(vector), dtype=bool)
    for index, (lower, upper) in enumerate(bounds):
        tolerance = 1.0e-9 * max(1.0, abs(vector[index]))
        at_lower = lower is not None and vector[index] <= lower + tolerance
        at_upper = upper is not None and vector[index] >= upper - tolerance
        if (at_lower and gradient[index] > 0) or (at_upper and gradient[index] < 0):
            projected[index] = 0.0
            free[index] = False
    return projected, free


def _stationarity_metrics(objective, details, hessian=None):
    vector = np.asarray(details["vector"], dtype=float)
    gradient = np.asarray(details["gradient"], dtype=float)
    scale = _optimizer_scale(len(vector))
    projected, free = _scaled_projected_gradient(
        vector,
        gradient,
        objective.bounds,
        scale,
    )
    projected_norm = float(np.max(np.abs(projected)))
    objective_scale = max(1.0, abs(float(details["objective"])))
    normalized_projected = projected_norm / objective_scale
    decrement = None
    normalized_decrement = None
    if hessian is not None and np.any(free):
        scaled_hessian = scale[:, None] * hessian * scale[None, :]
        free_hessian = scaled_hessian[np.ix_(free, free)]
        free_gradient = projected[free]
        ridge = INITIAL_DAMPING * max(
            1.0,
            float(np.max(np.diag(free_hessian), initial=0.0)),
        )
        try:
            solution = np.linalg.solve(
                free_hessian + ridge * np.eye(len(free_gradient)),
                free_gradient,
            )
            quadratic = float(free_gradient @ solution)
            if np.isfinite(quadratic) and quadratic >= -1.0e-10:
                decrement = float(np.sqrt(max(0.0, quadratic)))
                normalized_decrement = decrement / np.sqrt(len(free_gradient))
        except np.linalg.LinAlgError:
            pass
    return {
        "projected_gradient_inf_norm": projected_norm,
        "normalized_projected_gradient": normalized_projected,
        "newton_decrement": decrement,
        "normalized_newton_decrement": normalized_decrement,
    }


def _visibility_probe_stable(objective, details, visible):
    vector = np.asarray(details["vector"], dtype=float)
    gradient = np.asarray(details["gradient"], dtype=float)
    scale = _optimizer_scale(len(vector))
    projected, _free = _scaled_projected_gradient(
        vector,
        gradient,
        objective.bounds,
        scale,
    )
    norm = float(np.linalg.norm(projected))
    if norm == 0.0:
        direction = np.ones(len(vector), dtype=float) / np.sqrt(len(vector))
    else:
        direction = -projected / norm
    stable = True
    for sign in (-1.0, 1.0):
        probe = _project_bounds(
            vector + sign * 1.0e-6 * scale * direction,
            objective.bounds,
        )
        if not objective.state(probe)["ephemeris_valid"]:
            stable = False
            continue
        _prediction, probe_visible = objective.predict(probe)
        stable &= bool(np.array_equal(probe_visible, visible))
    return bool(stable)


def _stationarity_receipt(
    objective,
    details,
    hessian,
    visible,
    *,
    terminal_valid,
):
    metrics = _stationarity_metrics(objective, details, hessian)
    visibility_stable = _visibility_probe_stable(objective, details, visible)
    decrement = metrics["normalized_newton_decrement"]
    certified = bool(
        terminal_valid
        and details["ephemeris_valid"]
        and visibility_stable
        and metrics["projected_gradient_inf_norm"] <= PROJECTED_GRADIENT_GTOL
        and metrics["normalized_projected_gradient"]
        <= NORMALIZED_PROJECTED_GRADIENT_GTOL
        and decrement is not None
        and decrement <= NORMALIZED_NEWTON_DECREMENT_TOL
    )
    return {
        **metrics,
        "stationarity_certified": certified,
        "stationarity_scope": (
            "scaled projected gradient and Fisher Newton decrement on the "
            "locally probed visibility branch"
        ),
        "stationarity_terminal_valid": bool(terminal_valid),
        "visibility_probe_stable": visibility_stable,
        "projected_gradient_gtol": PROJECTED_GRADIENT_GTOL,
        "normalized_projected_gradient_gtol": (
            NORMALIZED_PROJECTED_GRADIENT_GTOL
        ),
        "normalized_newton_decrement_tol": NORMALIZED_NEWTON_DECREMENT_TOL,
    }


def _metrics_meet_tolerances(metrics):
    decrement = metrics["normalized_newton_decrement"]
    return bool(
        metrics["projected_gradient_inf_norm"] <= PROJECTED_GRADIENT_GTOL
        and metrics["normalized_projected_gradient"]
        <= NORMALIZED_PROJECTED_GRADIENT_GTOL
        and decrement is not None
        and decrement <= NORMALIZED_NEWTON_DECREMENT_TOL
    )


def _fisher_direction(objective, details, hessian, damping):
    vector = np.asarray(details["vector"], dtype=float)
    gradient = np.asarray(details["gradient"], dtype=float)
    scale = _optimizer_scale(len(vector))
    projected, free = _scaled_projected_gradient(
        vector,
        gradient,
        objective.bounds,
        scale,
    )
    direction = np.zeros(len(vector), dtype=float)
    if not np.any(free):
        return direction
    scaled_hessian = scale[:, None] * hessian * scale[None, :]
    free_hessian = scaled_hessian[np.ix_(free, free)]
    diagonal_scale = max(
        1.0,
        float(np.max(np.diag(free_hessian), initial=0.0)),
    )
    try:
        direction[free] = np.linalg.solve(
            free_hessian + damping * diagonal_scale * np.eye(np.count_nonzero(free)),
            -projected[free],
        )
    except np.linalg.LinAlgError:
        return np.full(len(vector), np.nan)
    return scale * direction


def _same_vector(left, right):
    return bool(
        np.allclose(
            np.asarray(left, dtype=float),
            np.asarray(right, dtype=float),
            rtol=TERMINAL_RTOL,
            atol=TERMINAL_ATOL,
        )
    )


def _best_details(objective, fallback):
    if objective.best is None:
        return fallback
    return copy.deepcopy(objective.best)


def _fit_fisher(objective, started, budget_s, max_iterations):
    current = objective.initial_vector
    details = _observed_details(objective, current)
    if details is None:
        raise RuntimeError("soft Fisher initial objective is not finite")
    initial_objective = float(details["objective"])
    objective_trace = [initial_objective]
    accepted_trace = []
    iteration_trace = []
    deadline_reached = False
    status = "iteration_limit"
    damping = INITIAL_DAMPING
    hessian = None
    visible = None

    for iteration in range(int(max_iterations)):
        try:
            objective.check_deadline()
            hessian, visible = _fisher_system(objective, current, details)
            metrics = _stationarity_metrics(objective, details, hessian)
            if _metrics_meet_tolerances(metrics):
                receipt = _stationarity_receipt(
                    objective,
                    details,
                    hessian,
                    visible,
                    terminal_valid=True,
                )
                if receipt["stationarity_certified"]:
                    status = "projected_stationary_visibility_branch"
                    break
            accepted = None
            accepted_details = None
            accepted_visible = None
            attempted = 0
            trial_damping = damping
            accepted_fraction = None
            accepted_damping = None
            visibility_changes = 0
            for _damping_attempt in range(9):
                direction = _fisher_direction(
                    objective,
                    details,
                    hessian,
                    trial_damping,
                )
                if np.any(~np.isfinite(direction)):
                    trial_damping *= 10.0
                    continue
                for fraction in 2.0 ** -np.arange(13):
                    if fraction < MIN_STEP_FRACTION:
                        break
                    candidate = _project_bounds(
                        current + fraction * direction,
                        objective.bounds,
                    )
                    step = candidate - current
                    directional_derivative = float(details["gradient"] @ step)
                    if directional_derivative >= 0.0 or not np.any(step):
                        continue
                    if not objective.state(candidate)["ephemeris_valid"]:
                        continue
                    attempted += 1
                    candidate_details = _observed_details(objective, candidate)
                    if candidate_details is None:
                        continue
                    objective.check_deadline()
                    candidate_visible = objective.predict(candidate)[1]
                    visibility_changes += int(
                        not np.array_equal(candidate_visible, visible)
                    )
                    armijo_limit = (
                        details["objective"]
                        + ARMIJO_COEFFICIENT * directional_derivative
                    )
                    if candidate_details["objective"] > armijo_limit:
                        continue
                    accepted = candidate
                    accepted_details = candidate_details
                    accepted_visible = candidate_visible
                    accepted_fraction = float(fraction)
                    accepted_damping = float(trial_damping)
                    break
                if accepted is not None:
                    break
                trial_damping *= 10.0
                if trial_damping > MAX_DAMPING:
                    break
            iteration_trace.append(
                {
                    "iteration": iteration,
                    "objective_before": float(details["objective"]),
                    "objective_after": (
                        None
                        if accepted_details is None
                        else float(accepted_details["objective"])
                    ),
                    "damping": accepted_damping,
                    "step_fraction": accepted_fraction,
                    "attempted_candidates": attempted,
                    "visibility_change_candidates": visibility_changes,
                    **metrics,
                }
            )
            if accepted is None:
                receipt = _stationarity_receipt(
                    objective,
                    details,
                    hessian,
                    visible,
                    terminal_valid=True,
                )
                status = (
                    "projected_stationary_visibility_branch"
                    if receipt["stationarity_certified"]
                    else "no_monotone_fisher_step_nonstationary"
                )
                break
            current = accepted
            details = accepted_details
            visible = accepted_visible
            objective_trace.append(float(details["objective"]))
            accepted_metrics = _stationarity_metrics(objective, details)
            accepted_trace.append(
                {
                    "iteration": iteration,
                    "elapsed_s": float(objective.clock() - started),
                    "objective": float(details["objective"]),
                    "projected_gradient_inf_norm": accepted_metrics[
                        "projected_gradient_inf_norm"
                    ],
                    "vector": current.copy(),
                }
            )
            damping = max(MIN_DAMPING, accepted_damping / 10.0)
        except DeadlineReached:
            deadline_reached = True
            status = "limit_reached_best_finite"
            break

    retained = _best_details(objective, details)
    best_is_terminal = _same_vector(retained["vector"], current)
    if retained["objective"] < min(objective_trace) - 1.0e-12:
        objective_trace.append(float(retained["objective"]))
    receipt = None
    if best_is_terminal and not deadline_reached:
        try:
            if not _same_vector(details["vector"], retained["vector"]):
                refreshed = _observed_details(objective, retained["vector"])
                if refreshed is not None:
                    details = refreshed
            hessian, visible = _fisher_system(objective, retained["vector"], details)
            receipt = _stationarity_receipt(
                objective,
                retained,
                hessian,
                visible,
                terminal_valid=True,
            )
        except DeadlineReached:
            deadline_reached = True
            status = "limit_reached_best_finite"
    if receipt is None:
        receipt = {
            **_stationarity_metrics(objective, retained),
            "stationarity_certified": False,
            "stationarity_scope": (
                "not certified for an interrupted or nonterminal retained state"
            ),
            "stationarity_terminal_valid": False,
            "visibility_probe_stable": None,
            "projected_gradient_gtol": PROJECTED_GRADIENT_GTOL,
            "normalized_projected_gradient_gtol": (
                NORMALIZED_PROJECTED_GRADIENT_GTOL
            ),
            "normalized_newton_decrement_tol": (
                NORMALIZED_NEWTON_DECREMENT_TOL
            ),
        }
    elif receipt["stationarity_certified"]:
        status = "projected_stationary_visibility_branch"
    if deadline_reached and not best_is_terminal:
        status = "limit_reached_best_finite_nonterminal"
    return _result(
        objective,
        retained,
        method="soft_damped_complete_data_fisher_observed_descent",
        status=status,
        success=receipt["stationarity_certified"],
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": False,
            "soft_likelihood": True,
            "initial_objective": initial_objective,
            "objective_trace": objective_trace,
            "observed_objective_history": objective_trace,
            "observed_monotone": bool(np.all(np.diff(objective_trace) <= 1.0e-9)),
            "accepted_trace": accepted_trace,
            "iteration_trace": iteration_trace,
            "best_is_terminal": best_is_terminal,
            "deadline_reached": deadline_reached,
            "optimizer_reported_success": False,
            **receipt,
            "convergence_basis": (
                "Posterior-weighted complete-data Fisher curvature with bounded "
                "scaled steps and true soft observed-objective Armijo acceptance; "
                "this is not EM"
            ),
            "message": status,
        },
    )


def _fit_lbfgsb(objective, started, budget_s, max_iterations, minimizer):
    start = objective.initial_vector
    initial_value, _gradient = objective.evaluate(start)
    optimize = _minimizer(minimizer)
    fitted = None
    deadline_reached = False
    try:
        fitted = _scaled_minimize(
            optimize,
            objective.evaluate,
            start,
            objective.bounds,
            lambda _vector: objective.check_deadline(),
            {
                "maxiter": int(max_iterations),
                "maxfun": max(50, 4 * int(max_iterations)),
                "ftol": 1.0e-12,
                "gtol": 1.0e-7,
            },
            _optimizer_scale(len(start)),
        )
    except DeadlineReached:
        deadline_reached = True
    if objective.best is None:
        raise RuntimeError("soft L-BFGS-B produced no finite valid evaluation")
    retained = objective.best
    terminal = np.asarray(getattr(fitted, "x", np.empty(0)), dtype=float)
    best_is_terminal = bool(
        terminal.shape == retained["vector"].shape
        and np.all(np.isfinite(terminal))
        and _same_vector(terminal, retained["vector"])
    )
    reported_success = bool(fitted is not None and getattr(fitted, "success", False))
    receipt = {
        **_stationarity_metrics(objective, retained),
        "stationarity_certified": False,
        "stationarity_scope": (
            "not certified without a posterior Fisher curvature receipt"
        ),
        "stationarity_terminal_valid": bool(best_is_terminal and reported_success),
        "visibility_probe_stable": None,
        "projected_gradient_gtol": PROJECTED_GRADIENT_GTOL,
        "normalized_projected_gradient_gtol": NORMALIZED_PROJECTED_GRADIENT_GTOL,
        "normalized_newton_decrement_tol": NORMALIZED_NEWTON_DECREMENT_TOL,
    }
    if deadline_reached:
        status = (
            "limit_reached_best_finite"
            if best_is_terminal
            else "limit_reached_best_finite_nonterminal"
        )
    elif reported_success and best_is_terminal:
        status = "optimizer_stopped_stationarity_unverified"
    elif not best_is_terminal:
        status = "best_finite_nonterminal"
    else:
        status = "optimizer_stopped"
    objective_trace = [float(initial_value)]
    if retained["objective"] < initial_value - 1.0e-12:
        objective_trace.append(float(retained["objective"]))
    return _result(
        objective,
        retained,
        method="soft_bounded_scaled_lbfgsb",
        status=status,
        success=False,
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": False,
            "soft_likelihood": True,
            "initial_objective": float(initial_value),
            "objective_trace": objective_trace,
            "observed_objective_history": objective_trace,
            "observed_monotone": True,
            "accepted_trace": [
                {
                    "iteration": 0,
                    "elapsed_s": float(objective.clock() - started),
                    "objective": float(retained["objective"]),
                    "projected_gradient_inf_norm": receipt[
                        "projected_gradient_inf_norm"
                    ],
                    "vector": np.asarray(retained["vector"], dtype=float).copy(),
                }
            ],
            "iteration_trace": [],
            "best_is_terminal": best_is_terminal,
            "deadline_reached": deadline_reached,
            "optimizer_reported_success": reported_success,
            **receipt,
            "convergence_basis": (
                "Bounded scaled L-BFGS-B fallback; optimizer termination alone is "
                "not accepted as a scientific stationarity certificate"
            ),
            "message": str(getattr(fitted, "message", status)),
        },
    )


def fit_soft(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=60.0,
    method="fisher",
    max_iterations=DEFAULT_MAX_ITERATIONS,
    minimizer=None,
    clock=time.monotonic,
    plan_factory=None,
):
    """Fit the ungated DS13 objective without changing its likelihood contract."""
    budget_s = _budget(budget_s)
    if isinstance(max_iterations, bool) or int(max_iterations) != max_iterations:
        raise ValueError("max_iterations must be a positive integer")
    max_iterations = int(max_iterations)
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    if method not in {"fisher", "lbfgsb"}:
        raise ValueError("method must be 'fisher' or 'lbfgsb'")
    objective, started = _make_objective(
        data,
        initial_parameters,
        satellites,
        likelihood,
        sigma_hz,
        budget_s,
        clock,
        plan_factory,
    )
    if method == "fisher":
        return _fit_fisher(objective, started, budget_s, max_iterations)
    return _fit_lbfgsb(
        objective,
        started,
        budget_s,
        max_iterations,
        minimizer,
    )


__all__ = ["fit_soft"]
