#!/usr/bin/env python3
"""Run the frozen two-case compact-workspace full-application comparison."""

from __future__ import annotations

import dataclasses
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
from prototype import compact_conditioned_glrt64_score  # noqa: E402

RATES = (2_500_000, 5_000_000)
CASE_IDS = (
    "newdev-r2500000-scan-fw-40ebc07665464c7d-v001077",
    "newdev-r5000000-scan-fw-e76c229e9dc498b3-v001077",
)
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
        "runner": HERE / "run_validation.py",
        "prototype": HERE / "prototype.py",
        "prototype_tests": HERE / "test_prototype.py",
        "validation_tests": HERE / "test_validation.py",
        "dataset_cases": DATASET / "cases.json",
        "detector": Path(detector.__file__),
        "acquisition": Path(acquisition.__file__),
        "pilot_methods": Path(pilot_methods.__file__),
        "scanner_models": ROOT / "src/leo/scanner/models.py",
        "templates": ROOT / "src/leo/analysis/starlink/templates.py",
        "native_acquisition": Path(acquisition._native_acquisition.__file__),
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("compact validation source lock changed")
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
        raise ValueError("compact validation case membership changed")
    return selected


def load_raw(case: dict) -> np.ndarray:
    path = (DATASET / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(DATASET.resolve()) or digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError("compact validation IQ source mismatch")
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    expected = (case["rate_hz"] * 120 // 1000, 2, 2)
    if values.dtype != np.dtype("<i2") or values.shape != expected:
        raise ValueError("compact validation IQ geometry changed")
    return values


def complex_frame(raw: np.ndarray) -> np.ndarray:
    output = np.empty(raw.shape[:2], dtype=np.complex64)
    output.real = raw[:, :, 0]
    output.imag = raw[:, :, 1]
    output.setflags(write=False)
    return output


def configuration(case: dict) -> ScannerConfiguration:
    target = next(
        item
        for item in current_low_band_targets()
        if item.channel == case["channel"] and item.edge.value == case["edge"]
    )
    return ScannerConfiguration(
        sample_rate_hz=case["rate_hz"],
        bandwidth_hz=case["rate_hz"],
        dwell_ms=120,
        receiver_ids=(0, 1),
        maximum_acquisition_candidates=10,
        targets=(target,),
    )


def serialize(result) -> dict:
    return {
        "first": None if result.first is None else result.first.model_dump(mode="json"),
        "decision_best_margin": result.decision_best_margin,
        "full_best_margin": result.full_best_margin,
        "reason": result.reason,
        "probes": [dataclasses.asdict(probe) for probe in result.probes],
    }


def output_digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def execute(raw: np.ndarray, config: ScannerConfiguration, edge: str, method: str):
    cpu_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    samples = complex_frame(raw)
    scorer = (
        pilot_methods.conditioned_glrt64_score
        if method == "baseline"
        else compact_conditioned_glrt64_score
    )
    with patch.object(detector, "conditioned_glrt64_score", scorer):
        result = detector.analyze_glrt64_dwell(samples, config, edge=edge)
    timing = {
        "process_cpu_ms": (time.process_time_ns() - cpu_started) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
    }
    return serialize(result), timing


def validate_case(case: dict) -> dict:
    raw = load_raw(case)
    input_before = digest((DATASET / case["raw_npy"]["path"]).resolve())
    config = configuration(case)
    baseline_warm, _ = execute(raw, config, case["edge"], "baseline")
    candidate_warm, _ = execute(raw, config, case["edge"], "candidate")
    if candidate_warm != baseline_warm:
        raise ValueError("compact candidate warmup response differs from baseline")
    rows = []
    for pair_index, pair in enumerate(SCHEDULE):
        for call_index, method in enumerate(pair):
            output, timing = execute(raw, config, case["edge"], method)
            if output != baseline_warm:
                raise ValueError(f"{method} full response differs from frozen warmup")
            rows.append(
                {
                    "pair_index": pair_index,
                    "call_index": call_index,
                    "method": method,
                    **timing,
                    "output_sha256": output_digest(output),
                }
            )
    input_after = digest((DATASET / case["raw_npy"]["path"]).resolve())
    if input_after != input_before:
        raise ValueError("compact validation input changed")
    summary = {}
    for method in ("baseline", "candidate"):
        selected = [row for row in rows if row["method"] == method]
        summary[method] = {
            "repetitions": len(selected),
            "median_process_cpu_ms": statistics.median(
                row["process_cpu_ms"] for row in selected
            ),
            "median_wall_ms": statistics.median(row["wall_ms"] for row in selected),
        }
    summary["cpu_speedup"] = (
        summary["baseline"]["median_process_cpu_ms"]
        / summary["candidate"]["median_process_cpu_ms"]
    )
    summary["wall_speedup"] = (
        summary["baseline"]["median_wall_ms"] / summary["candidate"]["median_wall_ms"]
    )
    return {
        "case_id": case["case_id"],
        "rate_hz": case["rate_hz"],
        "edge": case["edge"],
        "raw_sha256": input_before,
        "input_immutable": True,
        "warmup_full_response_exact": True,
        "full_response_sha256": output_digest(baseline_warm),
        "full_response_probe_rows": len(baseline_warm["probes"]),
        "schedule": rows,
        "summary": summary,
    }


def main() -> None:
    output = HERE / "results.json"
    if output.exists():
        raise ValueError("compact validation output already exists")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread limits must equal one")
    source_lock = verify_source_lock()
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("P-core 0 unavailable")
    started = time.perf_counter_ns()

    def timeout(_signal, _frame):
        raise TimeoutError("frozen 120 second compact validation bound reached")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        rows = [validate_case(case) for case in selected_cases()]
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, original_affinity)
    post_lock = verify_source_lock()
    payload = {
        "schema": "org.leo.research.application-compact-validation-result/v1",
        "status": "complete",
        "fresh_holdout_opened": False,
        "source_lock": source_lock,
        "source_lock_stable": post_lock == source_lock,
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": sorted(original_affinity),
        "elapsed_wall_ms": (time.perf_counter_ns() - started) / 1e6,
        "rows": rows,
        "limitations": [
            "Two metadata-selected development cases do not qualify sensitivity.",
            "Complete timings include CI16-to-complex64 conversion and scanner analysis.",
            "This saved-IQ server result is not a deployment, RF, ARM, or holdout claim."
        ],
    }
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": "complete", "output": str(output)}))


if __name__ == "__main__":
    main()
