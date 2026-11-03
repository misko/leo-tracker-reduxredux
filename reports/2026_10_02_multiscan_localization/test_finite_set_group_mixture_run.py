from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import finite_set_group_mixture_run as runner
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
    )


def source_trial(data, satellites, objective, success=False):
    satellites = np.asarray(satellites, dtype=int)
    penalty = 0.5 * len(satellites) * np.log(len(data.group))
    return {
        "satellite_indices": satellites,
        "satellite_count": len(satellites),
        "parameters": np.zeros(6 + len(data.numbers)),
        "satellite_weights": np.full(len(satellites), 1 / len(satellites)),
        "objective": float(objective),
        "entry_penalty": float(penalty),
        "selection_score": float(objective + penalty),
        "groups": len(data.group),
        "success": success,
        "status": "converged" if success else "nonconverged",
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


def test_every_bank_uses_separate_source_and_mixture_objectives(monkeypatch):
    data = synthetic_data()
    sources = [
        source_trial(data, [0], 100.0),
        source_trial(data, [0, 1], 90.0, True),
        source_trial(data, [0, 1, 2, 3], 80.0),
    ]
    source_fit = {"full_bank": [0, 1, 2, 3], "trials": sources}
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )
    evaluations = {}

    def fake_evaluate(data, trial, likelihood, **kwargs):
        del data, kwargs
        bank = tuple(trial["satellite_indices"])
        if isinstance(likelihood, Ordinary):
            return {"objective": trial["objective"], "groups": 4}
        value = trial["objective"] + 25.0 + len(bank)
        evaluations[bank] = value
        return {"objective": value, "groups": 4}

    monkeypatch.setattr(runner, "evaluate_frozen_objective", fake_evaluate)
    calls = []

    def fake_refiner(data, parameters, satellites, support, likelihood, **kwargs):
        del data, parameters, support
        bank = tuple(satellites)
        calls.append((bank, likelihood.configuration, kwargs))
        penalty = next(
            source["entry_penalty"]
            for source in sources
            if tuple(source["satellite_indices"]) == bank
        )
        return {
            "satellite_indices": np.asarray(satellites),
            "initial_objective": evaluations[bank],
            "objective": evaluations[bank] - 2.0,
            "entry_penalty": penalty,
            "selection_score": evaluations[bank] - 2.0 + penalty,
            "success": bank != (0, 1, 2, 3),
            "status": "converged" if bank != (0, 1, 2, 3) else "nonconverged",
        }

    result = runner.fit_group_mixture_branches(
        data,
        source_fit,
        refiner=fake_refiner,
        adapter_factory=Mixture,
    )

    assert len(result["trials"]) == len(sources)
    assert all(
        attempt["ordinary_200hz_source_objective_delta"] == 0
        for attempt in result["attempts"]
    )
    assert all(attempt["timing_profile_performed"] is False for attempt in result["attempts"])
    assert all(call[2]["budget_s"] == 15.0 for call in calls)
    assert all(call[2]["tau_sigma_s"] == 1.0 for call in calls)
    assert all(call[2]["tau_bound_s"] == 3.0 for call in calls)
    assert all(call[2]["slope_bound"] == 50.0 for call in calls)
    assert calls[0][1] == {
        "clutter_rate": 2.0,
        "narrow_sigma_hz": 100.0,
        "broad_sigma_hz": 400.0,
        "narrow_weight": 0.8,
    }
    assert result["new_parameter_count"] == 0
    assert result["selection"]["selection_resolved"] is False


def test_penalty_must_remain_the_source_bank_penalty(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = source_trial(data, [0], 20.0)
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )
    monkeypatch.setattr(
        runner,
        "evaluate_frozen_objective",
        lambda data, trial, likelihood, **kwargs: {
            "objective": trial["objective"] if isinstance(likelihood, Ordinary) else 30.0,
            "groups": 4,
        },
    )

    def wrong_penalty(*args, **kwargs):
        return {
            "satellite_indices": np.array([0]),
            "initial_objective": 30.0,
            "objective": 29.0,
            "entry_penalty": source["entry_penalty"] + 1,
            "selection_score": 31.0,
            "success": True,
            "status": "converged",
        }

    with pytest.raises(ValueError, match="penalty"):
        runner.fit_group_mixture_branches(
            data,
            {"full_bank": [0], "trials": [source]},
            refiner=wrong_penalty,
            adapter_factory=Mixture,
        )


def test_incomplete_mixture_seed_reproduction_is_rejected(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = source_trial(data, [0], 20.0)
    monkeypatch.setattr(
        runner,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": Ordinary()},
    )
    monkeypatch.setattr(
        runner,
        "evaluate_frozen_objective",
        lambda data, trial, likelihood, **kwargs: {
            "objective": trial["objective"] if isinstance(likelihood, Ordinary) else 30.0,
            "groups": 4,
        },
    )

    def incomplete(*args, **kwargs):
        return {
            "satellite_indices": np.array([0]),
            "initial_objective": 30.5,
            "objective": 29.0,
            "entry_penalty": source["entry_penalty"],
            "selection_score": 29.0 + source["entry_penalty"],
            "success": False,
            "status": "nonconverged",
        }

    with pytest.raises(ValueError, match="seed does not reproduce"):
        runner.fit_group_mixture_branches(
            data,
            {"full_bank": [0], "trials": [source]},
            refiner=incomplete,
            adapter_factory=Mixture,
        )


def test_source_dependencies_include_adapter_and_validators_before_validation(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "fit.json"
    inherited = tmp_path / "input.json"
    source_path.write_text("{}")
    inherited.write_text("input")
    source = {"source_hashes": {str(inherited.resolve()): "a" * 64}}
    paths = runner.source_dependency_paths(source, source_path)
    names = {Path(path).name for path in paths}
    assert {
        "finite_set_group_mixture.py",
        "finite_set_rf_cohort.py",
        "finite_set_tau_continue.py",
        "finite_set_fit.py",
        "gauss_newton.py",
    } <= names
    order = []

    def fake_snapshot(received):
        order.append("snapshot")
        assert set(received) == set(paths)
        return {path: "b" * 64 for path in received}

    receipt = runner.snapshot_before_source_validation(
        source, source_path, snapshotter=fake_snapshot
    )
    order.append("validator_would_run_next")
    assert order == ["snapshot", "validator_would_run_next"]
    assert set(receipt) == set(paths)


def test_missing_or_malformed_source_hashes_refuse_before_fit(tmp_path):
    source_path = tmp_path / "fit.json"
    source_path.write_text("{}")
    with pytest.raises(ValueError, match="inherited hashes"):
        runner.snapshot_before_source_validation({}, source_path)
    with pytest.raises(ValueError, match="inherited hashes"):
        runner.snapshot_before_source_validation({"source_hashes": []}, source_path)


def test_initial_scope_is_two_pilots_with_explicit_all32_escape_hatch():
    assert runner.INITIAL_UNITS == ("DS10-S01", "DS11-S02")
    assert len(runner.ALL_UNITS) == 32
    assert "DS10-S16" in runner.ALL_UNITS
    assert "DS11-S16" in runner.ALL_UNITS
