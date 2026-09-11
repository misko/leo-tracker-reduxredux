"""Failures and aliases must remain visible in the prototype's error accounting."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from summarize_glrt_refinement_prototype import details_for, identity, metrics


def test_missing_baseline_counts_as_failed_shift_and_alias_is_not_hidden():
    base = {
        "candidate_id": "a",
        "fs": 5000000,
        "version": "native",
        "profile": "local512",
        "session_id": "scan",
        "case": "baseline",
        "amount": 0,
        "target": {"epoch_s": 0.0001, "cfo_hz": 100, "rank": 0},
    }
    shifted = {
        **base,
        "case": "shift_hz",
        "amount": 137.19,
        "target": {"epoch_s": 0.0001, "cfo_hz": 237.19 + 1 / 4.4e-6, "rank": 1},
    }
    missing = {**base, "candidate_id": "b", "target": None}
    missed_shift = {**shifted, "candidate_id": "b"}
    details = details_for([base, shifted, missing, missed_shift])
    assert [r["recovered"] for r in details] == [True, False]
    report = metrics(details, {identity(shifted), identity(missed_shift)})
    assert report["attempted"] == 2
    assert report["recovered"] == report["common"] == report["alias_changes"] == 1
    assert report["cfo_error_hz_rms"] == pytest.approx(0, abs=1e-8)
    assert report["raw_cfo_error_hz_rms"] == pytest.approx(1 / 4.4e-6)


def test_common_mask_does_not_erase_unpaired_recovered_error():
    rows = [
        {
            "candidate_id": str(i),
            "case": "shift_hz",
            "amount": 100,
            "recovered": True,
            "alias_changed": False,
            "rank_changed": False,
            "timing_error_ns": 0,
            "cfo_error_hz": error,
            "raw_cfo_error_hz": error,
        }
        for i, error in enumerate([1, 100])
    ]
    report = metrics(rows, {identity(rows[0])})
    assert report["common"] == 1
    assert report["recovered"] == 2
    assert report["cfo_error_hz_rms"] == 1
    assert report["cfo_error_hz_all_recovered_rms"] > 70
