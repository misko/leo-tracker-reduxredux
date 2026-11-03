from __future__ import annotations

import copy
import time

import numpy as np

from timing_model import (
    DeadlineReached,
    GLOBAL_SHIFT_BOUND_S,
    GLOBAL_SHIFT_SIGMA_S,
    INDIVIDUAL_SHIFT_SIGMA_S,
    INVALID_OBJECTIVE,
    TimingObjective,
)


MAX_BUDGET_S = 30.0
TERMINAL_RTOL = 1e-10
TERMINAL_ATOL = 1e-9
STATIONARITY_GTOL = 1e-4
BASE_OPTIMIZER_SCALE = np.array([20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, 1.0])


def _budget(budget_s):
    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_BUDGET_S:
        raise ValueError("budget_s must lie in (0, 30]")
    return float(budget_s)


def _minimizer(minimizer):
    if minimizer is not None:
        return minimizer
    from scipy.optimize import minimize

    return minimize


def _optimizer_scale(size):
    if size < len(BASE_OPTIMIZER_SCALE):
        raise ValueError("optimizer vector is shorter than the common DS13 model")
    return np.r_[BASE_OPTIMIZER_SCALE, np.ones(size - len(BASE_OPTIMIZER_SCALE))]


def _scaled_minimize(optimize, function, start, bounds, callback, options, scale):
    start = np.asarray(start, dtype=float)
    scale = np.asarray(scale, dtype=float)
    scaled_bounds = [
        (
            None if lower is None else lower / factor,
            None if upper is None else upper / factor,
        )
        for (lower, upper), factor in zip(bounds, scale, strict=True)
    ]

    def scaled_function(scaled_vector):
        value, gradient = function(np.asarray(scaled_vector, dtype=float) * scale)
        return value, np.asarray(gradient, dtype=float) * scale

    def scaled_callback(scaled_vector):
        callback(np.asarray(scaled_vector, dtype=float) * scale)

    fitted = optimize(
        scaled_function,
        start / scale,
        jac=True,
        method="L-BFGS-B",
        bounds=scaled_bounds,
        callback=scaled_callback,
        options=options,
    )
    converted = copy.copy(fitted)
    converted.x = np.asarray(getattr(fitted, "x", start / scale), dtype=float) * scale
    return converted


def _projected_gradient_inf_norm(vector, gradient, bounds):
    vector = np.asarray(vector, dtype=float)
    gradient = np.asarray(gradient, dtype=float)
    projected = gradient * _optimizer_scale(len(vector))
    for index, (lower, upper) in enumerate(bounds):
        tolerance = 1e-9 * max(1.0, abs(vector[index]))
        if lower is not None and vector[index] <= lower + tolerance and gradient[index] > 0:
            projected[index] = 0.0
        if upper is not None and vector[index] >= upper - tolerance and gradient[index] < 0:
            projected[index] = 0.0
    return float(np.max(np.abs(projected)))


def _stationarity_receipt(objective, details, terminal_valid):
    norm = _projected_gradient_inf_norm(
        details["vector"], details["gradient"], objective.bounds
    )
    posterior = np.asarray(
        details["likelihood"]["row_association_probability"], dtype=float
    )
    active = posterior > 0
    gate_hz = float(getattr(objective.likelihood, "gate_hz", np.inf))
    minimum_gate_margin = None
    gate_interior = True
    if np.isfinite(gate_hz):
        if not np.any(active):
            gate_interior = False
        else:
            predicted, _visible = objective.predict(details["vector"])
            if hasattr(objective.likelihood, "alias_hz"):
                alias_hz = float(objective.likelihood.alias_hz)
            else:
                alias_hz = float(objective.likelihood.prepared.alias_hz)
            measured = np.asarray(objective.data.measured, dtype=float)[:, None]
            residual = (measured - predicted + alias_hz / 2) % alias_hz - alias_hz / 2
            minimum_gate_margin = float(np.min(gate_hz - np.abs(residual[active])))
            gate_interior = minimum_gate_margin > max(1e-6, gate_hz * 1e-9)
    certified = bool(
        terminal_valid
        and details["ephemeris_valid"]
        and gate_interior
        and norm <= STATIONARITY_GTOL
    )
    return {
        "stationarity_certified": certified,
        "stationarity_scope": "scaled projected gradient on current active hard-gate branch",
        "projected_gradient_inf_norm": norm,
        "stationarity_gtol": STATIONARITY_GTOL,
        "stationarity_terminal_valid": bool(terminal_valid),
        "active_gate_interior": bool(gate_interior),
        "minimum_active_gate_margin_hz": minimum_gate_margin,
    }


