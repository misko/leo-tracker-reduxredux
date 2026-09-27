#!/usr/bin/env python3
"""Validate and time the frozen exact decision-only early-exit prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
DATASET = REPORT / "new_data"
sys.path[:0] = [str(HERE), str(ROOT / "src")]

import leo.analysis.starlink.acquisition as acquisition  # noqa: E402
import leo.analysis.starlink.pilot_methods as pilot_methods  # noqa: E402
import leo.scanner.detector as detector  # noqa: E402
from leo.scanner import ScannerConfiguration, current_low_band_targets  # noqa: E402
import prototype  # noqa: E402

CASE_IDS = (
    "newdev-r2500000-scan-fw-40ebc07665464c7d-v001077",
    "newdev-r5000000-scan-fw-e76c229e9dc498b3-v001077",
)
RATES = (2_500_000, 5_000_000)
SCHEDULE = (("baseline", "candidate"), ("candidate", "baseline"), ("baseline", "candidate"))
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def verify_source_lock() -> dict:
    lock = json.loads((HERE / "source_lock.json").read_text())
    paths = {
        "design": HERE / "design.json",
        "prototype": HERE / "prototype.py",
        "prototype_tests": HERE / "test_prototype.py",
        "runner": HERE / "run_validation.py",
        "runner_tests": HERE / "test_validation.py",
        "dataset_cases": DATASET / "cases.json",
        "detector": Path(detector.__file__),
        "acquisition": Path(acquisition.__file__),
        "pilot_methods": Path(pilot_methods.__file__),
        "scanner_models": ROOT / "src/leo/scanner/models.py",
        "native_acquisition": Path(acquisition._native_acquisition.__file__),
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("early-exit validation source lock changed")
    return lock


def selected_cases() -> tuple[dict, ...]:
    cases = json.loads((DATASET / "cases.json").read_text())["cases"]
    by_id = {case["case_id"]: case for case in cases}
    selected = tuple(by_id[case_id] for case_id in CASE_IDS)
    if any(
        case["split"] != "dev"
        or case.get("is_holdout", False)
        or case["rate_hz"] != RATES[index]
        for index, case in enumerate(selected)
    ):
        raise ValueError("early-exit validation case membership changed")
    return selected


def load_samples(case: dict) -> np.ndarray:
    path = (DATASET / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(DATASET.resolve()) or digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError("early-exit validation IQ source mismatch")
    raw = np.load(path, mmap_mode="r", allow_pickle=False)
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if raw.dtype != np.dtype("<i2") or raw.shape != expected:
        raise ValueError("early-exit validation IQ geometry changed")
    output = np.empty(raw.shape[:2], dtype=np.complex64)
    output.real = raw[:, :, 0]
    output.imag = raw[:, :, 1]
    output.setflags(write=False)
    return output


def configuration(rate: int, *, channel: int, edge: str) -> ScannerConfiguration:
    target = next(
        item for item in current_low_band_targets()
        if item.channel == channel and item.edge.value == edge
    )
    return ScannerConfiguration(
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        dwell_ms=120,
        receiver_ids=(0, 1),
        maximum_acquisition_candidates=10,
        targets=(target,),
    )


def serialize(result) -> dict:
    return {
        "first": None if result.first is None else result.first.model_dump(mode="json"),
        "best_margin": result.best_margin,
        "reason": result.reason,
    }


def output_digest(value: dict) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def call(samples: np.ndarray, config: ScannerConfiguration, edge: str, method: str):
    function = (
        detector.detect_first_glrt64 if method == "baseline"
        else prototype.detect_first_glrt64_early
    )
    cpu_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    result = function(samples, config, edge=edge)
    timing = {
        "process_cpu_ms": (time.process_time_ns() - cpu_started) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
    }
    return serialize(result), timing


def diagnostic_counts(samples: np.ndarray, config: ScannerConfiguration, edge: str) -> tuple[dict, dict]:
    counts = {"receiver_probe_acquisitions": 0, "candidate_scores": 0}
    original_acquire = prototype.acquire_symbolwise
    original_score = prototype.conditioned_glrt64_score

    def counted_acquire(*args, **kwargs):
        counts["receiver_probe_acquisitions"] += 1
        return original_acquire(*args, **kwargs)

    def counted_score(*args, **kwargs):
        counts["candidate_scores"] += 1
        return original_score(*args, **kwargs)

    with patch.object(prototype, "acquire_symbolwise", counted_acquire), patch.object(
        prototype, "conditioned_glrt64_score", counted_score
    ):
        result = prototype.detect_first_glrt64_early(samples, config, edge=edge)
    return serialize(result), counts


def validate_real(case: dict) -> dict:
    samples = load_samples(case)
    config = configuration(case["rate_hz"], channel=case["channel"], edge=case["edge"])
    baseline_warm, _ = call(samples, config, case["edge"], "baseline")
    candidate_warm, _ = call(samples, config, case["edge"], "candidate")
    if candidate_warm != baseline_warm:
        raise ValueError("early-exit warmup response differs from baseline")
    rows = []
    for pair_index, pair in enumerate(SCHEDULE):
        for call_index, method in enumerate(pair):
            output, timing = call(samples, config, case["edge"], method)
            if output != baseline_warm:
                raise ValueError(f"{method} response differs from baseline warmup")
            rows.append({
                "pair_index": pair_index,
                "call_index": call_index,
                "method": method,
                **timing,
                "output_sha256": output_digest(output),
            })
    diagnostic, counts = diagnostic_counts(samples, config, case["edge"])
    if diagnostic != baseline_warm:
        raise ValueError("instrumented candidate response differs from baseline warmup")
    summary = {}
    for method in ("baseline", "candidate"):
        selected = [row for row in rows if row["method"] == method]
        summary[method] = {
            "repetitions": len(selected),
            "median_process_cpu_ms": statistics.median(row["process_cpu_ms"] for row in selected),
            "median_wall_ms": statistics.median(row["wall_ms"] for row in selected),
        }
    summary["cpu_speedup"] = (
        summary["baseline"]["median_process_cpu_ms"]
        / summary["candidate"]["median_process_cpu_ms"]
    )
    summary["wall_speedup"] = (
        summary["baseline"]["median_wall_ms"] / summary["candidate"]["median_wall_ms"]
    )
    summary["positive_path_cpu_gate"] = 3.0
    summary["positive_path_cpu_gate_pass"] = summary["cpu_speedup"] >= 3.0
    return {
        "case_id": case["case_id"],
        "origin": "recorded_development_outcome_informed_positive_path",
        "rate_hz": case["rate_hz"],
        "edge": case["edge"],
        "raw_sha256": case["raw_npy"]["sha256"],
        "response": baseline_warm,
        "response_sha256": output_digest(baseline_warm),
        "all_responses_exact": True,
        "candidate_diagnostic_counts": counts,
        "schedule": rows,
        "summary": summary,
    }


def validate_zero(rate: int) -> dict:
    edge, channel = "lower", 1
    config = configuration(rate, channel=channel, edge=edge)
    samples = np.zeros((config.dwell_samples, 2), dtype=np.complex64)
    samples.setflags(write=False)
    baseline, baseline_timing = call(samples, config, edge, "baseline")
    candidate, candidate_timing = call(samples, config, edge, "candidate")
    if candidate != baseline or baseline["first"] is not None:
        raise ValueError("constructed zero control did not preserve a no-result response")
    diagnostic, counts = diagnostic_counts(samples, config, edge)
    if diagnostic != baseline:
        raise ValueError("instrumented zero candidate response differs from baseline")
    return {
        "case_id": f"constructed-zero-r{rate}",
        "origin": "constructed_all_zero_no_result_control",
        "rate_hz": rate,
        "edge": edge,
        "input_sha256": "sha256:" + hashlib.sha256(samples).hexdigest(),
        "response": baseline,
        "response_sha256": output_digest(baseline),
        "all_responses_exact": True,
        "candidate_diagnostic_counts": counts,
        "schedule": [
            {"method": "baseline", **baseline_timing},
            {"method": "candidate", **candidate_timing},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file directly beneath application_early_exit")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread limits must equal one")
    source_lock = verify_source_lock()
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("P-core 0 unavailable")
    rows = []
    status, error = "complete", None
    started = time.perf_counter_ns()

    def timeout(_signal, _frame):
        raise TimeoutError("frozen 120 second early-exit validation bound reached")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        for case in selected_cases():
            rows.append(validate_real(case))
        for rate in RATES:
            rows.append(validate_zero(rate))
    except TimeoutError as caught:
        status, error = "timed_out_partial", str(caught)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, original_affinity)
    payload = {
        "schema": "org.leo.research.application-early-exit-result/v1",
        "status": status,
        "error": error,
        "fresh_holdout_opened": False,
        "source_lock": source_lock,
        "source_lock_stable": verify_source_lock() == source_lock,
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": sorted(original_affinity),
        "elapsed_wall_ms": (time.perf_counter_ns() - started) / 1e6,
        "rows": rows,
        "qualification": {
            "positive_path_cpu_gate": 3.0,
            "both_recorded_rates_pass": (
                status == "complete"
                and all(
                    row["summary"]["positive_path_cpu_gate_pass"]
                    for row in rows
                    if row["origin"] == "recorded_development_outcome_informed_positive_path"
                )
                and sum(
                    row["origin"] == "recorded_development_outcome_informed_positive_path"
                    for row in rows
                ) == 2
            ),
            "negative_control_speed_gate": None,
        },
        "limitations": json.loads((HERE / "design.json").read_text())["limitations"],
    }
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": status, "rows": len(rows), "output": str(output)}))


if __name__ == "__main__":
    main()
