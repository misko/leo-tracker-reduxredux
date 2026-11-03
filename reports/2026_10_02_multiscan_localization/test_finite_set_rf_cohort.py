from __future__ import annotations

import copy
from types import SimpleNamespace

import finite_set_rf_cohort as model
import numpy as np
import pytest


def synthetic_data(candidate_count=4):
    return SimpleNamespace(
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.arange(4),
        receiver=np.array([0, 0, 1, 1]),
        rf=np.array([10e9, 12e9, 10.5e9, 11.5e9]),
        numbers=np.arange(candidate_count),
    )


def source_trial(data, satellites, objective, success):
    satellites = np.asarray(satellites, dtype=int)
    groups = len(data.group)
    entry = 0.5 * len(satellites) * np.log(groups)
    return {
        "satellite_indices": satellites,
        "satellite_count": len(satellites),
        "parameters": np.zeros(6 + len(data.numbers)),
        "objective": objective,
        "entry_penalty": entry,
        "selection_score": objective + entry,
        "groups": groups,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "convergence_reason": "source_reason",
    }


def test_zero_rf_expansion_preserves_state_and_adds_two_parameter_penalty_once():
    data = synthetic_data()
    source = source_trial(data, [0, 2], 100.0, False)
    original = copy.deepcopy(source)
    expanded, receipt = model.derive_zero_rf_trial(source)
    np.testing.assert_array_equal(expanded["parameters"], source["parameters"])
    np.testing.assert_array_equal(expanded["coefficients_hz_ghz"], np.zeros(2))
    assert expanded["objective"] == source["objective"]
    assert expanded["coefficient_prior"] == 0
    assert expanded["rf_dof_penalty"] == pytest.approx(np.log(4))
    assert expanded["total_entry_penalty"] == pytest.approx(2.0 * np.log(4))
    assert receipt["source_convergence_not_inherited"] is True
    assert model.serializable(source) == model.serializable(original)


def test_variable_bank_count_and_unresolved_source_are_accepted(monkeypatch):
    data = synthetic_data()
    source_trials = [
        source_trial(data, [0], 100.0, False),
        source_trial(data, [0, 1], 90.0, True),
        source_trial(data, [0, 1, 2], 80.0, False),
        source_trial(data, [0, 1, 2, 3], 70.0, True),
    ]
    source_fit = {"full_bank": [0, 1, 2, 3], "trials": source_trials}
    budgets = []
    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": object()},
    )

    def fake_refiner(data, source, likelihood, design, *, budget_s):
        del data, likelihood, design
        budgets.append(budget_s)
        result = copy.deepcopy(source)
        result.update(
            {
                "initial_objective": source["objective"],
                "objective": source["objective"] - 1.0,
                "selection_score": source["objective"]
                - 1.0
                + source["total_entry_penalty"],
                "success": source["satellite_count"] != 3,
                "status": "converged" if source["satellite_count"] != 3 else "nonconverged",
            }
        )
        return result

    result = model.fit_rf_cohort_branches(data, source_fit, refiner=fake_refiner)
    assert len(result["trials"]) == 4
    assert budgets == [15.0] * 4
    assert result["attempts"][0]["source_success"] is False
    assert result["trials"][0]["source_convergence_not_inherited"] is True
    assert result["selection"]["selection_resolved"] is False


def test_nonconverged_retained_zero_rf_state_stays_nonconverged(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = source_trial(data, [0], 25.0, True)
    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": object()},
    )

    def fake_refiner(data, expanded, likelihood, design, *, budget_s):
        del data, likelihood, design, budget_s
        result = copy.deepcopy(expanded)
        result.update(
            {
                "initial_objective": expanded["objective"],
                "objective": expanded["objective"],
                "selection_score": expanded["selection_score"],
                "success": False,
                "status": "nonconverged",
                "convergence_reason": "budget_exhausted",
            }
        )
        return result

    result = model.fit_rf_cohort_branches(
        data,
        {"full_bank": [0], "trials": [source]},
        refiner=fake_refiner,
    )
    trial = result["trials"][0]
    assert trial["objective"] == source["objective"]
    assert trial["source_timing_profile_success"] is True
    assert trial["success"] is False
    assert result["selection"]["selection_resolved"] is False


def source_record(unit_id="DS10-S01", bank_count=4, source_success=False):
    data = synthetic_data(candidate_count=bank_count)
    trials = []
    attempts = []
    for count in range(1, bank_count + 1):
        trial = source_trial(data, list(range(count)), 100.0 - count, source_success)
        trial["satellite_indices"] = list(range(count))
        trial["parameters"] = trial["parameters"].tolist()
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": list(range(count)),
                "profile": {"complete": True},
            }
        )
    return {
        "schema": model.SOURCE_SCHEMA,
        "run_id": model.SOURCE_RUN,
        "unit": {"unit_id": unit_id, "size": 1, "session_ids": ["scan"]},
        "dataset": unit_id[:4],
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed_utc": "now",
        "source_fit_sha256": "a" * 64,
        "source_hashes": {"/input": "b" * 64},
        "fit": {
            "full_bank": list(range(bank_count)),
            "trials": trials,
            "attempts": attempts,
            "all_timing_profiles_complete": True,
            "local_refinements_resolved": source_success,
            "selection": {"selection_resolved": source_success},
        },
    }


def test_source_validation_accepts_unresolved_four_bank_ladder():
    source = source_record(bank_count=4, source_success=False)
    assert model.validate_source_record(source, "DS10-S01") is source
    source["fit"]["attempts"][2]["profile"]["complete"] = False
    with pytest.raises(ValueError, match="source bank or timing-profile attempt is invalid"):
        model.validate_source_record(source, "DS10-S01")


def test_source_validation_rejects_truth_or_hash_mismatch():
    source = source_record()
    source["reference_read_before_seal"] = True
    with pytest.raises(ValueError, match="truth-free"):
        model.validate_source_record(source, "DS10-S01")
    source = source_record()
    source["source_hashes"]["/input"] = "short"
    with pytest.raises(ValueError, match="hashes are malformed"):
        model.validate_source_record(source, "DS10-S01")


def test_supported_scope_is_exactly_all_32_singles():
    assert len(model.SUPPORTED_UNITS) == 32
    assert model.SUPPORTED_UNITS[:2] == ("DS10-S01", "DS10-S02")
    assert model.SUPPORTED_UNITS[-2:] == ("DS11-S15", "DS11-S16")
    assert all("-S" in unit for unit in model.SUPPORTED_UNITS)
