import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def receiver(value):
    return {"result": {"rank": value, "total_cpu_ms": 3}, "screens": {"order": [0, 1]}}


def reference(reference_dir, case_id, values):
    (reference_dir / f"{case_id}-D.json").write_text(json.dumps({"repetitions": [{"receivers": [receiver(v) for v in values]}]}))


def test_summary_classifies_metrics_parity_cpu_overlap_and_capture(tmp_path):
    from summarize import summarize_phase

    phase = tmp_path / "phase"; phase.mkdir()
    reference_dir = tmp_path / "reference"; reference_dir.mkdir()
    reference(reference_dir, "one", [1, 2]); reference(reference_dir, "two", [3, 4])
    (phase / "clock.json").write_text(json.dumps({"host_before_ns": 900_000_000,
        "host_after_ns": 1_100_000_000, "target_uptime": "0.1 0.0\n"}))
    write_jsonl(phase / "glrt.jsonl", [
        {"type": "ready", "receivers": 2, "jobs": 2, "period_ms": 120, "epoch_ms": 110},
        {"type": "visit", "index": 0, "case_id": "one", "start_ms": 120, "cpu_ms": 10, "wall_ms": 11,
         "queue_ms": 1, "response_ms": 111, "receivers": [receiver(1), receiver(2)]},
        {"type": "published", "index": 0, "end_ms": 132, "response_ms": 112, "service_cpu_ms": 12},
        {"type": "visit", "index": 1, "case_id": "two", "start_ms": 181, "cpu_ms": 20, "wall_ms": 21,
         "queue_ms": 2, "response_ms": 130, "receivers": [receiver(3), receiver(4)]},
        {"type": "published", "index": 1, "end_ms": 195, "response_ms": 131, "service_cpu_ms": 22},
        {"type": "complete", "end_ms": 240},
    ])
    write_jsonl(phase / "cpu.jsonl", [
        {"monotonic_ms": 119, "cores": [{"cpu": 0, "delta": {"user": 1}}]},
        {"monotonic_ms": 130, "cores": [{"cpu": 0, "delta": {"user": 5, "irq": 2}}]},
        {"monotonic_ms": 170, "cores": [{"cpu": 0, "delta": {"user": 7}}]},
        {"monotonic_ms": 230, "cores": [{"cpu": 0, "delta": {"user": 7}}]},
    ])
    capture = phase / "capture"; capture.mkdir()
    write_jsonl(capture / "visits.jsonl", [
        {"host_monotonic_ns": 1_020_000_000, "record": {"visit": 0, "result": 1, "missing_samples_before": 0}},
        {"host_monotonic_ns": 1_080_000_000, "record": {"visit": 2, "result": 3, "missing_samples_before": 4}},
    ])
    (phase / "capture.exit").write_text("0\n")
    (capture / "receipt.json").write_text(json.dumps({"terminal": {"skipped": 0, "invalid": 0,
        "cancelled": 0}, "restoration": {"expected": {"rate": 1}, "observed": {"rate": 1},
        "expected_kernel_buffers": 4, "observed_kernel_buffers": 4, "fastlock_inactive": True}}))
    (capture / "archive.json").write_text(json.dumps({"start_host_ns": 1_010_000_000, "end_host_ns": 1_090_000_000}))

    summary = summarize_phase(phase, reference_dir)
    assert summary["glrt"]["completed_published_response_misses_over_period"] == 1
    assert summary["glrt"]["metrics"]["response_ms"]["p95"] == 130
    assert summary["glrt"]["parity"] == {"mode": "both_rx", "comparisons": 4, "matched": 4,
                                          "passed": True, "mismatches": []}
    assert summary["cpu"]["glrt_interval"]["cores"]["0"]["user"] == 19
    assert summary["capture"]["terminal"] == "completed"
    assert summary["capture"]["terminal_receipt"]["skipped"] == 0
    assert summary["capture"]["restoration_exact"] is True
    assert summary["capture"]["visit_index_gaps"] == 1
    assert summary["capture"]["missing_samples_before"] == 4
    assert summary["cpu"]["capture_interval"]["samples"] == 1
    assert summary["cpu"]["capture_interval"]["cores"]["0"]["user"] == 7
    assert summary["cpu"]["capture_overlap"]["samples"] == 1
    assert summary["glrt"]["capture_overlap"]["fully_completed_published_visits"] == 1
    assert summary["glrt"]["capture_overlap"]["metrics"]["cpu_ms"]["mean"] == 10
    assert summary["glrt"]["validity"]["passed"] is True


def test_phase_validity_does_not_treat_deadline_miss_as_receipt_failure(tmp_path):
    from summarize import summarize_phase

    phase = tmp_path / "deadline"; phase.mkdir()
    reference_dir = tmp_path / "reference"; reference_dir.mkdir()
    reference(reference_dir, "one", [1])
    (phase / "run.json").write_text("{}")
    (phase / "remote.exit").write_text("0\n")
    (phase / "clock.json").write_text(json.dumps({"host_before_ns": 0, "host_after_ns": 0,
        "target_uptime": "0.0 0.0\n"}))
    write_jsonl(phase / "glrt.jsonl", [{"type": "ready", "receivers": 1, "jobs": 1,
        "period_ms": 120, "epoch_ms": 0}, {"type": "visit", "index": 0, "case_id": "one",
        "receivers": [receiver(1)]}, {"type": "published", "index": 0, "end_ms": 121,
        "response_ms": 121}, {"type": "complete", "end_ms": 121}])
    (phase / "cpu.jsonl").write_text("")
    summary = summarize_phase(phase, reference_dir)
    assert summary["glrt"]["completed_published_response_misses_over_period"] == 1
    assert summary["validity"]["passed"] is True


def test_receiver_count_mismatch_never_passes_parity(tmp_path):
    from summarize import summarize_phase

    phase = tmp_path / "bad-rx"; phase.mkdir()
    reference_dir = tmp_path / "reference"; reference_dir.mkdir()
    reference(reference_dir, "one", [1, 2])
    (phase / "clock.json").write_text(json.dumps({"host_before_ns": 0, "host_after_ns": 0,
        "target_uptime": "0.0 0.0\n"}))
    write_jsonl(phase / "glrt.jsonl", [{"type": "ready", "receivers": 2, "jobs": 1,
        "period_ms": 120, "epoch_ms": 0}, {"type": "visit", "index": 0, "case_id": "one",
        "receivers": [receiver(1)]}, {"type": "published", "index": 0, "end_ms": 1,
        "response_ms": 1}, {"type": "complete", "end_ms": 1}])
    (phase / "cpu.jsonl").write_text("")
    summary = summarize_phase(phase, reference_dir)
    assert summary["glrt"]["parity"]["passed"] is False
    assert summary["glrt"]["validity"]["passed"] is False


def test_empty_phase_reports_missing_receipts_explicitly(tmp_path):
    from summarize import summarize_phase

    phase = tmp_path / "empty"; phase.mkdir()
    summary = summarize_phase(phase, tmp_path / "reference")
    assert summary["glrt"]["visits"] == 0
    assert summary["capture"] == {"present": False, "terminal": "not_requested", "visits": 0}
    assert summary["errors"]
