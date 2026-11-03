"""Historical GLRT timing-10 objective and one-start bounded optimizer core."""

from __future__ import annotations

import copy
import time

import numpy as np
from finite_set_likelihood import DEFAULT_ALIAS_HZ, circular_residual
from prediction_plan import SharedPredictionPlan

SCALE_HZ = 200.0
CAP_HZ = 2000.0
TIMING_SIGMA_S = 10.0 / 3.0
TIMING_BOUND_S = 10.0
POSITION_BOUND_KM = 200.0
SLOPE_BOUND_HZ_S = 50.0
MAX_BUDGET_S = 60.0
TERMINAL_VECTOR_RTOL = 1e-10
TERMINAL_VECTOR_ATOL = 1e-9


class DeadlineReached(RuntimeError):
    pass


def capped_pseudo_huber(errors):
    clipped = np.minimum(np.abs(np.asarray(errors, dtype=float)), CAP_HZ)
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + (clipped / SCALE_HZ) ** 2) - 1)


def best_group_assignments(residual, visible, groups):
    """Match the historical stable one-row/one-satellite choice per source group."""

    residual = np.asarray(residual, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    groups = np.asarray(groups)
    if residual.ndim != 2 or visible.shape != residual.shape or groups.shape != residual.shape[:1]:
        raise ValueError("group assignment inputs have incompatible shapes")
    usable = visible & np.isfinite(residual)
    absolute = np.where(usable, np.abs(residual), np.inf)
    local_satellites = np.argmin(absolute, axis=1)
    row_index = np.arange(len(groups))
    errors = residual[row_index, local_satellites]
    errors = np.where(usable[row_index, local_satellites], errors, np.inf)
    ordering = np.lexsort((row_index, np.abs(errors), groups))
    first = np.r_[True, groups[ordering][1:] != groups[ordering][:-1]]
    rows = ordering[first]
    return rows, local_satellites[rows], errors[rows]


def _satellite_bank(data, satellites):
    candidate_count = len(np.asarray(data.numbers))
    if candidate_count == 0 or len(np.unique(data.numbers)) != candidate_count:
        raise ValueError("data.numbers must be a nonempty unique candidate bank")
    if satellites is None:
        satellites = np.arange(candidate_count, dtype=int)
    satellites = np.asarray(satellites)
    if (
        satellites.ndim != 1
        or not len(satellites)
        or not np.issubdtype(satellites.dtype, np.integer)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
    ):
        raise ValueError("satellite_indices must be unique in-bank integers")
    return satellites.astype(int, copy=True)


class LegacyTimingObjective:
    """Historical timing objective with dynamic bank size and analytic derivatives."""

    def __init__(
        self,
        data,
        initial,
        satellites=None,
        *,
        deadline=float("inf"),
        clock=time.monotonic,
        plan_factory=SharedPredictionPlan,
    ):
        self.data = data
        self.candidate_count = len(np.asarray(data.numbers))
        self.satellites = _satellite_bank(data, satellites)
        self.initial = np.asarray(initial, dtype=float).copy()
        if self.initial.shape != (6 + self.candidate_count,) or np.any(~np.isfinite(self.initial)):
            raise ValueError("initial must match the complete candidate bank")
        if np.any(np.abs(self.initial[:2]) > POSITION_BOUND_KM):
            raise ValueError("initial position lies outside the historical bounds")
        if np.any(np.abs(self.initial[[3, 5]]) > SLOPE_BOUND_HZ_S):
            raise ValueError("fixed RX slope lies outside +/-50 Hz/s")
        measured = np.asarray(data.measured, dtype=float)
        groups = np.asarray(data.group)
        if (
            measured.ndim != 1
            or groups.shape != measured.shape
            or not len(measured)
            or np.any(~np.isfinite(measured))
        ):
            raise ValueError("measured and group must be aligned nonempty vectors")
        self.measured = measured
        self.groups = groups
        self.frozen = self.initial.copy()
        self.frozen[6:] = 0.0
        self.deadline = float(deadline)
        self.clock = clock
        self.plan = plan_factory(data, self.satellites)
        self.calls = 0
        self.last = None
        self.best = None

    @property
    def initial_vector(self):
        return np.r_[self.initial[:2], np.zeros(len(self.satellites))]

    @property
    def bounds(self):
        return [(-POSITION_BOUND_KM, POSITION_BOUND_KM)] * 2 + [
            (-TIMING_BOUND_S, TIMING_BOUND_S)
        ] * len(self.satellites)

    def check_deadline(self):
        if self.clock() >= self.deadline:
            raise DeadlineReached("legacy timing-10 wall-clock budget reached")

    def parameters(self, vector):
        vector = np.asarray(vector, dtype=float)
        if vector.shape != (2 + len(self.satellites),) or np.any(~np.isfinite(vector)):
            raise ValueError("optimizer vector must contain position and selected-bank timing")
        parameters = self.frozen.copy()
        parameters[:2] = vector[:2]
        parameters[6 + self.satellites] = vector[2:]
        return parameters

    def evaluate(self, vector):
        self.check_deadline()
        self.calls += 1
        vector = np.asarray(vector, dtype=float)
        parameters = self.parameters(vector)
        prediction, visible, jacobian = self.plan.predict(parameters)
        shape = (len(self.measured), len(self.satellites))
        prediction = np.asarray(prediction, dtype=float).reshape(shape)
        visible = np.asarray(visible, dtype=bool).reshape(shape)
        residual = circular_residual(
            self.measured[:, None], prediction, DEFAULT_ALIAS_HZ
        )
        rows, local_satellites, errors = best_group_assignments(
            residual, visible, self.groups
        )
        data_objective = float(np.sum(capped_pseudo_huber(errors)) / (2 * SCALE_HZ**2))
        tau = vector[2:]
        prior_objective = float(0.5 * np.sum((tau / TIMING_SIGMA_S) ** 2))

        derivative = np.zeros(len(errors))
        active = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
        derivative[active] = (
            errors[active]
            / SCALE_HZ**2
            / np.sqrt(1 + (errors[active] / SCALE_HZ) ** 2)
        )
        prediction_score = np.zeros(shape)
        prediction_score[rows, local_satellites] = -derivative
        physical_gradient = jacobian.transpose_multiply(prediction_score.ravel())
        gradient = np.r_[
            physical_gradient[:2],
            physical_gradient[6 + self.satellites] + tau / TIMING_SIGMA_S**2,
        ]
        global_satellites = self.satellites[local_satellites]
        value = data_objective + prior_objective
        details = {
            "parameters": parameters.copy(),
            "vector": vector.copy(),
            "rows": rows.copy(),
            "satellites": global_satellites.copy(),
            "local_satellites": local_satellites.copy(),
            "errors": errors.copy(),
            "data_objective": data_objective,
            "prior_objective": prior_objective,
            "objective": value,
        }
        self.last = details
        if self.best is None or value < self.best["objective"]:
            self.best = copy.deepcopy(details)
        return value, gradient


def _finite_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def fit_legacy_timing10(
    data,
    initial,
    satellites=None,
    *,
    budget_s=MAX_BUDGET_S,
    minimizer=None,
    clock=time.monotonic,
    plan_factory=SharedPredictionPlan,
):
    """Run one zero-tau L-BFGS-B branch and preserve its best finite evaluation."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_BUDGET_S:
        raise ValueError("budget_s must lie in (0, 60]")
    started = clock()
    objective = LegacyTimingObjective(
        data,
        initial,
        satellites,
        deadline=started + float(budget_s),
        clock=clock,
        plan_factory=plan_factory,
    )
    start = objective.initial_vector
    initial_value, _ = objective.evaluate(start)
    if minimizer is None:
        from scipy.optimize import minimize

        minimizer = minimize

    deadline_reached = False
    fitted = None

    def callback(_vector):
        objective.check_deadline()

    try:
        fitted = minimizer(
            objective.evaluate,
            start,
            jac=True,
            method="L-BFGS-B",
            bounds=objective.bounds,
            callback=callback,
            options={"maxiter": 700, "maxfun": 1000, "ftol": 1e-9, "gtol": 1e-4, "maxls": 25},
        )
    except DeadlineReached:
        deadline_reached = True

    best = objective.best
    if best is None:
        raise RuntimeError("legacy timing-10 produced no finite evaluation")
    optimizer_reported_success = bool(
        fitted is not None
        and getattr(fitted, "success", False)
        and np.isfinite(getattr(fitted, "fun", np.nan))
    )
    terminal_vector = (
        np.asarray(getattr(fitted, "x", np.empty(0)), dtype=float)
        if fitted is not None
        else np.empty(0)
    )
    best_matches_terminal = bool(
        terminal_vector.shape == best["vector"].shape
        and np.all(np.isfinite(terminal_vector))
        and np.allclose(
            best["vector"],
            terminal_vector,
            rtol=TERMINAL_VECTOR_RTOL,
            atol=TERMINAL_VECTOR_ATOL,
        )
    )
    optimizer_success = bool(
        optimizer_reported_success and best_matches_terminal and not deadline_reached
    )
    optimizer_message = str(
        getattr(fitted, "message", "optimizer did not return a result")
    )
    if deadline_reached:
        status = "limit_reached"
        message = "legacy timing-10 wall-clock budget reached"
    elif optimizer_reported_success and not best_matches_terminal:
        status = "best_retained_nonterminal"
        message = "best finite evaluation differs from optimizer terminal state"
    else:
        status = "converged" if optimizer_success else "optimizer_failed"
        message = optimizer_message
    errors = best["errors"]
    matched = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
    group_count = len(errors)
    comparable = float(2 * SCALE_HZ**2 * best["objective"] / group_count)
    frequency = float(2 * SCALE_HZ**2 * best["data_objective"] / group_count)
    parameters = best["parameters"]
    satellite_indices = objective.satellites.copy()
    return {
        "parameters": parameters,
        "satellite_indices": satellite_indices,
        "catalog_numbers": np.asarray(data.numbers)[satellite_indices].copy(),
        "satellite_count": len(satellite_indices),
        "satellite_weights": np.ones(len(satellite_indices)),
        "success": optimizer_success,
        "status": status,
        "message": message,
        "convergence_reason": status,
        "algorithm_version": "historical-glrt-timing10-lbfgsb-analytic-jac/v1",
        "objective": comparable,
        "optimizer_objective": float(best["objective"]),
        "initial_objective": float(2 * SCALE_HZ**2 * initial_value / group_count),
        "selection_score": comparable,
        "entry_penalty": 0.0,
        "model_penalty": {"total_penalty": 0.0},
        "frequency_objective": frequency,
        "timing_prior_objective": float(best["prior_objective"]),
        "assigned_groups": int(np.sum(matched)),
        "total_source_groups": group_count,
        "groups": group_count,
        "fixed_assignment_rms_hz": (
            float(np.sqrt(np.mean(errors[matched] ** 2))) if np.any(matched) else None
        ),
        "assignment_rows": best["rows"],
        "assignment_satellites": best["satellites"],
        "timing_sigma_s": TIMING_SIGMA_S,
        "timing_bound_s": TIMING_BOUND_S,
        "timing_at_bound": int(
            np.sum(np.abs(parameters[6 + satellite_indices]) >= TIMING_BOUND_S - 1e-6)
        ),
        "position_bound_km": POSITION_BOUND_KM,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "rx_policy": "supplied shared RX intercepts/slopes fixed throughout optimization",
        "candidate_scope": (
            "explicit supplied candidate bank; dynamic unions are retained without "
            "prefix truncation"
        ),
        "free_parameter_count": 2 + len(satellite_indices),
        "free_parameters": ["east_km", "north_km"]
        + [f"tau_{int(index)}_s" for index in satellite_indices],
        "evaluations": objective.calls,
        "iterations": int(getattr(fitted, "nit", 0)) if fitted is not None else 0,
        "optimizer_status": (
            int(getattr(fitted, "status", -1)) if fitted is not None else None
        ),
        "optimizer_reported_status": (
            int(getattr(fitted, "status", -1)) if fitted is not None else None
        ),
        "optimizer_reported_success": optimizer_reported_success,
        "optimizer_reported_message": optimizer_message,
        "best_matches_optimizer_terminal": best_matches_terminal,
        "terminal_vector_rtol": TERMINAL_VECTOR_RTOL,
        "terminal_vector_atol": TERMINAL_VECTOR_ATOL,
        "elapsed_s": float(clock() - started),
        "budget_s": float(budget_s),
        "best_finite_preserved": True,
        "historical_objective_exact": True,
        "historical_pipeline_exact": False,
        "initialization_policy": "single supplied rough position with all selected taus zero",
        "omitted_historical_protocol_stages": [
            "broad fixed-GLRT position search warm start",
            "successful timing-3s warm branch",
            "second zero-tau start when warm and supplied positions differ",
        ],
        "training_scope": "all source groups; no holdout",
    }


__all__ = [
    "CAP_HZ",
    "DeadlineReached",
    "LegacyTimingObjective",
    "POSITION_BOUND_KM",
    "SCALE_HZ",
    "TIMING_BOUND_S",
    "TIMING_SIGMA_S",
    "best_group_assignments",
    "capped_pseudo_huber",
    "fit_legacy_timing10",
]
