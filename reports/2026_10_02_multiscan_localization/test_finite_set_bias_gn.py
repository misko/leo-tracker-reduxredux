from types import SimpleNamespace

import finite_set_bias_gn as model
import numpy as np
import pytest


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights, dtype=float)

    def normal_matrix(self, weights):
        weights = np.asarray(weights, dtype=float)
        return self.matrix.T @ (weights[:, None] * self.matrix)


class LinearPlan:
    def __init__(self, matrix, data, satellites, visibility=None):
        self.matrix = np.asarray(matrix, dtype=float)
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)
        shape = (len(data.times), len(satellites))
        self.visibility = (
            np.ones(shape, dtype=bool) if visibility is None else np.asarray(visibility, dtype=bool)
        )

    def predict(self, parameters):
        predicted = self.matrix @ np.asarray(parameters, dtype=float)
        return predicted, self.visibility.ravel(), DenseJacobian(self.matrix)


class FixedPrecisionLikelihood:
    def __init__(self, target, precision, masses):
        self.target = np.asarray(target, dtype=float)
        self.precision = np.asarray(precision, dtype=float)
        self.frozen_masses = masses
        self.last_result = None

    def evaluate(self, predicted, visible, **options):
        predicted = np.asarray(predicted, dtype=float)
        residual = predicted - self.target
        self.last_result = {
            "total_log_likelihood": -0.5 * float(np.sum(self.precision * residual**2)),
            "prediction_gradient": -self.precision * residual,
            "prediction_precision": self.precision.copy(),
            "group_values": np.arange(len(predicted)),
            "satellite_support": np.sum(self.precision, axis=0),
            "null_support": 0.0,
        }
        return self.last_result


def synthetic_data(candidate_count=3):
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 1.0, 1.0]),
        measured=np.zeros(4),
        rf=np.full(4, 11.2e9),
        receiver=np.array([0, 1, 0, 1]),
        channel=np.array([1, 2, 2, 1]),
        group=np.arange(4),
        numbers=np.arange(candidate_count),
    )


def source_trial(data, satellites, parameters=None, omega_hz=None):
    parameters = (
        np.zeros(6 + len(data.numbers))
        if parameters is None
        else np.asarray(parameters, dtype=float)
    )
    trial = {
        "satellite_indices": np.asarray(satellites, dtype=int),
        "parameters": parameters,
    }
    if omega_hz is not None:
        trial["omega_hz"] = np.asarray(omega_hz, dtype=float)
    return trial


def test_gradient_and_complete_data_fisher_match_dense_oracles():
    rng = np.random.default_rng(311)
    data = synthetic_data()
    satellites = np.array([0, 2])
    full_size = 6 + len(data.numbers)
    matrix = rng.normal(size=(len(data.times) * len(satellites), full_size))
    parameters = rng.normal(size=full_size)
    parameters[6:] = [0.2, -0.1, 0.3]
    trial = source_trial(data, satellites, parameters, omega_hz=[35.0, -20.0])
    specification = model.bias_trial_specification(data, trial)
    target = rng.normal(size=(len(data.times), len(satellites)))
    precision = rng.uniform(0.002, 0.02, size=target.shape)
    masses = {
        "raw_satellite_mass": np.full(2, 0.2),
        "raw_background_mass": 0.6,
    }
    likelihood = FixedPrecisionLikelihood(target, precision, masses)
    plan = LinearPlan(matrix, data, satellites)
    vector = specification["vector"].copy()
    state = model.evaluate_bias_fisher_state(
        vector,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )

    step = 1e-6
    finite_gradient = np.empty_like(vector)
    finite_hessian = np.empty_like(state.hessian)
    for index in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[index] = step
        upper = model.evaluate_bias_fisher_state(
            vector + delta,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        )
        lower = model.evaluate_bias_fisher_state(
            vector - delta,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        )
        finite_gradient[index] = (upper.objective - lower.objective) / (2 * step)
        finite_hessian[:, index] = (upper.gradient - lower.gradient) / (2 * step)
    np.testing.assert_allclose(state.gradient, finite_gradient, rtol=3e-6, atol=5e-5)
    np.testing.assert_allclose(state.hessian, finite_hessian, rtol=3e-6, atol=5e-5)


