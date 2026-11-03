from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import audit_final
import evaluate
import posthoc_reporting
import run_panel


def test_declared_matrix_is_exactly_128_cells(monkeypatch, tmp_path: Path) -> None:
    selected = {
        "selected": {
            "DS9": [{"unit_id": f"DS9-{index}"} for index in range(11)],
            "DS10": [{"unit_id": f"DS10-{index}"} for index in range(11)],
            "DS11": [{"unit_id": f"DS11-{index}"} for index in range(10)],
        }
    }
    (tmp_path / "selection.json").write_text(json.dumps(selected))
    monkeypatch.setattr(run_panel, "HERE", tmp_path)
    units = run_panel.units()
    assert len(units) == 32
    assert len(units) * len(run_panel.ARMS) == 128
    assert run_panel.ARMS == ("C1", "M2", "M4", "M24")


def test_evaluator_refuses_truth_scoring_before_passed_audit(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "final-integrity-audit.json").write_text(
        json.dumps({"passed": False, "planned_cells": 128, "launch_receipts": 128})
    )
    monkeypatch.setattr(evaluate, "HERE", tmp_path)
    with pytest.raises(ValueError, match="has not passed"):
        evaluate.evaluate()


def test_posthoc_requires_128_unique_cells_and_audit_binding(monkeypatch, tmp_path: Path) -> None:
    audit = {
        "passed": True,
        "planned_cells": 128,
        "execution_freeze_sha256": "sha256:freeze",
    }
    audit_path = tmp_path / "final-integrity-audit.json"
    audit_path.write_text(json.dumps(audit))
    summary = {
        "schema": "covariance-epoch-confirmation-results/v1",
        "final_integrity_audit_sha256": posthoc_reporting.digest(audit_path),
        "overall": {arm: {"planned": 32} for arm in posthoc_reporting.ARMS},
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    with (tmp_path / "per-scan.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("unit", "dataset", "arm", "status", "qualified", "error_m", "east_km", "north_km"),
        )
        writer.writeheader()
        for index in range(32):
            dataset = "DS9" if index < 11 else "DS10" if index < 22 else "DS11"
            for arm in posthoc_reporting.ARMS:
                writer.writerow({
                    "unit": f"unit-{index}",
                    "dataset": dataset,
                    "arm": arm,
                    "status": "completed",
                    "qualified": "True",
                    "error_m": "1.0",
                    "east_km": "0.0",
                    "north_km": "0.0",
                })
    monkeypatch.setattr(posthoc_reporting, "HERE", tmp_path)
    loaded_summary, rows, loaded_audit = posthoc_reporting.load_inputs()
    assert len(rows) == 128
    assert loaded_summary == summary
    assert loaded_audit == audit
    ablations = {
        comparator: posthoc_reporting.paired_report(rows, comparator)["M24"]
        for comparator in ("C1", "M2", "M4")
    }
    assert set(ablations) == {"C1", "M2", "M4"}
    assert all(comparison["overall"]["common_qualified"] == 32 for comparison in ablations.values())


def test_integrity_constants_bind_four_arms_and_128_cells() -> None:
    assert audit_final.EXPECTED_ARMS == ("C1", "M2", "M4", "M24")
    assert audit_final.EXPECTED_CELLS == 128


def test_failed_diagnostic_point_cannot_improve_primary_metric() -> None:
    result = evaluate.summarize(
        [
            {"qualified": True, "error_m": 2000.0, "status": "completed", "seconds": 1.0},
            {"qualified": False, "error_m": 1.0, "status": "optimizer_unqualified", "seconds": 2.0},
        ]
    )
    assert result["planned"] == 2
    assert result["qualified"] == 1
    assert result["median_m"] == 2000.0
    assert result["sub_km_qualified_over_planned"] == 0.0
