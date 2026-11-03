from __future__ import annotations

import time

import numpy as np
from solvers import (
    TERMINAL_ATOL,
    TERMINAL_RTOL,
    FixedPosteriorQ,
    _budget,
    _make_objective,
    _minimizer,
    _observed_details,
    _optimizer_scale,
    _result,
    _scaled_minimize,
    _stationarity_receipt,
)
from timing_model import DeadlineReached

FISHER_DAMPING = (1e-4, 1e-2, 1.0, 100.0)
BACKTRACK_FRACTIONS = (1.0, 0.5, 0.25, 0.125, 0.0625)


def _parameter_map(objective):
    vector_size = len(objective.initial_vector)
    mapping = np.zeros((6 + objective.candidate_count, vector_size))
    mapping[:6, :6] = np.eye(6)
    mapping[6 + objective.satellites, 6] = 1.0
    mapping[6 + objective.satellites, 7:] = objective.basis
    return mapping


def _fisher_system(objective, vector, posterior):
    posterior = np.asarray(posterior, dtype=float)
    _predicted, _visible, jacobian = objective.predict(vector, with_jacobian=True)
    weights = (posterior / objective.sigma_hz**2).ravel()
    if hasattr(jacobian, "normal_matrix"):
        physical = jacobian.normal_matrix(weights)
    elif hasattr(jacobian, "matrix"):
        dense = np.asarray(jacobian.matrix, dtype=float)
        physical = dense.T @ (weights[:, None] * dense)
    else:
        raise TypeError("prediction Jacobian must provide normal_matrix")
    mapping = _parameter_map(objective)
    hessian = mapping.T @ physical @ mapping
    hessian[6, 6] += 1.0 / 100.0
    hessian[7:, 7:] += np.eye(len(vector) - 7)
    return hessian


def _damped_fisher_proposals(objective, vector, gradient, hessian):
    scale = _optimizer_scale(len(vector))
    scaled_gradient = scale * gradient
    scaled_hessian = scale[:, None] * hessian * scale[None, :]
    identity = np.eye(len(vector))
    for damping in FISHER_DAMPING:
        try:
            scaled_step = np.linalg.solve(
                scaled_hessian + damping * identity,
                -scaled_gradient,
            )
        except np.linalg.LinAlgError:
            continue
        if np.any(~np.isfinite(scaled_step)):
            continue
        physical_step = scale * scaled_step
        for fraction in BACKTRACK_FRACTIONS:
            yield damping, fraction, vector + fraction * physical_step


def _strong_stationarity(objective, details, terminal_valid):
    receipt = _stationarity_receipt(objective, details, terminal_valid)
    return receipt, bool(receipt["stationarity_certified"])


def fit_gem(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=30.0,
    max_iterations=5,
    clock=time.monotonic,
    plan_factory=None,
):
    budget_s = _budget(budget_s)
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
    current = objective.initial_vector
    details = _observed_details(objective, current)
    if details is None:
        raise RuntimeError("follow-up GEM initial objective is not finite")
    initial_objective = float(details["objective"])
    observed_history = [initial_objective]
    q_history = []
    deadline_reached = False
    status = "iteration_limit"
    stationarity = None

    for iteration in range(int(max_iterations)):
        try:
            objective.check_deadline()
            posterior = np.asarray(
                details["likelihood"]["row_association_probability"],
                dtype=float,
            )
            q_objective = FixedPosteriorQ(objective, current, posterior)
            q_start, q_gradient = q_objective.evaluate(current)
            hessian = _fisher_system(objective, current, posterior)
            accepted = None
            accepted_details = None
            accepted_q = None
            accepted_damping = None
            accepted_fraction = None
            attempted = 0
            for damping, fraction, candidate in _damped_fisher_proposals(
                objective,
                current,
                q_gradient,
                hessian,
            ):
                attempted += 1
                q_candidate, _ = q_objective.evaluate(candidate)
                required = 1e-10 * max(1.0, abs(q_start))
                if not q_candidate < q_start - required:
                    continue
                candidate_details = _observed_details(objective, candidate)
                if candidate_details is None:
                    continue
                if candidate_details["objective"] > details["objective"] + 1e-9:
                    continue
                accepted = candidate
                accepted_details = candidate_details
                accepted_q = float(q_candidate)
                accepted_damping = float(damping)
                accepted_fraction = float(fraction)
                break
            q_history.append(
                {
                    "iteration": iteration,
                    "start": float(q_start),
                    "accepted": accepted_q,
                    "damping": accepted_damping,
                    "fraction": accepted_fraction,
                    "attempted_candidates": attempted,
                }
            )
            if accepted is None:
                stationarity, certified = _strong_stationarity(
                    objective,
                    details,
                    True,
                )
                status = (
                    "projected_stationary_active_gate_branch"
                    if certified
                    else "no_feasible_monotone_fisher_step"
                )
                break
            current = accepted
            details = accepted_details
            observed_history.append(float(details["objective"]))
        except DeadlineReached:
            deadline_reached = True
            status = "limit_reached_best_accepted"
            break

    if stationarity is None:
        stationarity, certified = _strong_stationarity(
            objective,
            details,
            status == "iteration_limit",
        )
        if certified:
            status = "projected_stationary_active_gate_branch"
    return _result(
        objective,
        details,
        method="followup_gem_damped_fisher",
        status=status,
        success=stationarity["stationarity_certified"],
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": True,
            "initial_objective": initial_objective,
            "observed_objective_history": observed_history,
            "fixed_posterior_q_history": q_history,
            "observed_monotone": bool(
                np.all(np.diff(observed_history) <= 1e-9)
            ),
            "best_is_terminal": True,
            "deadline_reached": deadline_reached,
            **stationarity,
            "convergence_basis": (
                "Damped complete-data Fisher step with frozen exact row posterior, "
                "alias branches, visibility, and active hard-gate support"
            ),
        },
    )


