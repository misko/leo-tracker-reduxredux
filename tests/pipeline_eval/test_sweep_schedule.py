import gzip
import json
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.sweep_trials import (
    METHOD,
    REPORT,
    TIMING_IDS,
    historical_controls,
)
from tools.pipeline_eval.variants.sweep_schedule import (
    cavity_source,
    selected_probes,
    track_support,
)


def document():
    invalid = {0, 18}
    return {
        "clock_anchor": {"sample_counter": 99},
        "last_sample_counter": 143,
        "delivery_clocks": [{"realtime_ns": i * 50_000_000} for i in range(26)],
        "provenance": {
            "window_count": 26,
            "processed_windows": 24,
            "invalid_capture": 2,
            "excluded_windows": [
                {"visit": i, "reason": "invalid capture"} for i in sorted(invalid)
            ],
        },
        "source": {
            "probes": [
                {
                    "visit_index": i,
                    "channel": i % 8 + 1,
                    "receiver_id": receiver,
                    "valid_start_counter": 100 + i,
                    "candidates": [{"passed_fractional_margin_gate": bool(receiver)}],
                }
                for i in range(26)
                if i not in invalid
                for receiver in (0, 1)
            ]
        },
    }


def test_select_complete_sweeps_with_fixed_phase_and_preserve_original_metadata():
    scan = document()
    before = deepcopy(scan)
    selected, metrics = selected_probes(scan)
    rows = selected["source"]["probes"]
    expected = {*range(1, 8), 16, 17, *range(19, 24)}
    for row in rows:
        assert any(row is candidate for candidate in scan["source"]["probes"])
    assert {r["visit_index"] for r in rows} == expected
    assert {r["channel"] for r in rows} == set(range(1, 9))
    assert [r["receiver_id"] for r in rows] == [0, 1] * len(expected)
    assert metrics["kept_scheduled_visits"] == 16
    assert metrics["kept_processed_visits"] == 14
    assert metrics["kept_exclusions"] == {"invalid capture": 2}
    assert metrics["trailing_partial_visits"] == 2
    assert metrics["kept_delivery_span_s"] == 1.15
    for field in ("clock_anchor", "last_sample_counter", "delivery_clocks", "provenance"):
        assert selected[field] is scan[field]
    assert scan == before


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"channel": 1}, "sweep order"),
        ({"receiver_id": 1}, "duplicate receiver"),
        ({"receiver_id": 3}, "both recorded receivers"),
        ({"visit_index": 27}, "sweep order"),
    ],
)
def test_reject_inconsistent_archived_visit_identity(change, message):
    scan = document()
    scan["source"]["probes"][0].update(change)
    with pytest.raises(ValueError, match=message):
        selected_probes(scan)


def test_track_support_measures_retained_ids_lost_fragments_and_splits():
    full = {
        "observations": [{"observation_id": i} for i in range(8)],
        "tracks": [{"observation_ids": [0, 1, 2, 3, 4]}, {"observation_ids": [5, 6]}],
        "curved_indices": [0, 1],
        "graph_points": 7,
    }
    half = {
        "observations": [{"observation_id": i} for i in (0, 1, 2, 5, 7)],
        "tracks": [{"observation_ids": [0, 7]}, {"observation_ids": [1]}],
        "curved_indices": [0],
        "graph_points": 3,
    }
    support = track_support(full, half)
    assert support["full_track_support"] == [
        dict(
            full_points=5,
            retained_points=3,
            retracked_points=2,
            largest_overlap=1,
            retracked_fragments=2,
        ),
        dict(
            full_points=2,
            retained_points=1,
            retracked_points=0,
            largest_overlap=0,
            retracked_fragments=0,
        ),
    ]
    assert support["half_track_sizes"] == [2, 1]
    assert support["full_observations"] == 8
    assert support["half_graph_points"] == 3


def test_shipped_receipts_use_the_full_roster_and_match_the_controls():
    assert cavity_source(REPORT / "cavity-source.py.gz")
    with gzip.open(REPORT / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    assert [(r["id"], r["method"]) for r in rows] == [(ident, METHOD) for ident in TIMING_IDS]
    assert len({r["cpu"] for r in rows}) == len(TIMING_IDS)
    controls = historical_controls()
    for row in rows:
        control = controls[row["id"], "v5_core"]
        assert row["input_sha256"] == control["input_sha256"]
        assert set(row["result"]["arms"]) == {"c0", "fitted_c"}
        metrics = row["result"]["metrics"]
        assert metrics["cavity_sha256"] == control["implementation_sha256"]
        assert metrics["kept_scheduled_visits"] == 3384
        assert all(metrics["kept_processed_by_channel"])
        assert metrics["kept_delivery_span_s"] > 299.0
        assert metrics["kept_probes"] == metrics["kept_processed_visits"] * 2
        assert metrics["full_observations"] == control["result"]["metrics"]["observations"]
        assert (
            sum(t["full_points"] for t in metrics["full_track_support"])
            == metrics["full_graph_points"]
        )


def test_only_partial_sweep_does_not_supply_any_observations():
    archive = document()
    archive["delivery_clocks"] = archive["delivery_clocks"][:4]
    archive["source"]["probes"] = [p for p in archive["source"]["probes"] if p["visit_index"] < 4]
    archive["provenance"].update(
        window_count=4, processed_windows=3, excluded_windows=[{"visit": 0, "reason": "invalid"}]
    )
    selected, metrics = selected_probes(archive)
    assert selected["source"]["probes"] == []
    assert metrics["kept_processed_visits"] == 0
