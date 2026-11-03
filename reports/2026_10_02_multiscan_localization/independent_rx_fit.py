"""Grouped GLRT fitting with independent receiver lines in every capture."""

from __future__ import annotations

import time

import numpy as np
from prediction_plan import SharedPredictionPlan


def capture_clock(data):
    capture = np.asarray(data.capture_index)
    receiver = np.asarray(data.receiver)
    count = len(data.child_sessions)
    times = np.asarray(data.times, dtype=float)
    if (
        count < 1 or capture.shape != times.shape or receiver.shape != times.shape
        or not len(times) or not np.all(np.isfinite(times))
        or not np.issubdtype(capture.dtype, np.integer)
        or not np.issubdtype(receiver.dtype, np.integer)
        or np.any(capture < 0) or np.any(capture >= count)
        or np.any(receiver < 0) or np.any(receiver > 1)
    ):
        raise ValueError("invalid capture/receiver observation indexing")
    origins = np.asarray(data.child_origins_utc_ns, dtype=np.int64)
    if origins.shape != (count,):
        raise ValueError("capture origins do not match sessions")
    centers = (origins - int(data.origin_utc_ns)) / 1e9 + 150.0
    if set(zip(capture.tolist(), receiver.tolist(), strict=True)) != {
        (scan, rx) for scan in range(count) for rx in (0, 1)
    }:
        raise ValueError("every capture/RX must have observations")
    return centers, times - centers[capture], 2 * capture + receiver


def continuous_to_lines(data, parameters):
    centers, _, _ = capture_clock(data)
    parameters = np.asarray(parameters, dtype=float)
    lines = np.empty((len(centers), 2, 2))
    for receiver in (0, 1):
        intercept, slope = parameters[2 + 2 * receiver:4 + 2 * receiver]
        lines[:, receiver, 0] = intercept + slope * (
            centers - float(getattr(data, "reference_time_s", 150.0))
        )
        lines[:, receiver, 1] = slope
    return lines


class IndependentRXObjective:
    def __init__(self, data, parameters, lines, satellites, likelihood, *,
                 plan_factory=SharedPredictionPlan):
        self.data = data
        self.parameters = np.asarray(parameters, dtype=float).copy()
        self.satellites = np.asarray(satellites, dtype=int)
        self.lines = np.asarray(lines, dtype=float).copy()
        self.centers, self.delta_time, self.line_index = capture_clock(data)
        if (self.parameters.shape != (6 + len(data.numbers),)
                or not np.all(np.isfinite(self.parameters))
                or self.lines.shape != (len(self.centers), 2, 2)
                or not np.all(np.isfinite(self.lines))
                or np.any(np.abs(self.lines[:, :, 1]) > 50)
                or np.any(np.abs(self.parameters[:2]) > 200)):
            raise ValueError("invalid independent receiver initializer")
        if (self.satellites.ndim != 1 or not len(self.satellites)
                or len(np.unique(self.satellites)) != len(self.satellites)
                or np.any(self.satellites < 0)
                or np.any(self.satellites >= len(data.numbers))
                or np.any(np.abs(self.parameters[6 + self.satellites]) > 3)):
            raise ValueError("invalid satellite bank or timing initializer")
        self.parameters[2:6] = 0.0
        self.scales = np.r_[20.0, 20.0, np.tile([1000.0, 10.0], 2 * len(self.centers)),
                            np.ones(len(self.satellites))]
        self.bounds = [(-10.0, 10.0)] * 2
        self.bounds += [(None, None), (-5.0, 5.0)] * (2 * len(self.centers))
        self.bounds += [(-3.0, 3.0)] * len(self.satellites)
        self.initial_vector = np.r_[self.parameters[:2], self.lines.ravel(),
                                    self.parameters[6 + self.satellites]] / self.scales
        self.plan = plan_factory(data, self.satellites)
        self.likelihood = likelihood
        self.best = None
        self.calls = 0

    def evaluate(self, vector):
        physical = np.asarray(vector) * self.scales
        split = 2 + self.lines.size
        parameters = self.parameters.copy()
        parameters[:2] = physical[:2]
        parameters[6 + self.satellites] = physical[split:]
        lines = physical[2:split].reshape(self.lines.shape)
        row_lines = lines.reshape(-1, 2)[self.line_index]
        prediction, visible, jacobian = self.plan.predict(parameters)
        shape = (len(self.data.times), len(self.satellites))
        prediction = prediction.reshape(shape) + (
            row_lines[:, 0] + row_lines[:, 1] * self.delta_time
        )[:, None]
        result = self.likelihood.evaluate(
            prediction, visible.reshape(shape), sigma_hz=200.0,
            satellite_weights=np.full(len(self.satellites), 1 / len(self.satellites)),
            background_mass=0.2, return_gradient=True,
        )
        derivative = -np.asarray(result["prediction_gradient"])
        base_gradient = jacobian.transpose_multiply(derivative.ravel())
        row_gradient = derivative.sum(axis=1)
        line_gradient = np.column_stack([
            np.bincount(self.line_index, weights=row_gradient, minlength=2 * len(self.centers)),
            np.bincount(self.line_index, weights=row_gradient * self.delta_time,
                        minlength=2 * len(self.centers)),
        ])
        tau = parameters[6 + self.satellites]
        objective = float(-result["total_log_likelihood"] + 0.5 * np.sum(tau**2))
        gradient = np.r_[base_gradient[:2], line_gradient.ravel(),
                         base_gradient[6 + self.satellites] + tau] * self.scales
        if not np.isfinite(objective) or not np.all(np.isfinite(gradient)):
            raise FloatingPointError("nonfinite independent-RX objective")
        self.calls += 1
        if self.best is None or objective < self.best["objective"]:
            self.best = {"objective": objective, "vector": np.asarray(vector).copy(),
                         "parameters": parameters, "rx_lines": lines.copy(),
                         "gradient": gradient.copy()}
        return objective, gradient