def _result(objective, details, *, method, status, success, started, budget_s, extra=None):
    state = objective.state(details["vector"])
    result = {
        "method": method,
        "status": status,
        "success": bool(success),
        "objective": float(details["objective"]),
        "data_objective": float(details["data_objective"]),
        "prior_objective": float(details["prior_objective"]),
        "parameters": state["parameters"].copy(),
        "global_shift_s": state["global_shift_s"],
        "individual_shifts_s": state["individual_shifts_s"].copy(),
        "total_shifts_s": state["total_shifts_s"].copy(),
        "satellite_indices": objective.satellites.copy(),
        "vector": np.asarray(details["vector"], dtype=float).copy(),
        "calls": int(objective.calls),
        "elapsed_s": float(objective.clock() - started),
        "budget_s": float(budget_s),
        "global_shift_bound_s": GLOBAL_SHIFT_BOUND_S,
        "global_shift_prior_sigma_s": GLOBAL_SHIFT_SIGMA_S,
        "individual_shift_prior_sigma_s": INDIVIDUAL_SHIFT_SIGMA_S,
        "individual_shift_bound_s": None,
        "timing_gauge": "unweighted zero-sum orthonormal nullspace",
        "optimizer_scale": _optimizer_scale(len(details["vector"])),
    }
    if extra:
        result.update(extra)
    return result


def _make_objective(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    budget_s,
    clock,
    plan_factory,
):
    started = clock()
    options = {"deadline": started + budget_s, "clock": clock}
    if plan_factory is not None:
        options["plan_factory"] = plan_factory
    objective = TimingObjective(
        data,
        initial_parameters,
        satellites,
        likelihood,
        sigma_hz,
        **options,
    )
    return objective, started


def fit_direct(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=30.0,
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
    start = objective.initial_vector
    initial_value, _ = objective.evaluate(start)
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
            {"maxiter": 500, "maxfun": 800, "ftol": 1e-10, "gtol": 1e-5},
            _optimizer_scale(len(start)),
        )
    except DeadlineReached:
        deadline_reached = True
    if objective.best is None:
        raise RuntimeError("direct timing optimization produced no finite valid evaluation")
    terminal = np.asarray(getattr(fitted, "x", np.empty(0)), dtype=float)
    best_is_terminal = bool(
        terminal.shape == objective.best["vector"].shape
        and np.all(np.isfinite(terminal))
        and np.allclose(
            terminal,
            objective.best["vector"],
            rtol=TERMINAL_RTOL,
            atol=TERMINAL_ATOL,
        )
    )
    reported_success = bool(fitted is not None and getattr(fitted, "success", False))
    success = reported_success and best_is_terminal and not deadline_reached
    if deadline_reached:
        status = "limit_reached"
    elif reported_success and not best_is_terminal:
        status = "best_retained_nonterminal"
    elif success:
        status = "optimizer_converged"
    else:
        status = "optimizer_stopped"
    terminal_objective = getattr(fitted, "fun", None) if fitted is not None else None
    if terminal_objective is not None and np.isfinite(terminal_objective):
        terminal_objective = float(terminal_objective)
    else:
        terminal_objective = None
    return _result(
        objective,
        objective.best,
        method="direct_bounded_lbfgsb",
        status=status,
        success=success,
        started=started,
        budget_s=budget_s,
        extra={
            "initial_objective": float(initial_value),
            "optimizer_reported_success": reported_success,
            "best_is_terminal": best_is_terminal,
            "terminal_objective": terminal_objective,
            "deadline_reached": deadline_reached,
            "stationarity_certified": False,
            "projected_gradient_inf_norm": _projected_gradient_inf_norm(
                objective.best["vector"], objective.best["gradient"], objective.bounds
            ),
            "stationarity_gtol": STATIONARITY_GTOL,
            "stationarity_scope": "not certified across hard-gate support changes",
            "convergence_basis": (
                "L-BFGS-B reported success and terminal equaled retained best; "
                "hard-gate stationarity was not independently certified"
            ),
            "message": str(getattr(fitted, "message", "deadline reached")),
        },
    )


