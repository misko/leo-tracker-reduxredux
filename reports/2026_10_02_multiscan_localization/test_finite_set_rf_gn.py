from __future__ import annotations

from types import SimpleNamespace

import finite_set_rf_gn as model
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
    def __init__(self, matrix, data, satellites):
        self.matrix = np.asarray(matrix, dtype=float)
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)

    def predict(self, parameters):
        predicted = self.matrix @ np.asarray(parameters, dtype=float)
        visible = np.ones_like(predicted, dtype=bool)
        return predicted, visible, DenseJacobian(self.matrix)


class FixedPrecisionLikelihood:
    def __init__(self, target, precision):
        self.target = np.asarray(target, dtype=float)
        self.precision = np.asarray(precision, dtype=float)
        self.last_result = None

    def evaluate(self, predicted, visible, **options):
        del visible, options
        residual = np.asarray(predicted, dtype=float) - self.target
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
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.arange(4),
        receiver=np.array([0, 0, 1, 1]),
        rf=np.array([10e9, 12e9, 10.5e9, 11.5e9]),
        numbers=np.arange(candidate_count),
    )


def source_trial(data, satellites, parameters, coefficients, *, groups=4):
    satellite_count = len(satellites)
    penalties = model.model_penalties(groups, satellite_count)
    return {
        "satellite_indices": np.asarray(satellites, dtype=int),
        "parameters": np.asarray(parameters, dtype=float),
        "coefficients_hz_ghz": np.asarray(coefficients, dtype=float),
        "entry_penalty": penalties["source_entry_penalty"],
        "total_entry_penalty": penalties["total_entry_penalty"],
    }


def test_gradient_and_fisher_cross_blocks_match_dense_oracles():
    rng = np.random.default_rng(497)
    data = synthetic_data()
    satellites = np.array([0, 2])
    full_size = 6 + len(data.numbers)
    matrix = rng.normal(size=(len(data.times) * len(satellites), full_size)) / 30
    parameters = rng.normal(size=full_size)
    parameters[6:] = [0.2, -0.1, 0.3]
    trial = source_trial(data, satellites, parameters, [35.0, -20.0])
    specification = model.rf_trial_specification(data, trial)
    design, _, _ = model.receiver_rf_design(data)
    target = rng.normal(size=(len(data.times), len(satellites)))
    precision = rng.uniform(0.002, 0.02, size=target.shape)
    likelihood = FixedPrecisionLikelihood(target, precision)
    plan = LinearPlan(matrix, data, satellites)
    vector = specification["vector"]
    state = model.evaluate_rf_fisher_state(
        vector,
        data=data,
        specification=specification,
        likelihood=likelihood,
        plan=plan,
        design=design,
    )

    step = 1e-6
    finite_gradient = np.empty_like(vector)
    finite_hessian = np.empty_like(state.hessian)
    for index in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[index] = step
        upper = model.evaluate_rf_fisher_state(
            vector + delta,
            data=data,
            specification=specification,
            likelihood=likelihood,
            plan=plan,
            design=design,
        )
        lower = model.evaluate_rf_fisher_state(
            vector - delta,
            data=data,
            specification=specification,
            likelihood=likelihood,
            plan=plan,
            design=design,
        )
        finite_gradient[index] = (upper.objective - lower.objective) / (2 * step)
        finite_hessian[:, index] = (upper.gradient - lower.gradient) / (2 * step)
    np.testing.assert_allclose(state.gradient, finite_gradient, rtol=4e-6, atol=5e-5)
    np.testing.assert_allclose(state.hessian, finite_hessian, rtol=4e-6, atol=5e-5)

    active_matrix = matrix[:, specification["active"]]
    expanded_design = np.repeat(design, len(satellites), axis=0)
    unscaled = np.column_stack([active_matrix, expanded_design])
    dense = unscaled.T @ (precision.ravel()[:, None] * unscaled)
    tau_start = 6
    for index in range(len(satellites)):
        dense[tau_start + index, tau_start + index] += 1.0
    dense[-2:, -2:] += np.eye(2) / model.RF_PRIOR_SIGMA_HZ_GHZ**2
    scaled_dense = dense * specification["scales"][:, None] * specification["scales"][None, :]
    np.testing.assert_allclose(state.hessian, scaled_dense, rtol=1e-12, atol=1e-12)


