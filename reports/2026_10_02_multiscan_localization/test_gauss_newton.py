from types import SimpleNamespace

import gauss_newton
import numpy as np
from coherent_fit import FixedBankLikelihood
from test_staged_gradient import synthetic_orbital_data
from track_likelihood import prepare_track_grouped_likelihood


class LinearJacobian:
    def __init__(self, design):
        self.design = design

    def transpose_multiply(self, weights):
        return self.design.T @ np.asarray(weights)

    def normal_matrix(self, weights):
        weights = np.asarray(weights)
        return self.design.T @ (weights[:, None] * self.design)


class LinearPredictionPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites)

    def predict(self, parameters):
        predicted = self.data.design @ parameters
        visible = np.ones_like(predicted, dtype=bool)
        return predicted, visible, LinearJacobian(self.data.design)


class QuadraticPrepared:
    def __init__(self, target, sigma_hz=1.0):
        self.target = np.asarray(target)
        self.sigma_hz = sigma_hz
        self.calls = []
        self.last_prediction = None

    def evaluate(self, predicted, visible, **options):
        assert options["return_gradient"] is True
        assert options["return_precision"] is True
        assert options["background_mass"] == 0.2
        assert np.all(visible)
        residual = np.asarray(predicted) - self.target
        precision = np.full_like(residual, 1.0 / self.sigma_hz**2)
        self.calls.append(np.asarray(predicted).copy())
        self.last_prediction = np.asarray(predicted).copy()
        return {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2) / self.sigma_hz**2),
            "prediction_gradient": -residual / self.sigma_hz**2,
            "prediction_precision": precision,
            "group_values": np.arange(predicted.shape[0]),
            "satellite_support": np.ones(predicted.shape[1]),
            "null_support": 0.0,
        }


class FlatPrepared:
    def __init__(self):
        self.calls = 0

    def evaluate(self, predicted, visible, **options):
        assert options["return_gradient"] is True
        assert options["return_precision"] is True
        self.calls += 1
        return {
            "total_log_likelihood": -5.0,
            "prediction_gradient": np.zeros_like(predicted),
            "prediction_precision": np.zeros_like(predicted),
            "group_values": np.arange(predicted.shape[0]),
            "satellite_support": np.zeros(predicted.shape[1]),
            "null_support": float(predicted.shape[0]),
        }


def linear_fixture(row_count=6):
    candidate_count = 2
    parameter_count = 6 + candidate_count
    output_count = row_count * candidate_count
    rng = np.random.default_rng(84)
    design = rng.normal(size=(output_count, parameter_count))
    design[:parameter_count] += np.eye(parameter_count)
    data = SimpleNamespace(
        numbers=np.array([101, 202]),
        times=np.arange(row_count, dtype=float),
        design=design,
        provenance={"reference_truth_read": False},
    )
    return data


