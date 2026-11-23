from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("short_raw_diagnostic")


def test_incomplete_or_partial_cache_is_rejected(trial):
    warm = dict(members=3, observed_members=3, observed_file_pages=100, cached_pages=100, unavailable={})
    trial.require_warm(warm)
    for change in (dict(cached_pages=99), dict(observed_members=2), dict(unavailable={"EPERM": 1})):
        with pytest.raises(ValueError, match="not fully resident"):
            trial.require_warm(warm | change)


def test_cumulative_clocks_keep_missed_and_failed_assignments(trial):
    rows = [dict(case="withhold", missed_fix=False, false_fix=False, runs={
        "stock": dict(elapsed_s=4, decision="withheld"), "candidate": dict(elapsed_s=2, decision="withheld")}),
        dict(case="fix", missed_fix=True, false_fix=False, runs={
            "stock": dict(elapsed_s=16, decision="complete"), "candidate": dict(elapsed_s=2, error="timeout")})]
    assert trial.cumulative(rows[:1])["paired_median_elapsed_ratio"] == 0.5
    result = trial.cumulative(rows)
    assert result["paired_median_elapsed_ratio"] == 0.3125
    assert result["summed_elapsed_ratio"] == 0.2
    assert (result["candidate_misses"], result["candidate_false_fixes"], result["candidate_failures"]) == (1, 0, 1)
    assert result["stock_complete"] == 1 and result["candidate_complete"] == 0
