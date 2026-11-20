import socket

import pytest

from tools.pipeline_eval.qualification import parallel_acquisition as replay
from tools.pipeline_eval.qualification import parallel_acquisition_figures as figures
from tools.pipeline_eval.qualification import parallel_acquisition_results as results


def test_detector_fifos_have_independent_waiting_slots(tmp_path):
    with (
        (tmp_path / "wide.count").open("wb+", buffering=0) as wide,
        (tmp_path / "original.count").open("wb+", buffering=0) as original,
    ):
        for counter in (wide, original):
            counter.write(replay.WORD.pack(0))
        producer, consumer = socket.socketpair(type=socket.SOCK_SEQPACKET)
        peer, original_consumer = socket.socketpair(type=socket.SOCK_SEQPACKET)
        with producer, consumer, peer, original_consumer:
            assert replay.offer(wide.fileno(), producer, 4)
            assert replay.receive(consumer) == 4
            assert replay.offer(wide.fileno(), producer, 5)
            assert not replay.offer(wide.fileno(), producer, 6)
            assert replay.offer(original.fileno(), peer, 6)
            replay.complete(wide.fileno())
            assert replay.offer(wide.fileno(), producer, 7)
            assert replay.receive(consumer) == 5
            replay.complete(wide.fileno())
            assert replay.receive(consumer) == 7
            assert replay.receive(original_consumer) == 6


def fixture_trace():
    events = [
        {"visit": i, "arrival_ns": 10 * i, "status": status, "delivery_clock": {"monotonic_ns": i}}
        for i, status in enumerate(("processed", "processed", "processed", "invalid_capture"))
    ]
    archive = [{"visit": row["visit"]} for row in events]
    output = [
        dict(
            visit=i,
            start_ns=begin,
            finish_ns=end,
            native_cpu_ns=3,
            native_wall_ns=5,
            packet=archive[i],
        )
        for i, begin, end in ((0, 0, 15), (1, 15, 35))
    ]
    arrivals = [
        dict(
            visit=i,
            released_ns=10 * i,
            outcomes={"wide": dict(admission=status, offered_ns=10 * i)},
        )
        for i, status in enumerate(("queued", "queued", "dropped_busy", "invalid_capture"))
    ]
    return events, arrivals, output, archive


def test_trace_preserves_final_invalid_arrival_and_marks_late_drain():
    trace = results.assemble_trace(*fixture_trace(), "wide")
    assert [row["observed_by_cutoff"] for row in trace] == [True, False, False, False]
    assert trace[1]["finish_ns"] > trace[-1]["arrival_ns"]
    assert trace[1]["packet"] == {"visit": 1}
    assert trace[2]["admission"] == "dropped_busy"
    assert trace[3]["admission"] == trace[3]["status"] == "invalid_capture"
    assert trace[3]["delivery_clock"] == {"monotonic_ns": 3}
    assert all(row["packet"] is None and row["finish_ns"] is None for row in trace[2:])


def test_rejects_mismatched_full_emission_or_missing_admission():
    events, arrivals, output, archive = fixture_trace()
    output[1]["packet"] = {"visit": 1, "unexpected_candidate": 42}
    with pytest.raises(ValueError, match="complete measured packet"):
        results.assemble_trace(events, arrivals, output, archive, "wide")
    with pytest.raises(ValueError, match="corresponding admission"):
        results.assemble_trace(events, arrivals, output[:1], archive, "wide")


def test_chart_keeps_late_positive_and_dropped_visits_in_coverage():
    trace = results.assemble_trace(*fixture_trace(), "wide")
    positive_probe = {"candidates": [{"passed_fractional_margin_gate": True}]}
    for row in trace[:2]:
        row["packet"]["probes"] = [positive_probe]
    assert figures.branch_counts(trace, 30) == {
        "processed_by_cutoff": 1,
        "queue_drops": 1,
        "late_drain": 1,
        "positive_within_20ms_by_cutoff": 1,
    }
