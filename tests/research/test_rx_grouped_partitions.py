from __future__ import annotations

import copy

import pytest

from tools.rx_grouped_partitions import build_partition

RATES = [10_000_000] * 4 + [2_500_000] * 3 + [5_000_000] * 2 + [7_500_000]


def test_external_panel_keeps_temporal_groups_but_all_records_evaluation():
    rows = corpus()
    old = build_partition(rows)
    external = build_partition(rows, evaluation_only=True)
    assert external["groups"] == old["groups"]
    assert [(w["source_window_id"], w["role"]) for w in external["windows"]] == [
        (w["source_window_id"], w["role"]) for w in old["windows"]
    ]
    assert external["counts"]["recordings_by_split"] == {"evaluation": 10}
    small = build_partition(rows[:2], evaluation_only=True)
    assert small["counts"]["recordings"] == 1
    assert {r["recording_split"] for r in small["recordings"]} == {"evaluation"}
    with pytest.raises(ValueError, match="frozen sample-rate panel"):
        build_partition(rows[:2])


def opportunity(
    session: str,
    window: str,
    start: int,
    end: int,
    rate: int,
    *,
    intervals: list[tuple[str, int, int]] | None = None,
) -> dict:
    candidates = [
        {
            "source_interval": {
                "source_group_id": group,
                "stream_id": None,
                "source_sample_start": sample_start,
                "source_sample_end": sample_end,
            },
            "passed_fractional_margin_gate": True,
            "fractional_exact_score": 99.0,
        }
        for group, sample_start, sample_end in intervals or []
    ]
    return {
        "schema": "rx-paired-opportunity/v1",
        "source_window_id": window,
        "source_window": {
            "session_id": session,
            "sample_rate_hz": rate,
            "visit_index": start,
            "probe_index": 0,
            "probe_start_ms": 0,
            "channel": 1,
            "edge": "lower",
        },
        "window_start_utc_ns": start,
        "window_end_utc_ns": end,
        "opportunity_status": "both_receivers_candidate_present",
        "receivers": {
            "rx0": {
                "receiver_id": 0,
                "receiver_status": "observed_candidate_present",
                "actual_rf_hz": 10_710_000_000.0,
                "candidates": candidates,
            },
            "rx1": {
                "receiver_id": 1,
                "receiver_status": "observed_candidate_absent",
                "actual_rf_hz": 10_710_000_000.0,
                "candidates": [],
            },
        },
    }


def corpus(extra: list[dict] | None = None) -> list[dict]:
    rows = []
    for index, rate in enumerate(RATES):
        session = f"session-{index}"
        rows.extend(
            [
                opportunity(session, f"{session}-first", 0, 10, rate),
                opportunity(session, f"{session}-last", 90, 100, rate),
            ]
        )
    return rows + (extra or [])


def test_source_overlap_groups_transitively_across_tracks() -> None:
    rows = corpus()
    # Replace the first recording's ordinary endpoints with three disjoint UTC
    # windows whose source samples form one transitive overlap component.
    rows = [row for row in rows if row["source_window"]["session_id"] != "session-0"]
    rows.extend(
        [
            opportunity("session-0", "a", 0, 10, 10_000_000, intervals=[("source", 0, 10)]),
            opportunity("session-0", "b", 20, 30, 10_000_000, intervals=[("other", 9, 20)]),
            opportunity("session-0", "c", 90, 100, 10_000_000, intervals=[("third", 19, 30)]),
        ]
    )

    result = build_partition(rows)
    selected = [
        window for window in result["windows"] if window["source_window_id"] in {"a", "b", "c"}
    ]
    assert len({window["group_id"] for window in selected}) == 1
    assert {window["role"] for window in selected} == {"embargo"}


def test_fixed_time_boundaries_and_crossing_groups_are_embargoed() -> None:
    rows = corpus()
    rows.extend(
        [
            opportunity("session-0", "training-boundary", 50, 60, 10_000_000),
            opportunity("session-0", "crossing-boundary", 59, 61, 10_000_000),
            opportunity("session-0", "reception-boundary", 60, 80, 10_000_000),
            opportunity("session-0", "held-boundary", 80, 90, 10_000_000),
        ]
    )
    roles = {item["source_window_id"]: item["role"] for item in build_partition(rows)["windows"]}
    # The crossing window overlaps both adjacent windows, so the entire
    # connected component is embargoed rather than split at 60 ns.
    assert roles["training-boundary"] == "embargo"
    assert roles["crossing-boundary"] == "embargo"
    assert roles["reception-boundary"] == "embargo"
    assert roles["held-boundary"] == "held_frequency"


def test_receiver_pair_is_kept_in_one_window_and_missing_receiver_is_rejected() -> None:
    result = build_partition(corpus())
    assert all(window["receiver_ids"] == [0, 1] for window in result["windows"])
    assert result["overlap_validation"]["windows_with_both_receivers"] == len(result["windows"])

    broken = corpus()
    del broken[0]["receivers"]["rx1"]
    with pytest.raises(ValueError, match="exactly receivers 0 and 1"):
        build_partition(broken)


def test_detection_outcomes_cannot_change_membership() -> None:
    original = corpus()
    changed = copy.deepcopy(original)
    for row in changed:
        row["opportunity_status"] = "both_receivers_candidate_absent"
        for receiver in row["receivers"].values():
            receiver["receiver_status"] = "observed_candidate_absent"
            for candidate in receiver["candidates"]:
                candidate["passed_fractional_margin_gate"] = False
                candidate["fractional_exact_score"] = -1_000_000.0
    assert build_partition(changed) == build_partition(original)


def test_whole_record_split_is_deterministic_with_rate_coverage() -> None:
    first = build_partition(corpus())
    second = build_partition(reversed(corpus()))
    assert first == second
    assert first["counts"]["recordings_by_split"] == {"calibration": 6, "evaluation": 4}
    by_rate: dict[int, set[str]] = {}
    for recording in first["recordings"]:
        by_rate.setdefault(recording["sample_rate_hz"], set()).add(recording["recording_split"])
    assert by_rate[7_500_000] == {"calibration"}
    assert by_rate[10_000_000] == {"calibration", "evaluation"}
    assert by_rate[2_500_000] == {"calibration", "evaluation"}
    assert by_rate[5_000_000] == {"calibration", "evaluation"}


def test_null_source_stream_is_normalized_to_receiver_before_union() -> None:
    rows = [row for row in corpus() if row["source_window"]["session_id"] != "session-0"]
    left = opportunity("session-0", "rx0-support", 0, 10, 10_000_000, intervals=[("left", 0, 10)])
    right = opportunity(
        "session-0", "rx1-support", 90, 100, 10_000_000, intervals=[("right", 0, 10)]
    )
    right["receivers"]["rx1"]["candidates"] = right["receivers"]["rx0"].pop("candidates")
    right["receivers"]["rx0"]["candidates"] = []
    rows.extend([left, right])

    result = build_partition(rows)
    selected = {
        item["source_window_id"]: item
        for item in result["windows"]
        if item["source_window_id"] in {"rx0-support", "rx1-support"}
    }
    assert selected["rx0-support"]["group_id"] != selected["rx1-support"]["group_id"]
    assert selected["rx0-support"]["window_midpoint_utc_ns"] == 5
    assert selected["rx0-support"]["actual_rf_hz_by_receiver"] == {
        "rx0": 10_710_000_000.0,
        "rx1": 10_710_000_000.0,
    }
