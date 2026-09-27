#!/usr/bin/env python3
"""Bounded profile of the actual repository scanner GLRT-64 application call."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import signal
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATASET = REPORT / "new_data"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import leo.analysis.starlink.acquisition as acquisition  # noqa: E402
import leo.analysis.starlink.pilot_methods as pilot_methods  # noqa: E402
import leo.scanner.detector as detector  # noqa: E402
from leo.scanner import ScannerConfiguration, current_low_band_targets  # noqa: E402

RATES = (2_500_000, 5_000_000)
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_source_lock() -> dict:
    lock = load_json(HERE / "source_lock.json")
    paths = {
        "design": HERE / "design.json",
        "runner": Path(__file__),
        "dataset_cases": DATASET / "cases.json",
        "detector": Path(detector.__file__),
        "acquisition": Path(acquisition.__file__),
        "pilot_methods": Path(pilot_methods.__file__),
        "scanner_models": Path(__file__).resolve().parents[3] / "src/leo/scanner/models.py",
        "native_acquisition": Path(acquisition._native_acquisition.__file__),
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError("application profile source lock changed")
    return lock


def select_cases() -> list[dict]:
    cases = load_json(DATASET / "cases.json")["cases"]
    selected = []
    for rate in RATES:
        subset = [case for case in cases if case["split"] == "dev" and case["rate_hz"] == rate]
        selected.append(min(subset, key=lambda case: (
            case["session_id"], case["source_start_counter"],
            case["visit_index"], case["case_id"],
        )))
    expected = [
        "newdev-r2500000-scan-fw-40ebc07665464c7d-v001077",
        "newdev-r5000000-scan-fw-e76c229e9dc498b3-v001077",
    ]
    if [case["case_id"] for case in selected] != expected:
        raise ValueError("metadata-selected profile cases changed")
    return selected


def load_iq(case: dict) -> np.ndarray:
    path = (DATASET / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(DATASET.resolve()) or digest(path) != case["raw_npy"]["sha256"]:
        raise ValueError(f"IQ source mismatch: {case['case_id']}")
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    if values.dtype != np.dtype("<i2") or values.shape != (
        case["rate_hz"] * 120 // 1000, 2, 2
    ):
        raise ValueError("IQ geometry mismatch")
    return values


def complex_frame(raw: np.ndarray) -> np.ndarray:
    output = np.empty(raw.shape[:2], dtype=np.complex64)
    output.real = raw[:, :, 0]
    output.imag = raw[:, :, 1]
    output.setflags(write=False)
    return output


def serialized_output(result) -> dict:
    return {
        "first": None if result.first is None else result.first.model_dump(mode="json"),
        "best_margin": result.best_margin,
        "reason": result.reason,
    }


def configuration(case: dict) -> ScannerConfiguration:
    target = next(
        item for item in current_low_band_targets()
        if item.channel == case["channel"] and item.edge.value == case["edge"]
    )
    return ScannerConfiguration(
        sample_rate_hz=case["rate_hz"], bandwidth_hz=case["rate_hz"],
        dwell_ms=120, receiver_ids=(0, 1), maximum_acquisition_candidates=10,
        targets=(target,),
    )


def timed(function):
    cpu_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu_started) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
    }


@dataclass
class StageRecorder:
    rows: dict[str, list[dict]] = field(default_factory=dict)
    originals: list[tuple[object, str, object]] = field(default_factory=list)

    def patch(self, module, name: str, label: str, metadata=None) -> None:
        original = getattr(module, name)
        self.originals.append((module, name, original))

        def wrapped(*args, **kwargs):
            cpu_started = time.process_time_ns()
            wall_started = time.perf_counter_ns()
            result = original(*args, **kwargs)
            row = {
                "process_cpu_ms": (time.process_time_ns() - cpu_started) / 1e6,
                "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
            }
            if metadata is not None:
                row.update(metadata(args, kwargs, result))
            self.rows.setdefault(label, []).append(row)
            return result

        setattr(module, name, wrapped)

    def restore(self) -> None:
        for module, name, original in reversed(self.originals):
            setattr(module, name, original)
        self.originals.clear()

    def summary(self) -> dict:
        return {
            label: {
                "calls": len(rows),
                "inclusive_process_cpu_ms": sum(row["process_cpu_ms"] for row in rows),
                "inclusive_wall_ms": sum(row["wall_ms"] for row in rows),
                "median_process_cpu_ms": statistics.median(row["process_cpu_ms"] for row in rows),
                "maximum_process_cpu_ms": max(row["process_cpu_ms"] for row in rows),
                "metadata": [
                    {key: value for key, value in row.items()
                     if key not in ("process_cpu_ms", "wall_ms")}
                    for row in rows
                ],
            }
            for label, rows in self.rows.items()
        }


@contextlib.contextmanager
def instrumented_stages(recorder: StageRecorder):
    recorder.patch(
        detector, "acquire_symbolwise", "acquire_symbolwise",
        lambda _a, _k, result: {
            "candidate_count": len(result.candidates), "status": result.status.value,
        },
    )
    recorder.patch(detector, "conditioned_glrt64_score", "conditioned_glrt64_score")
    recorder.patch(
        acquisition, "_folded_anchor_score_grid", "folded_anchor_score_grid",
        lambda args, _k, _r: {
            "sample_count": len(args[0]), "cfo_hypotheses": len(args[3]),
            "epoch_hypotheses": args[5],
        },
    )
    recorder.patch(
        acquisition, "_normalized_frame_scores", "normalized_frame_scores",
        lambda args, _k, _r: {"cfo_hypotheses": len(args[4]), "symbols": len(args[5])},
    )
    recorder.patch(
        acquisition, "_conditioned_frame_scores", "conditioned_frame_scores",
        lambda args, _k, _r: {"cfo_hypotheses": len(args[4]), "template_samples": len(args[1])},
    )
    recorder.patch(acquisition, "normalized_frame_score", "normalized_frame_score")
    recorder.patch(
        pilot_methods, "_conditioned_correlation_workspace", "conditioned_correlation_workspace",
        lambda args, kwargs, _r: {
            "sample_count": len(args[0]),
            "selected_symbols": len(kwargs.get("selected_symbols", ())),
        },
    )
    recorder.patch(
        pilot_methods, "_glrt_pair", "glrt_pair",
        lambda args, _k, _r: {"shape": list(args[0].values.shape)},
    )
    try:
        yield
    finally:
        recorder.restore()


def profile_case(case: dict) -> dict:
    raw = load_iq(case)
    before = "sha256:" + hashlib.sha256(raw).hexdigest()
    samples, conversion = timed(lambda: complex_frame(raw))
    config = configuration(case)
    call = lambda: detector.detect_first_glrt64(samples, config, edge=case["edge"])
    baseline, baseline_timing = timed(call)
    row = {
        "case_id": case["case_id"], "rate_hz": case["rate_hz"],
        "edge": case["edge"], "channel": case["channel"],
        "raw_sha256": case["raw_npy"]["sha256"], "conversion": conversion,
        "application_uninstrumented": baseline_timing,
        "application_output": serialized_output(baseline),
        "expected_operation_counts": {
            "scheduled_probes": config.scheduled_probe_count,
            "receiver_probe_acquisitions": config.scheduled_probe_count * len(config.receiver_ids),
            "maximum_glrt64_candidate_scores": (
                config.scheduled_probe_count * len(config.receiver_ids)
                * config.maximum_acquisition_candidates
            ),
            "overlap_reprocessing_factor_per_receiver": (
                config.scheduled_probe_count * config.probe_samples / config.dwell_samples
            ),
        },
        "diagnostic_status": "started",
    }
    recorder = StageRecorder()
    with instrumented_stages(recorder):
        diagnostic, diagnostic_timing = timed(call)
    diagnostic_output = serialized_output(diagnostic)
    row.update(
        diagnostic_status="complete",
        application_diagnostic=diagnostic_timing,
        diagnostic_output_exact=(diagnostic_output == row["application_output"]),
        diagnostic_output_sha256="sha256:" + hashlib.sha256(
            json.dumps(diagnostic_output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        stages=recorder.summary(),
    )
    if "sha256:" + hashlib.sha256(raw).hexdigest() != before:
        raise ValueError("profile input mutated")
    return row


def runtime_text() -> str:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        np.show_runtime()
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file directly beneath application_profile")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all declared numerical thread environment variables must equal 1")
    lock = verify_source_lock()
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("P-core 0 unavailable")
    rows = []
    status, error = "complete", None
    started = time.perf_counter_ns()

    def timeout(_signal, _frame):
        raise TimeoutError("frozen 120 second application profile bound reached")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        for case in select_cases():
            rows.append(profile_case(case))
            print(json.dumps({"case_complete": case["case_id"],
                              "wall_ms": rows[-1]["application_uninstrumented"]["wall_ms"]}),
                  flush=True)
    except TimeoutError as caught:
        status, error = "timed_out_partial", str(caught)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, original_affinity)
    payload = {
        "schema": "org.leo.research.scanner-application-profile-result/v1",
        "status": status, "error": error, "fresh_holdout_opened": False,
        "source_lock": lock, "thread_environment": environment,
        "numpy_runtime": runtime_text(), "native_backend": acquisition._folded_anchor_score_grid_backend(),
        "affinity_cpu": 0, "affinity_restored": sorted(original_affinity),
        "elapsed_wall_ms": (time.perf_counter_ns() - started) / 1e6,
        "selected_case_ids": [case["case_id"] for case in select_cases()],
        "rows": rows,
        "limitations": [
            "The second pass is instrumented diagnostic time, not baseline performance time.",
            "Nested stage times are inclusive and cannot be summed as exclusive time.",
            "This is repository scanner analysis on saved IQ, not evidence of live deployed DS5 use.",
        ],
    }
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": status, "completed_cases": len(rows), "output": str(output)}))


if __name__ == "__main__":
    main()
