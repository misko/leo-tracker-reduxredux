from types import SimpleNamespace

import numpy as np
import pytest

from timing_model import TimingObjective, zero_sum_basis


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights, dtype=float)


class LinearPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)

    def predict(self, parameters):
        rows = len(self.data.times)
        count = len(self.satellites)
        matrix = np.zeros((rows * count, len(parameters)))
        for row in range(rows):
            receiver = self.data.receiver[row]
            for local, satellite in enumerate(self.satellites):
                index = row * count + local
                matrix[index, 0] = self.data.location_design[row, local]
                matrix[index, 1] = self.data.north_design[row, local]
                matrix[index, 2 + 2 * receiver] = 1.0
                matrix[index, 3 + 2 * receiver] = self.data.times[row] - 150.0
                matrix[index, 6 + satellite] = self.data.tau_design[row, local]
        prediction = matrix @ parameters
        visible = np.ones(rows * count, dtype=bool)
        return prediction, visible, DenseJacobian(matrix)


class GaussianLikelihood:
    gate_hz = 1000.0
    alias_hz = 1 / 4.4e-6

    def __init__(self, target, posterior=None):
        self.target = np.asarray(target, dtype=float)
        self.posterior = posterior

    def evaluate(self, predicted, visible, *, sigma_hz, return_gradient, return_precision):
        residual = self.target - predicted
        gradient = residual / sigma_hz**2
        posterior = (
            np.ones_like(predicted)
            if self.posterior is None
            else np.asarray(self.posterior, dtype=float)
        )
        return {
            "total_log_likelihood": -0.5 * float(np.sum((residual / sigma_hz) ** 2)),
            "prediction_gradient": gradient,
            "row_association_probability": posterior,
        }


def synthetic_problem(candidate_count=3):
    rows = 4
    satellites = np.arange(candidate_count)
    data = SimpleNamespace(
        times=np.array([149.0, 150.0, 151.0, 152.0]),
        measured=np.zeros(rows),
        receiver=np.array([0, 0, 1, 1]),
        numbers=np.arange(100, 100 + candidate_count),
        nodes=np.array([100.0, 200.0]),
        reference_time_s=150.0,
        location_design=np.tile(np.linspace(0.2, 0.5, rows)[:, None], (1, candidate_count)),
        north_design=np.tile(np.linspace(-0.3, 0.1, rows)[:, None], (1, candidate_count)),
        tau_design=np.tile(np.arange(1, candidate_count + 1), (rows, 1)),
    )
    initial = np.zeros(6 + candidate_count)
    target = np.arange(rows * candidate_count, dtype=float).reshape(rows, candidate_count) / 10
    likelihood = GaussianLikelihood(target)
    objective = TimingObjective(
        data,
        initial,
        satellites,
        likelihood,
        2.0,
        plan_factory=LinearPlan,
    )
    return data, objective


def test_zero_sum_basis_is_orthonormal_and_exact_gauge():
    basis = zero_sum_basis(5)
    np.testing.assert_allclose(basis.T @ basis, np.eye(4), atol=1e-14)
    np.testing.assert_allclose(np.sum(basis, axis=0), 0.0, atol=1e-14)
    _, objective = synthetic_problem(5)
    vector = objective.initial_vector
    vector[6] = 2.5
    vector[7:] = [1.0, -0.5, 0.25, 0.75]
    state = objective.state(vector)
    assert np.sum(state["individual_shifts_s"]) == pytest.approx(0.0, abs=1e-14)
    np.testing.assert_allclose(
        state["parameters"][6 + objective.satellites],
        state["global_shift_s"] + state["individual_shifts_s"],
    )


def test_initial_vector_preserves_mean_and_total_selected_tau():
    data, _ = synthetic_problem(3)
    initial = np.zeros(9)
    initial[6:] = [2.0, 4.0, 6.0]
    objective = TimingObjective(
        data,
        initial,
        [0, 1, 2],
        GaussianLikelihood(np.zeros((4, 3))),
        100.0,
        plan_factory=LinearPlan,
    )
    state = objective.state(objective.initial_vector)
    assert state["global_shift_s"] == pytest.approx(4.0)
    np.testing.assert_allclose(state["individual_shifts_s"], [-2.0, 0.0, 2.0], atol=1e-14)
    np.testing.assert_allclose(state["parameters"][6:], initial[6:])


def test_analytic_gradient_matches_finite_difference():
    _, objective = synthetic_problem(3)
    vector = objective.initial_vector
    vector[:7] = [0.2, -0.1, 1.0, 0.4, -0.5, -0.3, 0.2]
    vector[7:] = [0.1, -0.15]
    value, gradient = objective.evaluate(vector)
    numerical = np.zeros_like(vector)
    step = 1e-6
    for index in range(len(vector)):
        upper = vector.copy()
        lower = vector.copy()
        upper[index] += step
        lower[index] -= step
        numerical[index] = (objective.evaluate(upper)[0] - objective.evaluate(lower)[0]) / (2 * step)
    assert np.isfinite(value)
    np.testing.assert_allclose(gradient, numerical, rtol=2e-6, atol=2e-7)


def test_timing_changes_do_not_change_receiver_parameters():
    _, objective = synthetic_problem(3)
    vector = objective.initial_vector
    vector[2:6] = [120.0, 2.0, -80.0, -3.0]
    original = objective.state(vector)["parameters"][2:6].copy()
    vector[6] = 4.0
    vector[7:] = [0.8, -0.4]
    updated = objective.state(vector)
    np.testing.assert_array_equal(updated["parameters"][2:6], original)
    assert updated["parameters"][3] == 2.0
    assert updated["parameters"][5] == -3.0


def test_bounds_and_penalty_match_model_contract():
    _, objective = synthetic_problem(3)
    assert objective.bounds[:2] == [(-200.0, 200.0), (-200.0, 200.0)]
    assert objective.bounds[2] == (None, None)
    assert objective.bounds[3] == (-50.0, 50.0)
    assert objective.bounds[6] == (-10.0, 10.0)
    vector = objective.initial_vector
    vector[6] = 3.0
    vector[7:] = [0.4, -0.2]
    value, gradient = objective.penalty(vector)
    state = objective.state(vector)
    expected = 0.5 * np.sum(state["individual_shifts_s"] ** 2) + 0.5 * (3.0 / 10) ** 2
    assert value == pytest.approx(expected)
    assert gradient[6] == pytest.approx(0.03)


def test_invalid_ephemeris_evaluation_is_finite_and_not_recorded_best():
    data, objective = synthetic_problem(3)
    data.nodes[:] = [149.0, 153.0]
    objective.minimum_shift_s = 0.0
    objective.maximum_shift_s = 1.0
    vector = objective.initial_vector
    vector[6] = -1.0
    value, gradient = objective.evaluate(vector)
    assert value >= 1e30
    assert np.all(np.isfinite(gradient))
    assert objective.best is None
