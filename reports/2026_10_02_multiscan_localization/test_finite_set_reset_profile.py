import copy
from types import SimpleNamespace

import numpy as np
import pytest
from capture_reset_fit import capture_reset_model_penalty
from finite_set_cavity import prepare_replacement_scorer
from finite_set_fit import build_likelihood_arms
from finite_set_reset_profile import (
    FixedResetPredictor,
    fit_reset_profile_branches,
    validate_source_binding,
)
from finite_set_tau_profile import profile_timing_offsets


def _data():
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 10.0, 10.0]),
        measured=np.array([120.0, 260.0, -90.0, 30.0]),
        group=np.array([0, 0, 1, 1]),
        rf=np.full(4, 11.0e9),
        receiver=np.array([0, 0, 1, 1]),
        channel=np.zeros(4, dtype=int),
        capture_index=np.array([0, 0, 1, 1]),
        child_sessions=("first", "second"),
        child_origins_utc_ns=np.array([0, 100_000_000_000]),
        numbers=np.array([1001, 1002]),
    )


class _Plan:
    builds = []

    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)
        self.builds.append(tuple(self.satellites))

    def predict(self, parameters):
        receiver = self.data.receiver[:, None]
        tau = parameters[6 + self.satellites][None, :]
        intercept = parameters[2 + 2 * receiver]
        predicted = intercept + 100.0 * tau
        visible = np.ones_like(predicted, dtype=bool)
        return predicted.ravel(), visible.ravel(), None


def _source_trial(data, parameters, jumps, satellites):
    likelihood = build_likelihood_arms(data, len(satellites), len(satellites))["finite_set"]
    predictor = FixedResetPredictor(data, jumps, plan_factory=_Plan)
    predicted, visible = predictor(data, parameters, satellites)
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        satellite_weights=np.full(len(satellites), 1.0 / len(satellites)),
        background_mass=0.2,
    )
    objective = -result["total_log_likelihood"] + 0.5 * np.sum(parameters[6 + satellites] ** 2)
    penalty = capture_reset_model_penalty(len(result["group_values"]), len(satellites), 2)
    return {
        "parameters": parameters.copy(),
        "capture_jumps_hz": jumps.copy(),
        "success": False,
        "status": "nonconverged",
        "satellite_indices": satellites.copy(),
        "catalog_numbers": data.numbers[satellites],
        "satellite_support": np.ones(len(satellites)),
        "objective": float(objective),
        "selection_score": float(objective + penalty["total_penalty"]),
        "model_penalty": penalty,
    }


def test_cached_predictor_applies_nonzero_resets_after_expansion():
    _Plan.builds = []
    data = _data()
    jumps = np.array([[0.0, 0.0], [300.0, -400.0]])
    predictor = FixedResetPredictor(data, jumps, plan_factory=_Plan)
    parameters = np.zeros(8)
    first, _ = predictor(data, parameters, np.array([0]))
    second, _ = predictor(data, parameters, np.array([0]))
    pair, _ = predictor(data, parameters, np.array([0, 1]))
    np.testing.assert_array_equal(first[:, 0], [0.0, 0.0, -400.0, -400.0])
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(pair[2:], np.full((2, 2), -400.0))
    assert predictor.plan_build_count == 2
    assert _Plan.builds == [(0,), (0, 1)]


def test_profile_cavity_reproduces_full_objective_with_nonzero_resets():
    _Plan.builds = []
    data = _data()
    parameters = np.zeros(8)
    parameters[6:] = [0.25, -0.4]
    satellites = np.array([0, 1])
    jumps = np.array([[0.0, 0.0], [100.0, -250.0]])
    source = _source_trial(data, parameters, jumps, satellites)
    prepared = build_likelihood_arms(data, 2, 2)["finite_set"].prepared
    predictor = FixedResetPredictor(data, jumps, plan_factory=_Plan)
    profile = profile_timing_offsets(
        data,
        parameters,
        satellites,
        prepared,
        cavity_factory=prepare_replacement_scorer,
        detection_probability=0.4,
        sigma_hz=200.0,
        clutter_rate=2.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        step_s=3.0,
        budget_s=30.0,
        predictor=predictor,
    )
    assert profile["initial_objective"] == pytest.approx(source["objective"], abs=1e-10)
    assert profile["objective"] <= source["objective"] + 1e-10
    assert profile["complete"]


