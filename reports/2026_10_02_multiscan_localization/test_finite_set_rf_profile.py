from __future__ import annotations

import copy
from types import SimpleNamespace

import finite_set_rf_profile as model
import numpy as np
import pytest


class ConstantPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)

    def predict(self, parameters):
        del parameters
        shape = (len(self.data.times), len(self.satellites))
        return np.zeros(shape).ravel(), np.ones(shape, dtype=bool).ravel(), None


def synthetic_data(candidate_count=2):
    return SimpleNamespace(
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.arange(4),
        receiver=np.array([0, 0, 1, 1]),
        rf=np.array([10e9, 12e9, 10.5e9, 11.5e9]),
        numbers=np.arange(candidate_count),
    )


def source_trial(data, objective=10.625, success=True):
    parameters = np.zeros(6 + len(data.numbers))
    satellites = np.arange(len(data.numbers))
    groups = len(data.group)
    source_penalty = 0.5 * len(satellites) * np.log(groups)
    rf_penalty = np.log(groups)
    return {
        "satellite_indices": satellites,
        "parameters": parameters,
        "coefficients_hz_ghz": np.array([125.0, -250.0]),
        "coefficient_prior": 0.625,
        "objective": objective,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "selection_score": objective + source_penalty + rf_penalty,
        "source_entry_penalty": source_penalty,
        "rf_dof_penalty": rf_penalty,
        "total_entry_penalty": source_penalty + rf_penalty,
        "satellite_count": len(satellites),
    }


def source_fit(data, trial):
    _, centers, spans = model.receiver_rf_design(data)
    return {
        "full_bank": trial["satellite_indices"].copy(),
        "rf_centers_hz": centers,
        "rf_spans": spans,
        "trials": [trial],
    }


def test_fixed_rf_predictor_adds_after_expansion_and_caches_by_bank():
    data = synthetic_data()
    design, _, _ = model.receiver_rf_design(data)
    coefficients = np.array([100.0, -200.0])
    predictor = model.FixedRFPredictor(
        data,
        coefficients,
        design,
        plan_factory=ConstantPlan,
    )
    predicted, visible = predictor(data, np.zeros(8), np.array([0, 1]))
    expected = np.repeat((design @ coefficients)[:, None], 2, axis=1)
    np.testing.assert_allclose(predicted, expected)
    assert np.all(visible)
    predictor(data, np.ones(8), np.array([0, 1]))
    predictor(data, np.ones(8), np.array([1]))
    assert predictor.plan_build_count == 2


def test_constant_prior_profile_and_derived_gn_objectives_are_consistent(monkeypatch):
    data = synthetic_data()
    source = source_trial(data)
    original = copy.deepcopy(source)
    seen = {}

    def fake_build_likelihood(data, selected_count, full_bank_count):
        del data, selected_count, full_bank_count
        return {"finite_set": SimpleNamespace(prepared=object())}

    def fake_profiler(data, parameters, satellites, prepared, **options):
        del data, satellites, prepared
        np.testing.assert_array_equal(
            options["predictor"].coefficients_hz_ghz,
            source["coefficients_hz_ghz"],
        )
        return {
            "parameters": np.asarray(parameters).copy(),
            "initial_objective": 10.0,
            "objective": 9.5,
            "complete": True,
            "status": "complete_pass",
            "profiles": [],
        }

    def fake_refiner(data, seed, likelihood, design, **options):
        del data, likelihood, design, options
        seen["seed"] = copy.deepcopy(seed)
        result = copy.deepcopy(seed)
        result.update(
            {
                "initial_objective": seed["objective"],
                "objective": 9.75,
                "selection_score": 9.75 + seed["total_entry_penalty"],
                "success": True,
                "status": "converged",
            }
        )
        return result

    monkeypatch.setattr(model, "build_likelihood_arms", fake_build_likelihood)
    result = model.fit_rf_profile_branches(
        data,
        source_fit(data, source),
        cavity_factory=object(),
        profiler=fake_profiler,
        refiner=fake_refiner,
    )
    assert seen["seed"]["objective"] == pytest.approx(10.125)
    np.testing.assert_array_equal(
        seen["seed"]["coefficients_hz_ghz"], source["coefficients_hz_ghz"]
    )
    assert result["attempts"][0]["constant_rf_prior"] == pytest.approx(0.625)
    assert result["attempts"][0]["profile_full_objective"] == pytest.approx(10.125)
    assert result["trials"][0]["objective"] == pytest.approx(9.75)
    assert result["trials"][0]["selected_branch"] == "profile_then_rf_gn"
    assert model.serializable(source) == model.serializable(original)