def _block_evaluator(objective, base, block):
    base = np.asarray(base, dtype=float).copy()
    block = np.asarray(block, dtype=int).copy()

    def evaluate(values):
        candidate = base.copy()
        candidate[block] = values
        value, gradient = objective.evaluate(candidate)
        return value, gradient[block]

    return evaluate


def fit_block_observed(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=30.0,
    max_cycles=8,
    minimizer=None,
    clock=time.monotonic,
    plan_factory=None,
):
    budget_s = _budget(budget_s)
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
    optimize = _minimizer(minimizer)
    current = objective.initial_vector
    details = _observed_details(objective, current)
    if details is None:
        raise RuntimeError("follow-up block initial objective is not finite")
    initial_objective = float(details["objective"])
    observed_history = [initial_objective]
    deadline_reached = False
    status = "cycle_limit"
    stationarity = None
    blocks = [np.arange(7), np.arange(7, len(current))]

    try:
        for _cycle in range(int(max_cycles)):
            changed = False
            cycle_terminal_valid = True
            for block in blocks:
                if not len(block):
                    continue
                base = current.copy()
                fitted = _scaled_minimize(
                    optimize,
                    _block_evaluator(objective, base, block),
                    current[block],
                    [objective.bounds[index] for index in block],
                    lambda _vector: objective.check_deadline(),
                    {
                        "maxiter": 5,
                        "maxfun": 25,
                        "ftol": 1e-10,
                        "gtol": 1e-5,
                    },
                    _optimizer_scale(len(current))[block],
                )
                candidate = current.copy()
                candidate[block] = np.asarray(fitted.x, dtype=float)
                candidate_details = _observed_details(objective, candidate)
                cycle_terminal_valid &= bool(
                    getattr(fitted, "success", False)
                    and candidate_details is not None
                )
                if candidate_details is None:
                    continue
                if candidate_details["objective"] > details["objective"] + 1e-9:
                    continue
                changed |= candidate_details["objective"] < details["objective"] - 1e-9
                current = candidate
                details = candidate_details
                observed_history.append(float(details["objective"]))
            if not changed:
                stationarity, certified = _strong_stationarity(
                    objective,
                    details,
                    cycle_terminal_valid,
                )
                status = (
                    "projected_stationary_active_gate_branch"
                    if certified
                    else "no_accepted_block_improvement"
                )
                break
    except DeadlineReached:
        deadline_reached = True
        status = "limit_reached_best_finite"

    retained = objective.best if objective.best is not None else details
    best_is_terminal = bool(
        np.allclose(
            retained["vector"],
            current,
            rtol=TERMINAL_RTOL,
            atol=TERMINAL_ATOL,
        )
    )
    if not best_is_terminal:
        status = (
            "limit_reached_best_finite_nonterminal"
            if deadline_reached
            else "best_finite_nonterminal"
        )
        stationarity = None
    if stationarity is None:
        stationarity = {
            "stationarity_certified": False,
            "stationarity_scope": (
                "not certified for retained nonterminal or interrupted block state"
            ),
            "projected_gradient_inf_norm": None,
            "stationarity_gtol": 1e-4,
            "stationarity_terminal_valid": False,
            "active_gate_interior": None,
            "minimum_active_gate_margin_hz": None,
        }
    if retained["objective"] < min(observed_history) - 1e-9:
        observed_history.append(float(retained["objective"]))
    return _result(
        objective,
        retained,
        method="followup_alternating_observed_blocks_best_finite",
        status=status,
        success=bool(
            best_is_terminal and stationarity["stationarity_certified"]
        ),
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": False,
            "initial_objective": initial_objective,
            "observed_objective_history": observed_history,
            "observed_monotone": bool(
                np.all(np.diff(observed_history) <= 1e-9)
            ),
            "best_is_terminal": best_is_terminal,
            "deadline_reached": deadline_reached,
            **stationarity,
            "convergence_basis": (
                "Short bounded observed-likelihood block solves; retain best finite "
                "evaluation even when an inner solve is interrupted"
            ),
        },
    )


fit_block = fit_block_observed


__all__ = ["fit_block", "fit_block_observed", "fit_gem"]
