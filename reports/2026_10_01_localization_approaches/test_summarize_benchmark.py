from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "localization_benchmark_summary", HERE / "summarize_benchmark.py"
)
assert SPEC and SPEC.loader
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


def test_threshold_fractions_retain_failed_rows_in_denominator() -> None:
    rows = [
        {"unit_id": "a", "accepted": True, "error_m": 900.0, "runtime_s": 10.0},
        {"unit_id": "b", "accepted": True, "error_m": 3000.0, "runtime_s": 20.0},
        {"unit_id": "c", "accepted": False, "error_m": None, "runtime_s": 30.0},
        {"unit_id": "d", "accepted": False, "error_m": None, "runtime_s": 40.0},
    ]
    result = SUMMARY.stats(rows)
    assert result["planned"] == 4
    assert result["accepted"] == 2
    assert result["within_threshold_counts"]["1000"] == 1
    assert result["within_threshold_fraction_of_planned"]["1000"] == 0.25
    assert result["median_runtime_s"] == 25.0


def test_paired_summary_uses_only_jointly_accepted_units() -> None:
    left = [
        {"unit_id": "a", "accepted": True, "error_m": 10.0},
        {"unit_id": "b", "accepted": True, "error_m": 1.0},
    ]
    right = [
        {"unit_id": "a", "accepted": True, "error_m": 12.0},
        {"unit_id": "b", "accepted": False, "error_m": None},
    ]
    result = SUMMARY.paired(left, right)
    assert result["paired_count"] == 1
    assert result["median_left_minus_right_m"] == -2.0
    assert result["left_better_by_more_than_1m"] == 1


def _new_rows(arm: str, offset: float) -> list[dict]:
    return [
        {
            "arm": arm,
            "unit_id": f"DS9-F{index:03d}",
            "dataset": "DS9",
            "attempted": True,
            "accepted": True,
            "error_m": offset + index,
            "runtime_s": 10.0,
        }
        for index in range(64)
    ]


def test_stage_matched_historical_controls_are_kept_distinct() -> None:
    controls = {
        "primary-evaluation.json": {
            "rows": [
                {
                    "unit_id": f"DS9-F{index:03d}",
                    "dataset": "DS9",
                    "accepted": True,
                    "error_m": 100.0 + index,
                    "runtime_s": 20.0,
                }
                for index in range(64)
            ]
        },
        "continuation-evaluation.json": {
            "rows": [
                {
                    "unit_id": f"DS9-F{index:03d}",
                    "dataset": "DS9",
                    "effective_accepted": True,
                    "effective_error_m": 200.0 + index,
                    "total_runtime_s": 30.0,
                }
                for index in range(64)
            ]
        },
    }
    primary = {"arms": ["A1"], "rows": _new_rows("A1", 300.0)}
    two_stage = {"arms": ["A1"], "rows": _new_rows("A1", 400.0)}
    panels = SUMMARY.build_panels(controls, primary, two_stage)
    assert panels["Historical primary"][0]["error_m"] == 100.0
    assert panels["Historical two-stage"][0]["error_m"] == 200.0
    assert panels["A1 primary"][0]["error_m"] == 300.0
    assert panels["A1 two-stage"][0]["error_m"] == 400.0


def test_incomplete_or_failed_official_audit_is_rejected() -> None:
    base = {
        "passed": True,
        "require_complete": True,
        "this_companion_is_required_for_final_acceptance": True,
    }
    SUMMARY.require_official_audit(base)
    for field in base:
        invalid = dict(base)
        invalid[field] = False
        with pytest.raises(ValueError, match="Complete passing companion audit"):
            SUMMARY.require_official_audit(invalid)


def test_dataset_alignment_uses_unit_ids_and_rejects_mismatch() -> None:
    historical = [
        {"unit_id": "DS9-F001", "dataset": "DS9"},
        {"unit_id": "DS9-F002", "dataset": "DS9"},
    ]
    panels = {
        "Historical two-stage": historical,
        "A1 two-stage": list(reversed(historical)),
    }
    order, aligned = SUMMARY.aligned_dataset_rows(
        panels, ["Historical two-stage", "A1 two-stage"], "DS9"
    )
    assert order == ["DS9-F001", "DS9-F002"]
    assert [row["unit_id"] for row in aligned["A1 two-stage"]] == order
    panels["A1 two-stage"] = panels["A1 two-stage"][:1]
    with pytest.raises(ValueError, match="unit mismatch"):
        SUMMARY.aligned_dataset_rows(panels, ["Historical two-stage", "A1 two-stage"], "DS9")