class FixedPosteriorQ:
    def __init__(self, objective, e_vector, posterior=None):
        self.objective = objective
        self.e_vector = np.asarray(e_vector, dtype=float).copy()
        predicted, visible = objective.predict(self.e_vector)
        if posterior is None:
            objective.evaluate(self.e_vector)
            posterior = objective.last["likelihood"]["row_association_probability"]
        self.posterior = np.asarray(posterior, dtype=float).copy()
        if self.posterior.shape != predicted.shape:
            raise ValueError("row posterior must match prediction rows and satellites")
        if np.any(~np.isfinite(self.posterior)) or np.any(self.posterior < 0):
            raise ValueError("row posterior must be finite and nonnegative")
        measured = np.asarray(objective.data.measured, dtype=float)[:, None]
        alias_hz = float(
            getattr(
                objective.likelihood,
                "alias_hz",
                getattr(getattr(objective.likelihood, "prepared", None), "alias_hz", 1 / 4.4e-6),
            )
        )
        circular = (measured - predicted + alias_hz / 2) % alias_hz - alias_hz / 2
        self.branches = np.rint((measured - predicted - circular) / alias_hz)
        self.alias_hz = alias_hz
        self.active = self.posterior > 0
        self.e_visible = visible.copy()
        self.gate_hz = float(getattr(objective.likelihood, "gate_hz", np.inf))
        if np.any(self.active & ~visible):
            raise ValueError("positive posterior mass requires visible E-step support")

    def evaluate(self, vector):
        self.objective.check_deadline()
        state = self.objective.state(vector)
        if not state["ephemeris_valid"]:
            return self.objective._invalid_ephemeris(np.asarray(vector, dtype=float), state)
        predicted, visible, jacobian = self.objective.predict(vector, with_jacobian=True)
        measured = np.asarray(self.objective.data.measured, dtype=float)[:, None]
        residual = measured - predicted - self.branches * self.alias_hz
        visibility_changed = np.any(visible != self.e_visible)
        support_violation = self.active & (
            ~visible | ~np.isfinite(residual) | (np.abs(residual) > self.gate_hz)
        )
        if visibility_changed or np.any(support_violation):
            excess = np.maximum(np.abs(residual[support_violation]) - self.gate_hz, 0.0)
            return INVALID_OBJECTIVE + float(np.sum(excess**2)), np.zeros_like(vector)
        scaled = residual / self.objective.sigma_hz
        data_value = 0.5 * float(np.sum(self.posterior * scaled**2))
        prediction_score = -self.posterior * residual / self.objective.sigma_hz**2
        physical_gradient = jacobian.transpose_multiply(prediction_score.ravel())
        penalty_value, penalty_gradient = self.objective.penalty(vector)
        gradient = self.objective.vector_gradient(physical_gradient, vector) + penalty_gradient
        return data_value + penalty_value, gradient


def _observed_details(objective, vector):
    value, _ = objective.evaluate(vector)
    if (
        objective.last is None
        or not np.isfinite(value)
        or not np.array_equal(objective.last["vector"], np.asarray(vector, dtype=float))
    ):
        return None
    return objective.last


