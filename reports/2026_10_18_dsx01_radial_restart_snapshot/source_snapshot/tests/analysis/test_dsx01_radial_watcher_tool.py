"""A prior pilot receipt cannot terminate the full-campaign plot watcher."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from watch_dsx01_radial_restarts import matching_receipt, watch  # noqa: E402


def protocol(path):
    (path / "protocol.json").write_text(json.dumps(dict(
        source_fingerprint="current",
        expected_pipeline_results=3185,
        cases=[f"S{i}" for i in range(5)],
        starts=list(range(13)),
    )))


def receipt(path, requested=3250, completed=3250, failures=None, binding="current"):
    (path / "run_receipt.json").write_text(json.dumps(dict(
        source_fingerprint=binding, requested=requested, completed=completed,
        failures=failures or [], blocked_by_dependency=[],
    )))


def test_pilot_and_foreign_source_receipts_are_not_full_campaign_completion(tmp_path):
    protocol(tmp_path)
    receipt(tmp_path, requested=8, completed=8)
    assert matching_receipt(tmp_path, 3250) == (3250, None)
    receipt(tmp_path, binding="old")
    assert matching_receipt(tmp_path, 3250) == (3250, None)
    with pytest.raises(ValueError, match="job count differs"):
        matching_receipt(tmp_path, 8)


def test_watcher_refreshes_again_after_pilot_then_finishes_full_matching_receipt(tmp_path):
    protocol(tmp_path)
    receipt(tmp_path, requested=8, completed=8)
    reports, sleeps = [], []

    def report(output):
        reports.append(output)
        return dict(completed_worker_results=3185 if len(reports) > 1 else 7)

    def sleep(seconds):
        sleeps.append(seconds)
        receipt(tmp_path)

    assert watch(tmp_path, expected_jobs=3250, sleep=sleep, report=report) == 0
    assert len(reports) == 2 and sleeps == [120]
    status = json.loads((tmp_path / "watcher_status.json").read_text())
    assert status["terminal_matching_receipt"]
    assert status["completed_pipeline_results"] == 3185


def test_terminal_failure_still_generates_report_and_returns_nonzero(tmp_path):
    protocol(tmp_path)
    receipt(tmp_path, completed=3249, failures=[["S01", "normal", 2]])
    reports = []
    assert watch(tmp_path, report=lambda output: reports.append(output) or {}) == 1
    assert reports == [tmp_path]
    assert json.loads((tmp_path / "watcher_status.json").read_text())["exit_code"] == 1


def test_final_plot_failure_is_recorded_instead_of_claiming_success(tmp_path):
    protocol(tmp_path)
    receipt(tmp_path)

    def broken_report(output):
        raise RuntimeError("synthetic plot failure")

    assert watch(tmp_path, report=broken_report) == 2
    status = json.loads((tmp_path / "watcher_status.json").read_text())
    assert "synthetic plot failure" in status["report_error"]
