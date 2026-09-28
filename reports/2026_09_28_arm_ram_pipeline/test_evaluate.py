import hashlib
import json
from pathlib import Path

import pytest

import evaluate


def _candidate() -> dict:
    return {
        "epoch": 100.0, "fractional_offset_samples": 0.25,
        "acquired_cfo_hz": 10.0, "tracking_cfo_hz": 12.0,
        "exact_score": 0.05, "control_score": 0.01, "margin": 0.04,
        "acquire_score": 0.0, "verify_score": 0.0, "verify_control_score": 0.0,
        "conditioned_score": 0.2, "coarse_score": 0.3,
        "exact_grid": [0.1] * 5, "control_grid": [0.1] * 5,
        "fractional_complete": 1,
    }


def _receiver(receiver: int, *, exact: float = 0.05) -> dict:
    candidate = _candidate()
    candidate["exact_score"] = exact
    candidate["margin"] = exact - candidate["control_score"]
    return {
        "receiver": receiver,
        "packing_cpu_ms": 1.0,
        "packing_wall_ms": 1.0,
        "probe_process_cpu_ms": 2.0,
        "detector_wall_ms": 2.0,
        "result": {
            "rank": {"scores": [1.0] * 6, "order": [0, 1, 2, 3, 4, 5], "projected_epoch_samples": [1] * 6},
            "confirmation_count": 1,
            "confirmation_window_mask": 1,
            "confirmations": [{"candidate_count": 1, "candidates": [candidate]}],
        },
        "screens": {"selected": 0, "scores": [[1.0] * 6, [1.0] * 6], "order": [[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]], "epochs": [[1] * 6, [1] * 6], "contrast": [1.0, 1.0]},
    }


def _stats(idle: int) -> dict:
    return {"user": 10, "nice": 0, "system": 10, "idle": idle, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}


def _phase(method: str, mode: str, *, jobs: int = 2, dropped: bool = False, exact: float = 0.05, overlap: bool = True, nested_timer: float | None = None) -> list[dict]:
    ready = {"type": "ready", "schema": evaluate.SCHEMA, "method": method, "mode": mode, "rate_hz": 2500000, "schedule_kind": "fixed-period", "jobs": jobs, "case_count": 1}
    jobs = []
    for index in range(ready["jobs"]):
        job = {"type": "job", "index": index, "case_id": "ds7-a-v1", "status": "processed", "arrival_ms": index * 120.0, "capture_complete_due_ms": index * 120.0 + 120.0, "ready_ms": index * 120.0 + 120.0, "start_ms": index * 120.0 + 121.0, "end_ms": index * 120.0 + 151.0, "consumer_thread_cpu_ms": 29.0, "receivers": [_receiver(0, exact=exact), _receiver(1, exact=exact)]}
        if dropped and index == ready["jobs"] - 1:
            job.update({"status": "dropped_queue_full", "start_ms": None, "end_ms": None, "consumer_thread_cpu_ms": 0.0, "receivers": None})
        elif nested_timer is not None:
            job["receivers"][0]["result"]["rank"]["total_cpu_ms"] = nested_timer
            job["receivers"][1]["result"]["confirmations"][0]["total_wall_ms"] = nested_timer + 1.0
        jobs.append(job)
    start, producer_end, final = _stats(80), _stats(100), _stats(150)
    producer_end["user"] = 30
    count = ready["jobs"]
    complete = {"type": "complete", "schema": evaluate.SCHEMA, "complete": True, "mode": mode, "jobs": count, "processed": count - int(dropped), "consumed": count - int(dropped), "dropped_queue_full": int(dropped), "queue_full_overruns": int(dropped), "detector_failures": 0, "pending": 0, "timed_start_ms": 0.0, "timed_end_ms": 250.0, "arrival_epoch_ms": 0.0, "producer_end_ms": 240.0, "consumer_thread_cpu_ms": 58.0, "producer_thread_cpu_ms": 4.0, "process_cpu_ms": 62.0, "producer_late_chunks_over_1ms": 0, "producer_max_chunk_late_ms": 0.2, "ring_occupied_highwater": 2, "ready_queue_highwater": 1, "consumer_core_stat_start": start, "consumer_core_stat_end": final}
    if mode == "concurrent" and overlap:
        complete["producer_end_consumer_core_stat"] = producer_end
    elif mode == "concurrent":
        complete["producer_end_consumer_core_stat"] = None
    return [ready, *jobs, complete]


