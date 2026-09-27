from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PATH = Path(__file__).with_name("summarize_portable.py")
SPEC = importlib.util.spec_from_file_location("ds5_summarize_portable", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_distance_is_zero_at_reference() -> None:
    assert MODULE.distance_km(37.8, -122.4, 37.8, -122.4) == 0.0


def test_aggregate_retains_pending_denominator() -> None:
    summary = MODULE.aggregate([
        {"state": "complete", "horizontal_error_km": 1.0},
        {"state": "pending"},
        {"state": "complete", "horizontal_error_km": 3.0},
    ])
    assert summary["expected_count"] == 3
    assert summary["complete_count"] == 2
    assert summary["pending_count"] == 1
    assert summary["median_error_km"] == 2.0


def test_real_partial_build_preserves_strata_and_truth_gate() -> None:
    run_root = Path("/srv/bulk/leo/experiments/ds5-all-methods/portable-results")
    if not (run_root / "plan.json").exists():
        return
    result = MODULE.build(37.848639396, -122.4752910122, run_root)
    assert result["expected_result_count"] == 416
    assert result["reference_used_postseal_only"] is True
    single = next(row for row in result["rows"] if row["scope"] == "single")
    assert single["sample_rate_hz"] in {2_500_000, 5_000_000, 7_500_000, 10_000_000}
    assert single["active_dwell_time_stratum"] in {"low", "middle", "high"}
    assert single["active_dwell_seconds"] > 0
    assert len(result["summaries"]["single_rate_active_method"]) == 4 * 3 * 8
