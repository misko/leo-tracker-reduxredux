import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("live_summary", HERE / "summarize.py")
SUMMARY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SUMMARY)
HARNESS_SPEC = importlib.util.spec_from_file_location("live_harness", HERE / "run_live.py")
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
assert HARNESS_SPEC.loader is not None
HARNESS_SPEC.loader.exec_module(HARNESS)


def test_nearest_rank_percentiles_and_counter_units_are_explicit():
    values = [0.0, 10.0, 20.0, 30.0]
    result = SUMMARY.distribution(values, "ms")
    assert result["p50"] == 10.0
    assert result["p95"] == 30.0
    assert result["mean"] == 15.0
    assert result["percentile_method"] == "nearest rank (ceil(p*n))"
    assert SUMMARY.counter_ms(300_000) == 120.0


def test_strict_json_rejects_duplicate_and_nonfinite_values():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        SUMMARY.strict_loads('{"a":1,"a":2}', "test")
    with pytest.raises(ValueError, match="non-finite JSON number"):
        SUMMARY.strict_loads('{"a":NaN}', "test")


def test_harness_rejects_watchdog_overflow_before_execution():
    assert HARNESS.watchdog_seconds(585) == 600
    with pytest.raises(ValueError, match="requires 615s watchdog"):
        HARNESS.watchdog_seconds(600)


def test_harness_accepts_only_receipt_bound_finished_charge(tmp_path):
    receipt = {
        "name": "bounded",
        "exit_code": 7,
        "elapsed_wall_s": 16.1,
        "summaries": [
            {
                "source_close_status": 0,
                "owner_deactivate_status": 0,
                "radio_restore_status": 0,
                "owner_release_status": 0,
                "detector_destroy_status": 0,
            }
        ],
        "stderr": "",
    }
    receipt_path = tmp_path / "bounded-receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    row = {
        "name": "bounded",
        "status": "finished",
        "reserved_seconds": 135,
        "charged_seconds": 17,
        "unused_reservation_released_seconds": 118,
        "exit_code": 7,
        "elapsed_wall_s": 16.1,
        "finished_process_upper_bound_evidence": {
            "receipt_path": receipt_path.name,
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "host_elapsed_seconds": 16.1,
            "no_capture_process_after_close": True,
        },
    }
    assert HARNESS.charged_seconds_for_run(row, tmp_path) == 17
    row["status"] = "started"
    assert HARNESS.charged_seconds_for_run(row, tmp_path) == 135
    row["status"] = "finished"
    row["finished_process_upper_bound_evidence"]["receipt_sha256"] = "0" * 64
    assert HARNESS.charged_seconds_for_run(row, tmp_path) == 135
    receipt["summaries"][0]["radio_restore_status"] = -1
    receipt_path.write_text(json.dumps(receipt))
    row["finished_process_upper_bound_evidence"]["receipt_sha256"] = hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    assert HARNESS.charged_seconds_for_run(row, tmp_path) == 135


def test_current_reconciled_charges_are_bound_to_archived_receipts():
    ledger = json.loads((HERE / "budget.json").read_text())
    rows = {row["name"]: row for row in ledger["runs"]}
    assert HARNESS.charged_seconds_for_run(rows["baseline-120ms-block"], HERE) == 17
    assert HARNESS.charged_seconds_for_run(rows["revisitfix-continuous-585s"], HERE) == 234


def test_xadc_monitor_layout_and_temperature_conversion():
    receipt = {
        "monitor": [
            {
                "host_monotonic_s": 12.5,
                "raw": (
                    "9657.88 18083.29\n2699\n-2219\n123.040771484\n"
                    "MemAvailable: 411288 kB\nVmHWM: 21720 kB\nVmRSS: 21460 kB\n"
                ),
            }
        ],
        "radio_before": {"frequency_hz": "2400000000"},
        "radio_after": {"frequency_hz": "2400000000"},
        "radio_settings_restored": True,
    }
    result = SUMMARY.monitor_metrics(receipt)
    assert result["xadc_temperature_celsius"]["p50"] == pytest.approx(59.05957031232)
    assert result["scanner_rss_kib"]["maximum"] == 21460
    assert result["scanner_hwm_kib"]["maximum"] == 21720
    assert result["radio_settings_restored"] is True


def test_current_corrected_smoke_has_bounded_counter_and_detector_metrics():
    run = SUMMARY.summarize_run(HERE, HERE / "corrected-smoke-20ms-receipt.json")
    assert run["visits"] == {
        "started": 87,
        "event_records": 87,
        "intact": 86,
        "failed_or_incomplete": 1,
        "missing_event_visit_ids": [],
        "extra_event_visit_ids": [],
    }
    assert run["target_revisit_over_3000ms"] == 0
    assert run["detector"]["queue_drops"] == 0
    assert run["detector"]["runtime_ms"]["count"] == 86
    assert run["completed_visit_valid_window_duty"]["completed_visits"] == 86
    assert 0.79 < run["completed_visit_valid_window_duty"]["fraction"] < 0.80
    assert run["gaps_and_stop"]["missing_samples"] == 0
    assert run["cleanup"]["radio_restore_status"] == 0


def test_pre_execution_rejection_requires_hashed_proof_and_reports_unavailable(tmp_path):
    name = "rejected"
    proof = tmp_path / "proof.txt"
    proof.write_text("limit check before fork\n")
    proof_hash = hashlib.sha256(proof.read_bytes()).hexdigest()
    (tmp_path / f"{name}.jsonl").write_bytes(b"")
    (tmp_path / f"{name}.stderr").write_bytes(b"")
    receipt_path = tmp_path / f"{name}-receipt.json"
    receipt = {
        "name": name,
        "exit_code": 2,
        "elapsed_wall_s": 0.4,
        "event_count": 0,
        "summaries": [],
        "stderr": "",
        "raw_iq_transferred": False,
        "release_id": "test",
        "pre_execution_rejection": {
            "kind": "watchdog_limit_rejected_before_fork",
            "requested_watchdog_seconds": 615,
            "maximum_watchdog_seconds": 600,
            "disassembly_path": proof.name,
            "disassembly_sha256": proof_hash,
            "binary_sha256": "0" * 64,
            "detail": "rejected before fork",
        },
    }
    receipt_path.write_text(json.dumps(receipt))
    run = SUMMARY.summarize_run(tmp_path, receipt_path)
    assert run["execution_scope"] == "pre_execution_rejection"
    assert run["visits"] == {"available": False, "reason": "scanner_not_executed"}
    assert run["detector"] == {"available": False, "reason": "scanner_not_executed"}
    assert run["event_kind_counts"] is None
    receipt["pre_execution_rejection"]["disassembly_sha256"] = "f" * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="proof file/hash differs"):
        SUMMARY.summarize_run(tmp_path, receipt_path)
