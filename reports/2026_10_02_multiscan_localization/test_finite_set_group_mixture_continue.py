from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import finite_set_group_mixture_continue as runner
import numpy as np
import pytest


def synthetic_data(candidate_count=4):
    return SimpleNamespace(
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.arange(4),
        receiver=np.array([0, 0, 1, 1]),
        rf=np.full(4, 11e9),
        numbers=np.arange(candidate_count),
        geometry_receipt={"full": {"orbit": "sealed", "rows": [0, 1, 2, 3]}},
    )


def source_trial(data, satellites, objective, success=False):
    satellites = np.asarray(satellites, dtype=int)
    penalty = 0.5 * len(satellites) * np.log(len(data.group))
    return {
        "satellite_indices": satellites,
        "parameters": np.zeros(6 + len(data.numbers)),
        "satellite_weights": np.full(len(satellites), 1 / len(satellites)),
        "objective": float(objective),
        "entry_penalty": float(penalty),
        "selection_score": float(objective + penalty),
        "success": success,
        "status": "converged" if success else "nonconverged",
    }


def source_fit(data, trials):
    return {
        "full_bank": list(trials[-1]["satellite_indices"]),
        "trials": trials,
        "attempts": [
            {
                "satellite_indices": list(trial["satellite_indices"]),
                "timing_profile_performed": False,
            }
            for trial in trials
        ],
        "source_trial_count": len(trials),
        "source_bank_order_preserved": True,
        "source_sigma_hz": 200.0,
        "narrow_sigma_hz": 100.0,
        "broad_sigma_hz": 400.0,
        "narrow_weight": 0.8,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "new_parameter_count": 0,
    }


class Ordinary:
    prepared = object()
    detection_probability = 0.2
    clutter_rate = 2.0


class Mixture:
    def __init__(self, prepared, detection_probability, **kwargs):
        self.prepared = prepared
        self.detection_probability = detection_probability
        self.configuration = kwargs


def test_every_bank_gets_one_unchanged_twenty_second_continuation(monkeypatch):
    data = synthetic_data()
    sources = [
        source_trial(data, [0], 30.0, True),
        source_trial(data, [0, 1], 20.0),
        source_trial(data, [0, 1, 2, 3], 10.0),
    ]
    fit = source_fit(data, sources)
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )
    calls = []

    def refiner(data, parameters, satellites, support, likelihood, **kwargs):
        del data, support
        index = len(calls)
        source = sources[index]
        changed = parameters.copy()
        if index == 1:
            changed[0] = 0.25
        objective = source["objective"] - (1.0 if index == 1 else 0.0)
        success = index == 2
        calls.append((tuple(satellites), likelihood.configuration, kwargs))
        return {
            "parameters": changed,
            "satellite_indices": np.asarray(satellites),
            "initial_objective": source["objective"],
            "objective": objective,
            "entry_penalty": source["entry_penalty"],
            "selection_score": objective + source["entry_penalty"],
            "success": success,
            "status": "converged" if success else "nonconverged",
        }

    result = runner.continue_group_mixture_branches(
        data,
        fit,
        refiner=refiner,
        adapter_factory=Mixture,
    )

    assert len(calls) == len(sources)
    assert all(call[2]["budget_s"] == 20.0 for call in calls)
    assert all(call[2]["tau_sigma_s"] == 1.0 for call in calls)
    assert all(call[2]["tau_bound_s"] == 3.0 for call in calls)
    assert all(call[2]["slope_bound"] == 50.0 for call in calls)
    assert all(call[2]["sigma_hz"] == 200.0 for call in calls)
    assert calls[0][1] == {
        "clutter_rate": 2.0,
        "narrow_sigma_hz": 100.0,
        "broad_sigma_hz": 400.0,
        "narrow_weight": 0.8,
    }
    assert result["trials"][0]["selected_branch"] == "sealed_source"
    assert result["trials"][1]["selected_branch"] == "continued_gn"
    assert result["trials"][1]["selected_state_changed_from_source"]
    assert not result["trials"][1]["success"]
    assert result["trials"][2]["selected_branch"] == "continued_gn"
    assert not result["trials"][2]["selected_state_changed_from_source"]
    assert result["trials"][2]["success"]
    assert all(not item["timing_profile_performed"] for item in result["attempts"])


def test_source_incumbent_and_penalty_cannot_be_lost(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = source_trial(data, [0], 20.0, True)
    fit = source_fit(data, [source])
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )

    def result(objective=20.0, penalty=source["entry_penalty"]):
        return {
            **copy.deepcopy(source),
            "initial_objective": 20.0,
            "objective": objective,
            "entry_penalty": penalty,
        }

    with pytest.raises(ValueError, match="lost its sealed source incumbent"):
        runner.continue_group_mixture_branches(
            data,
            fit,
            refiner=lambda *args, **kwargs: result(objective=21.0),
            adapter_factory=Mixture,
        )
    with pytest.raises(ValueError, match="penalty"):
        runner.continue_group_mixture_branches(
            data,
            fit,
            refiner=lambda *args, **kwargs: result(
                penalty=source["entry_penalty"] + 1
            ),
            adapter_factory=Mixture,
        )


