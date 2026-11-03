from __future__ import annotations

from types import SimpleNamespace

import finite_set_rf_fit as module
import numpy as np
import pytest


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, values):
        return self.matrix.T @ np.asarray(values, dtype=float)


class LinearPlan:
    def __init__(self, data, satellites, matrix):
        self.data = data
        self.satellites = np.asarray(satellites)
        self.matrix = np.asarray(matrix, dtype=float)

    def predict(self, parameters):
        predicted = self.matrix @ np.asarray(parameters, dtype=float)
        visible = np.ones_like(predicted, dtype=bool)
        return predicted, visible, DenseJacobian(self.matrix)


class QuadraticLikelihood:
    def __init__(self, target, groups):
        self.target = np.asarray(target, dtype=float)
        self.groups = np.asarray(groups)

    def evaluate(self, predicted, visible, **kwargs):
        del visible, kwargs
        residual = np.asarray(predicted) - self.target
        return {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
            "group_values": np.unique(self.groups),
            "satellite_support": np.ones(predicted.shape[1]),
            "null_support": 0.0,
        }


def synthetic_problem():
    data = SimpleNamespace(
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.array([0, 1, 2, 3]),
        receiver=np.array([0, 0, 1, 1]),
        rf=np.array([10e9, 12e9, 10.5e9, 11.5e9]),
        numbers=np.array([100, 200, 300]),
    )
    satellites = np.array([0, 2])
    parameter_count = 6 + len(data.numbers)
    matrix = np.arange(4 * 2 * parameter_count, dtype=float).reshape(8, parameter_count)
    matrix = (matrix % 11 - 5) / 50.0
    parameters = np.linspace(-0.3, 0.4, parameter_count)
    parameters[6:] = np.array([0.2, 0.0, -0.4])
    active, scales, bounds = module.optimization_specification(parameter_count - 6, satellites)
    design, _, _ = module.receiver_rf_design(data)
    vector = np.r_[parameters[active], [30.0, -45.0]] / scales
    target = np.linspace(-0.2, 0.3, 8).reshape(4, 2)
    plan = LinearPlan(data, satellites, matrix)
    likelihood = QuadraticLikelihood(target, data.group)
    return data, satellites, parameters, active, scales, bounds, design, vector, plan, likelihood


def test_joint_gradient_matches_finite_difference():
    data, satellites, parameters, active, scales, _, design, vector, plan, likelihood = (
        synthetic_problem()
    )

    def evaluate(candidate):
        return module.evaluate_joint_objective(
            candidate,
            data=data,
            source_parameters=parameters,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
            design=design,
            active=active,
            scales=scales,
        )

    analytic = evaluate(vector)["gradient"]
    numeric = np.empty_like(analytic)
    step = 1e-6
    for index in range(len(vector)):
        upper = vector.copy()
        lower = vector.copy()
        upper[index] += step
        lower[index] -= step
        numeric[index] = (evaluate(upper)["objective"] - evaluate(lower)["objective"]) / (
            2 * step
        )
    np.testing.assert_allclose(analytic, numeric, rtol=2e-6, atol=2e-6)


def test_zero_rf_exactly_reproduces_source_objective():
    data, satellites, parameters, active, scales, _, design, vector, plan, likelihood = (
        synthetic_problem()
    )
    vector[-2:] = 0
    state = module.evaluate_joint_objective(
        vector,
        data=data,
        source_parameters=parameters,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
        design=design,
        active=active,
        scales=scales,
    )
    prediction, visible, _ = plan.predict(state["parameters"])
    direct = likelihood.evaluate(prediction.reshape(4, 2), visible.reshape(4, 2))
    tau = state["parameters"][6 + satellites]
    expected = -direct["total_log_likelihood"] + 0.5 * np.sum(tau**2)
    assert state["objective"] == pytest.approx(expected, abs=1e-12)
    assert state["coefficient_prior"] == 0


def test_prior_penalty_and_bound_ordering():
    active, scales, bounds = module.optimization_specification(7, np.array([1, 4, 6]))
    assert active.tolist() == [0, 1, 2, 3, 4, 5, 7, 10, 12]
    assert scales[-2:].tolist() == [250.0, 250.0]
    assert bounds[3] == (-5.0, 5.0)
    assert bounds[5] == (-5.0, 5.0)
    assert bounds[6:9] == [(-3.0, 3.0)] * 3
    assert bounds[-2:] == [(-4.0, 4.0)] * 2
    penalty = module.model_penalties(101, 7)
    assert penalty["source_entry_penalty"] == pytest.approx(3.5 * np.log(101))
    assert penalty["rf_dof_penalty"] == pytest.approx(np.log(101))
    assert penalty["total_entry_penalty"] == pytest.approx(4.5 * np.log(101))


