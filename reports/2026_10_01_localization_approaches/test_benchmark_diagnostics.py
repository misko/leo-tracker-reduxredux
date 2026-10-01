from __future__ import annotations

import json

from benchmark_diagnostics import _comparison, analyze


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def test_aggregate_thresholds_and_incremental_continuation(tmp_path):
    primary_rows, final_rows = [], []
    for arm, error, runtime in (("A1", 1000., 10.), ("B1", 700., 15.)):
        parent = _write(tmp_path / arm / "primary.json", {
            "fits": [{"seed_index": 0, "fit_seconds": 2., "iterations": 4,
                      "reason": "iteration_limit", "associations": ["background"]}],
            "best": {"associations": ["background"]}, "acquisition_seconds": 5.,
            "cpu_seconds": 9., "max_rss_kib": 100., "port_calls": {"jacobians": 3}})
        row = {"arm": arm, "unit_id": "DS9-X", "attempted": True, "accepted": True,
               "status": "converged_local_mode", "runtime_s": runtime, "error_m": error,
               "receipt_path": str(parent)}
        primary_rows.append(row)
        final_rows.append(row)
    primary = _write(tmp_path / "primary-eval.json", {"rows": primary_rows})
    final = _write(tmp_path / "final-eval.json", {"rows": final_rows})
    result = analyze(primary, final, repository_root=tmp_path)
    assert result["arms"]["A1"]["fit_only_seconds"]["sum"] == 2.
    assert result["arms"]["A1"]["best_background_argmax_count"] == 1
    assert result["a1_b1"]["decision_checks"]["b1_paired_median_at_least_20_percent_lower"]
    assert result["a1_b1"]["practical_accuracy_win"]
    assert not result["coverage_is_complete"]


def test_no_accepted_loss_is_set_inclusion_not_equal_counts():
    rows = {
        ("A1", "u1"): {"accepted": True, "error_m": 1000.},
        ("A1", "u2"): {"accepted": False},
        ("B1", "u1"): {"accepted": False},
        ("B1", "u2"): {"accepted": True, "error_m": 500.},
    }
    result = _comparison(rows)
    assert result["a1_only_accepted_units"] == ["u1"]
    assert result["b1_only_accepted_units"] == ["u2"]
    assert not result["decision_checks"]["b1_no_accepted_scan_loss"]
