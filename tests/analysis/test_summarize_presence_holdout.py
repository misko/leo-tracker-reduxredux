import copy

import pytest

from tools.summarize_presence_holdout import metrics, validate_one


def test_temporal_accounting_never_counts_unresolved_flags_as_reference_matches():
    def row(visit, offset, reference, detected, matched):
        return {
            "result": {"rate_hz": 5000000},
            "provenance": {"session_id": "a", "visit": visit, "probe_offset_ms": offset},
            "reference_positive": reference,
            "detected": detected,
            "matched_reference": matched,
        }

    rows = [
        row(0, 0, False, True, False),
        row(0, 100, True, True, True),
        row(1, 0, True, False, False),
        row(1, 100, False, False, False),
    ]
    result = metrics(rows)["5000000"]
    assert result["first_window"]["reference_positive"] == 1
    assert result["first_window"]["reference_positive_detected"] == 0
    first = result["temporal_schedules"][0]
    assert first["reference_positive_visits_anywhere"] == 2
    assert first["reference_seen_at_scheduled_windows"] == 1
    assert first["native_reference_associated_at_scheduled_windows"] == 0
    assert first["native_flag_at_scheduled_windows_including_unresolved"] == 1


def test_identity_and_gate_accounting_are_verified():
    probe = {
        "file": "a",
        "provenance": {},
        "rate_hz": 5000000,
        "edge": "lower",
        "device_counter": str(10**16 + 21),
        "oracle_candidates": [],
    }
    row = {
        "probe": "a",
        "provenance": {},
        "result": {
            "rate_hz": 5000000,
            "edge": 0,
            "format": 2,
            "device_counter": probe["device_counter"],
            "candidates": [],
        },
        "reference_positive": False,
        "detected": False,
        "matched_reference": False,
    }
    validate_one(probe, row, {})
    altered = copy.deepcopy(row)
    altered["result"]["device_counter"] = str(10**16 + 20)
    with pytest.raises(ValueError, match="identity"):
        validate_one(probe, altered, {})
    row["detected"] = True
    with pytest.raises(ValueError, match="accounting"):
        validate_one(probe, row, {})
