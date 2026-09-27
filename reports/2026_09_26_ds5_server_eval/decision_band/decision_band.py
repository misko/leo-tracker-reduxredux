#!/usr/bin/env python3
"""Bounded native decision-band evaluation over the session-disjoint DS5 pack.

This research runner reduces each source rate to a 2.5 MS/s decision stream
with a causal Q15 anti-alias FIR, then uses the existing native whole-dwell
GLRT.  Native 2.5 and 5 MS/s runs are matched-rate comparators.  Higher-rate
rows deliberately carry no recall claim because no matched-rate oracle exists.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes as ct
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

DECISION_RATE_HZ = 2_500_000
DWELL_MS = 120
WINDOW_COUNT = 6
WINDOW_SAMPLES = DECISION_RATE_HZ // 50
PILOT_PERIOD_SECONDS = 1.0 / 750.0
SUPPORTED_SOURCE_RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def q15_coefficients(source_rate_hz: int, *, beta: float, span_outputs: int) -> np.ndarray:
    """Return a symmetric direct FIR with a 1 MHz pass-band edge.

    ``span_outputs`` controls the complete-support boundary in decision samples.
    An even span gives odd tap count and an integer group delay.
    """
    if source_rate_hz not in SUPPORTED_SOURCE_RATES[1:]:
        raise ValueError("a reduced supported source rate is required")
    factor = source_rate_hz // DECISION_RATE_HZ
    if span_outputs <= 0 or span_outputs % 2:
        raise ValueError("span_outputs must be a positive even integer")
    taps = span_outputs * factor + 1
    x = np.arange(taps, dtype=np.float64) - (taps - 1) / 2
    cutoff = 1_000_000.0 / source_rate_hz
    h = 2 * cutoff * np.sinc(2 * cutoff * x) * np.kaiser(taps, beta)
    q = np.rint(h / h.sum() * 32768).astype(np.int64)
    q[taps // 2] += 32768 - int(q.sum())
    if np.max(np.abs(q)) >= 32768 or np.sum(np.abs(q)) >= 65536:
        raise ValueError("unsafe Q15 coefficient geometry")
    return q.astype("<i2")


def filter_geometry(source_rate_hz: int, config: dict[str, Any]) -> dict[str, Any]:
    if source_rate_hz == DECISION_RATE_HZ:
        return {
            "factor": 1,
            "taps": 1,
            "group_delay_source_samples": 0,
            "complete_support_decision_sample": 0,
            "fractional_valid_start_decision_sample": 2,
        }
    factor = source_rate_hz // DECISION_RATE_HZ
    h = q15_coefficients(
        source_rate_hz,
        beta=float(config["filter_beta"]),
        span_outputs=int(config["filter_span_outputs"]),
    )
    group_delay = (len(h) - 1) // 2
    complete = (len(h) - 1 + factor - 1) // factor
    return {
        "factor": factor,
        "taps": len(h),
        "group_delay_source_samples": group_delay,
        "complete_support_decision_sample": complete,
        "fractional_valid_start_decision_sample": complete + 2,
    }


def circular_difference_seconds(left: float, right: float) -> float:
    """Signed shortest difference on the 750 Hz pilot timing lattice."""
    delta = left - right
    return (delta + PILOT_PERIOD_SECONDS / 2) % PILOT_PERIOD_SECONDS - PILOT_PERIOD_SECONDS / 2


def source_time_seconds(
    window: int,
    epoch: int,
    fractional_offset: float,
    source_rate_hz: int,
    analysis_rate_hz: int,
    group_delay_source_samples: int,
) -> float:
    if source_rate_hz % analysis_rate_hz:
        raise ValueError("analysis rate must divide source rate")
    analysis_index = window * (analysis_rate_hz // 50) + epoch + fractional_offset
    factor = source_rate_hz // analysis_rate_hz
    return (factor * analysis_index - group_delay_source_samples) / source_rate_hz


def candidate_supported(
    window: int,
    epoch: int,
    fractional_complete: bool,
    complete_support_decision_sample: int,
    analysis_rate_hz: int = DECISION_RATE_HZ,
) -> bool:
    if not fractional_complete or not 0 <= window < WINDOW_COUNT:
        return False
    # The native fractional confirmation evaluates +/-2 decision samples.
    global_epoch = window * (analysis_rate_hz // 50) + epoch
    return global_epoch - 2 >= complete_support_decision_sample


@dataclass(frozen=True)
class Detection:
    detected: bool
    diagnostic_exact_gate_detected: bool
    evaluation_status: str
    candidate_count: int
    supported: bool
    fractional_complete: bool
    window: int
    epoch: int
    fractional_offset: float
    source_time_seconds: float | None
    source_window: int | None
    cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    confirmation_mask: int


def detection_from_result(
    result: Any,
    *,
    source_rate_hz: int,
    analysis_rate_hz: int,
    group_delay_source_samples: int,
    complete_support_decision_sample: int,
    exact_threshold: float,
    margin_threshold: float,
) -> Detection:
    mask = int(result.confirmation_window_mask)
    window = mask.bit_length() - 1 if mask else -1
    candidate = result.confirmations[0].candidates[0]
    candidate_count = int(result.confirmations[0].candidate_count)
    fractional_complete = bool(candidate.fractional_complete)
    supported = candidate_supported(
        window,
        int(candidate.epoch),
        True,
        complete_support_decision_sample,
        analysis_rate_hz,
    )
    timing = (
        source_time_seconds(
            window,
            int(candidate.epoch),
            float(candidate.fractional_offset_samples),
            source_rate_hz,
            analysis_rate_hz,
            group_delay_source_samples,
        )
        if candidate_count > 0 and supported
        else None
    )
    exact = float(candidate.exact_score)
    control = float(candidate.control_score)
    margin = float(candidate.margin)
    if candidate_count <= 0:
        evaluation_status = "evaluated_no_candidate"
    elif not fractional_complete:
        evaluation_status = "evaluated_fractional_incomplete"
    elif not supported:
        evaluation_status = "unknown_unsupported_boundary"
    else:
        evaluation_status = "evaluated"
    source_window = int(timing * 50) if timing is not None and timing >= 0 else None
    return Detection(
        detected=(
            candidate_count > 0
            and fractional_complete
            and supported
            and margin > margin_threshold
        ),
        diagnostic_exact_gate_detected=(
            candidate_count > 0
            and fractional_complete
            and supported
            and exact >= exact_threshold
            and margin > margin_threshold
        ),
        evaluation_status=evaluation_status,
        candidate_count=candidate_count,
        supported=supported,
        fractional_complete=fractional_complete,
        window=window,
        epoch=int(candidate.epoch),
        fractional_offset=float(candidate.fractional_offset_samples),
        source_time_seconds=timing,
        source_window=source_window,
        cfo_hz=float(candidate.tracking_cfo_hz),
        exact_score=exact,
        control_score=control,
        margin=margin,
        confirmation_mask=mask,
    )


class NativeDecimator:
    """Bound ctypes wrapper for the reviewed direct Q15 decimator."""

    def __init__(self, library: Path, source_rate_hz: int, count: int, config: dict[str, Any]):
        self.rate = source_rate_hz
        self.factor = source_rate_hz // DECISION_RATE_HZ
        self.count = count
        self.output_count = count // self.factor
        self.geometry = filter_geometry(source_rate_hz, config)
        self.library = ct.CDLL(str(library))
        self.library.leo_decimator_create.argtypes = [
            ct.c_void_p,
            ct.c_uint,
            ct.c_void_p,
            ct.c_uint,
            ct.c_size_t,
        ]
        self.library.leo_decimator_create.restype = ct.c_void_p
        self.library.leo_decimator_create_factor.argtypes = [
            ct.c_void_p,
            ct.c_uint,
            ct.c_uint,
            ct.c_size_t,
        ]
        self.library.leo_decimator_create_factor.restype = ct.c_void_p
        self.library.leo_decimator_run.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
        ]
        self.library.leo_decimator_run.restype = ct.c_int
        self.library.leo_decimator_destroy.argtypes = [ct.c_void_p]
        self.library.leo_decimator_destroy.restype = None
        self.coefficients = q15_coefficients(
            source_rate_hz,
            beta=float(config["filter_beta"]),
            span_outputs=int(config["filter_span_outputs"]),
        )
        self.workspace = (
            self.library.leo_decimator_create(
                None,
                0,
                self.coefficients.ctypes.data,
                len(self.coefficients),
                count,
            )
            if self.factor == 4
            else self.library.leo_decimator_create_factor(
                self.coefficients.ctypes.data,
                len(self.coefficients),
                self.factor,
                count,
            )
        )
        if not self.workspace:
            raise ValueError("native decimator rejected the configuration")

    def close(self) -> None:
        if self.workspace:
            self.library.leo_decimator_destroy(self.workspace)
            self.workspace = None

    def run(self, values: np.ndarray) -> np.ndarray:
        if values.dtype != np.dtype("<i2") or values.shape != (self.count, 2):
            raise ValueError("decimator requires one complete contiguous CI16 receiver dwell")
        output = np.empty((self.output_count, 2), dtype="<i2")
        if self.library.leo_decimator_run(
            self.workspace, values.ctypes.data, len(values), output.ctypes.data
        ):
            raise ValueError("native decimator failed")
        boundary = int(self.geometry["complete_support_decision_sample"])
        output[:boundary] = 0
        return output


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(values, percentile))


def _summarize(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"rates": {}}
    for rate in SUPPORTED_SOURCE_RATES:
        rate_rows = [row for row in rows if row["rate_hz"] == rate]
        candidate_rows = [row for row in rate_rows if row["method"] == "decision_2p5m"]
        baseline_rows = [row for row in rate_rows if row["method"] == "native_rate"]
        visits: dict[str, list[dict[str, Any]]] = {}
        for row in candidate_rows:
            visits.setdefault(row["case_id"], []).append(row)
        visit_cpu = [sum(r["timing_cpu_ms_mean"] for r in group) for group in visits.values()]
        visit_wall = [sum(r["timing_wall_ms_mean"] for r in group) for group in visits.values()]
        baseline_visits: dict[str, list[dict[str, Any]]] = {}
        for row in baseline_rows:
            baseline_visits.setdefault(row["case_id"], []).append(row)
        baseline_visit_cpu = [
            sum(r["timing_cpu_ms_mean"] for r in group) for group in baseline_visits.values()
        ]
        baseline_visit_wall = [
            sum(r["timing_wall_ms_mean"] for r in group) for group in baseline_visits.values()
        ]
        candidate_cpu_mean = statistics.fmean(visit_cpu) if visit_cpu else None
        candidate_wall_mean = statistics.fmean(visit_wall) if visit_wall else None
        baseline_cpu_mean = (
            statistics.fmean(baseline_visit_cpu) if baseline_visit_cpu else None
        )
        baseline_wall_mean = (
            statistics.fmean(baseline_visit_wall) if baseline_visit_wall else None
        )
        section: dict[str, Any] = {
            "case_count": len(visits),
            "receiver_count": len(candidate_rows),
            "candidate_detected": sum(row["detection"]["detected"] for row in candidate_rows),
            "both_rx_visit_cpu_ms_mean": candidate_cpu_mean,
            "both_rx_visit_wall_ms_mean": candidate_wall_mean,
            "both_rx_visit_wall_ms_p95": _percentile(visit_wall, 95),
            "matched_rate_oracle": rate in (2_500_000, 5_000_000),
            "candidate_evaluation_status_counts": {
                status: sum(
                    row["detection"]["evaluation_status"] == status
                    for row in candidate_rows
                )
                for status in (
                    "evaluated",
                    "evaluated_no_candidate",
                    "evaluated_fractional_incomplete",
                    "unknown_unsupported_boundary",
                )
            },
        }
        if baseline_rows:
            section.update(
                baseline_both_rx_visit_cpu_ms_mean=baseline_cpu_mean,
                baseline_both_rx_visit_wall_ms_mean=baseline_wall_mean,
                baseline_both_rx_visit_wall_ms_p95=_percentile(baseline_visit_wall, 95),
                baseline_relative_cpu_speedup=(
                    baseline_cpu_mean / candidate_cpu_mean
                    if baseline_cpu_mean is not None and candidate_cpu_mean
                    else None
                ),
                baseline_relative_wall_speedup=(
                    baseline_wall_mean / candidate_wall_mean
                    if baseline_wall_mean is not None and candidate_wall_mean
                    else None
                ),
            )
            baseline_by_key = {(r["case_id"], r["receiver"]): r for r in baseline_rows}
            positives = 0
            retained = 0
            candidate_positive = 0
            agreements: list[dict[str, Any]] = []
            for row in candidate_rows:
                baseline = baseline_by_key[(row["case_id"], row["receiver"])]
                if row["detection"]["detected"]:
                    candidate_positive += 1
                if not baseline["detection"]["detected"]:
                    continue
                positives += 1
                candidate = row["detection"]
                base = baseline["detection"]
                if candidate["source_time_seconds"] is None or base["source_time_seconds"] is None:
                    continue
                cfo_error = abs(candidate["cfo_hz"] - base["cfo_hz"])
                timing_error = abs(
                    circular_difference_seconds(
                        candidate["source_time_seconds"], base["source_time_seconds"]
                    )
                )
                matched = (
                    candidate["detected"]
                    and candidate["window"] == base["window"]
                    and cfo_error
                    <= float(config["matching"]["maximum_cfo_error_hz"])
                    and timing_error
                    <= float(config["matching"]["maximum_circular_timing_error_us"])
                    * 1e-6
                )
                retained += int(matched)
                agreements.append(
                    {
                        "cfo_error_hz": cfo_error,
                        "circular_timing_error_us": timing_error * 1e6,
                        "same_window": candidate["window"] == base["window"],
                        "same_source_window": (
                            candidate["source_window"] == base["source_window"]
                        ),
                        "matched": matched,
                    }
                )
            section["baseline_positive_count"] = positives
            section["baseline_relative_retained_count"] = retained
            section["baseline_relative_retention"] = retained / positives if positives else None
            section["candidate_positive_count"] = candidate_positive
            section["matched_positive_agreements"] = agreements
        else:
            section["recall_claim"] = None
            section["limitation"] = (
                "no matched native-rate oracle; detection counts are descriptive only"
            )
        summary["rates"][str(rate)] = section
    control_rows = [row for row in rows if row.get("truth_kind")]
    if control_rows:
        by_method = {}
        for method in ("native_rate", "decision_2p5m"):
            method_rows = [row for row in control_rows if row["method"] == method]
            by_method[method] = {
                kind: {
                    "receiver_count": sum(row["truth_kind"] == kind for row in method_rows),
                    "positive_count": sum(
                        row["truth_kind"] == kind and row["detection"]["detected"]
                        for row in method_rows
                    ),
                }
                for kind in ("pilot", "noise", "tone")
            }
        candidate_keys = {
            (row["case_id"], row["receiver"])
            for row in control_rows
            if row["method"] == "decision_2p5m" and row["detection"]["detected"]
        }
        baseline_keys = {
            (row["case_id"], row["receiver"])
            for row in control_rows
            if row["method"] == "native_rate" and row["detection"]["detected"]
        }
        baseline_inventory = {
            (row["case_id"], row["receiver"])
            for row in control_rows
            if row["method"] == "native_rate"
        }
        pilot_truth_errors = []
        for row in control_rows:
            if row["method"] != "decision_2p5m" or row["truth_kind"] != "pilot":
                continue
            truth = row["truth_receiver"]
            expected_time = (
                truth["window"] / 50
                + (truth["epoch_samples"] + truth["fractional_delay_samples"])
                / row["rate_hz"]
            )
            observed_time = row["detection"]["source_time_seconds"]
            pilot_truth_errors.append(
                {
                    "case_id": row["case_id"],
                    "receiver": row["receiver"],
                    "detected": row["detection"]["detected"],
                    "same_window": row["detection"]["window"] == truth["window"],
                    "cfo_error_hz": abs(row["detection"]["cfo_hz"] - truth["cfo_hz"]),
                    "circular_timing_error_us": (
                        abs(circular_difference_seconds(observed_time, expected_time)) * 1e6
                        if observed_time is not None
                        else None
                    ),
                }
            )
        summary["synthetic_controls"] = {
            "methods": by_method,
            "matched_rate_additional_positive_count": len(
                (candidate_keys & baseline_inventory) - baseline_keys
            ),
            "candidate_noise_or_tone_positive_count": sum(
                row["method"] == "decision_2p5m"
                and row["truth_kind"] in ("noise", "tone")
                and row["detection"]["detected"]
                for row in control_rows
            ),
            "pilot_truth_errors": pilot_truth_errors,
            "scope": "constructed smoke controls, not RF false-alarm calibration",
        }
    return summary


def load_cases(dataset_manifest: Path, split: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(dataset_manifest.read_text())
    cases = [case for case in payload["cases"] if case["split"] == split]
    if not cases:
        raise ValueError(f"dataset has no {split!r} cases")
    for case in cases:
        if case["rate_hz"] not in SUPPORTED_SOURCE_RATES or case["dwell_ms"] != DWELL_MS:
            raise ValueError("unsupported dataset geometry")
    return payload, cases


def validate_config(config: dict[str, Any], *, split: str, dataset_sha256: str) -> None:
    """Reject scientific or timing changes hidden behind the same config schema."""
    expected = default_config()
    allowed = {*expected, "freeze"}
    if set(config) - allowed:
        raise ValueError("frozen configuration has unknown fields")
    for key, value in expected.items():
        if key == "stage":
            continue
        if config.get(key) != value:
            raise ValueError(f"configuration field {key!r} differs from the sealed design")
    if config.get("stage") not in ("development", "frozen_after_dev"):
        raise ValueError("configuration stage is invalid")
    if split not in ("validation", "holdout"):
        return
    freeze = config.get("freeze")
    if config["stage"] != "frozen_after_dev" or not isinstance(freeze, dict):
        raise ValueError("validation and holdout require a post-development freeze")
    if freeze.get("dataset_manifest_sha256") != dataset_sha256:
        raise ValueError("frozen dataset manifest hash does not match")
    if freeze.get("experiment_source_sha256") != sha256(Path(__file__).resolve()):
        raise ValueError("experiment source changed after configuration freeze")


def load_raw(dataset_dir: Path, case: dict[str, Any]) -> np.ndarray:
    path = dataset_dir / case["raw_npy"]["path"]
    expected_hash = case["raw_npy"]["sha256"].removeprefix("sha256:")
    if sha256(path) != expected_hash:
        raise ValueError(f"raw hash mismatch: {path}")
    raw = np.load(path, allow_pickle=False)
    expected_shape = (case["rate_hz"] * DWELL_MS // 1000, 2, 2)
    if raw.dtype != np.dtype("<i2") or raw.shape != expected_shape:
        raise ValueError(f"raw array violates contract: {path}")
    return raw


def build_native(reference_root: Path, output_dir: Path) -> Path:
    sys.path[:0] = [str(reference_root), str(reference_root / "src")]
    from tools.prepare_decimated_dwell_replay import build

    output_dir.mkdir(parents=True, exist_ok=True)
    library = output_dir / "decision_band_native.so"
    receipt = library.with_name(library.name + ".build.json")
    if not library.exists():
        build(library, shared=True)
    if not receipt.exists():
        raise ValueError("native build receipt is missing")
    expected = json.loads(receipt.read_text())["binary_sha256"]
    if sha256(library) != expected:
        raise ValueError("cached native binary hash does not match its build receipt")
    return library


def evaluate(
    *,
    dataset_manifest: Path,
    split: str,
    config_path: Path,
    reference_root: Path,
    output: Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text())
    dataset_hash = sha256(dataset_manifest)
    validate_config(config, split=split, dataset_sha256=dataset_hash)
    _, cases = load_cases(dataset_manifest, split)
    dataset_dir = dataset_manifest.parent
    library = build_native(reference_root, output.parent / "native")
    if (
        split in ("validation", "holdout")
        and config["freeze"].get("native_library_sha256") != sha256(library)
    ):
        raise ValueError("native library changed after configuration freeze")
    sys.path[:0] = [str(reference_root), str(reference_root / "src")]
    from tools.presence_dwell import NativeDwell

    repetitions = int(config["timing_repetitions"])
    rows: list[dict[str, Any]] = []
    initialization_wall_start = time.perf_counter_ns()
    with contextlib.ExitStack() as stack:
        candidate_detectors = {
            edge: stack.enter_context(
                NativeDwell(library, DECISION_RATE_HZ, edge, int(config["screen_bins"]))
            )
            for edge in ("lower", "upper")
        }
        baseline_detectors = {
            (rate, edge): stack.enter_context(
                NativeDwell(library, rate, edge, int(config["baseline_screen_bins"][str(rate)]))
            )
            for rate in (2_500_000, 5_000_000)
            for edge in ("lower", "upper")
        }
        decimators: dict[int, NativeDecimator] = {}
        for rate in SUPPORTED_SOURCE_RATES[1:]:
            decimator = NativeDecimator(
                library, rate, rate * DWELL_MS // 1000, config
            )
            decimators[rate] = decimator
            stack.callback(decimator.close)

        initialization_wall_ms = (time.perf_counter_ns() - initialization_wall_start) / 1e6
        warmup_wall_start = time.perf_counter_ns()
        for edge, detector in candidate_detectors.items():
            del edge
            detector.run(
                np.zeros((DECISION_RATE_HZ * DWELL_MS // 1000, 2), dtype="<i2"),
                maximum=1,
                seeded=False,
            )
        for (rate, edge), detector in baseline_detectors.items():
            del edge
            detector.run(
                np.zeros((rate * DWELL_MS // 1000, 2), dtype="<i2"),
                maximum=1,
                seeded=False,
            )
        for rate, decimator in decimators.items():
            decimator.run(np.zeros((rate * DWELL_MS // 1000, 2), dtype="<i2"))
        warmup_wall_ms = (time.perf_counter_ns() - warmup_wall_start) / 1e6

        for case in cases:
            raw = load_raw(dataset_dir, case)
            raw_data_sha256 = hashlib.sha256(raw.tobytes()).hexdigest()
            raw_file = dataset_dir / case["raw_npy"]["path"]
            raw_file_sha256 = sha256(raw_file)
            edge = case["edge"]
            rate = int(case["rate_hz"])
            geometry = filter_geometry(rate, config)
            for receiver in range(2):
                candidate_detections: list[Detection] = []
                candidate_cpu: list[float] = []
                candidate_wall: list[float] = []
                for _ in range(repetitions):
                    cpu_start, wall_start = time.thread_time_ns(), time.perf_counter_ns()
                    one_rx = np.ascontiguousarray(raw[:, receiver, :])
                    decision = one_rx if rate == DECISION_RATE_HZ else decimators[rate].run(one_rx)
                    candidate_result = candidate_detectors[edge].run(
                        decision, maximum=1, seeded=False
                    )
                    candidate_cpu.append((time.thread_time_ns() - cpu_start) / 1e6)
                    candidate_wall.append((time.perf_counter_ns() - wall_start) / 1e6)
                    candidate_detections.append(
                        detection_from_result(
                            candidate_result,
                            source_rate_hz=rate,
                            analysis_rate_hz=DECISION_RATE_HZ,
                            group_delay_source_samples=geometry[
                                "group_delay_source_samples"
                            ],
                            complete_support_decision_sample=geometry[
                                "complete_support_decision_sample"
                            ],
                            exact_threshold=float(config["exact_threshold"]),
                            margin_threshold=float(config["margin_threshold"]),
                        )
                    )
                if any(value != candidate_detections[0] for value in candidate_detections[1:]):
                    raise ValueError("candidate detector output changed across timing repetitions")
                candidate_detection = candidate_detections[0]
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "session_id": case["session_id"],
                        "visit_index": case["visit_index"],
                        "rate_hz": rate,
                        "edge": edge,
                        "receiver": receiver,
                        "truth_kind": case.get("truth", {}).get("kind"),
                        "truth_receiver": (
                            case.get("truth", {}).get("receivers", [None, None])[receiver]
                        ),
                        "method": "decision_2p5m",
                        "filter_geometry": geometry,
                        "detection": asdict(candidate_detection),
                        "timing_cpu_ms": candidate_cpu,
                        "timing_wall_ms": candidate_wall,
                        "timing_cpu_ms_mean": statistics.fmean(candidate_cpu),
                        "timing_wall_ms_mean": statistics.fmean(candidate_wall),
                        "input_array_sha256": raw_data_sha256,
                        "input_file_sha256": raw_file_sha256,
                    }
                )
                if rate not in (2_500_000, 5_000_000):
                    continue
                baseline_detections: list[Detection] = []
                baseline_cpu: list[float] = []
                baseline_wall: list[float] = []
                for _ in range(repetitions):
                    cpu_start, wall_start = time.thread_time_ns(), time.perf_counter_ns()
                    one_rx = np.ascontiguousarray(raw[:, receiver, :])
                    baseline_result = baseline_detectors[(rate, edge)].run(
                        one_rx, maximum=1, seeded=False
                    )
                    baseline_cpu.append((time.thread_time_ns() - cpu_start) / 1e6)
                    baseline_wall.append((time.perf_counter_ns() - wall_start) / 1e6)
                    baseline_detections.append(
                        detection_from_result(
                            baseline_result,
                            source_rate_hz=rate,
                            analysis_rate_hz=rate,
                            group_delay_source_samples=0,
                            complete_support_decision_sample=0,
                            exact_threshold=float(config["exact_threshold"]),
                            margin_threshold=float(config["margin_threshold"]),
                        )
                    )
                if any(value != baseline_detections[0] for value in baseline_detections[1:]):
                    raise ValueError("baseline detector output changed across timing repetitions")
                baseline_detection = baseline_detections[0]
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "session_id": case["session_id"],
                        "visit_index": case["visit_index"],
                        "rate_hz": rate,
                        "edge": edge,
                        "receiver": receiver,
                        "truth_kind": case.get("truth", {}).get("kind"),
                        "truth_receiver": (
                            case.get("truth", {}).get("receivers", [None, None])[receiver]
                        ),
                        "method": "native_rate",
                        "filter_geometry": filter_geometry(rate, config)
                        if rate == DECISION_RATE_HZ
                        else None,
                        "detection": asdict(baseline_detection),
                        "timing_cpu_ms": baseline_cpu,
                        "timing_wall_ms": baseline_wall,
                        "timing_cpu_ms_mean": statistics.fmean(baseline_cpu),
                        "timing_wall_ms_mean": statistics.fmean(baseline_wall),
                        "input_array_sha256": raw_data_sha256,
                        "input_file_sha256": raw_file_sha256,
                    }
                )
            if hashlib.sha256(raw.tobytes()).hexdigest() != raw_data_sha256:
                raise ValueError("native evaluation mutated the loaded source array")
            if sha256(raw_file) != raw_file_sha256:
                raise ValueError("source file changed during evaluation")
    receipt = {
        "schema": "org.leo.research.ds5-decision-band-evaluation/v1",
        "created_unix_ns": time.time_ns(),
        "split": split,
        "dataset_manifest": str(dataset_manifest.resolve()),
        "dataset_manifest_sha256": dataset_hash,
        "config": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "native_library": str(library.resolve()),
        "native_library_sha256": sha256(library),
        "native_build_profile": json.loads(
            library.with_name(library.name + ".build.json").read_text()
        )["command"],
        "server": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "load_average_at_receipt": os.getloadavg(),
        },
        "initialization_wall_ms": initialization_wall_ms,
        "warmup_wall_ms": warmup_wall_ms,
        "timing_scope": (
            "thread CPU and monotonic wall include channel materialization, FIR, "
            "boundary masking, screening, and one blind native confirmation"
        ),
        "timing_repetitions": repetitions,
        "rows": rows,
        "summary": _summarize(rows, config),
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def default_config() -> dict[str, Any]:
    return {
        "schema": "org.leo.research.ds5-decision-band-config/v1",
        "stage": "development",
        "decision_rate_hz": DECISION_RATE_HZ,
        "filter_kind": "direct_causal_q15_kaiser",
        "filter_passband_edge_hz": 1_000_000,
        "filter_beta": 8.6,
        "filter_span_outputs": 40,
        "screen_bins": 512,
        "baseline_screen_bins": {"2500000": 512, "5000000": 512},
        "confirmations": 1,
        "seeded": False,
        "exact_threshold": 0.175,
        "margin_threshold": 0.025,
        "matching": {
            "maximum_cfo_error_hz": 8000,
            "maximum_circular_timing_error_us": 2,
            "timing_period_hz": 750,
        },
        "timing_repetitions": 3,
        "warmup_repetitions": 1,
        "scope": {
            "recall_rates_hz": [2_500_000, 5_000_000],
            "descriptive_only_rates_hz": [7_500_000, 10_000_000],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init-config")
    init.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("evaluate")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument(
        "--split", choices=("dev", "validation", "holdout", "control"), required=True
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--reference-root", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init-config":
        args.output.write_text(json.dumps(default_config(), indent=2, sort_keys=True) + "\n")
        return
    evaluate(
        dataset_manifest=args.dataset,
        split=args.split,
        config_path=args.config,
        reference_root=args.reference_root,
        output=args.output,
    )


if __name__ == "__main__":
    main()
