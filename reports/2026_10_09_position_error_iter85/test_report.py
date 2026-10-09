"""Ensure partial cohorts and failed fits cannot produce flattering summaries."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "ablation_report", Path(__file__).with_name("report.py")
)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_pending_and_input_failure_prevent_full_stage_metrics():
    for status in ("pending", "failed"):
        assert REPORT.stage_metrics([dict(status=status)], "B7", "fitted-c") is None


def test_failed_candidate_keeps_large_fallback_and_failure_count():
    fallback = dict(stage="B0", error_km=151, posterior_rms_hz=90, converged=True)
    row = dict(
        status="complete",
        stages={"B0": {"fitted-c": fallback}, "B7": {"fitted-c": fallback}},
        raw={"B7": {"fitted-c": dict(converged=False, error_km=0.01, elapsed_s=90)}},
    )
    result = REPORT.stage_metrics([row], "B7", "fitted-c")
    assert result["position"]["mean"] == 151
    assert result["raw_failed"] == result["fallbacks"] == result["thresholds"]["100"] == 1
    assert result["versus_baseline"]["tied"] == 1


def test_not_attempted_and_raw_failed_are_distinct():
    fallback = dict(stage="B3", error_km=4, posterior_rms_hz=80, converged=True)
    row = dict(
        status="complete", stages={"B0": {"zero-c": fallback}, "B7": {"zero-c": fallback}}, raw={}
    )
    result = REPORT.stage_metrics([row], "B7", "zero-c")
    assert result["not_attempted"] == result["fallbacks"] == 1
    assert result["raw_failed"] == 0


def test_paired_changes_keep_regressions():
    result = REPORT.paired([1, 3, 2], [2, 1, 2])
    assert result["improved"] == result["regressed"] == result["tied"] == 1
    assert result["worst_regression_km"] == 2
