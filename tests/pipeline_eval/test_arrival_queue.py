import pytest

from tools.pipeline_eval.qualification.arrival_queue import reference_events
from tools.pipeline_eval.qualification.arrival_queue_position import subtract
from tools.pipeline_eval.qualification.arrival_queue_results import queues


def physical():
    source = dict(sample_rate_hz=10_000_000, probe_ms=20, analysis_manifest_sha256="bound")
    source["probes"] = [
        dict(visit_index=visit, receiver_id=rx, valid_start_counter=counter)
        for visit, counter in ((0, 1_000_000), (2, 1_800_000))
        for rx in (0, 1)
    ]
    return dict(
        source=source,
        provenance=dict(
            window_count=3,
            excluded_windows=[
                dict(visit=1, sample_start=1_400_000, sample_end=1_600_000),
            ],
        ),
        delivery_clocks=[dict(monotonic_ns=10 + n, realtime_ns=100 + n) for n in (0, 10, 20)],
        clock_anchor={"sample_counter": 1_000_000},
    )


def test_authenticated_counter_and_hardware_exclusion_restoration():
    original = physical()
    rows = [
        dict(
            visit=i,
            status="processed" if i != 1 else "invalid_capture",
            full_visit_sha256="recorded",
            **({"cpu_s": 0.01, "wall_s": 0.02} if i != 1 else {}),
        )
        for i in range(3)
    ]
    events = reference_events(original, rows)
    assert events[1]["detector_wall_ns"] == 0
    assert (events[2]["arrival_ns"], events[2]["sample_end"]) == (20, 2_000_000)
    original["source"]["probes"][0]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="sample counters"):
        reference_events(original, rows)


def test_fifo_no_wait_drops_burst_but_one_slot_preserves_order_and_counters():
    events = [
        dict(
            visit=i,
            status="processed",
            arrival_ns=at,
            sample_start=i * 100,
            sample_end=i * 100 + 10,
            detector_cpu_ns=10,
            detector_wall_ns=10,
        )
        for i, at in enumerate((0, 1, 12))
    ]
    rows = {
        r["waiting_slots"]: (r, drops)
        for r, drops in queues(events, "test", "control")
        if r["workers"] == 1 and r["clock"] == "cpu"
    }
    assert rows[0][1] == [dict(visit=1, sample_start=100, sample_end=110, arrival_ns=1)]
    assert rows[1][0]["completed"] == 3 and rows[1][1] == []


def test_postfit_removes_both_receiver_packets_without_retiming():
    original = physical()
    fit = subtract(original, {2}, "sealed-actual-replay")
    assert fit["delivery_clocks"] == original["delivery_clocks"]
    assert fit["clock_anchor"] == original["clock_anchor"]
    assert fit["provenance"]["excluded_windows"] == original["provenance"]["excluded_windows"]
    assert [p["visit_index"] for p in fit["source"]["probes"]] == [0, 0]
    with pytest.raises(ValueError, match="valid recorded detector"):
        subtract(original, {1}, "invalid hardware shouldn't be a queue drop")
