from collections import Counter

import pytest
from selection import eligible_windows, select_dataset


def manifest(count=32):
    return {
        "dataset_id": "TEST",
        "excluded": [],
        "captures": [
            {
                "session_id": f"scan-{index:03d}",
                "capture_start_utc_ns": index * 423_000_000_000,
                "capture_end_utc_ns": (index * 423 + 300) * 1_000_000_000,
                "utc_qualified": True,
                "receiver_ids": [0, 1],
                "radio_id": "same",
            }
            for index in range(count)
        ],
    }


def test_nested_counts_and_unique_captures():
    selected = select_dataset(manifest(), 123)
    assert selected == select_dataset(manifest(), 123)
    assert len(set(selected["selected"])) == 16
    assert Counter(row["size"] for row in selected["units"]) == {1: 16, 2: 8, 4: 4}
    for size in (1, 2, 4):
        members = [
            member
            for row in selected["units"]
            if row["size"] == size
            for member in row["session_ids"]
        ]
        assert set(members) == set(selected["selected"])
        assert len(members) == 16


def test_excluded_capture_is_not_silently_skipped():
    source = manifest()
    source["excluded"] = [source["captures"].pop(5)]
    windows = eligible_windows(source)
    for window in windows:
        indices = [int(row["session_id"].split("-")[1]) for row in window]
        assert 5 not in indices
        assert indices == list(range(indices[0], indices[0] + 4))


def test_real_gaps_preserved_not_concatenated_away():
    result = select_dataset(manifest(), 42)
    quad = next(row for row in result["units"] if row["size"] == 4)
    assert quad["elapsed_span_s"] == 1569
    assert quad["capture_time_offsets_s"] == [0, 423, 846, 1269]
    assert quad["idle_gaps_s"] == [123, 123, 123]


def test_long_gap_or_different_radio_breaks_adjacency():
    source = manifest(4)
    source["captures"][2]["radio_id"] = "other"
    assert eligible_windows(source) == []
    source = manifest(4)
    source["captures"][2]["capture_start_utc_ns"] += 100_000_000_000
    assert eligible_windows(source) == []


def test_duplicate_or_missing_timestamp_fails_closed():
    source = manifest()
    source["excluded"] = [source["captures"][0]]
    with pytest.raises(ValueError, match="Duplicate"):
        eligible_windows(source)
    source = manifest()
    source["captures"][0]["capture_start_utc_ns"] = None
    with pytest.raises(ValueError, match="timestamps"):
        eligible_windows(source)