def _write_run(tmp_path: Path, cells: dict[tuple, list[dict]]) -> Path:
    phases = []
    for identity, rows in cells.items():
        method, mode, *rest = identity
        repeat = rest[0] if rest else 0
        name = f"{method}-{mode}-r{repeat}.jsonl"
        raw = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
        (tmp_path / name).write_text(raw)
        phases.append({"name": name.removesuffix('.jsonl'), "file": name, "method": method, "mode": mode, "rate_hz": 2500000, "schedule_kind": "fixed-period", "jobs": rows[0]["jobs"], "returncode": 0, "sha256": hashlib.sha256(raw.encode()).hexdigest()})
    (tmp_path / "run.json").write_text(json.dumps({"complete": True, "source_hashes": {"worker": "a" * 64}, "phases": phases}))
    return tmp_path


def test_complete_matrix_reports_exact_and_inherited_gate(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {(method, mode): _phase(method, mode) for method in evaluate.METHODS for mode in evaluate.MODES})
    summary = evaluate.evaluate(run)
    comparisons = summary["comparisons"]["rate=2500000/schedule=fixed-period"]
    assert comparisons["same_binary_isolated_vs_concurrent_exact"]["D"]["concurrent_repeat_0"]["passed"] is True
    assert comparisons["D_vs_goal40mag_inherited_gate"]["concurrent"]["repeat_0"]["passed"] is True
    concurrent = summary["phases"]["D/concurrent/2500000/fixed-period/0"]
    assert concurrent["actual_overlap_headroom"]["available"] is True
    assert concurrent["actual_overlap_headroom"]["headroom_fraction"] == pytest.approx(0.5)


def test_exact_pair_detects_scientific_difference_excluding_timers(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "isolated"): _phase("D", "isolated"), ("D", "concurrent"): _phase("D", "concurrent", exact=0.06)})
    summary = evaluate.evaluate(run)
    result = summary["comparisons"]["rate=2500000/schedule=fixed-period"]["same_binary_isolated_vs_concurrent_exact"]["D"]["concurrent_repeat_0"]
    assert result["passed"] is False
    assert result["exact_mismatches"] == [0, 1]


def test_exact_pair_ignores_nested_native_timer_instrumentation(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "isolated"): _phase("D", "isolated", nested_timer=1.0), ("D", "concurrent"): _phase("D", "concurrent", nested_timer=99.0)})
    summary = evaluate.evaluate(run)
    result = summary["comparisons"]["rate=2500000/schedule=fixed-period"]["same_binary_isolated_vs_concurrent_exact"]["D"]["concurrent_repeat_0"]
    assert result["passed"] is True


def test_concurrent_jobs_compare_to_repeated_isolated_case_reference(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "isolated", 0): _phase("D", "isolated", jobs=3), ("D", "concurrent", 0): _phase("D", "concurrent", jobs=5)})
    summary = evaluate.evaluate(run)
    result = summary["comparisons"]["rate=2500000/schedule=fixed-period"]["same_binary_isolated_vs_concurrent_exact"]["D"]["concurrent_repeat_0"]
    assert result["isolated_jobs"] == 3
    assert result["concurrent_planned"] == 5
    assert result["isolated_case_references"] == 1
    assert result["passed"] is True


def test_drop_stays_in_pair_denominator_and_prevents_gate(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "concurrent"): _phase("D", "concurrent"), ("goal40mag", "concurrent"): _phase("goal40mag", "concurrent", dropped=True)})
    summary = evaluate.evaluate(run)
    result = summary["comparisons"]["rate=2500000/schedule=fixed-period"]["D_vs_goal40mag_inherited_gate"]["concurrent"]["repeat_0"]
    assert result["planned"] == 2
    assert result["both_processed"] == 1
    assert result["unavailable_or_dropped"] == [1]
    assert result["passed"] is False


def test_missing_overlap_counter_never_claims_headroom(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "concurrent"): _phase("D", "concurrent", overlap=False)})
    summary = evaluate.evaluate(run)
    headroom = summary["phases"]["D/concurrent/2500000/fixed-period/0"]["actual_overlap_headroom"]
    assert headroom == {"available": False, "reason": "producer-overlap /proc/stat end counter absent"}


def test_phase_sha_mismatch_is_rejected(tmp_path: Path) -> None:
    run = _write_run(tmp_path, {("D", "isolated"): _phase("D", "isolated")})
    inventory = json.loads((run / "run.json").read_text())
    inventory["phases"][0]["sha256"] = "0" * 64
    (run / "run.json").write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="SHA256"):
        evaluate.evaluate(run)
