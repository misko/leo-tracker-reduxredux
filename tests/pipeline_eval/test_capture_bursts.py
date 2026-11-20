from collections import Counter

import pytest

from tools.pipeline_eval.qualification.capture_bursts_results import (
    backlog,
    largest_gap_connected_count,
)
from tools.pipeline_eval.variants import capture_bursts as bursts


def geometry(cycles=bursts.HORIZON, skipped=()):
    return [(v, v % 8 + 1) for v in range(cycles * 8) if v not in skipped]


@pytest.mark.parametrize(
    "periodic,burst,quota", [("periodic", "burst", 12), ("periodic_high", "burst_high", 52)]
)
def test_same_per_rf_budget_and_four_consecutive_visits(periodic, burst, quota):
    visits = geometry(bursts.HORIZON + 4, skipped=(0, 26, 127, 128))
    for mode in (periodic, burst):
        picked = bursts.scheduled_visits(visits, mode)
        assert Counter(v % 8 + 1 for v in picked) == dict.fromkeys(bursts.CHANNELS, quota)
        assert not {0, 26, 127, 128}.intersection(picked)
        assert picked == sorted(picked)
    for channel in bursts.CHANNELS:
        slots = list(bursts.clock_slots(burst, channel))
        assert all(slots[i + 3] - slots[i] == 3 for i in range(0, quota, 4))
        assert len(bursts.clock_slots(periodic, channel)) == quota


def test_rejects_overlapping_or_short_opportunity_ledger():
    visits = geometry()
    with pytest.raises(ValueError, match="chronological"):
        bursts.scheduled_visits(visits[:2] + visits[1:], "periodic")
    with pytest.raises(ValueError, match="horizon"):
        bursts.scheduled_visits(visits[:-1], "burst")


def test_preserves_exclusions_clocks_and_entire_original_retained_packet():
    def probe(visit, rx):
        return dict(
            channel=visit + 1,
            actual_rf_hz=11e9 + visit,
            edge="lower",
            valid_start_counter=10 + visit,
            payload_start_sample=500 + visit,
            receiver_id=rx,
            visit_index=visit,
            candidates=[{"rank": 0}, {"rank": 1}],
        )

    clocks = [{"monotonic_ns": t} for t in range(3)]
    old = dict(
        source={"probes": [probe(v, r) for v in (0, 2) for r in (0, 1)]},
        delivery_clocks=clocks,
        provenance={"window_count": 3, "processed_windows": 2, "excluded_windows": [{"visit": 1}]},
    )
    assert bursts.inventories(old) == [(0, 1), (2, 3)]
    new = bursts.select_document(old, [2], "sha256:" + "0" * 64)
    assert new["delivery_clocks"] is clocks
    assert new["provenance"]["excluded_windows"] == [{"visit": 1}]
    assert new["source"]["probes"][2:] == old["source"]["probes"][2:]
    assert new["source"]["probes"][:2] == [dict(probe(0, r), candidates=[]) for r in (0, 1)]
    assert len(old["source"]["probes"][0]["candidates"]) == 2


def test_decisions_for_a_common_prefix_only_depend_on_prior_valid_opportunities():
    original = geometry(bursts.HORIZON + 3)
    changed = geometry(bursts.HORIZON + 4, skipped=(6650,))
    for mode in bursts.CALLS:
        assert [v for v in bursts.scheduled_visits(original, mode) if v < 6650] == [
            v for v in bursts.scheduled_visits(changed, mode) if v < 6650
        ]


def test_queue_and_largest_temporal_component():
    assert backlog([0, 0.5, 4, 5], 2) == pytest.approx(3.5)
    assert largest_gap_connected_count([0, 1, 9, 12, 13, 40], 8) == 5
    assert largest_gap_connected_count([], 10) == 0