def fit_independent_rx(data, parameters, lines, satellites, likelihood, *,
                       budget_s=15.0, minimizer=None, plan_factory=SharedPredictionPlan,
                       clock=time.monotonic):
    if not np.isfinite(budget_s) or budget_s <= 0:
        raise ValueError("budget must be positive and finite")
    if minimizer is None:
        from scipy.optimize import minimize

        minimizer = minimize
    started = clock()
    objective = IndependentRXObjective(data, parameters, lines, satellites, likelihood,
                                       plan_factory=plan_factory)
    initial_loss, _ = objective.evaluate(objective.initial_vector)
    reason = "budget_exhausted"
    success = False

    def bounded(vector):
        if clock() - started >= budget_s:
            raise TimeoutError("independent RX fit budget exhausted")
        return objective.evaluate(vector)

    try:
        result = minimizer(bounded, objective.initial_vector, jac=True, method="L-BFGS-B",
                           bounds=objective.bounds,
                           options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-4})
        success = bool(result.success) and np.allclose(
            result.x, objective.best["vector"], rtol=1e-10, atol=1e-9,
        )
        reason = (str(result.message) if success or not result.success
                  else "best_retained_nonterminal")
    except TimeoutError:
        pass
    best = objective.best
    groups = len(np.unique(data.group))
    extra = 4 * (len(data.child_sessions) - 1)
    penalty = 0.5 * (len(satellites) + extra) * np.log(groups)
    return {
        "parameters": best["parameters"], "rx_lines_hz_hz_s": best["rx_lines"],
        "rx_line_reference_times_s": objective.centers,
        "parameter_layout": "parameters RX slots are zero; rx_lines_hz_hz_s is authoritative",
        "satellite_indices": np.asarray(satellites), "satellite_count": len(satellites),
        "objective": best["objective"], "initial_objective": initial_loss,
        "selection_score": best["objective"] + penalty,
        "model_penalty": {"total_penalty": float(penalty), "extra_rx_parameters": extra},
        "free_parameter_count": len(objective.scales),
        "success": success, "status": "converged" if success else "nonconverged",
        "convergence_reason": reason, "evaluations": objective.calls,
        "elapsed_s": clock() - started, "slope_bound_hz_s": 50.0,
        "tau_sigma_s": 1.0, "tau_bound_s": 3.0,
        "rx_policy": "Independent intercept and slope per scan/RX; no sharing or shrinkage",
    }
