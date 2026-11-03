from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

import numpy as np

try:
    from prediction_plan import SharedPredictionPlan
except ModuleNotFoundError as error:
    if error.name != "prediction_plan":
        raise
    _SHARED_MODEL = Path(__file__).resolve().parents[1] / "2026_10_02_multiscan_localization"
    sys.path.insert(0, str(_SHARED_MODEL))
    from prediction_plan import SharedPredictionPlan


POSITION_BOUND_KM = 200.0
SLOPE_BOUND_HZ_S = 50.0
GLOBAL_SHIFT_BOUND_S = 10.0
INDIVIDUAL_SHIFT_SIGMA_S = 1.0
GLOBAL_SHIFT_SIGMA_S = 10.0
INVALID_OBJECTIVE = 1.0e30


class DeadlineReached(RuntimeError):
    pass


def zero_sum_basis(size):
    if isinstance(size, bool) or int(size) != size or size < 1:
        raise ValueError("basis size must be a positive integer")
    size = int(size)
    basis = np.zeros((size, size - 1), dtype=float)
    for column in range(size - 1):
        scale = np.sqrt((column + 1) * (column + 2))
        basis[: column + 1, column] = 1.0 / scale
        basis[column + 1, column] = -(column + 1) / scale
    return basis


def _satellite_indices(data, satellites):
    candidate_count = len(np.asarray(data.numbers))
    values = np.asarray(satellites)
    if (
        values.ndim != 1
        or not len(values)
        or not np.issubdtype(values.dtype, np.integer)
        or len(np.unique(values)) != len(values)
        or np.any(values < 0)
        or np.any(values >= candidate_count)
    ):
        raise ValueError("satellites must be unique in-bank integer indices")
    return values.astype(int, copy=True)