def test_receiver_rf_design_is_groupwise_and_midpoint_centered():
    data = SimpleNamespace(
        receiver=np.array([0, 0, 0, 1, 1]),
        rf=np.array([10e9, 10e9, 12e9, 11e9, 13e9]),
        group=np.array([1, 1, 2, 3, 4]),
    )
    design, centers, spans = module.receiver_rf_design(data)
    np.testing.assert_array_equal(centers, [11e9, 12e9])
    np.testing.assert_allclose(design[:, 0], [-1, -1, 1, 0, 0])
    np.testing.assert_allclose(design[:, 1], [0, 0, 0, -1, 1])
    assert [row["span_ghz"] for row in spans] == [2.0, 2.0]
    data.rf[1] += 1
    with pytest.raises(ValueError, match="one receiver and RF"):
        module.receiver_rf_design(data)


@pytest.mark.parametrize("terminal_is_best", [False, True])
def test_solver_success_does_not_override_projected_gradient_or_best_state(terminal_is_best):
    data, satellites, parameters, active, scales, _, design, vector, plan, likelihood = (
        synthetic_problem()
    )
    initial = module.evaluate_joint_objective(
        np.r_[parameters[active], [0.0, 0.0]] / scales,
        data=data,
        source_parameters=parameters,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
        design=design,
        active=active,
        scales=scales,
    )
    source = {
        "satellite_indices": satellites,
        "parameters": parameters,
        "objective": initial["objective"],
        "entry_penalty": 0.5 * len(satellites) * np.log(4),
    }

    def fake_minimize(fun, start, **kwargs):
        del kwargs
        worse = np.asarray(start).copy()
        if not terminal_is_best:
            worse[0] += 0.25
        fun(worse)
        return SimpleNamespace(success=True, status=0, message="ftol", nit=1, x=worse)

    result = module.fit_rf_trial(
        data,
        source,
        3,
        likelihood,
        design,
        plan_factory=lambda ignored_data, ignored_satellites: plan,
        minimize_fn=fake_minimize,
    )
    assert result["objective"] == pytest.approx(source["objective"])
    assert result["optimizer_success"] is True
    assert result["best_is_optimizer_terminal"] is terminal_is_best
    assert result["success"] is False
    if terminal_is_best:
        assert result["projected_gradient_inf_norm"] > module.STATIONARITY_THRESHOLD
        assert result["convergence_reason"] == "solver_success_without_projected_stationarity"
    else:
        assert result["convergence_reason"] == "retained_best_not_optimizer_terminal"


@pytest.mark.parametrize("corruption", [
    "profile", "source_hashes", "global_reference_accessed", "global_evaluation_artifact_accessed",
    "global_fit_performed", "unit_reference_accessed", "unit_evaluation_artifact_accessed",
    "unit_fit_performed",
])
def test_source_and_diagnostic_provenance_reject_mismatch(tmp_path, monkeypatch, corruption):
    root = tmp_path / "experiment"
    root.mkdir()
    source_path = root / "profile.json"
    source_path.write_text("source")
    diagnostic_path = root / "diagnostic.json"
    diagnostic_path.write_text("diagnostic")
    source = {
        "source_fit_sha256": "a" * 64,
        "source_hashes": {"/input": "b" * 64},
    }
    diagnostic = {
        "schema": "finite-set-rf-zero-score/v1",
        "sealed": True,
        "failed_unit_count": 0,
        "provenance": {"reference_accessed": False, "evaluation_artifact_accessed": False,
                       "fit_performed": False},
        "configuration": {
            "sigma_hz": 200.0,
            "coefficient_prior_sigma_hz_per_ghz": 250.0,
            "rf_center_policy": "midpoint of observed RF span independently per receiver/unit",
        },
        "units": [
            {
                "unit_id": "DS10-S01",
                "status": "complete",
                "profile_fit_sha256": "actual-profile",
                "profile_source_fit_sha256": "a" * 64,
                "sealed_profile_source_hashes": source["source_hashes"],
                "input_sha256_pre": {},
                "input_sha256_post": {},
                "source_sha256_pre": {"code": "hash"},
                "source_sha256_post": {"code": "hash"},
                "provenance": {"reference_accessed": False, "evaluation_artifact_accessed": False,
                               "fit_performed": False},
            }
        ],
    }
    row = diagnostic["units"][0]
    if corruption == "profile":
        row["profile_fit_sha256"] = "wrong"
    elif corruption == "source_hashes":
        row["source_sha256_post"] = {"code": "changed"}
    elif corruption.startswith("global_"):
        diagnostic["provenance"][corruption.removeprefix("global_")] = True
    else:
        row["provenance"][corruption.removeprefix("unit_")] = True
    monkeypatch.setattr(module, "digest", lambda path: "actual-profile")
    with pytest.raises(ValueError, match="RF diagnostic"):
        module.validate_diagnostic(
            diagnostic, diagnostic_path, source, source_path, "DS10-S01"
        )