def test_rf_prior_and_source_state_are_preserved_exactly():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    parameters[6:] = [0.2, -0.3]
    coefficients = np.array([125.0, -250.0])
    matrix = np.zeros((len(data.times) * 2, len(parameters)))
    target = np.zeros((len(data.times), 2))
    precision = np.ones_like(target)
    likelihood = FixedPrecisionLikelihood(target, precision)
    trial = source_trial(data, satellites, parameters, coefficients)
    specification = model.rf_trial_specification(data, trial)
    design, _, _ = model.receiver_rf_design(data)
    plan = LinearPlan(matrix, data, satellites)
    state = model.evaluate_rf_fisher_state(
        specification["vector"],
        data=data,
        specification=specification,
        likelihood=likelihood,
        plan=plan,
        design=design,
    )
    trial["objective"] = state.objective
    result = model.fit_rf_gauss_newton_trial(
        data,
        trial,
        likelihood,
        design,
        budget_s=1.0,
        plan_factory=lambda source, selected: LinearPlan(matrix, source, selected),
    )
    assert result["objective"] <= trial["objective"]
    assert result["source_reproduction"]["sealed_source_objective_delta"] == 0
    assert result["source_reproduction"]["frozen_evaluator_objective_delta"] == 0
    assert result["source_reproduction"]["frozen_evaluator_gradient_max_abs_delta"] == 0
    assert state.coefficient_prior == pytest.approx(0.5 * (0.5**2 + 1.0**2))
    assert result["total_entry_penalty"] == pytest.approx(2.0 * np.log(4))


def test_upper_rf_bound_with_outward_gradient_is_converged():
    data = synthetic_data(candidate_count=1)
    satellites = np.array([0])
    parameters = np.zeros(7)
    coefficients = np.array([model.RF_BOUND_HZ_GHZ, 0.0])
    matrix = np.zeros((len(data.times), len(parameters)))
    design, _, _ = model.receiver_rf_design(data)
    target = (design @ np.array([2000.0, 0.0]))[:, None]
    precision = np.ones_like(target)
    likelihood = FixedPrecisionLikelihood(target, precision)
    trial = source_trial(data, satellites, parameters, coefficients)
    specification = model.rf_trial_specification(data, trial)
    state = model.evaluate_rf_fisher_state(
        specification["vector"],
        data=data,
        specification=specification,
        likelihood=likelihood,
        plan=LinearPlan(matrix, data, satellites),
        design=design,
    )
    trial["objective"] = state.objective
    result = model.fit_rf_gauss_newton_trial(
        data,
        trial,
        likelihood,
        design,
        budget_s=1.0,
        plan_factory=lambda source, selected: LinearPlan(matrix, source, selected),
    )
    assert result["success"] is True
    assert result["convergence_reason"] == "projected_gradient"
    assert result["coefficients_hz_ghz"][0] == model.RF_BOUND_HZ_GHZ
    assert result["projected_gradient_inf_norm"] <= 1e-4


def test_budget_exhaustion_retains_source_incumbent(monkeypatch):
    data = synthetic_data(candidate_count=1)
    satellites = np.array([0])
    parameters = np.zeros(7)
    coefficients = np.zeros(2)
    matrix = np.zeros((len(data.times), len(parameters)))
    design, _, _ = model.receiver_rf_design(data)
    target = (design @ np.array([100.0, -80.0]))[:, None]
    precision = np.ones_like(target)
    likelihood = FixedPrecisionLikelihood(target, precision)
    trial = source_trial(data, satellites, parameters, coefficients)
    specification = model.rf_trial_specification(data, trial)
    state = model.evaluate_rf_fisher_state(
        specification["vector"],
        data=data,
        specification=specification,
        likelihood=likelihood,
        plan=LinearPlan(matrix, data, satellites),
        design=design,
    )
    trial["objective"] = state.objective
    ticks = iter([0.0, 0.0, 2.0, 2.0, 2.0])
    monkeypatch.setattr(model.time, "monotonic", lambda: next(ticks, 2.0))
    result = model.fit_rf_gauss_newton_trial(
        data,
        trial,
        likelihood,
        design,
        budget_s=1.0,
        plan_factory=lambda source, selected: LinearPlan(matrix, source, selected),
    )
    assert result["success"] is False
    assert result["convergence_reason"] == "budget_exhausted"
    assert result["objective"] == trial["objective"]
    np.testing.assert_array_equal(result["coefficients_hz_ghz"], coefficients)


def test_source_binding_rejects_model_or_provenance_mismatch(monkeypatch):
    data = synthetic_data(candidate_count=1)
    data.geometry_receipt = {"geometry": "frozen"}
    source = {
        "schema": model.SOURCE_SCHEMA,
        "run_id": model.SOURCE_RUN,
        "unit": {"unit_id": "DS10-S01"},
        "dataset": "DS10",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed": True,
        "sealed_utc": "now",
        "source_hashes": {"/numerical.py": "a" * 64},
        "bound_input_hashes": {},
        "geometry_receipt": data.geometry_receipt,
        "fit": {
            "coefficient_prior_sigma_hz_ghz": 251.0,
            "coefficient_bound_hz_ghz": 1000.0,
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "coefficient_count": 2,
            "full_bank": [0],
            "trials": [{"satellite_indices": [0]}] * 5,
        },
    }
    monkeypatch.setattr(model, "assert_snapshot_unchanged", lambda hashes: None)
    with pytest.raises(ValueError, match="configuration differs"):
        model.validate_source_binding(source, "DS10-S01", data, [])
