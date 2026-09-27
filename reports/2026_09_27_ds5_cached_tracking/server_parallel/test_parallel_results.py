"""Frozen parallel results checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT_SHA256 = "2a628eeb6ef43f7f4fc8f7b1da0a5f8cf4c330870970fca8ceda654e5e3bcda1"


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_result_is_complete_bounded_and_bound_to_refrozen_sources() -> None:
    result = load("results.json")
    lock = load("source_lock.json")
    assert digest(HERE / "results.json") == "sha256:" + RESULT_SHA256
    assert result["status"] == "complete"
    assert result["design_sha256"] == lock["files"]["design"]
    assert result["frozen_sources"] == lock["files"]
    assert result["input"]["physical_visits"] == 128
    assert result["input"]["receiver_visits"] == 256
    assert result["schedule"]["warmups_per_mode"] == 1
    assert result["schedule"]["timed_repetitions_per_mode"] == 3
    assert result["schedule"]["timed_phase_seconds"] < 60
    assert result["affinity"]["restored_main_thread"] == result["affinity"][
        "original_main_thread"
    ]


def test_worker_affinity_and_repetition_determinism() -> None:
    result = load("results.json")
    for workers in (1, 2, 4, 8):
        observed = result["affinity"]["worker_threads"][f"batch_{workers}"]
        assert len(observed) == workers
        for worker, receipt in observed.items():
            assert receipt["assigned_cpu"] == int(worker)
            assert receipt["observed"] == [int(worker)]
    for receipt in result["affinity"]["worker_threads"]["fp32_parallel_pair"].values():
        assert receipt["observed"] == [receipt["assigned_cpu"]]
    candidate_digest = None
    for mode, summary in result["summary"].items():
        assert len(summary["science_batch_sha256"]) == 3
        assert len(set(summary["science_batch_sha256"])) == 1
        if mode != "fp64_serial_pair":
            candidate_digest = candidate_digest or summary["science_batch_sha256"][0]
            assert summary["science_batch_sha256"][0] == candidate_digest


def test_science_identity_gate_and_cpu_wall_separation() -> None:
    result = load("results.json")
    validation = result["validation"]
    assert validation["gate_pass"] is True
    assert validation["reference_positive"] == 129
    assert validation["candidate_positive"] == 129
    assert validation["matched_reference_positive"] == 129
    assert validation["lost_reference_positive"] == 0
    assert validation["additional_candidate_positive"] == 0
    assert validation["all_candidate_runs_equal_serial_fp32"] is True
    assert validation["parallel_signature_mismatches"] == []
    eight = result["summary"]["batch_8"]
    assert eight["batch_wall_speedup_vs_packed_fp64_serial"] < 10
    assert eight["aggregate_process_cpu_ms"]["median"] > eight["batch_wall_ms"]["median"]
    assert eight["aggregate_cpu_ratio_vs_packed_fp64_serial"] > 0


def test_pair_mode_waits_per_visit_and_reports_tail_without_promotion_claim() -> None:
    result = load("results.json")
    serial = result["summary"]["fp32_serial_pair"]
    parallel = result["summary"]["fp32_parallel_pair"]
    assert serial["physical_visit_pair_wall_ms"]["samples"] == 384
    assert parallel["physical_visit_pair_wall_ms"]["samples"] == 384
    assert parallel["physical_visit_pair_wall_ms"]["p95"] > serial[
        "physical_visit_pair_wall_ms"
    ]["p95"]
    assert parallel["aggregate_process_cpu_ms"]["median"] > serial[
        "aggregate_process_cpu_ms"
    ]["median"]
    serialized = json.dumps(result["interpretation"]).lower()
    assert "not single-visit latency" in serialized
    assert "not an end-to-end" in serialized


def test_invalid_first_attempt_remains_disclosed_and_unusable() -> None:
    lock = load("source_lock.json")
    invalid = load("invalid_attempt_1.json")
    assert invalid["eligible_for_scientific_use"] is False
    assert invalid["timing_outcomes_persisted"] is False
    assert invalid["results_json_created"] is False
    assert lock["invalid_attempt_receipt_sha256"] == digest(HERE / "invalid_attempt_1.json")
