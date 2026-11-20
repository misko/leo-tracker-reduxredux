from types import SimpleNamespace

from tools.pipeline_eval.qualification import staggered_whole as worker
from tools.pipeline_eval.qualification.staggered_whole_results import (
    fingerprint,
    parity,
    per_call,
    rows_from_plain,
)
from tools.pipeline_eval.variants.staggered_native import RfStagger


def test_complete_worker_advances_only_valid_rf_visits(monkeypatch):
    seen = []

    def native_visit(frame, analyze, call, policy):
        valid = frame[1].valid
        if valid:
            call(frame[1].target)
        return dict(
            visit=frame[0],
            status="processed" if valid else "invalid_capture",
            sample_start=frame[0] * 20,
            sample_end=(frame[0] + 1) * 20,
            probes=[],
        ), None

    def mixed(samples, lane, *, trace):
        assert trace
        seen.append((samples["rf_center_hz"], lane))
        return None, dict(fifth_lane=lane, lanes=[dict(cpu=worker.MAIN), dict(cpu=worker.HELPER)])

    monkeypatch.setattr(worker.arrival_queue, "native_visit", native_visit)
    schedule = [(10, True), (10, False), (20, True), (10, True), (20, True)]
    cache = RfStagger()
    for index, (rf, valid) in enumerate(schedule):
        frame = index, SimpleNamespace(target={"rf_center_hz": rf}, valid=valid)
        _, receipt = worker.run_visit(frame, cache, SimpleNamespace(mixed=mixed), None, None)
        assert ("fifth_lane" in receipt) is valid
    assert seen == [(10, 0), (20, 0), (10, 1), (20, 1)]


def test_per_lane_audit_retains_actual_mismatches():
    def probes(branch):
        return [dict(visit_index=0, receiver_id=rx, candidates=[branch]) for rx in (0, 1)]

    def native(rows):
        return dict(source=dict(probes=rows), provenance=dict(window_count=1))

    stock, fifth = probes("stock"), probes("fifth")
    base = dict(visit=0, status="processed", visit_metadata_sha256="same", full_visit_sha256="row")
    releases = [
        [dict(base, probes=[dict(payload_sha256=fingerprint(p["candidates"])) for p in r])]
        for r in (stock, fifth)
    ]
    trace = [dict(base, fifth_lane=0, rf_center_hz=10)]
    controls = dict(control=native(stock), candidate=native(fifth))
    correct = parity(trace, native([fifth[0], stock[1]]), controls, releases)
    assert correct["status"] == "exact" and not correct["discrepancies"]
    wrong = parity(trace, native(stock), controls, releases)
    assert wrong["status"] == "mismatch"
    assert wrong["per_role_lane"]["candidate"]["rx0_mismatched"] == 1
    assert [(row["visit"], row["rx"], row["role"]) for row in wrong["discrepancies"]] == [
        (0, 0, "candidate")
    ]


def test_native_response_counts_only_valid_complete_visits():
    valid = dict(
        status="processed",
        wall_ns=21_000_000,
        typed_ns=19_000_000,
        cpu_ns=31_000_000,
        lanes=[dict(cpu_ns=16_000_000), dict(cpu_ns=15_000_000)],
    )
    out = per_call([dict(status="invalid_capture"), valid])
    assert (out["physical_visits_seen"], out["native_calls"]) == (2, 1)
    assert (out["typed_within_20ms"], out["decoded_within_20ms"]) == (1, 0)


def test_partial_terminal_trace_keeps_only_emitted_rows(tmp_path):
    trace = tmp_path / "visits.jsonl"
    trace.write_text('{"visit": 0}\n{"visi')
    assert rows_from_plain(trace, complete=False) == [{"visit": 0}]
