from types import SimpleNamespace

import finite_set_satellite_influence as influence
import numpy as np
import pytest


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights, dtype=float)

    def normal_matrix(self, weights):
        return self.matrix.T @ (np.asarray(weights, dtype=float)[:, None] * self.matrix)


class Plan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites)

    def predict(self, parameters):
        count = len(self.data.times) * len(self.satellites)
        return self.data.predicted.ravel(), np.ones(count, dtype=bool), DenseJacobian(
            self.data.jacobian
        )


class Evaluator:
    def __init__(self, data, objective):
        self.data = data
        self.objective = objective

    def evaluate(self, predicted, visible, **kwargs):
        assert kwargs["return_gradient"] and kwargs["return_precision"]
        return {
            "total_log_likelihood": -self.objective,
            "prediction_gradient": self.data.prediction_score.copy(),
            "prediction_precision": self.data.prediction_precision.copy(),
            "row_association_probability": self.data.association.copy(),
            "satellite_support": np.sum(self.data.association, axis=0),
            "alias_hz": 1 / 4.4e-6,
        }


def synthetic_problem():
    generator = np.random.default_rng(20261002)
    row_count = 6
    satellite_count = 2
    parameter_count = 8
    jacobian = generator.normal(size=(row_count * satellite_count, parameter_count))
    jacobian[:parameter_count] += 2 * np.eye(parameter_count)
    prediction_score = generator.normal(scale=0.02, size=(row_count, satellite_count))
    prediction_precision = generator.uniform(0.5, 1.5, size=(row_count, satellite_count))
    association = generator.uniform(0.1, 0.9, size=(row_count, satellite_count))
    predicted = generator.normal(scale=100, size=(row_count, satellite_count))
    measured = predicted[:, 0] + generator.normal(scale=10, size=row_count)
    data = SimpleNamespace(
        times=np.linspace(100, 160, row_count),
        measured=measured,
        numbers=np.array([61001, 61002]),
        predicted=predicted,
        jacobian=jacobian,
        prediction_score=prediction_score,
        prediction_precision=prediction_precision,
        association=association,
    )
    parameters = np.array([20.0, -30.0, 4000.0, 2.0, -5000.0, -3.0, 0.4, -0.7])
    tau_prior = 0.5 * np.sum(parameters[6:] ** 2)
    likelihood_objective = 123.0
    trial = {
        "satellite_indices": [0, 1],
        "parameters": parameters,
        "satellite_weights": [0.5, 0.5],
        "objective": likelihood_objective + tau_prior,
    }
    return data, trial, Evaluator(data, likelihood_objective)


def test_masked_gradients_and_common_nuisance_solve_sum_exactly():
    data, trial, evaluator = synthetic_problem()

    result = influence.compute_satellite_influence(
        data,
        trial,
        evaluator,
        plan_factory=Plan,
    )

    assert result["status"] == "complete"
    assert result["availability"]["gradient_sum_max_abs_error"] < 1e-12
    assert result["availability"]["step_sum_max_abs_error"] < 1e-12
    assert result["availability"]["free_parameter_count"] == 8
    assert result["total_score_step_east_km"] == pytest.approx(
        result["sum_satellite_step_east_km"]
    )
    assert result["total_score_step_north_km"] == pytest.approx(
        result["sum_satellite_step_north_km"]
    )
    assert result["method"]["position_scale_km"] == 20.0
    assert "not exact delete-one" in result["interpretation"]


def test_solver_uses_total_gradient_free_mask_and_full_nuisance_system():
    gradients = np.array([[-2.0, 1.0, 3.0], [-1.0, -2.0, -1.0]])
    hessian = np.array([[5.0, 1.0, 2.0], [1.0, 4.0, 0.5], [2.0, 0.5, 6.0]])
    total = gradients.sum(axis=0)
    vector = np.array([10.0, 0.0, 0.0])
    bounds = [(-10.0, 10.0), (None, None), (None, None)]
    scales = np.array([20.0, 20.0, 1000.0])

    result = influence.solve_score_allocations(
        gradients, total, hessian, vector, bounds, scales
    )

    assert result["diagnostics"]["available"]
    assert result["free"].tolist() == [False, True, True]
    expected = np.linalg.solve(hessian[1:, 1:], -gradients[:, 1:].T).T
    np.testing.assert_allclose(result["per_satellite_steps_scaled"][:, 1:], expected)
    assert np.all(result["per_satellite_steps_scaled"][:, 0] == 0)
    assert result["per_satellite_steps_physical"][0, 1] == pytest.approx(
        20 * expected[0, 0]
    )


@pytest.mark.parametrize(
    "hessian, reason",
    [
        (np.diag([1.0, -0.1]), "materially_indefinite"),
        (np.diag([1.0, 1e-15]), "nonpositive_or_rank_deficient"),
        (np.diag([1.0, 1e-8]), "ill_conditioned"),
    ],
)
def test_bad_curvature_is_reported_unavailable_without_pseudoinverse(hessian, reason):
    gradients = np.array([[0.2, -0.1], [-0.3, 0.4]])
    result = influence.solve_score_allocations(
        gradients,
        gradients.sum(axis=0),
        hessian,
        np.zeros(2),
        [(None, None), (None, None)],
        np.ones(2),
        condition_limit=1e7,
    )
    assert not result["diagnostics"]["available"]
    assert result["diagnostics"]["reason"] == reason
    assert result["diagnostics"]["pseudoinverse_used"] is False


def test_corrupted_gradient_sum_and_objective_are_rejected():
    gradients = np.array([[1.0, 2.0], [3.0, 4.0]])
    with pytest.raises(ValueError, match="do not sum"):
        influence.solve_score_allocations(
            gradients,
            np.array([4.0, 6.1]),
            np.eye(2),
            np.zeros(2),
            [(None, None), (None, None)],
            np.ones(2),
        )

    data, trial, evaluator = synthetic_problem()
    trial["objective"] += 1
    with pytest.raises(ValueError, match="does not reproduce"):
        influence.compute_satellite_influence(
            data,
            trial,
            evaluator,
            plan_factory=Plan,
        )


def test_run_defaults_to_two_and_requires_explicit_all32(monkeypatch):
    monkeypatch.setattr(
        influence,
        "diagnose_unit",
        lambda unit_id, **kwargs: {"unit_id": unit_id, "status": "complete"},
    )
    default = influence.run()
    assert [row["unit_id"] for row in default["units"]] == list(influence.INITIAL_UNITS)
    with pytest.raises(ValueError, match="exactly"):
        influence.run(["DS10-S01"])
    all_units = influence.run(allow_all_32=True)
    assert len(all_units["units"]) == 32
    assert all_units["configuration"]["allow_all_32"] is True
