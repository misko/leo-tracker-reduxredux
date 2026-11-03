from __future__ import annotations

import json
from types import SimpleNamespace

import finite_set_prior_sensitivity_run as runner
import numpy as np
import pytest


def synthetic_data():
    return SimpleNamespace(
        times=np.array([0.0, 1.0]),
        numbers=np.array([100, 200, 300]),
    )


def source_trial(objective=10.625):
    parameters = np.zeros(9)
    parameters[[6, 8]] = [0.5, -1.0]
    return {
        "satellite_indices": np.array([0, 2]),
        "parameters": parameters,
        "satellite_weights": np.array([0.4, 0.6]),
        "objective": objective,
    }


class Jacobian:
    def transpose_multiply(self, weights):
        np.testing.assert_array_equal(weights, np.array([1.0, 2.0, 3.0, 4.0]))
        return np.arange(1.0, 10.0)

    def normal_matrix(self, weights):
        np.testing.assert_array_equal(weights, np.array([0.5, 1.0, 1.5, 2.0]))
        return np.diag(np.arange(2.0, 11.0))


class Plan:
    def __init__(self, data, satellites):
        assert data is DATA
        np.testing.assert_array_equal(satellites, [0, 2])

    def predict(self, parameters):
        np.testing.assert_array_equal(parameters, source_trial()["parameters"])
        return np.zeros(4), np.ones(4, dtype=bool), Jacobian()


class Evaluator:
    def evaluate(self, predicted, visible, **kwargs):
        np.testing.assert_array_equal(predicted, np.zeros((2, 2)))
        np.testing.assert_array_equal(visible, np.ones((2, 2), dtype=bool))
        assert kwargs["sigma_hz"] == 200.0
        np.testing.assert_array_equal(kwargs["satellite_weights"], [0.4, 0.6])
        assert kwargs["background_mass"] == 0.2
        assert kwargs["return_gradient"] is True
        assert kwargs["return_precision"] is True
        return {
            "total_log_likelihood": -10.0,
            "prediction_gradient": np.array([[1.0, 2.0], [3.0, 4.0]]),
            "prediction_precision": np.array([[0.5, 1.0], [1.5, 2.0]]),
        }


DATA = synthetic_data()


def test_exact_scaled_gnv2_state_is_passed_to_helper():
    captured = {}

    def helper(hessian, total_gradient, prior_gradient, vector, bounds, scales):
        captured.update(
            hessian=hessian,
            total_gradient=total_gradient,
            prior_gradient=prior_gradient,
            vector=vector,
            bounds=bounds,
            scales=scales,
        )
        return {
            "available": True,
            "physical_response_per_unit_precision": [0.0] * 8,
            "position_response_km_per_unit_precision": [0.0, 0.0],
            "linearized_zero_precision_position_shift_km": [0.0, 0.0],
            "condition_number": 1.0,
            "free_mask": [True] * 8,
        }

    result = runner.compute_prior_sensitivity(
        DATA,
        source_trial(),
        Evaluator(),
        plan_factory=Plan,
        sensitivity=helper,
    )

    scales = np.array([20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, 1.0, 1.0])
    active = np.array([0, 1, 2, 3, 4, 5, 6, 8])
    physical_hessian = np.diag(np.arange(2.0, 11.0))
    physical_hessian[[6, 8], [6, 8]] += 1.0
    expected_hessian = physical_hessian[np.ix_(active, active)]
    expected_hessian *= scales[:, None] * scales[None, :]
    physical_gradient = -np.arange(1.0, 10.0)
    physical_gradient[[6, 8]] += [0.5, -1.0]
    np.testing.assert_allclose(captured["hessian"], expected_hessian)
    np.testing.assert_allclose(
        captured["total_gradient"], physical_gradient[active] * scales
    )
    np.testing.assert_array_equal(
        captured["prior_gradient"], [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, -1.0]
    )
    np.testing.assert_array_equal(captured["scales"], scales)
    assert result["status"] == "complete"
    assert result["reproduced_objective"] == pytest.approx(10.625)
    assert result["source_parameters_unchanged"]


def test_source_objective_must_reproduce_exactly():
    with pytest.raises(ValueError, match="does not reproduce sealed objective"):
        runner.compute_prior_sensitivity(
            DATA,
            source_trial(objective=11.0),
            Evaluator(),
            plan_factory=Plan,
            sensitivity=lambda *args: {"available": True},
        )


def test_dependencies_are_snapshotted_before_source_validation():
    paths = runner.source_dependency_paths()
    names = {path.name for path in paths}
    assert {
        "finite_set_prior_sensitivity_run.py",
        "finite_set_prior_sensitivity.py",
        "finite_set_satellite_influence.py",
        "finite_set_rf_score.py",
    } <= names
    order = []

    def snapshotter(received):
        order.append("snapshot")
        assert received == paths
        return {str(path): "a" * 64 for path in paths}

    receipt = runner.snapshot_before_validation(snapshotter=snapshotter)
    order.append("validator_would_run_next")
    assert order == ["snapshot", "validator_would_run_next"]
    assert len(receipt) == len(paths)


def test_source_receipt_corruption_is_rejected(monkeypatch, tmp_path):
    grouped_path = tmp_path / "fit.json"
    grouped_path.write_text("grouped")
    monkeypatch.setattr(runner, "digest", lambda path: "b" * 64)
    profile = {
        "run_id": runner.SOURCE_RUN,
        "unit": {"unit_id": "DS10-S01", "size": 1},
        "dataset": "DS10",
        "source_fit_sha256": "b" * 64,
        "source_hashes": {"input": "c" * 64},
    }
    grouped = {
        "schema": "finite-set-grouped-cohort/v1",
        "unit": {"unit_id": "DS10-S01"},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
    }
    monkeypatch.setattr(runner, "_selected_trial", lambda value: {"selected": True})
    trial, hashes = runner.validate_source_receipts(
        profile, grouped, "DS10-S01", grouped_path
    )
    assert trial == {"selected": True}
    assert hashes == profile["source_hashes"]

    changed = dict(profile, source_fit_sha256="d" * 64)
    with pytest.raises(ValueError, match="not strictly bound"):
        runner.validate_source_receipts(changed, grouped, "DS10-S01", grouped_path)

    changed_grouped = dict(grouped, evaluation_written=True)
    with pytest.raises(ValueError, match="not strictly bound"):
        runner.validate_source_receipts(
            profile, changed_grouped, "DS10-S01", grouped_path
        )


def test_run_requires_all32_and_declares_no_fit_or_correction():
    calls = []

    def diagnoser(unit_id, **kwargs):
        calls.append(unit_id)
        return {"unit_id": unit_id}

    receipt = runner.run(diagnoser=diagnoser)
    assert tuple(calls) == runner.ALL_UNITS
    assert len(receipt["units"]) == 32
    assert "not a fit or correction" in receipt["scope"]
    with pytest.raises(ValueError, match="exactly all 32"):
        runner.run(runner.ALL_UNITS[:-1], diagnoser=diagnoser)


def test_main_refuses_to_overwrite_existing_output(monkeypatch, tmp_path):
    output = tmp_path / "existing.json"
    output.write_text(json.dumps({"sealed": True}))
    monkeypatch.setattr(runner, "run", lambda **kwargs: {"units": []})
    monkeypatch.setattr(
        "sys.argv",
        ["finite_set_prior_sensitivity_run.py", "--output", str(output)],
    )
    with pytest.raises(FileExistsError):
        runner.main()
