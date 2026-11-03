from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import finite_set_identity_refine as refine
import numpy as np
import pytest


def data_and_source():
    data = SimpleNamespace(times=np.array([0.0, 1.0]), numbers=np.arange(5))
    source = {
        "satellite_indices": np.array([0, 1]),
        "parameters": np.zeros(11),
        "satellite_weights": np.array([0.5, 0.5]),
        "objective": 100.0,
        "entry_penalty": np.log(2.0),
        "selection_score": 100.0 + np.log(2.0),
        "success": True,
        "status": "converged",
    }
    return data, source


def screen_diagnostic(swaps):
    return {
        "complete": True,
        "status": "complete",
        "evaluated_pair_count": 6,
        "total_pair_count": 6,
        "selected_count": 2,
        "source_full_bank_count": 4,
        "source_objective": 100.0,
        "source_entry_penalty": np.log(2.0),
        "top3_full_dp": swaps,
    }


def swap(removed, added, objective, improvement):
    return {
        "removed_index": removed,
        "added_index": added,
        "objective": objective,
        "objective_improvement": improvement,
        "cavity_full_dp_objective_error": 0.0,
    }


class Evaluator:
    detection_probability = 0.2


def test_refines_only_positive_top3_and_keeps_source_incumbent(monkeypatch):
    data, source = data_and_source()
    diagnostic = screen_diagnostic(
        [
            swap(0, 2, 90.0, 10.0),
            swap(1, 3, 95.0, 5.0),
            swap(0, 4, 101.0, -1.0),
        ]
    )
    monkeypatch.setattr(
        refine,
        "_objective",
        lambda data, parameters, satellites, weights, evaluator, plan_factory: (
            100.0 if tuple(satellites) == (0, 1) else 90.0 if tuple(satellites) == (2, 1) else 95.0
        ),
    )
    calls = []

    def refiner(data, parameters, satellites, weights, evaluator, **kwargs):
        del data, weights, evaluator
        initial = 90.0 if tuple(satellites) == (2, 1) else 95.0
        calls.append((parameters.copy(), satellites.copy(), kwargs))
        return {
            "parameters": parameters.copy(),
            "satellite_indices": satellites.copy(),
            "initial_objective": initial,
            "objective": initial - 2.0,
            "entry_penalty": source["entry_penalty"],
            "selection_score": initial - 2.0 + source["entry_penalty"],
            "success": True,
            "status": "converged",
        }

    result = refine.refine_identity_replacements(
        data,
        source,
        [0, 1, 2, 3],
        diagnostic,
        refiner=refiner,
        arms_factory=lambda *args: {"finite_set": Evaluator()},
    )

    assert len(calls) == 2
    assert result["candidate_fit_count"] == 2
    assert len(result["trials"]) == 3
    assert result["trials"][0]["branch"] == "sealed_source_incumbent"
    assert result["selection"]["score_leader"]["objective"] == 88.0
    assert all(call[2]["budget_s"] == 15.0 for call in calls)
    assert all(call[2]["tau_sigma_s"] == 1.0 for call in calls)
    assert all(call[2]["tau_bound_s"] == 3.0 for call in calls)
    assert all(call[2]["slope_bound"] == 50.0 for call in calls)
    assert calls[0][0][8] == 0.0
    assert calls[1][0][9] == 0.0
    assert result["full_bank_global_convergence_claimed"] is False


def test_no_positive_replacement_records_unchanged_source_without_fit():
    data, source = data_and_source()

    def forbidden(*args, **kwargs):
        raise AssertionError("no evaluator or refiner should be constructed")

    result = refine.refine_identity_replacements(
        data,
        source,
        [0, 1, 2, 3],
        screen_diagnostic([swap(0, 2, 101.0, -1.0)]),
        refiner=forbidden,
        arms_factory=forbidden,
    )
    assert result["candidate_fit_count"] == 0
    assert result["source_unchanged_without_fit"]
    assert result["selection"]["score_leader"]["branch"] == "sealed_source_incumbent"