def fit_gem(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=30.0,
    max_iterations=8,
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
        raise RuntimeError("GEM initial observed objective is not finite")
    initial_objective = details["objective"]
    history = [float(initial_objective)]
    q_history = []
    deadline_reached = False
    status = "iteration_limit"
    stationarity = None
    for _iteration in range(int(max_iterations)):
        try:
            objective.check_deadline()
            posterior = details["likelihood"]["row_association_probability"]
            q_objective = FixedPosteriorQ(objective, current, posterior)
            q_start, _ = q_objective.evaluate(current)
            fitted = _scaled_minimize(
                optimize,
                q_objective.evaluate,
                current,
                objective.bounds,
                lambda _vector: objective.check_deadline(),
                {"maxiter": 80, "maxfun": 150, "ftol": 1e-11, "gtol": 1e-5},
                _optimizer_scale(len(current)),
            )
            proposal = np.asarray(getattr(fitted, "x", current), dtype=float)
            q_end, _ = q_objective.evaluate(proposal)
            accepted = None
            accepted_details = None
            if q_end <= q_start + 1e-9:
                candidate_details = _observed_details(objective, proposal)
                if (
                    candidate_details is not None
                    and candidate_details["objective"] <= details["objective"] + 1e-9
                ):
                    accepted = proposal
                    accepted_details = candidate_details
            if accepted is None:
                for fraction in (0.5, 0.25, 0.125, 0.0625):
                    candidate = current + fraction * (proposal - current)
                    q_candidate, _ = q_objective.evaluate(candidate)
                    if q_candidate > q_start + 1e-9:
                        continue
                    candidate_details = _observed_details(objective, candidate)
                    if (
                        candidate_details is not None
                        and candidate_details["objective"] <= details["objective"] + 1e-9
                    ):
                        accepted = candidate
                        accepted_details = candidate_details
                        q_end = q_candidate
                        break
            q_history.append({"start": float(q_start), "accepted": None if accepted is None else float(q_end)})
            if accepted is None:
                status = "no_monotone_m_step"
                break
            improvement = details["objective"] - accepted_details["objective"]
            current = accepted
            details = accepted_details
            history.append(float(details["objective"]))
            if improvement <= 1e-8 * max(1.0, abs(details["objective"])):
                terminal_valid = bool(
                    getattr(fitted, "success", False)
                    and np.allclose(
                        accepted,
                        proposal,
                        rtol=TERMINAL_RTOL,
                        atol=TERMINAL_ATOL,
                    )
                )
                stationarity = _stationarity_receipt(
                    objective, details, terminal_valid
                )
                status = (
                    "projected_stationary_active_gate_branch"
                    if stationarity["stationarity_certified"]
                    else "small_monotone_step_stationarity_unverified"
                )
                break
        except DeadlineReached:
            deadline_reached = True
            status = "limit_reached"
            break
    if stationarity is None:
        stationarity = _stationarity_receipt(objective, details, False)
    success = bool(stationarity["stationarity_certified"])
    return _result(
        objective,
        details,
        method="generalized_em_fixed_row_posterior",
        status=status,
        success=success,
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": True,
            "initial_objective": float(initial_objective),
            "observed_objective_history": history,
            "fixed_posterior_q_history": q_history,
            "observed_monotone": bool(np.all(np.diff(history) <= 1e-9)),
            "best_is_terminal": True,
            "deadline_reached": deadline_reached,
            **stationarity,
            "convergence_basis": (
                "GEM enforces fixed-posterior Q and observed-objective monotonicity; "
                "small improvement does not certify stationarity at hard gates"
            ),
        },
    )


def fit_block_observed(
    data,
    initial_parameters,
    satellites,
    likelihood,
    sigma_hz,
    *,
    budget_s=30.0,
    max_cycles=5,
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
    history = [float(details["objective"])]
    status = "cycle_limit"
    deadline_reached = False
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

                def reduced(values):
                    candidate = base.copy()
                    candidate[block] = values
                    value, gradient = objective.evaluate(candidate)
                    return value, gradient[block]

                block_bounds = [objective.bounds[index] for index in block]
                fitted = _scaled_minimize(
                    optimize,
                    reduced,
                    current[block],
                    block_bounds,
                    lambda _vector: objective.check_deadline(),
                    {"maxiter": 80, "maxfun": 150, "ftol": 1e-10, "gtol": 1e-5},
                    _optimizer_scale(len(current))[block],
                )
                candidate = current.copy()
                candidate[block] = np.asarray(getattr(fitted, "x", current[block]))
                candidate_details = _observed_details(objective, candidate)
                cycle_terminal_valid &= bool(
                    getattr(fitted, "success", False) and candidate_details is not None
                )
                if (
                    candidate_details is not None
                    and candidate_details["objective"] <= details["objective"] + 1e-9
                ):
                    changed |= candidate_details["objective"] < details["objective"] - 1e-9
                    current = candidate
                    details = candidate_details
                    history.append(float(details["objective"]))
            if not changed:
                stationarity = _stationarity_receipt(
                    objective, details, cycle_terminal_valid
                )
                status = (
                    "projected_stationary_active_gate_branch"
                    if stationarity["stationarity_certified"]
                    else "no_accepted_block_improvement_stationarity_unverified"
                )
                break
    except DeadlineReached:
        deadline_reached = True
        status = "limit_reached"
    if stationarity is None:
        stationarity = _stationarity_receipt(objective, details, False)
    return _result(
        objective,
        details,
        method="alternating_observed_likelihood_blocks_not_em",
        status=status,
        success=stationarity["stationarity_certified"],
        started=started,
        budget_s=budget_s,
        extra={
            "is_em": False,
            "observed_objective_history": history,
            "observed_monotone": bool(np.all(np.diff(history) <= 1e-9)),
            "best_is_terminal": True,
            "deadline_reached": deadline_reached,
            **stationarity,
            "convergence_basis": (
                "Alternating observed-likelihood blocks are monotone when accepted; "
                "no accepted improvement does not certify hard-gate stationarity"
            ),
        },
    )


__all__ = ["FixedPosteriorQ", "fit_block_observed", "fit_direct", "fit_gem"]