def test_zero_omega_objective_matches_baseline_and_continuation_is_routed():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    parameters[6:] = [0.2, -0.3]
    matrix = np.zeros((len(data.times) * 2, len(parameters)))
    target = np.ones((len(data.times), 2))
    precision = np.ones_like(target)
    masses = {"raw_satellite_mass": np.full(2, 0.4), "raw_background_mass": 0.2}
    likelihood = FixedPrecisionLikelihood(target, precision, masses)
    plan = LinearPlan(matrix, data, satellites)
    zero_specification = model.bias_trial_specification(
        data, source_trial(data, satellites, parameters)
    )
    zero = model.evaluate_bias_fisher_state(
        zero_specification["vector"],
        data=data,
        specification=zero_specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    baseline = 0.5 * np.sum(target**2) + 0.5 * np.sum(parameters[6:] ** 2)
    assert zero.objective == pytest.approx(baseline)
    assert zero_specification["omega_initialization"] == "zero_default"

    continuation = model.bias_trial_specification(
        data, source_trial(data, satellites, parameters, omega_hz=[30.0, -45.0])
    )
    np.testing.assert_allclose(continuation["vector"][-2:], [0.15, -0.225])
    assert continuation["omega_initialization"] == "source_trial_continuation"


def test_fitter_penalty_and_stationary_connected_result():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    matrix = np.zeros((len(data.times) * 2, len(parameters)))
    target = np.zeros((len(data.times), 2))
    precision = np.ones_like(target)
    masses = {"raw_satellite_mass": np.full(2, 0.4), "raw_background_mass": 0.2}
    likelihood = FixedPrecisionLikelihood(target, precision, masses)

    result = model.fit_satellite_bias_trial(
        data,
        source_trial(data, satellites, parameters),
        likelihood,
        budget_s=1.0,
        plan_factory=lambda source, selected: LinearPlan(matrix, source, selected),
    )
    assert result["success"] is True
    assert result["message"] == "projected_gradient"
    assert result["final_topology"]["connected"] is True
    assert result["optimizer_terminal_matches_retained"] is True
    assert result["optimizer_status"] is None
    assert result["omega_identifiable_parameter_count"] == 1
    assert result["omega_parameter_penalty"] == pytest.approx(0.5 * np.log(4))
    assert result["selection_score"] == pytest.approx(
        result["objective"] + 0.5 * 2 * np.log(4) + 0.5 * np.log(4)
    )


def test_disconnected_lower_state_is_not_accepted_or_labeled_converged():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    target = np.full((len(data.times), 2), 20.0)
    precision = np.ones_like(target)
    masses = {"raw_satellite_mass": np.full(2, 0.4), "raw_background_mass": 0.2}
    likelihood = FixedPrecisionLikelihood(target, precision, masses)
    connected = np.ones((len(data.times), 2), dtype=bool)
    disconnected = np.array(
        [[True, False], [False, True], [True, False], [False, True]], dtype=bool
    )

    class VisibilityChangingPlan:
        def __init__(self, source, selected):
            self.matrix = np.zeros((len(source.times) * len(selected), len(parameters)))
            self.matrix[:, 0] = 1.0

        def predict(self, current):
            current = np.asarray(current, dtype=float)
            visibility = connected if current[0] == 0 else disconnected
            predicted = self.matrix @ current
            return predicted, visibility.ravel(), DenseJacobian(self.matrix)

    result = model.fit_satellite_bias_trial(
        data,
        source_trial(data, satellites, parameters),
        likelihood,
        budget_s=1.0,
        plan_factory=VisibilityChangingPlan,
    )
    assert result["success"] is False
    assert result["status"] == "nonconverged"
    assert result["message"] == "no_acceptable_connected_step"
    assert result["final_topology"]["connected"] is True
    assert result["disconnected_topology_evaluation_count"] > 0
    assert result["parameters"][0] == 0.0


def test_budget_exhaustion_retains_initial_connected_state(monkeypatch):
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    matrix = np.zeros((len(data.times) * 2, len(parameters)))
    target = np.ones((len(data.times), 2))
    precision = np.ones_like(target)
    masses = {"raw_satellite_mass": np.full(2, 0.4), "raw_background_mass": 0.2}
    likelihood = FixedPrecisionLikelihood(target, precision, masses)
    ticks = iter([0.0, 0.0, 2.0, 2.0, 2.0])
    monkeypatch.setattr(model.time, "monotonic", lambda: next(ticks, 2.0))

    result = model.fit_satellite_bias_trial(
        data,
        source_trial(data, satellites, parameters),
        likelihood,
        budget_s=1.0,
        plan_factory=lambda source, selected: LinearPlan(matrix, source, selected),
    )
    assert result["success"] is False
    assert result["message"] == "budget_exhausted"
    assert result["best_connected_finite_preserved"] is True
    np.testing.assert_array_equal(result["omega_hz"], np.zeros(2))