def test_equal_candidate_does_not_replace_source_or_inherit_changed_convergence(monkeypatch):
    data = synthetic_data()
    source = source_trial(data, success=True)

    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": SimpleNamespace(prepared=object())},
    )

    def fake_profiler(data, parameters, satellites, prepared, **options):
        del data, satellites, prepared, options
        changed = np.asarray(parameters).copy()
        changed[6] = 0.1
        return {
            "parameters": changed,
            "initial_objective": 10.0,
            "objective": 10.0,
            "complete": True,
        }

    def fake_refiner(data, seed, likelihood, design, **options):
        del data, likelihood, design, options
        result = copy.deepcopy(seed)
        result.update(
            {
                "initial_objective": seed["objective"],
                "objective": 10.625,
                "selection_score": 10.625 + seed["total_entry_penalty"],
                "success": False,
                "status": "nonconverged",
            }
        )
        return result

    result = model.fit_rf_profile_branches(
        data,
        source_fit(data, source),
        cavity_factory=object(),
        profiler=fake_profiler,
        refiner=fake_refiner,
    )
    selected = result["trials"][0]
    assert selected["selected_branch"] == "sealed_source"
    assert selected["success"] is True
    np.testing.assert_array_equal(selected["parameters"], source["parameters"])


def test_incomplete_profile_and_changed_nonconvergence_remain_explicit(monkeypatch):
    data = synthetic_data()
    source = source_trial(data, success=True)
    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": SimpleNamespace(prepared=object())},
    )

    def fake_profiler(data, parameters, satellites, prepared, **options):
        del data, satellites, prepared, options
        return {
            "parameters": np.asarray(parameters).copy(),
            "initial_objective": 10.0,
            "objective": 9.5,
            "complete": False,
            "status": "budget_exhausted",
        }

    def fake_refiner(data, seed, likelihood, design, **options):
        del data, likelihood, design, options
        result = copy.deepcopy(seed)
        result.update(
            {
                "initial_objective": seed["objective"],
                "objective": 9.9,
                "selection_score": 9.9 + seed["total_entry_penalty"],
                "success": False,
                "status": "nonconverged",
            }
        )
        return result

    result = model.fit_rf_profile_branches(
        data,
        source_fit(data, source),
        cavity_factory=object(),
        profiler=fake_profiler,
        refiner=fake_refiner,
    )
    assert result["trials"][0]["success"] is False
    assert result["trials"][0]["convergence_provenance"] == "derived_profile_gn_terminal"
    assert result["all_timing_profiles_complete"] is False
    assert result["selection"]["selection_resolved"] is False


def test_source_binding_rejects_unresolved_or_changed_provenance(monkeypatch):
    data = synthetic_data(candidate_count=5)
    data.geometry_receipt = {"geometry": "frozen"}
    trial = source_trial(data, success=False)
    trial.update(
        {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "rx_slope_bound_hz_s": 50.0,
            "coefficient_prior_sigma_hz_ghz": 250.0,
            "coefficient_bound_hz_ghz": 1000.0,
        }
    )
    trials = []
    for count in range(1, 6):
        branch = copy.deepcopy(trial)
        branch["satellite_indices"] = np.arange(count)
        branch["satellite_count"] = count
        trials.append(branch)
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
            "full_bank": list(range(5)),
            "trials": trials,
        },
    }
    monkeypatch.setattr(model, "assert_snapshot_unchanged", lambda hashes: None)
    with pytest.raises(ValueError, match="model or convergence"):
        model.validate_source_binding(source, "DS10-S01", data, [])
