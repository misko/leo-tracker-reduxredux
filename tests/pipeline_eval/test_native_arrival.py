from tools.pipeline_eval.qualification.native_arrival import retained_document
from tools.pipeline_eval.variants.native_arrival import Arrival, Policy, simulate


def arrivals(times, bins, invalid=()):
    return [Arrival(i, ns, bins[i], i not in invalid) for i, ns in enumerate(times)]


def test_native_fifo_preserves_physical_arrivals_and_invalid_slots():
    rows = arrivals([0, 2, 4, 6, 7], [0, 1, 0, 1, 0], invalid=(3,))
    trace = simulate(rows, [4, 3, 2, 0, 1], 1, Policy.FIFO, (0, 1), capacity=1, lag_ns=4)
    assert trace["start_ns"] == {0: 0, 1: 4, 2: 7, 4: 9}
    assert trace["finish_ns"] == {0: 4, 1: 7, 2: 9, 4: 10}
    assert trace["outcomes"] == {
        0: "ready",
        1: "expired_running",
        2: "expired_running",
        3: "invalid_capture",
        4: "ready",
    }
    assert trace["last_delivery"] == {"waiting": [4], "running": [2]}
    assert trace["deadline"] == {"waiting": [], "running": []}
    assert trace["ready_next"] == []


def test_replacement_and_round_robin_use_different_waiting_rule():
    rows = arrivals([0, 1, 2, 3, 4], [0, 1, 0, 1, 1])
    options = dict(capacity=2, lag_ns=20)
    duration = [5, 1, 1, 1, 1]
    fifo = simulate(rows, duration, 1, Policy.FIFO, (0, 1), **options)
    replace = simulate(rows, duration, 1, Policy.REPLACE, (0, 1), **options)
    rr = simulate(rows, duration, 1, Policy.ROUND_ROBIN, (0, 1), **options)
    assert list(fifo["start_ns"]) == [0, 1, 2]
    assert list(replace["start_ns"]) == [0, 3, 4]
    assert list(rr["start_ns"]) == [0, 4, 2]
    assert rr["outcomes"][1] == rr["outcomes"][3] == "replaced_rf"
    assert all(t["peak_waiting"] == 2 for t in (fifo, replace, rr))


def test_aging_and_terminal_snapshot_track_in_flight_work():
    rows = arrivals([0, 2, 3, 4], [0, 1, 0, 1])
    trace = simulate(rows, [20, 1, 1, 20], 2, Policy.FIFO, (0, 1), capacity=2, lag_ns=5)
    assert trace["ready_next"] == [1, 2]
    assert trace["deadline"] == {"waiting": [], "running": [0, 3]}
    assert trace["outcomes"] == {
        0: "deadline_running", 1: "ready", 2: "ready", 3: "deadline_running",
    }

    blocked = simulate(rows, [20, 1, 1, 20], 1, Policy.FIFO, (0, 1), capacity=1, lag_ns=5)
    assert blocked["outcomes"] == {
        0: "deadline_running", 1: "expired_waiting", 2: "queue_full", 3: "queue_full",
    }


def test_duration_unavailable_for_replaced_and_invalid_visits():
    class ServiceClock:
        def __len__(self):
            return 4

        def __getitem__(self, visit):
            return {0: 5, 2: 1}[visit]

    rows = arrivals([0, 1, 2, 3], [0, 1, 0, 1], invalid=(3,))
    trace = simulate(rows, ServiceClock(), 1, Policy.REPLACE, (0, 1), capacity=1, lag_ns=10)
    assert trace["outcomes"] == {
        0: "ready", 1: "replaced_oldest", 2: "ready", 3: "invalid_capture",
    }


def test_retained_native_uses_both_probe_rows_and_preserves_capture_validity():
    physical = [dict(visit_index=i, receiver_id=rx, candidates=[]) for i in (0, 2) for rx in (0, 1)]
    full = dict(
        source=dict(probes=physical, analysis_manifest_sha256="sha256:full", qualified=True),
        provenance=dict(processed_windows=2, excluded_windows=[dict(visit=1)], invalid_capture=1),
        clock_anchor=dict(sample_counter=123),
        delivery_clocks=[{}, {}, {}],
        last_sample_counter=456,
    )
    filtered = retained_document(full, {2}, "sha256:schedule")
    assert filtered["source"]["probes"] == physical[2:]
    assert filtered["source"]["analysis_manifest_sha256"] != "sha256:full"
    assert filtered["provenance"]["excluded_windows"] == [dict(visit=1)]
    assert filtered["provenance"]["invalid_capture"] == 1
    assert filtered["provenance"]["processed_windows"] == 1
    assert filtered["clock_anchor"] == full["clock_anchor"]
    assert filtered["delivery_clocks"] == full["delivery_clocks"]
    assert filtered["last_sample_counter"] == full["last_sample_counter"]