class TimingObjective:
    def __init__(
        self,
        data,
        initial_parameters,
        satellites,
        likelihood,
        sigma_hz,
        *,
        common_prior=True,
        plan_factory=SharedPredictionPlan,
        deadline=float("inf"),
        clock=time.monotonic,
    ):
        self.data = data
        self.satellites = _satellite_indices(data, satellites)
        self.candidate_count = len(np.asarray(data.numbers))
        self.initial_parameters = np.asarray(initial_parameters, dtype=float).copy()
        if self.initial_parameters.shape != (6 + self.candidate_count,):
            raise ValueError("initial_parameters must match the complete candidate bank")
        if np.any(~np.isfinite(self.initial_parameters)):
            raise ValueError("initial_parameters must be finite")
        if np.any(np.abs(self.initial_parameters[:2]) > POSITION_BOUND_KM):
            raise ValueError("initial location lies outside +/-200 km")
        if np.any(np.abs(self.initial_parameters[[3, 5]]) > SLOPE_BOUND_HZ_S):
            raise ValueError("initial RX slope lies outside +/-50 Hz/s")
        if not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be positive and finite")
        reference_time = float(getattr(data, "reference_time_s", 150.0))
        if not np.isfinite(reference_time) or reference_time != 150.0:
            raise ValueError("DS13 one-scan timing requires reference_time_s=150")
        self.sigma_hz = float(sigma_hz)
        self.likelihood = likelihood
        self.common_prior = bool(common_prior)
        self.basis = zero_sum_basis(len(self.satellites))
        self.plan = plan_factory(data, self.satellites)
        self.clock = clock
        self.deadline = float(deadline)
        self.calls = 0
        self.last = None
        self.best = None
        times = np.asarray(data.times, dtype=float)
        nodes = np.asarray(data.nodes, dtype=float)
        if times.ndim != 1 or not len(times) or np.any(~np.isfinite(times)):
            raise ValueError("data.times must be a nonempty finite vector")
        if nodes.ndim != 1 or len(nodes) < 2 or np.any(~np.isfinite(nodes)):
            raise ValueError("data.nodes must be a finite ephemeris vector")
        self.minimum_shift_s = float(nodes[0] - np.min(times))
        self.maximum_shift_s = float(np.nextafter(nodes[-1] - np.max(times), -np.inf))
        selected = self.initial_parameters[6 + self.satellites]
        initial_global = float(np.mean(selected))
        if abs(initial_global) > GLOBAL_SHIFT_BOUND_S:
            raise ValueError("initial selected-bank mean timing lies outside +/-10 s")
        initial_delta = selected - initial_global
        self._initial_vector = np.r_[
            self.initial_parameters[:6],
            initial_global,
            self.basis.T @ initial_delta,
        ]
        if not self.state(self._initial_vector)["ephemeris_valid"]:
            raise ValueError("initial selected-bank timing lies outside ephemeris support")

    @property
    def initial_vector(self):
        return self._initial_vector.copy()

    @property
    def bounds(self):
        return [
            (-POSITION_BOUND_KM, POSITION_BOUND_KM),
            (-POSITION_BOUND_KM, POSITION_BOUND_KM),
            (None, None),
            (-SLOPE_BOUND_HZ_S, SLOPE_BOUND_HZ_S),
            (None, None),
            (-SLOPE_BOUND_HZ_S, SLOPE_BOUND_HZ_S),
            (-GLOBAL_SHIFT_BOUND_S, GLOBAL_SHIFT_BOUND_S),
            *([(None, None)] * (len(self.satellites) - 1)),
        ]

    def check_deadline(self):
        if self.clock() >= self.deadline:
            raise DeadlineReached("DS13 timing wall-clock budget reached")

    def state(self, vector):
        vector = np.asarray(vector, dtype=float)
        expected = 7 + len(self.satellites) - 1
        if vector.shape != (expected,) or np.any(~np.isfinite(vector)):
            raise ValueError("timing vector has the wrong shape or non-finite values")
        individual = self.basis @ vector[7:]
        total = vector[6] + individual
        parameters = self.initial_parameters.copy()
        parameters[:6] = vector[:6]
        parameters[6 + self.satellites] = total
        valid = bool(
            np.all(total >= self.minimum_shift_s)
            and np.all(total <= self.maximum_shift_s)
        )
        return {
            "parameters": parameters,
            "global_shift_s": float(vector[6]),
            "individual_shifts_s": individual,
            "total_shifts_s": total,
            "ephemeris_valid": valid,
        }

    def penalty(self, vector):
        vector = np.asarray(vector, dtype=float)
        individual = self.basis @ vector[7:]
        value = 0.5 * float(np.dot(individual, individual)) / INDIVIDUAL_SHIFT_SIGMA_S**2
        gradient = np.zeros_like(vector)
        gradient[7:] = self.basis.T @ individual / INDIVIDUAL_SHIFT_SIGMA_S**2
        if self.common_prior:
            value += 0.5 * (vector[6] / GLOBAL_SHIFT_SIGMA_S) ** 2
            gradient[6] = vector[6] / GLOBAL_SHIFT_SIGMA_S**2
        return value, gradient

    def _invalid_ephemeris(self, vector, state):
        total = state["total_shifts_s"]
        below = np.maximum(self.minimum_shift_s - total, 0.0)
        above = np.maximum(total - self.maximum_shift_s, 0.0)
        tau_gradient = 2.0e6 * (above - below)
        gradient = np.zeros_like(vector)
        gradient[6] = np.sum(tau_gradient)
        gradient[7:] = self.basis.T @ tau_gradient
        value = INVALID_OBJECTIVE + 1.0e6 * float(np.sum(below**2 + above**2))
        return value, gradient

    def predict(self, vector, *, with_jacobian=False):
        state = self.state(vector)
        if not state["ephemeris_valid"]:
            raise ValueError("timing vector lies outside ephemeris support")
        predicted, visible, jacobian = self.plan.predict(state["parameters"])
        shape = (len(np.asarray(self.data.times)), len(self.satellites))
        predicted = np.asarray(predicted, dtype=float).reshape(shape)
        visible = np.asarray(visible, dtype=bool).reshape(shape)
        if with_jacobian:
            return predicted, visible, jacobian
        return predicted, visible

    def vector_gradient(self, physical_gradient, vector):
        physical_gradient = np.asarray(physical_gradient, dtype=float)
        if physical_gradient.shape != (6 + self.candidate_count,):
            raise ValueError("physical gradient must match the complete parameter bank")
        selected = physical_gradient[6 + self.satellites]
        gradient = np.zeros_like(np.asarray(vector, dtype=float))
        gradient[:6] = physical_gradient[:6]
        gradient[6] = np.sum(selected)
        gradient[7:] = self.basis.T @ selected
        return gradient

    def evaluate(self, vector):
        self.check_deadline()
        self.calls += 1
        vector = np.asarray(vector, dtype=float)
        state = self.state(vector)
        if not state["ephemeris_valid"]:
            self.last = None
            return self._invalid_ephemeris(vector, state)
        predicted, visible, jacobian = self.predict(vector, with_jacobian=True)
        likelihood_result = self.likelihood.evaluate(
            predicted,
            visible,
            sigma_hz=self.sigma_hz,
            return_gradient=True,
            return_precision=False,
        )
        prediction_gradient = np.asarray(
            likelihood_result["prediction_gradient"], dtype=float
        )
        if prediction_gradient.shape != predicted.shape:
            raise ValueError("likelihood prediction_gradient has the wrong shape")
        data_objective = -float(likelihood_result["total_log_likelihood"])
        penalty_value, penalty_gradient = self.penalty(vector)
        physical_gradient = jacobian.transpose_multiply(-prediction_gradient.ravel())
        gradient = self.vector_gradient(physical_gradient, vector) + penalty_gradient
        value = data_objective + penalty_value
        details = {
            **state,
            "vector": vector.copy(),
            "objective": float(value),
            "data_objective": data_objective,
            "prior_objective": penalty_value,
            "gradient": gradient.copy(),
            "likelihood": likelihood_result,
        }
        self.last = details
        if np.isfinite(value) and (self.best is None or value < self.best["objective"]):
            self.best = copy.deepcopy({key: item for key, item in details.items() if key != "likelihood"})
        return float(value), gradient


__all__ = [
    "DeadlineReached",
    "GLOBAL_SHIFT_BOUND_S",
    "TimingObjective",
    "zero_sum_basis",
]