def test_incomplete_seed_reproduction_is_rejected(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = source_trial(data, [0], 20.0)
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )
    candidate = {
        **copy.deepcopy(source),
        "initial_objective": 20.5,
    }
    with pytest.raises(ValueError, match="does not reproduce"):
        runner.continue_group_mixture_branches(
            data,
            source_fit(data, [source]),
            refiner=lambda *args, **kwargs: candidate,
            adapter_factory=Mixture,
        )


def valid_source(tmp_path, data):
    adapter = runner.ROOT / "finite_set_group_mixture.py"
    upstream = (
        runner.ROOT
        / "runs"
        / "finite-set-tau-profile-v1"
        / "DS10-S01"
        / "fit.json"
    )
    inherited = tmp_path / "input.json"
    inherited.write_text("input")
    hashes = {
        str(adapter.resolve()): runner.FROZEN_ADAPTER_SHA256,
        str(upstream.resolve()): "a" * 64,
        str(inherited.resolve()): "b" * 64,
    }
    trials = [source_trial(data, [0], 20.0)]
    trials[0]["satellite_indices"] = [0]
    trials[0]["satellite_weights"] = [1.0]
    trials[0]["parameters"] = trials[0]["parameters"].tolist()
    trials[0]["algorithm_version"] = "complete-data-fisher-gn/v2"
    fit = source_fit(data, trials)
    return {
        "schema": runner.SOURCE_SCHEMA,
        "run_id": runner.SOURCE_RUN,
        "source_run_id": "finite-set-tau-profile-v1",
        "unit": {"unit_id": "DS10-S01", "size": 1, "session_ids": ["scan"]},
        "dataset": "DS10",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed": True,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "source_hashes": hashes,
        "source_fit_sha256": "a" * 64,
        "bound_input_hashes": {str(inherited.resolve()): "b" * 64},
        "geometry_receipt": data.geometry_receipt,
        "fit": fit,
    }


def test_strict_source_validation_binds_adapter_and_complete_ladder(tmp_path):
    data = synthetic_data(candidate_count=1)
    source = valid_source(tmp_path, data)
    assert runner.validate_source_record(source, "DS10-S01") is source

    changed = copy.deepcopy(source)
    adapter = str((runner.ROOT / "finite_set_group_mixture.py").resolve())
    changed["source_hashes"][adapter] = "0" * 64
    with pytest.raises(ValueError, match="frozen group-mixture adapter"):
        runner.validate_source_record(changed, "DS10-S01")

    changed = copy.deepcopy(source)
    changed["fit"]["narrow_weight"] = 0.7
    with pytest.raises(ValueError, match="narrow_weight"):
        runner.validate_source_record(changed, "DS10-S01")

    changed = copy.deepcopy(source)
    changed["fit"]["attempts"] = []
    with pytest.raises(ValueError, match="ladder is incomplete"):
        runner.validate_source_record(changed, "DS10-S01")


def test_reconstructed_inputs_and_full_geometry_must_match(tmp_path):
    data = synthetic_data(candidate_count=1)
    source = valid_source(tmp_path, data)
    expected = source["bound_input_hashes"]
    validated, geometry = runner.validate_reconstructed_source(
        source,
        data,
        ["loader-input"],
        expected_factory=lambda value: expected,
        input_validator=lambda paths, hashes: hashes,
    )
    assert validated == expected
    assert geometry == data.geometry_receipt

    changed = copy.deepcopy(source)
    changed["bound_input_hashes"] = {"wrong": "c" * 64}
    with pytest.raises(ValueError, match="bound inputs differ"):
        runner.validate_reconstructed_source(
            changed,
            data,
            [],
            expected_factory=lambda value: expected,
            input_validator=lambda paths, hashes: hashes,
        )

    data.geometry_receipt = {"full": {"orbit": "changed"}}
    with pytest.raises(ValueError, match="full geometry differs"):
        runner.validate_reconstructed_source(
            source,
            data,
            [],
            expected_factory=lambda value: expected,
            input_validator=lambda paths, hashes: hashes,
        )


def test_dependencies_are_snapshotted_before_validation(tmp_path):
    data = synthetic_data(candidate_count=1)
    source = valid_source(tmp_path, data)
    source_path = tmp_path / "fit.json"
    source_path.write_text("{}")
    paths = runner.source_dependency_paths(source, source_path)
    names = {Path(path).name for path in paths}
    assert {
        "finite_set_group_mixture_continue.py",
        "finite_set_group_mixture.py",
        "finite_set_tau_continue.py",
        "gauss_newton.py",
    } <= names
    order = []

    def snapshotter(received):
        order.append("snapshot")
        assert set(received) == set(paths)
        return {path: "d" * 64 for path in received}

    receipt = runner.snapshot_before_source_validation(
        source, source_path, snapshotter=snapshotter
    )
    order.append("validator_would_run_next")
    assert order == ["snapshot", "validator_would_run_next"]
    assert set(receipt) == set(paths)


def test_scope_is_only_the_two_completed_pilots():
    assert runner.SUPPORTED_UNITS == ("DS10-S01", "DS11-S02")
    assert runner.RUN_ID == "finite-set-group-mixture-continue-v1"