def test_initial_objective_and_penalty_must_match(monkeypatch):
    data, source = data_and_source()
    diagnostic = screen_diagnostic([swap(0, 2, 90.0, 10.0)])
    monkeypatch.setattr(refine, "_objective", lambda *args: 100.0)
    with pytest.raises(ValueError, match="does not reproduce sealed screen"):
        refine.refine_identity_replacements(
            data,
            source,
            [0, 1, 2, 3],
            diagnostic,
            arms_factory=lambda *args: {"finite_set": Evaluator()},
        )

    values = iter([100.0, 90.0])
    monkeypatch.setattr(refine, "_objective", lambda *args: next(values))

    def wrong_penalty(*args, **kwargs):
        return {
            "satellite_indices": np.array([2, 1]),
            "initial_objective": 90.0,
            "objective": 89.0,
            "entry_penalty": source["entry_penalty"] + 1.0,
            "selection_score": 90.0,
            "success": True,
            "status": "converged",
        }

    with pytest.raises(ValueError, match="entry penalty"):
        refine.refine_identity_replacements(
            data,
            source,
            [0, 1, 2, 3],
            diagnostic,
            refiner=wrong_penalty,
            arms_factory=lambda *args: {"finite_set": Evaluator()},
        )


def test_no_substitution_for_negative_or_lower_ranked_swaps():
    diagnostic = screen_diagnostic(
        [swap(0, 2, 90.0, 10.0), swap(1, 3, 101.0, -1.0)]
    )
    diagnostic["top10"] = [*diagnostic["top3_full_dp"], swap(1, 4, 91.0, 9.0)]
    assert refine._positive_prescribed_swaps(diagnostic) == [
        diagnostic["top3_full_dp"][0]
    ]


def test_incomplete_or_corrupt_screen_is_rejected():
    diagnostic = screen_diagnostic([swap(0, 2, 90.0, 10.0)])
    diagnostic["complete"] = False
    with pytest.raises(ValueError, match="must be complete"):
        refine._positive_prescribed_swaps(diagnostic)
    diagnostic = screen_diagnostic([swap(0, 2, 90.0, 10.0)])
    diagnostic["top3_full_dp"][0]["cavity_full_dp_objective_error"] = 1e-3
    with pytest.raises(ValueError, match="malformed"):
        refine._positive_prescribed_swaps(diagnostic)


def test_dependency_closure_requires_screen_source_hashes(tmp_path):
    screen_path = tmp_path / "screen.json"
    profile = tmp_path / "profile.json"
    grouped = tmp_path / "grouped.json"
    inherited = tmp_path / "input.json"
    for path in (screen_path, profile, grouped, inherited):
        path.write_text("sealed")
    receipt = {
        "units": [
            {
                "source_hashes_snapshotted_before_validator_use": {
                    str(inherited.resolve()): "a" * 64
                }
            }
        ]
    }
    paths = refine.source_dependency_paths(receipt, screen_path, [profile], [grouped])
    names = {Path(path).name for path in paths}
    assert {
        "finite_set_identity_refine.py",
        "finite_set_identity_screen.py",
        "finite_set_cavity.py",
        "gauss_newton.py",
    } <= names
    assert str(inherited.resolve()) in paths

    with pytest.raises(ValueError, match="source-hash closure"):
        refine.source_dependency_paths({"units": [{}]}, screen_path, [profile], [grouped])


def test_run_requires_exact_two_pilot_screen(monkeypatch, tmp_path):
    path = tmp_path / "screen.json"
    path.write_text(
        __import__("json").dumps(
            {
                "schema": refine.SCREEN_SCHEMA,
                "source_run_id": refine.SOURCE_RUN,
                "units": [{"unit_id": unit} for unit in refine.SUPPORTED_UNITS],
            }
        )
    )
    monkeypatch.setattr(refine, "digest", lambda value: "a" * 64)
    calls = []
    receipt = refine.run(
        screen_path=path,
        diagnoser=lambda unit, screen, **kwargs: calls.append(unit) or {"unit_id": unit},
    )
    assert tuple(calls) == refine.SUPPORTED_UNITS
    assert "No substitution filtering" in receipt["scope"]