def test_gauss_newton_descends_actual_objective(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    data = linear_fixture()
    satellites = np.array([0, 1])
    target_parameters = np.array([15.0, -10.0, 120.0, 2.0, -80.0, -1.5, 0.4, -0.3])
    target = (data.design @ target_parameters).reshape(len(data.times), len(satellites))
    prepared = QuadraticPrepared(target)
    result = gauss_newton.refine_gauss_newton(
        data,
        np.zeros(8),
        satellites,
        np.array([9.0, 7.0]),
        prepared,
        sigma_hz=1.0,
        budget_s=5.0,
    )

    assert result["objective"] < result["initial_objective"]
    assert result["success"]
    assert result["accepted_steps"] > 0
    assert result["shared_predictions"] is True
    assert result["curvature_method"].startswith("Complete-data/Fisher")
    assert len(prepared.calls) == result["evaluations"]
    np.testing.assert_allclose(
        prepared.last_prediction.ravel(), data.design @ result["parameters"]
    )
    assert data.provenance["reference_truth_read"] is False


def test_gauss_newton_enforces_bounds_and_tau_prior(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    data = linear_fixture()
    initial = np.array([300.0, -250.0, 40.0, 80.0, -30.0, -90.0, 2.5, -2.0])
    prepared = FlatPrepared()
    result = gauss_newton.refine_gauss_newton(
        data,
        initial,
        np.array([0, 1]),
        np.array([1.0, 1.0]),
        prepared,
        tau_sigma_s=0.5,
        tau_bound_s=3.0,
        slope_bound=50.0,
        budget_s=5.0,
    )

    parameters = result["parameters"]
    np.testing.assert_allclose(parameters[:2], [200.0, -200.0])
    np.testing.assert_allclose(parameters[[3, 5]], [50.0, -50.0])
    np.testing.assert_allclose(parameters[6:], 0.0, atol=1e-7)
    assert result["objective"] < result["initial_objective"]
    assert result["success"]
    assert prepared.calls == result["evaluations"]


def test_gauss_newton_preserves_best_finite_on_later_failure(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    data = linear_fixture()
    target = np.ones((len(data.times), 2))

    class FailingPrepared(QuadraticPrepared):
        def evaluate(self, predicted, visible, **options):
            if self.calls:
                raise RuntimeError("synthetic later failure")
            return super().evaluate(predicted, visible, **options)

    prepared = FailingPrepared(target)
    result = gauss_newton.refine_gauss_newton(
        data,
        np.zeros(8),
        np.array([0, 1]),
        np.array([1.0, 1.0]),
        prepared,
        sigma_hz=1.0,
        budget_s=5.0,
    )

    assert np.isfinite(result["objective"])
    assert result["objective"] == result["initial_objective"]
    assert not result["success"]
    assert result["convergence_reason"].startswith("evaluation_error:RuntimeError")
    assert result["final_evaluation_error"].startswith("RuntimeError")
    assert result["best_finite_preserved"] is True


def test_gauss_newton_tiny_step_is_not_false_convergence(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    monkeypatch.setattr(
        gauss_newton.np.linalg,
        "solve",
        lambda system, right_hand_side: 1e-12 * np.sign(right_hand_side),
    )
    data = linear_fixture()
    target = np.ones((len(data.times), 2))
    result = gauss_newton.refine_gauss_newton(
        data,
        np.zeros(8),
        np.array([0, 1]),
        np.array([1.0, 1.0]),
        QuadraticPrepared(target),
        sigma_hz=1.0,
        budget_s=5.0,
    )

    assert not result["success"]
    assert result["convergence_reason"] == "tiny_accepted_step_without_gradient_convergence"
    assert result["last_accepted_step_inf_norm"] <= 1e-6
    assert result["last_accepted_loss_decrease"] > 0
    assert result["damping_to_free_min_eigenvalue"] > 1e-6
    assert not result["low_damping_positive_newton_converged"]


def test_gauss_newton_solves_only_free_block_at_active_bound(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    data = linear_fixture(row_count=4)
    data.design = np.eye(8)
    target_parameters = np.array([300.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    target = target_parameters.reshape(len(data.times), 2)
    prepared = QuadraticPrepared(target)
    solve = np.linalg.solve
    system_sizes = []

    def record_solve(system, right_hand_side):
        system_sizes.append(len(right_hand_side))
        return solve(system, right_hand_side)

    monkeypatch.setattr(gauss_newton.np.linalg, "solve", record_solve)
    initial = np.zeros(8)
    initial[0] = 300.0
    result = gauss_newton.refine_gauss_newton(
        data,
        initial,
        np.array([0, 1]),
        np.array([1.0, 1.0]),
        prepared,
        sigma_hz=1.0,
        budget_s=5.0,
    )

    assert system_sizes and max(system_sizes) == 7
    np.testing.assert_allclose(result["parameters"][0], 200.0)
    np.testing.assert_allclose(result["parameters"][2], 50.0, atol=1e-5)
    assert result["success"]


def test_newton_stationarity_requires_positive_curvature_and_low_damping():
    objective = 100.0
    gradient = np.array([5e-4, -1e-3])
    hessian = np.diag([100.0, 200.0])
    free = np.ones(2, dtype=bool)

    accepted = gauss_newton._newton_stationarity(
        objective, gradient, hessian, free, damping=1e-8
    )
    assert accepted["low_damping_positive_newton_converged"]
    assert accepted["undamped_newton_step_inf_norm"] == 5e-6
    assert accepted["modeled_newton_relative_loss_decrease"] < 1e-10

    high_damping = gauss_newton._newton_stationarity(
        objective, gradient, hessian, free, damping=1.0
    )
    assert high_damping["undamped_newton_step_inf_norm"] == 5e-6
    assert high_damping["damping_to_free_min_eigenvalue"] > 1e-6
    assert not high_damping["low_damping_positive_newton_converged"]

    indefinite = gauss_newton._newton_stationarity(
        objective, gradient, np.diag([-1.0, 200.0]), free, damping=1e-8
    )
    assert not indefinite["low_damping_positive_newton_converged"]


def test_gauss_newton_fixed_position_is_exact_and_excluded_from_free_block(monkeypatch):
    monkeypatch.setattr(gauss_newton, "SharedPredictionPlan", LinearPredictionPlan)
    data = linear_fixture(row_count=4)
    data.design = np.eye(8)
    target_parameters = np.array([90.0, -70.0, 40.0, 2.0, -30.0, -1.0, 0.2, -0.1])
    target = target_parameters.reshape(len(data.times), 2)
    fixed_position = np.array([12.3456789, -8.2345678])
    system_sizes = []
    solve = np.linalg.solve

    def record_solve(system, right_hand_side):
        system_sizes.append(len(right_hand_side))
        return solve(system, right_hand_side)

    monkeypatch.setattr(gauss_newton.np.linalg, "solve", record_solve)
    result = gauss_newton.refine_gauss_newton(
        data,
        np.zeros(8),
        np.array([0, 1]),
        np.array([1.0, 1.0]),
        QuadraticPrepared(target),
        sigma_hz=1.0,
        fixed_position_km=fixed_position,
        budget_s=5.0,
    )

    np.testing.assert_array_equal(result["parameters"][:2], fixed_position)
    np.testing.assert_array_equal(result["fixed_position_km"], fixed_position)
    assert result["position_fixed"] is True
    assert result["zero_width_bound_count"] == 2
    assert result["free_parameter_count"] == 6
    assert system_sizes and max(system_sizes) == 6
    assert data.provenance["reference_truth_read"] is False


def test_gauss_newton_integrates_shared_orbit_fisher_and_coherent_precision():
    data, initial = synthetic_orbital_data()
    satellites = np.array([0, 2])
    perturbed = initial.copy()
    perturbed[:6] += [1.2, -0.8, 15.0, 0.12, -11.0, -0.09]
    perturbed[6 + satellites] += [0.08, -0.06]
    grouped = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=np.ones(len(data.times)),
        anchors=[],
    )
    masses = {
        "raw_satellite_mass": np.array([0.4, 0.4]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.empty((0, 2)),
        "anchor_unknown_mass": np.empty(0),
    }
    likelihood = FixedBankLikelihood(grouped, masses)
    result = gauss_newton.refine_gauss_newton(
        data,
        perturbed,
        satellites,
        np.array([4.0, 3.0]),
        likelihood,
        sigma_hz=260.0,
        tau_sigma_s=0.7,
        budget_s=5.0,
    )

    assert np.isfinite(result["objective"])
    assert result["objective"] <= result["initial_objective"]
    assert result["evaluations"] >= 1
    assert np.all(np.isfinite(likelihood.last_result["prediction_gradient"]))
    assert np.all(np.isfinite(likelihood.last_result["prediction_precision"]))
    assert np.all(likelihood.last_result["prediction_precision"] >= 0)
    assert data.provenance["reference_truth_read"] is False