def test_branch_keeps_lower_incumbent_and_changed_state_convergence(monkeypatch):
    import finite_set_reset_profile as module

    monkeypatch.setattr(module, "SharedPredictionPlan", _Plan)
    data = _data()
    parameters = np.zeros(8)
    satellites = np.array([0, 1])
    jumps = np.array([[0.0, 0.0], [10.0, -20.0]])
    source = _source_trial(data, parameters, jumps, satellites)

    def profiler(*args, **kwargs):
        changed = parameters.copy()
        changed[6] = 0.5
        return {
            "parameters": changed,
            "initial_objective": source["objective"],
            "objective": source["objective"] - 2.0,
            "complete": True,
        }

    def refiner(*args, **kwargs):
        penalty = source["model_penalty"]
        changed = np.asarray(args[1]).copy()
        return {
            **copy.deepcopy(source),
            "parameters": changed,
            "success": False,
            "status": "nonconverged",
            "initial_objective": source["objective"] - 2.0,
            "objective": source["objective"] - 3.0,
            "selection_score": source["objective"] - 3.0 + penalty["total_penalty"],
        }

    fitted = fit_reset_profile_branches(
        data,
        {"full_bank": satellites, "trials": [source]},
        cavity_factory=None,
        profiler=profiler,
        refiner=refiner,
    )
    trial = fitted["trials"][0]
    assert trial["selected_branch"] == "profile_then_reset_gn"
    assert trial["selected_state_changed_from_source"]
    assert trial["convergence_provenance"] == "candidate_terminal_state"
    assert not trial["success"]


def test_incomplete_profile_is_not_retried_and_marks_selection_unresolved(monkeypatch):
    import finite_set_reset_profile as module

    monkeypatch.setattr(module, "SharedPredictionPlan", _Plan)
    data = _data()
    parameters = np.zeros(8)
    satellites = np.array([0, 1])
    jumps = np.array([[0.0, 0.0], [10.0, -20.0]])
    source = _source_trial(data, parameters, jumps, satellites)
    source["satellite_support"] = [0.0, 0.0]
    calls = []

    def profiler(*args, **kwargs):
        calls.append(kwargs)
        return {
            "parameters": parameters.copy(),
            "initial_objective": source["objective"],
            "objective": source["objective"],
            "complete": False,
        }

    def refiner(*args, **kwargs):
        np.testing.assert_array_equal(args[4], np.ones(2))
        return {
            **copy.deepcopy(source),
            "success": True,
            "status": "converged",
            "initial_objective": source["objective"],
        }

    fitted = fit_reset_profile_branches(
        data,
        {"full_bank": satellites, "trials": [source]},
        cavity_factory=None,
        profiler=profiler,
        refiner=refiner,
    )
    assert len(calls) == 1
    assert calls[0]["budget_s"] == 30.0
    assert calls[0]["step_s"] == 0.1
    assert (
        fitted["attempts"][0]["gn_support_policy"]
        == "uniform_ones_finite_set_adapter_ignores_optimizer_weights"
    )
    assert not fitted["all_timing_profiles_complete"]
    assert not fitted["selection"]["selection_resolved"]
    assert not fitted["selection"]["success"]


def test_equal_nonconverged_candidate_keeps_converged_unchanged_source(monkeypatch):
    import finite_set_reset_profile as module

    monkeypatch.setattr(module, "SharedPredictionPlan", _Plan)
    data = _data()
    parameters = np.zeros(8)
    satellites = np.array([0, 1])
    jumps = np.array([[0.0, 0.0], [10.0, -20.0]])
    source = _source_trial(data, parameters, jumps, satellites)
    source["success"] = True
    source["status"] = "converged"

    def profiler(*args, **kwargs):
        return {
            "parameters": parameters.copy(),
            "initial_objective": source["objective"],
            "objective": source["objective"],
            "complete": True,
        }

    def refiner(*args, **kwargs):
        return {
            **copy.deepcopy(source),
            "success": False,
            "status": "nonconverged",
            "initial_objective": source["objective"],
        }

    fitted = fit_reset_profile_branches(
        data,
        {"full_bank": satellites, "trials": [source]},
        cavity_factory=None,
        profiler=profiler,
        refiner=refiner,
    )
    trial = fitted["trials"][0]
    assert trial["selected_branch"] == "sealed_source"
    assert trial["convergence_provenance"] == "sealed_source_unchanged"
    assert trial["success"]
    assert not trial["selected_state_changed_from_source"]


def test_source_binding_rejects_input_and_full_geometry_changes(tmp_path):
    import finite_set_reset_profile as module

    input_path = tmp_path / "bundle.json"
    input_path.write_text("sealed")
    hashes = {str(input_path.resolve()): module.digest(input_path)}
    data = _data()
    data.geometry_receipt = {"full": {"capture_index": "abc", "orbit": "def"}}
    source = {
        "schema": "finite-set-capture-reset/v1",
        "run_id": "finite-set-capture-reset-v1",
        "unit": {"unit_id": "DS10-D01", "session_ids": ["first", "second"]},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed": True,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "source_hashes": hashes,
        "bound_input_hashes": hashes,
        "geometry_receipt": data.geometry_receipt,
        "fit": {"capture_count": 2},
    }
    validate_source_binding(source, "DS10-D01", data, [input_path])

    changed = copy.deepcopy(source)
    changed["geometry_receipt"] = {"full": {"capture_index": "wrong"}}
    with pytest.raises(ValueError, match="geometry differs"):
        validate_source_binding(changed, "DS10-D01", data, [input_path])

    input_path.write_text("changed")
    with pytest.raises(RuntimeError, match="provenance changed"):
        validate_source_binding(source, "DS10-D01", data, [input_path])
