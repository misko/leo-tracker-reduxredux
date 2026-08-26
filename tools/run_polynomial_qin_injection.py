#!/usr/bin/env python3
"""Run the frozen exact-Qin polynomial injection on three hard-null spans."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.doppler_dataset_policy import (  # noqa: E402
    CaptureDisposition,
    authorize_manifest_files,
    finalize_capture_dispositions,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from leo.analysis.research.polynomial_injection import (  # noqa: E402
    CubicEstimate,
    FrameCfoEvidence,
    RateEstimateRow,
    evaluate_exact_qin_frames,
    fit_full_span_cubic,
    fixed_history_rate_estimates,
    inject_exact_qin,
)
from leo.analysis.research.polynomial_injection_protocol import (  # noqa: E402
    BackgroundSpan,
    InjectionScenario,
    load_polynomial_injection_protocol,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402

DEFAULT_POLICY = Path("config/analysis/doppler-experiment-dataset-policy-v1.json")
DEFAULT_PROTOCOL = Path("config/analysis/polynomial-phase-injection-protocol-v1.json")
DEFAULT_OUTPUT = Path("reports/figures/2026_08_25_polynomial_qin_injection")
DEFAULT_REPORT = Path("reports/2026_08_25_polynomial_qin_injection_results.md")
PREREGISTRATION_COMMIT = "5970769a34e40fde5d64ddf57b4be7fe2ac14d93"


@dataclass(frozen=True, slots=True)
class VerifiedBackground:
    binding: BackgroundSpan
    samples: np.ndarray
    span_sha256: str
    background_power: float
    compressed_bytes_read: int
    uncompressed_bytes_verified: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--maximum-scenarios",
        type=int,
        help="noncanonical implementation smoke only; canonical output refuses this option",
    )
    parser.add_argument(
        "--postprocess-existing",
        action="store_true",
        help=(
            "regenerate report figures from already sealed canonical row artifacts without IQ reads"
        ),
    )
    return parser.parse_args()


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _canonical_complex_sha256(values: np.ndarray) -> str:
    payload = np.asarray(values, dtype="<c8").tobytes(order="C")
    return _sha256_bytes(payload)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _git_head(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _read_verified_background(
    background: BackgroundSpan,
    *,
    policy: Any,
) -> VerifiedBackground:
    authorize_manifest_files(
        policy,
        experiment_role="polynomial_injection",
        session_id=background.session_id,
        analysis_run_id=background.analysis_run_id,
        recording_manifest_path=background.recording_manifest_path,
        analysis_manifest_path=background.analysis_manifest_path,
    )
    manifest_value = json.loads(background.recording_manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest_value, dict)
        or manifest_value.get("session_id") != background.session_id
    ):
        raise ValueError(f"recording manifest identity differs: {background.session_id}")
    streams = manifest_value.get("streams")
    if not isinstance(streams, list):
        raise ValueError(f"recording manifest has no stream list: {background.session_id}")
    matches = [
        item
        for item in streams
        if isinstance(item, dict) and item.get("stream_id") == background.stream_id
    ]
    if len(matches) != 1:
        raise ValueError(f"recording stream binding is ambiguous: {background.session_id}")
    stream = matches[0]
    radio = stream.get("radio")
    applied = stream.get("applied_settings")
    continuity = stream.get("continuity")
    chunks = stream.get("chunks")
    if not all(isinstance(item, dict) for item in (radio, applied, continuity)):
        raise ValueError(f"recording stream metadata is incomplete: {background.session_id}")
    assert isinstance(radio, dict) and isinstance(applied, dict) and isinstance(continuity, dict)
    if (
        radio.get("radio_id") != background.radio_id
        or radio.get("serial") != background.radio_serial
    ):
        raise ValueError(f"recording radio binding differs: {background.session_id}")
    if applied.get("sample_rate_hz") != background.sample_rate_hz:
        raise ValueError(f"recording sample rate differs: {background.session_id}")
    receiver_ids = applied.get("receiver_ids")
    if not isinstance(receiver_ids, list) or background.receiver_id not in receiver_ids:
        raise ValueError(f"recording receiver binding differs: {background.session_id}")
    lossless = (
        continuity.get("sample_loss_observable") is True
        and continuity.get("gap_count") == 0
        and continuity.get("missing_sample_count") == 0
        and continuity.get("overflow_count") == 0
        and continuity.get("enqueue_failure_count") == 0
        and continuity.get("clipped_sample_count") == 0
        and continuity.get("constant_iq_refill_count") == 0
        and continuity.get("terminal_rejected_gap_count") == 0
        and continuity.get("terminal_rejected_missing_sample_count") == 0
        and continuity.get("terminal_rejected_overflow_count") == 0
        and continuity.get("segment_count") == 1
        and continuity.get("observed_sample_count") == stream.get("captured_sample_count")
        and continuity.get("device_span_sample_count") == stream.get("captured_sample_count")
    )
    if not lossless or stream.get("state") != "complete":
        raise ValueError(f"recording is not lossless and complete: {background.session_id}")
    if not isinstance(chunks, list):
        raise ValueError(f"recording stream has no chunk list: {background.session_id}")
    chunk_matches = [
        item
        for item in chunks
        if isinstance(item, dict) and item.get("chunk_index") == background.chunk.chunk_index
    ]
    if len(chunk_matches) != 1:
        raise ValueError(f"recording chunk binding is ambiguous: {background.session_id}")
    chunk = chunk_matches[0]
    expected_chunk = (
        background.chunk.sample_start,
        background.chunk.sample_count,
        background.chunk.relative_path,
        background.chunk.compressed_sha256,
        background.chunk.uncompressed_sha256,
        "ci16_le",
        "sample_receiver_iq",
    )
    actual_chunk = (
        chunk.get("sample_start"),
        chunk.get("sample_count"),
        chunk.get("relative_path"),
        chunk.get("compressed_sha256"),
        chunk.get("uncompressed_sha256"),
        chunk.get("sample_format"),
        chunk.get("sample_layout"),
    )
    if actual_chunk != expected_chunk:
        raise ValueError(f"recording chunk fields differ: {background.session_id}")
    capture_root = background.recording_manifest_path.parent.resolve()
    chunk_path = (capture_root / background.chunk.relative_path).resolve()
    if not chunk_path.is_relative_to(capture_root):
        raise ValueError("chunk path escapes its exact recording root")
    compressed = chunk_path.read_bytes()
    if _sha256_bytes(compressed) != background.chunk.compressed_sha256:
        raise ValueError(f"compressed chunk digest differs: {background.session_id}")
    compressed_bytes = chunk.get("compressed_bytes")
    uncompressed_bytes = chunk.get("uncompressed_bytes")
    if not isinstance(compressed_bytes, int) or len(compressed) != compressed_bytes:
        raise ValueError(f"compressed chunk size differs: {background.session_id}")
    if not isinstance(uncompressed_bytes, int) or uncompressed_bytes <= 0:
        raise ValueError(f"uncompressed chunk size is invalid: {background.session_id}")
    payload = zstd.ZstdDecompressor().decompress(compressed, max_output_size=uncompressed_bytes)
    if len(payload) != uncompressed_bytes:
        raise ValueError(f"uncompressed chunk size differs: {background.session_id}")
    if _sha256_bytes(payload) != background.chunk.uncompressed_sha256:
        raise ValueError(f"uncompressed chunk digest differs: {background.session_id}")
    receiver_count = len(receiver_ids)
    raw = np.frombuffer(payload, dtype="<i2")
    expected_values = background.chunk.sample_count * receiver_count * 2
    if raw.size != expected_values:
        raise ValueError(f"CI16 chunk geometry differs: {background.session_id}")
    cube = raw.reshape(background.chunk.sample_count, receiver_count, 2)
    receiver_column = receiver_ids.index(background.receiver_id)
    offset = background.sample_start - background.chunk.sample_start
    selected = cube[offset : offset + background.sample_count, receiver_column]
    if selected.shape != (background.sample_count, 2):
        raise ValueError(f"frozen background span is incomplete: {background.session_id}")
    samples = np.asarray(
        (selected[:, 0].astype(np.float32) + 1j * selected[:, 1].astype(np.float32)) / 32_768.0,
        dtype=np.complex64,
    )
    power = float(np.mean(np.abs(samples.astype(np.complex128)) ** 2))
    if not math.isfinite(power) or power <= np.finfo(float).tiny:
        raise ValueError(f"frozen background has no finite power: {background.session_id}")
    return VerifiedBackground(
        binding=background,
        samples=samples,
        span_sha256=_canonical_complex_sha256(samples),
        background_power=power,
        compressed_bytes_read=len(compressed),
        uncompressed_bytes_verified=len(payload),
    )


def _factor_fields(scenario: InjectionScenario) -> dict[str, object]:
    return {
        "background_session_id": scenario.background_session_id,
        "seed": scenario.seed,
        "truth_rate_hz_s": scenario.rate_hz_s,
        "truth_acceleration_hz_s2": scenario.acceleration_hz_s2,
        "truth_jerk_hz_s3": scenario.jerk_hz_s3,
        "snr_db": scenario.snr_db,
        "frame_occupancy": scenario.frame_occupancy,
        "alias_change_hz": scenario.alias_change_hz,
        "cfo_step_hz": scenario.cfo_step_hz,
        "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
    }


def _frame_row(item: FrameCfoEvidence, scenario: InjectionScenario) -> dict[str, object]:
    row = asdict(item)
    row["training_rejection_reasons"] = ";".join(item.training_rejection_reasons)
    row.update(_factor_fields(scenario))
    row["even_cfo_error_receiver_hz"] = (
        None
        if item.even_canonical_cfo_hz is None
        else item.even_canonical_cfo_hz - item.receiver_truth_cfo_hz
    )
    row["odd_cfo_error_receiver_hz"] = (
        None
        if item.odd_canonical_cfo_hz is None
        else item.odd_canonical_cfo_hz - item.receiver_truth_cfo_hz
    )
    return row


def _rate_row(item: RateEstimateRow, scenario: InjectionScenario) -> dict[str, object]:
    row = asdict(item)
    row.update(_factor_fields(scenario))
    return row


def _cubic_row(item: CubicEstimate, scenario: InjectionScenario) -> dict[str, object]:
    row = asdict(item)
    row.update(_factor_fields(scenario))
    for coordinate in ("receiver", "physical"):
        for derivative, estimate, truth, sigma, threshold in (
            (
                "rate",
                item.rate_hz_s,
                getattr(item, f"{coordinate}_rate_truth_hz_s"),
                item.rate_sigma_hz_s,
                500.0,
            ),
            (
                "acceleration",
                item.acceleration_hz_s2,
                getattr(item, f"{coordinate}_acceleration_truth_hz_s2"),
                item.acceleration_sigma_hz_s2,
                500.0,
            ),
            (
                "jerk",
                item.jerk_hz_s3,
                getattr(item, f"{coordinate}_jerk_truth_hz_s3"),
                item.jerk_sigma_hz_s3,
                500.0,
            ),
        ):
            error = None if estimate is None else estimate - truth
            row[f"{coordinate}_{derivative}_error"] = error
            row[f"{coordinate}_{derivative}_covered_95"] = (
                None if error is None or sigma is None else abs(error) <= 1.96 * sigma
            )
            row[f"{coordinate}_{derivative}_failure"] = (
                None if error is None else abs(error) > threshold
            )
    return row


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty evidence table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    if any(set(row) != set(fields) for row in rows):
        raise ValueError(f"evidence rows have inconsistent fields: {path.name}")
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as source:
        return [dict(row) for row in csv.DictReader(source)]


def _metric(errors: np.ndarray, coverage: np.ndarray, failures: np.ndarray) -> dict[str, object]:
    if errors.size == 0:
        return {
            "count": 0,
            "bias": None,
            "mse": None,
            "rmse": None,
            "median_absolute_error": None,
            "failure_rate": None,
            "coverage_95": None,
        }
    return {
        "count": int(errors.size),
        "bias": float(np.mean(errors)),
        "mse": float(np.mean(errors**2)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "median_absolute_error": float(np.median(np.abs(errors))),
        "failure_rate": float(np.mean(failures)),
        "coverage_95": float(np.mean(coverage)),
    }


def _rate_scenario_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    complete_groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    all_groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        scenario_id = str(row["scenario_id"])
        estimator = str(row["estimator"])
        all_groups[(scenario_id, estimator)].append(row)
        if row["status"] != "complete":
            continue
        phase = str(row["step_phase"])
        complete_groups[(scenario_id, estimator, phase)].append(row)
    groups: dict[tuple[str, str, str], tuple[list[dict[str, object]], dict[str, object]]] = {}
    for (scenario_id, estimator), all_rows in all_groups.items():
        complete = [row for row in all_rows if row["status"] == "complete"]
        groups[(scenario_id, estimator, "all_complete")] = (complete, all_rows[0])
    for key, complete in complete_groups.items():
        groups[key] = (complete, complete[0])
    output: list[dict[str, object]] = []
    for (scenario_id, estimator, scope), (selected, base) in sorted(groups.items()):
        row: dict[str, object] = {
            "scenario_id": scenario_id,
            "estimator": estimator,
            "scope": scope,
            "estimator_no_result": len(selected) == 0,
            **{name: base[name] for name in _factor_fields_key_order()},
        }
        for coordinate in ("receiver", "physical"):
            errors = np.asarray([float(item[f"{coordinate}_error_hz_s"]) for item in selected])
            coverage = np.asarray(
                [bool(item[f"{coordinate}_covered_95"]) for item in selected], dtype=bool
            )
            failures = np.asarray(
                [bool(item[f"{coordinate}_failure"]) for item in selected], dtype=bool
            )
            for name, value in _metric(errors, coverage, failures).items():
                row[f"{coordinate}_{name}"] = value
        output.append(row)
    return output


def _factor_fields_key_order() -> tuple[str, ...]:
    return (
        "background_session_id",
        "seed",
        "truth_rate_hz_s",
        "truth_acceleration_hz_s2",
        "truth_jerk_hz_s3",
        "snr_db",
        "frame_occupancy",
        "alias_change_hz",
        "cfo_step_hz",
        "sample_clock_offset_ppm",
    )


def _aggregate_scenario_metrics(
    rows: list[dict[str, object]],
    *,
    selector: Any,
    scope_name: str,
    stratum: str = "summary",
    stratum_value: object = "",
) -> list[dict[str, object]]:
    selected = [row for row in rows if row["scope"] == "all_complete" and selector(row)]
    methods = sorted({str(row["estimator"]) for row in selected})
    output = []
    for method in methods:
        method_rows = [row for row in selected if row["estimator"] == method]
        evaluable_rows = [row for row in method_rows if int(row["receiver_count"]) > 0]
        aggregate: dict[str, object] = {
            "scope": scope_name,
            "stratum": stratum,
            "stratum_value": stratum_value,
            "estimator": method,
            "scenario_count": len(method_rows),
            "evaluable_scenario_count": len(evaluable_rows),
            "no_result_scenario_count": len(method_rows) - len(evaluable_rows),
            "no_result_scenario_rate": (
                (len(method_rows) - len(evaluable_rows)) / len(method_rows) if method_rows else None
            ),
            "background_count": len({row["background_session_id"] for row in method_rows}),
            "evaluable_background_count": len(
                {row["background_session_id"] for row in evaluable_rows}
            ),
        }
        for coordinate in ("receiver", "physical"):
            counts = np.asarray([float(row[f"{coordinate}_count"]) for row in evaluable_rows])
            aggregate[f"{coordinate}_frame_count"] = int(np.sum(counts))
            for metric in ("bias", "mse", "median_absolute_error", "failure_rate", "coverage_95"):
                values = np.asarray(
                    [float(row[f"{coordinate}_{metric}"]) for row in evaluable_rows],
                    dtype=float,
                )
                aggregate[f"{coordinate}_{metric}"] = (
                    float(np.mean(values)) if values.size else None
                )
            mse = aggregate[f"{coordinate}_mse"]
            aggregate[f"{coordinate}_rmse"] = None if mse is None else math.sqrt(float(mse))
        output.append(aggregate)
    return output


def _cubic_metrics(
    rows: list[dict[str, object]],
    *,
    selector: Any,
    scope_name: str,
    stratum: str = "summary",
    stratum_value: object = "",
) -> list[dict[str, object]]:
    eligible = [row for row in rows if selector(row)]
    selected = [row for row in eligible if row["status"] == "complete"]
    output = []
    for coordinate in ("receiver", "physical"):
        for derivative in ("rate", "acceleration", "jerk"):
            errors = np.asarray(
                [float(row[f"{coordinate}_{derivative}_error"]) for row in selected], dtype=float
            )
            coverage = np.asarray(
                [bool(row[f"{coordinate}_{derivative}_covered_95"]) for row in selected],
                dtype=bool,
            )
            failures = np.asarray(
                [bool(row[f"{coordinate}_{derivative}_failure"]) for row in selected],
                dtype=bool,
            )
            output.append(
                {
                    "scope": scope_name,
                    "stratum": stratum,
                    "stratum_value": stratum_value,
                    "coordinate": coordinate,
                    "derivative": derivative,
                    "scenario_count": len(eligible),
                    "evaluable_scenario_count": len(selected),
                    "no_result_scenario_count": len(eligible) - len(selected),
                    "no_result_scenario_rate": (
                        (len(eligible) - len(selected)) / len(eligible) if eligible else None
                    ),
                    "background_count": len({row["background_session_id"] for row in eligible}),
                    "evaluable_background_count": len(
                        {row["background_session_id"] for row in selected}
                    ),
                    **_metric(errors, coverage, failures),
                }
            )
    return output


def _frame_summaries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["scenario_id"])].append(row)
    output = []
    for scenario_id, selected in sorted(groups.items()):
        base = selected[0]
        occupied = [row for row in selected if bool(row["occupied"])]
        empty = [row for row in selected if not bool(row["occupied"])]
        supported = [row for row in selected if bool(row["training_supported"])]
        supported_occupied = [row for row in occupied if bool(row["training_supported"])]
        false_support = [row for row in empty if bool(row["training_supported"])]
        even_errors = np.asarray(
            [
                float(row["even_cfo_error_receiver_hz"])
                for row in supported_occupied
                if row["even_cfo_error_receiver_hz"] is not None
            ],
            dtype=float,
        )
        odd_errors = np.asarray(
            [
                float(row["odd_cfo_error_receiver_hz"])
                for row in supported_occupied
                if row["odd_cfo_error_receiver_hz"] is not None
            ],
            dtype=float,
        )
        output.append(
            {
                "scenario_id": scenario_id,
                **{name: base[name] for name in _factor_fields_key_order()},
                "opportunity_count": len(selected),
                "occupied_opportunity_count": len(occupied),
                "training_supported_count": len(supported),
                "supported_occupied_count": len(supported_occupied),
                "supported_unoccupied_count": len(false_support),
                "occupied_support_rate": len(supported_occupied) / max(len(occupied), 1),
                "unoccupied_false_support_rate": len(false_support) / max(len(empty), 1),
                "even_control_wins_occupied": sum(
                    row["even_profile_margin"] is not None
                    and float(row["even_profile_margin"]) <= 0.0
                    for row in occupied
                ),
                "odd_control_wins_occupied": sum(
                    row["odd_profile_margin"] is not None
                    and float(row["odd_profile_margin"]) <= 0.0
                    for row in occupied
                ),
                "even_cfo_rmse_hz": (
                    float(np.sqrt(np.mean(even_errors**2))) if even_errors.size else None
                ),
                "odd_cfo_rmse_hz": (
                    float(np.sqrt(np.mean(odd_errors**2))) if odd_errors.size else None
                ),
            }
        )
    return output


def _promotion(
    rate_aggregate: list[dict[str, object]],
    cubic_aggregate: list[dict[str, object]],
    config: dict[str, Any],
) -> dict[str, object]:
    gates = config["promotion_gates"]
    fixed = next(
        (
            row
            for row in rate_aggregate
            if row["scope"] == "promotion" and row["estimator"] == "fixed_500ms_linear"
        ),
        None,
    )
    acceleration = next(
        (
            row
            for row in cubic_aggregate
            if row["scope"] == "promotion"
            and row["coordinate"] == "receiver"
            and row["derivative"] == "acceleration"
        ),
        None,
    )
    jerk = next(
        (
            row
            for row in cubic_aggregate
            if row["scope"] == "promotion"
            and row["coordinate"] == "receiver"
            and row["derivative"] == "jerk"
        ),
        None,
    )
    fixed_rmse = None if fixed is None else fixed["receiver_rmse"]
    fixed_failure = None if fixed is None else fixed["receiver_failure_rate"]
    fixed_coverage = None if fixed is None else fixed["receiver_coverage_95"]
    acceleration_rmse = None if acceleration is None else acceleration["rmse"]
    jerk_rmse = None if jerk is None else jerk["rmse"]
    checks = {
        "all_three_backgrounds": fixed is not None
        and int(fixed["evaluable_background_count"]) == 3,
        "fixed_500ms_rate_rmse": fixed_rmse is not None
        and float(fixed_rmse) <= float(gates["fixed_500ms_rate_rmse_hz_s_max"]),
        "fixed_500ms_rate_failure_rate": fixed_failure is not None
        and float(fixed_failure) <= float(gates["fixed_500ms_rate_failure_rate_max"]),
        "fixed_500ms_rate_coverage_lower": fixed_coverage is not None
        and float(fixed_coverage) >= float(gates["fixed_500ms_rate_coverage_min"]),
        "fixed_500ms_rate_coverage_upper": fixed_coverage is not None
        and float(fixed_coverage) <= float(gates["fixed_500ms_rate_coverage_max"]),
        "offline_cubic_acceleration_rmse": acceleration_rmse is not None
        and float(acceleration_rmse) <= float(gates["offline_cubic_acceleration_rmse_hz_s2_max"]),
        "offline_cubic_jerk_rmse": jerk_rmse is not None
        and float(jerk_rmse) <= float(gates["offline_cubic_jerk_rmse_hz_s3_max"]),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "fixed_500ms": fixed,
        "offline_cubic_acceleration": acceleration,
        "offline_cubic_jerk": jerk,
    }


def _plot_rate(rate_aggregate: list[dict[str, object]], path: Path) -> None:
    selected = [row for row in rate_aggregate if row["scope"] == "no_step"]
    labels = ["20 ms", "125 ms", "500 ms"]
    methods = ["causal_20ms_linear", "fixed_125ms_linear", "fixed_500ms_linear"]
    by_method = {str(row["estimator"]): row for row in selected}
    figure = Figure(figsize=(15.5, 4.8), constrained_layout=True)
    axes = figure.subplots(1, 3)
    x = np.arange(len(methods))
    axes[0].bar(
        x,
        [
            np.nan
            if by_method[item]["receiver_rmse"] is None
            else float(by_method[item]["receiver_rmse"])
            for item in methods
        ],
        color=["#d97706", "#6b7280", "#2563eb"],
    )
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Receiver-clock rate RMSE (Hz/s)")
    axes[0].set_title("A · Known-truth rate error, no-step scenarios", loc="left")
    axes[1].bar(
        x,
        [
            np.nan
            if by_method[item]["receiver_coverage_95"] is None
            else float(by_method[item]["receiver_coverage_95"])
            for item in methods
        ],
        color=["#d97706", "#6b7280", "#2563eb"],
    )
    axes[1].axhline(0.95, color="black", linestyle="--", linewidth=1, label="nominal 95%")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylim(0.0, 1.03)
    axes[1].set_ylabel("Nominal 95% interval coverage")
    axes[1].set_title("B · Conditional covariance calibration", loc="left")
    axes[1].legend()
    axes[2].bar(
        x,
        [float(by_method[item]["no_result_scenario_rate"]) for item in methods],
        color=["#d97706", "#6b7280", "#2563eb"],
    )
    axes[2].set_xticks(x, labels)
    axes[2].set_ylim(0.0, 1.03)
    axes[2].set_ylabel("No-result scenario fraction")
    axes[2].set_title("C · Availability across six no-step rows", loc="left")
    for axis in axes:
        axis.grid(alpha=0.25, axis="y")
    figure.savefig(path, dpi=170)


def _plot_scenario_recovery(
    frame_summary: list[dict[str, object]],
    rate_scenarios: list[dict[str, object]],
    cubic_rows: list[dict[str, object]],
    path: Path,
) -> None:
    scenarios = sorted(frame_summary, key=lambda row: str(row["scenario_id"]))
    scenario_ids = [str(row["scenario_id"]) for row in scenarios]
    snr_colors = {-32.0: "#9ca3af", -24.0: "#d97706", -16.0: "#2563eb"}
    support = [float(row["occupied_support_rate"]) for row in scenarios]
    rate_lookup = {
        (str(row["scenario_id"]), str(row["estimator"])): int(row["receiver_count"])
        for row in rate_scenarios
        if row["scope"] == "all_complete"
    }
    cubic_lookup = {str(row["scenario_id"]): row for row in cubic_rows}
    row_labels = ("20 ms", "125 ms", "500 ms", "offline cubic")
    methods = ("causal_20ms_linear", "fixed_125ms_linear", "fixed_500ms_linear")
    availability = np.zeros((4, len(scenarios)), dtype=float)
    cell_text: list[list[str]] = [["—" for _ in scenarios] for _ in row_labels]
    for column, scenario_id in enumerate(scenario_ids):
        for row_index, method in enumerate(methods):
            count = rate_lookup.get((scenario_id, method), 0)
            availability[row_index, column] = float(count > 0)
            cell_text[row_index][column] = str(count) if count else "—"
        cubic = cubic_lookup[scenario_id]
        complete = cubic["status"] == "complete"
        availability[3, column] = float(complete)
        cell_text[3][column] = "fit" if complete else "—"

    figure = Figure(figsize=(15.5, 7.2), constrained_layout=True)
    axes = figure.subplots(2, 1, height_ratios=(1.15, 1.0))
    x = np.arange(len(scenarios))
    axes[0].bar(
        x,
        support,
        color=[snr_colors[float(row["snr_db"])] for row in scenarios],
    )
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_ylabel("Occupied-frame support fraction")
    axes[0].set_title("A · Public even-Qin gate by frozen scenario", loc="left")
    for snr, color in snr_colors.items():
        axes[0].plot(
            [],
            [],
            color=color,
            marker="s",
            linestyle="none",
            markersize=9,
            label=f"{snr:.0f} dB",
        )
    axes[0].legend(ncols=3, loc="upper left")
    axes[0].grid(alpha=0.25, axis="y")
    axes[0].set_xticks(x, scenario_ids)

    axes[1].imshow(availability, aspect="auto", cmap="RdYlGn", vmin=0.0, vmax=1.0)
    axes[1].set_xticks(x, scenario_ids)
    axes[1].set_yticks(np.arange(len(row_labels)), row_labels)
    axes[1].set_title(
        "B · Complete rate endpoints (counts) and cubic availability; dash means no result",
        loc="left",
    )
    for row_index in range(len(row_labels)):
        for column in range(len(scenarios)):
            axes[1].text(
                column,
                row_index,
                cell_text[row_index][column],
                ha="center",
                va="center",
                fontsize=8,
                color="black",
            )
    figure.savefig(path, dpi=170)


def _plot_frame_support(frame_summary: list[dict[str, object]], path: Path) -> None:
    snrs = sorted({float(row["snr_db"]) for row in frame_summary})
    support = []
    false = []
    even_control = []
    odd_control = []
    for snr in snrs:
        selected = [row for row in frame_summary if float(row["snr_db"]) == snr]
        support.append(float(np.mean([float(row["occupied_support_rate"]) for row in selected])))
        false.append(
            float(np.mean([float(row["unoccupied_false_support_rate"]) for row in selected]))
        )
        occupied = sum(int(row["occupied_opportunity_count"]) for row in selected)
        even_control.append(
            sum(int(row["even_control_wins_occupied"]) for row in selected) / occupied
        )
        odd_control.append(
            sum(int(row["odd_control_wins_occupied"]) for row in selected) / occupied
        )
    figure = Figure(figsize=(11.5, 4.8), constrained_layout=True)
    axes = figure.subplots(1, 2)
    axes[0].plot(snrs, support, marker="o", label="occupied frame supported")
    axes[0].plot(snrs, false, marker="s", label="unoccupied false support")
    axes[0].set(xlabel="Injected raw frame SNR (dB)", ylabel="Fraction")
    axes[0].set_title("A · Even-Qin training gate", loc="left")
    axes[0].legend()
    axes[1].plot(snrs, even_control, marker="o", label="even rolled ≥ exact")
    axes[1].plot(snrs, odd_control, marker="s", label="odd rolled ≥ exact")
    axes[1].set(xlabel="Injected raw frame SNR (dB)", ylabel="Occupied-frame fraction")
    axes[1].set_title("B · Exact versus rolled-Qin controls", loc="left")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.set_ylim(bottom=0.0)
    figure.savefig(path, dpi=170)


def _plot_cubic(cubic_rows: list[dict[str, object]], path: Path) -> None:
    selected = [
        row
        for row in cubic_rows
        if row["status"] == "complete" and float(row["cfo_step_hz"]) == 0.0
    ]
    figure = Figure(figsize=(11.5, 4.8), constrained_layout=True)
    axes = figure.subplots(1, 2)
    if not selected:
        for axis in axes:
            axis.text(0.5, 0.5, "No complete cubic estimates", ha="center", va="center")
            axis.set_axis_off()
        figure.savefig(path, dpi=170)
        return
    for axis, derivative, unit in (
        (axes[0], "acceleration", "Hz/s²"),
        (axes[1], "jerk", "Hz/s³"),
    ):
        truth = np.asarray(
            [
                float(
                    row[
                        f"receiver_{derivative}_truth_hz_s2"
                        if derivative == "acceleration"
                        else f"receiver_{derivative}_truth_hz_s3"
                    ]
                )
                for row in selected
            ]
        )
        estimate_field = "acceleration_hz_s2" if derivative == "acceleration" else "jerk_hz_s3"
        estimate = np.asarray([float(row[estimate_field]) for row in selected])
        axis.scatter(
            truth, estimate, c=[float(row["snr_db"]) for row in selected], cmap="viridis", s=55
        )
        low = min(float(np.min(truth)), float(np.min(estimate)))
        high = max(float(np.max(truth)), float(np.max(estimate)))
        axis.plot([low, high], [low, high], color="black", linestyle="--", linewidth=1)
        axis.set(xlabel=f"Receiver truth ({unit})", ylabel=f"Estimated ({unit})")
        axis.set_title(
            f"{'A' if derivative == 'acceleration' else 'B'} · Full-span cubic {derivative}",
            loc="left",
        )
        axis.grid(alpha=0.25)
        axis.text(
            0.02,
            0.98,
            f"complete no-step fits: {len(selected)}/6",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    figure.savefig(path, dpi=170)


def _plot_step(rate_rows: list[dict[str, object]], path: Path) -> None:
    selected = [
        row for row in rate_rows if row["status"] == "complete" and float(row["cfo_step_hz"]) != 0.0
    ]
    methods = ["causal_20ms_linear", "fixed_125ms_linear", "fixed_500ms_linear"]
    phases = ["pre_step", "transition", "post_history"]
    values = np.zeros((len(methods), len(phases)), dtype=float)
    for i, method in enumerate(methods):
        for j, phase in enumerate(phases):
            errors = np.asarray(
                [
                    float(row["receiver_error_hz_s"])
                    for row in selected
                    if row["estimator"] == method and row["step_phase"] == phase
                ]
            )
            values[i, j] = float(np.sqrt(np.mean(errors**2))) if errors.size else np.nan
    figure = Figure(figsize=(9.5, 5.0), constrained_layout=True)
    axis = figure.subplots()
    x = np.arange(len(methods))
    width = 0.24
    for j, phase in enumerate(phases):
        axis.bar(x + (j - 1) * width, values[:, j], width, label=phase.replace("_", " "))
    axis.set_xticks(x, ["20 ms", "125 ms", "500 ms"])
    axis.set_ylabel("Receiver-clock rate RMSE (Hz/s)")
    axis.set_title("Physical CFO-step response by causal history")
    axis.grid(alpha=0.25, axis="y")
    axis.legend()
    figure.savefig(path, dpi=170)


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _write_report(
    path: Path,
    *,
    evidence: dict[str, Any],
    rate_aggregate: list[dict[str, object]],
    cubic_aggregate: list[dict[str, object]],
    frame_summary: list[dict[str, object]],
    rate_scenarios: list[dict[str, object]],
    rate_estimates: list[dict[str, object]],
    cubic_estimates: list[dict[str, object]],
    figures: dict[str, Path],
) -> None:
    no_step = {str(row["estimator"]): row for row in rate_aggregate if row["scope"] == "no_step"}
    rate_rows = []
    for method, label in (
        ("causal_20ms_linear", "Causal 20 ms"),
        ("fixed_125ms_linear", "Fixed 125 ms"),
        ("fixed_500ms_linear", "Fixed 500 ms"),
    ):
        row = no_step[method]
        rate_rows.append(
            (
                label,
                int(row["scenario_count"]),
                int(row["no_result_scenario_count"]),
                _fmt(row["receiver_bias"]),
                _fmt(row["receiver_rmse"]),
                _fmt(row["receiver_median_absolute_error"]),
                _fmt(100 * float(row["receiver_failure_rate"]), 1) + "%",
                _fmt(100 * float(row["receiver_coverage_95"]), 1) + "%",
                _fmt(row["physical_rmse"]),
            )
        )
    cubic_rows = []
    for derivative in ("rate", "acceleration", "jerk"):
        receiver = next(
            row
            for row in cubic_aggregate
            if row["scope"] == "no_step"
            and row["coordinate"] == "receiver"
            and row["derivative"] == derivative
        )
        physical = next(
            row
            for row in cubic_aggregate
            if row["scope"] == "no_step"
            and row["coordinate"] == "physical"
            and row["derivative"] == derivative
        )
        cubic_rows.append(
            (
                derivative,
                int(receiver["scenario_count"]),
                int(receiver["no_result_scenario_count"]),
                _fmt(receiver["bias"]),
                _fmt(receiver["rmse"]),
                _fmt(100 * float(receiver["coverage_95"]), 1) + "%",
                _fmt(physical["rmse"]),
            )
        )
    clock_rows = []
    for row in rate_aggregate:
        if row["stratum"] != "sample_clock_offset_ppm_no_step":
            continue
        if row["estimator"] != "fixed_500ms_linear":
            continue
        clock_rows.append(
            (
                _fmt(row["stratum_value"], 0),
                int(row["scenario_count"]),
                int(row["no_result_scenario_count"]),
                _fmt(row["receiver_bias"]),
                _fmt(row["receiver_rmse"]),
                _fmt(row["physical_bias"]),
                _fmt(row["physical_rmse"]),
            )
        )
    clock_rows.sort(key=lambda row: float(row[0]))
    scenario_rate_counts = {
        (str(row["scenario_id"]), str(row["estimator"])): int(row["receiver_count"])
        for row in rate_scenarios
        if row["scope"] == "all_complete"
    }
    cubic_by_scenario = {str(row["scenario_id"]): row for row in cubic_estimates}
    scenario_rows = []
    for row in sorted(frame_summary, key=lambda item: str(item["scenario_id"])):
        scenario_id = str(row["scenario_id"])
        capture_stamp = str(row["background_session_id"]).split("-")[1].removeprefix("20260825T")
        scenario_rows.append(
            (
                scenario_id,
                capture_stamp,
                _fmt(row["snr_db"], 0),
                _fmt(row["frame_occupancy"], 2),
                _fmt(row["cfo_step_hz"], 0),
                _fmt(row["sample_clock_offset_ppm"], 0),
                f"{row['supported_occupied_count']}/{row['occupied_opportunity_count']}",
                int(row["supported_unoccupied_count"]),
                scenario_rate_counts.get((scenario_id, "causal_20ms_linear"), 0),
                scenario_rate_counts.get((scenario_id, "fixed_125ms_linear"), 0),
                scenario_rate_counts.get((scenario_id, "fixed_500ms_linear"), 0),
                str(cubic_by_scenario[scenario_id]["status"]),
            )
        )
    step_rows = []
    for method, label in (
        ("causal_20ms_linear", "20 ms"),
        ("fixed_125ms_linear", "125 ms"),
        ("fixed_500ms_linear", "500 ms"),
    ):
        for phase in ("pre_step", "transition", "post_history"):
            errors = np.asarray(
                [
                    float(row["receiver_error_hz_s"])
                    for row in rate_estimates
                    if row["status"] == "complete"
                    and row["estimator"] == method
                    and row["step_phase"] == phase
                    and float(row["cfo_step_hz"]) != 0.0
                ],
                dtype=float,
            )
            step_rows.append(
                (
                    label,
                    phase.replace("_", " "),
                    errors.size,
                    _fmt(float(np.sqrt(np.mean(errors**2))) if errors.size else None),
                    _fmt(float(np.median(np.abs(errors))) if errors.size else None),
                )
            )
    snr_rows = []
    for snr in sorted({float(row["snr_db"]) for row in frame_summary}):
        selected = [row for row in frame_summary if float(row["snr_db"]) == snr]
        snr_rows.append(
            (
                _fmt(snr, 0),
                _fmt(
                    100 * float(np.mean([float(row["occupied_support_rate"]) for row in selected])),
                    1,
                )
                + "%",
                _fmt(
                    100
                    * float(
                        np.mean([float(row["unoccupied_false_support_rate"]) for row in selected])
                    ),
                    2,
                )
                + "%",
                sum(int(row["even_control_wins_occupied"]) for row in selected),
                sum(int(row["odd_control_wins_occupied"]) for row in selected),
            )
        )
    promotion = evidence["promotion"]
    failed_checks = [name for name, passed in promotion["checks"].items() if not passed]
    verdict = (
        "The preregistered promotion gate passed."
        if promotion["status"] == "pass"
        else "The preregistered promotion gate failed: " + ", ".join(failed_checks) + "."
    )
    relative_figures = {name: value.relative_to(path.parent) for name, value in figures.items()}
    text = f"""# Known polynomial-phase injection into real POST-FIX backgrounds

Date: 2026-08-25 UTC

Status: **{promotion["status"].upper()} against preregistered component gates**

This report executes the frozen exact-Qin protocol at repository commit
`{PREREGISTRATION_COMMIT}`. It used only the three authorized hard-null spans,
verified every inventory/manifest/chunk digest before decoding CI16, and kept
all 18 scenario outcomes. No holdout, newer capture, dynamic discovery, or
replacement input was used.

## Bottom line

{verdict} The 500 ms line met the point-error limits, but its nominal 95%
interval covered only 64.5% of promotion endpoints. Its uncertainty is
overconfident and the unchanged estimator should not be promoted. This is a
conditional frame-CFO/rate calibration with exact timing and the correct
coarse 750 Hz basin supplied; it is not an acquisition-yield claim.
Receiver-clock error is primary.

## Inputs and execution

{
        _markdown_table(
            ("Capture", "Span samples", "Canonical span SHA-256", "Power"),
            [
                (
                    row["session_id"],
                    f"[{row['sample_start']}, {row['sample_start'] + row['sample_count']})",
                    row["span_sha256"],
                    f"{row['background_power']:.6g}",
                )
                for row in evidence["inputs"]
            ],
        )
    }

The exact lower-edge Qin template contains 3,333 samples and was placed without
overlap on `round(10000*k/3)`. The public parity-split likelihood kernel supplied
even-trained CFO points, the public robust tracker supplied fixed 20/125/500 ms
lines, the even rolled control remained a training specificity gate, and odd
exact/control values remained response-only.

The `sample_clock_offset_ppm` factor warps only the injected phase/polynomial
time coordinate. It does **not** resample Qin waveform boundaries or move the
fixed 3,333/3,334-sample lattice. It is therefore a phase-coordinate
clock-scale test, not a full sample-clock or timing-offset simulation.

## Frame recovery and controls

{
        _markdown_table(
            (
                "SNR (dB)",
                "Occupied support",
                "Empty false support",
                "Even control wins",
                "Odd control wins",
            ),
            snr_rows,
        )
    }

![Frame support and controls]({relative_figures["support"]})

The SNR transition is sharp: occupied support is effectively absent at -32 dB,
only 3.9% at -24 dB, and 99.7% at -16 dB. Rolled-control wins track the same
transition and the unoccupied false-support fraction remains below 0.1%.

## Scenario-level availability

No-result outcomes are evidence, not missing rows. Endpoint counts below are
the public tracker's complete outputs; zero means that the frozen support,
coverage, frame-count, or gap requirements never produced an estimate.

{
        _markdown_table(
            (
                "ID",
                "Capture UTC",
                "SNR",
                "Occ.",
                "Step Hz",
                "Clock ppm",
                "Supported/occupied",
                "False supports",
                "20 ms n",
                "125 ms n",
                "500 ms n",
                "Cubic",
            ),
            scenario_rows,
        )
    }

![Scenario recovery]({relative_figures["scenario"]})

## Causal rate truth

Scenario-equal results below use the six no-step scenarios. Endpoints are
serially correlated, so coverage is descriptive rather than a binomial
confidence experiment.

{
        _markdown_table(
            (
                "Estimator",
                "Scenarios",
                "No result",
                "Receiver bias",
                "Receiver RMSE",
                "Median absolute error",
                ">500 Hz/s",
                "95% coverage",
                "Physical RMSE",
            ),
            rate_rows,
        )
    }

![Rate accuracy]({relative_figures["rate"]})

The 20 ms line is not competitive here: despite wide intervals giving about
95% coverage on its two evaluable no-step rows, its 3.77 kHz/s RMSE and 82.9%
large-error rate are unacceptable. The 125 ms line is much more stable but has
no result outside the two -16 dB no-step rows. The 500 ms line reaches all four
promotion rows and has the lowest point RMSE, but its frozen 50 Hz measurement
scale does not capture its actual endpoint error.

## Acceleration and jerk diagnostic

The full-span cubic is offline and diagnostic. It estimates all three
derivatives; the causal line baselines estimate rate only.

{
        _markdown_table(
            (
                "Derivative",
                "Scenarios",
                "No result",
                "Receiver bias",
                "Receiver RMSE",
                "95% coverage",
                "Physical RMSE",
            ),
            cubic_rows,
        )
    }

![Cubic derivative recovery]({relative_figures["cubic"]})

Those cubic numbers are conditional on only two of the six no-step rows, both
at -16 dB. Four rows—including both -24 dB rows—were below the frozen 300-frame
minimum. The numerical acceleration and jerk thresholds passed on the two
complete fits, but this is not evidence of usable weak-signal acceleration or
jerk recovery and is not a causal result.

## Receiver-clock versus injected physical truth

The phase-coordinate clock scale is not folded into the primary estimator
error. The table below keeps it explicit for the fixed 500 ms line across the
six no-step scenarios in each frozen clock stratum.

{
        _markdown_table(
            (
                "Clock ppm",
                "Scenarios",
                "No result",
                "Receiver bias",
                "Receiver RMSE",
                "Physical bias",
                "Physical RMSE",
            ),
            clock_rows,
        )
    }

Across this deliberately small ±25 ppm phase scaling, receiver-clock and
physical errors differ by less than the estimator's dominant frame-CFO error.
This does not calibrate the real receiver clock and, because no waveform
resampling occurred, says nothing about clock-driven frame-boundary drift.

## CFO steps and alias labels

Known ±750 Hz alias-label changes were canonicalized before training. They test
downstream branch handling, not blind alias discovery. Physical ±300 Hz CFO
steps remained in the signal. The transition interval for each history is kept
out of smooth calibration and shown explicitly below.

![Step response]({relative_figures["step"]})

The table is endpoint-pooled within step phase (not scenario-equal) and is a
recovery diagnostic rather than smooth calibration.

{
        _markdown_table(
            ("History", "Phase", "Endpoints", "RMSE Hz/s", "Median absolute error Hz/s"),
            step_rows,
        )
    }

The fixed 500 ms line contains the step transient to 640 Hz/s RMSE and returns
to 179 Hz/s after one full history. The 125 ms line returns to 213 Hz/s but has
a 2.61 kHz/s transition. The 20 ms line is noisy before and after the step and
spikes to 15.8 kHz/s in transition.

## Promotion checks

{
        _markdown_table(
            ("Check", "Pass"), [(name, str(passed)) for name, passed in promotion["checks"].items()]
        )
    }

The promotion subset contains smooth/no-step scenarios at SNR ≥ -24 dB and all
three backgrounds. The cubic point-error checks are conditional on two
complete fits; two other promotion rows are explicitly retained as no result.
A failed coverage gate does not mean point error is large;
it means the conditional covariance is not calibrated to the frozen interval
criterion. Conversely, a point-error pass cannot establish end-to-end recovery
because timing and the coarse CFO basin were supplied.

## Artifacts and limits

- `frame-evidence.csv`: every opportunity, support rejection, even/odd CFO,
  exact/rolled profile maxima, and truth.
- `rate-estimates.csv`: every warmup or complete fixed-history output and both
  truth-coordinate errors; an explicit `no_result` row is retained if a public
  tracker emits no endpoint at all.
- `cubic-estimates.csv`: every scenario including no-result rows.
- `scenario-summary.csv` and `metrics.json`: scenario-equal summaries,
  promotion checks, provenance, hashes, and runtime.

The waveform contains exact published Qin pilot content but no unknown payload.
The three real backgrounds are hard nulls rather than active-signal
interference. The test measures estimator bias, failure, and interval behavior
conditional on a correct lattice/coarse bin; it does not establish blind
acquisition yield, satellite identity, absolute LNB calibration, or clock-free
physical Doppler. The ppm factor is a phase-coordinate scale only, not a
resampled sample-clock/timing-offset experiment.
"""
    path.write_text(text, encoding="utf-8")


def _postprocess_existing(args: argparse.Namespace, repository_root: Path) -> None:
    metrics_path = args.output_root / "metrics.json"
    result = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("existing metrics document is not an object")
    if result.get("schema") != "org.leo.research.polynomial-qin-injection-evidence/v1":
        raise ValueError("existing metrics schema differs")
    if result.get("preregistration_commit") != PREREGISTRATION_COMMIT:
        raise ValueError("existing metrics use another preregistration")
    if result.get("scenario_count") != 18 or result.get("frame_row_count") != 27_000:
        raise ValueError("existing canonical result has incomplete scenario/frame coverage")
    row_names = (
        "frame-evidence.csv",
        "rate-estimates.csv",
        "cubic-estimates.csv",
        "scenario-summary.csv",
        "rate-scenario-metrics.csv",
    )
    prior_artifacts = result.get("artifacts")
    if not isinstance(prior_artifacts, dict):
        raise ValueError("existing metrics have no artifact ledger")
    for name in row_names:
        path = args.output_root / name
        if prior_artifacts.get(name) != _sha256_file(path):
            raise ValueError(f"sealed row artifact differs before postprocessing: {name}")
    for name in row_names:
        path = args.output_root / name
        payload = path.read_bytes()
        normalized = payload.replace(b"\r\n", b"\n")
        if b"\r" in normalized:
            raise ValueError(f"sealed row artifact contains a non-CRLF carriage return: {name}")
        if normalized != payload:
            path.write_bytes(normalized)
    frame_rows = _read_csv(args.output_root / "frame-evidence.csv")
    rate_rows = _read_csv(args.output_root / "rate-estimates.csv")
    cubic_rows = _read_csv(args.output_root / "cubic-estimates.csv")
    frame_summary = _read_csv(args.output_root / "scenario-summary.csv")
    rate_scenarios = _read_csv(args.output_root / "rate-scenario-metrics.csv")
    if len(frame_rows) != 27_000 or len(cubic_rows) != 18 or len(frame_summary) != 18:
        raise ValueError("sealed row artifacts have unexpected canonical row counts")
    if {str(row["scenario_id"]) for row in frame_summary} != {
        f"P{index:03d}" for index in range(1, 19)
    }:
        raise ValueError("sealed row artifacts have unexpected scenario identities")
    rate_aggregate = result.get("rate_aggregate")
    cubic_aggregate = result.get("cubic_aggregate")
    if not isinstance(rate_aggregate, list) or not isinstance(cubic_aggregate, list):
        raise ValueError("existing aggregate metrics are missing")

    figures = {
        "support": args.output_root / "01-frame-support-and-controls.png",
        "rate": args.output_root / "02-known-truth-rate-accuracy.png",
        "cubic": args.output_root / "03-cubic-acceleration-jerk.png",
        "step": args.output_root / "04-cfo-step-response.png",
        "scenario": args.output_root / "05-scenario-recovery-matrix.png",
    }
    _plot_frame_support(frame_summary, figures["support"])
    _plot_rate(rate_aggregate, figures["rate"])
    _plot_cubic(cubic_rows, figures["cubic"])
    _plot_step(rate_rows, figures["step"])
    _plot_scenario_recovery(frame_summary, rate_scenarios, cubic_rows, figures["scenario"])
    result["sample_clock_factor_implementation"] = {
        "scope": "phase_coordinate_scale_only",
        "phase_polynomial_time_warped": True,
        "qin_waveform_resampled": False,
        "frame_lattice_resampled": False,
        "interpretation": (
            "not a full sample-clock or timing-offset simulation; fixed 3333/3334-sample "
            "frame boundaries are unchanged"
        ),
    }
    result["postprocessed_utc"] = datetime.now(UTC).isoformat()
    result["implementation"]["tool_sha256"] = _sha256_file(Path(__file__).resolve())
    result["implementation"]["kernel_sha256"] = _sha256_file(
        repository_root / "src/leo/analysis/research/polynomial_injection.py"
    )
    _write_report(
        args.report,
        evidence=result,
        rate_aggregate=rate_aggregate,
        cubic_aggregate=cubic_aggregate,
        frame_summary=frame_summary,
        rate_scenarios=rate_scenarios,
        rate_estimates=rate_rows,
        cubic_estimates=cubic_rows,
        figures=figures,
    )
    result["artifacts"] = {
        path.name: _sha256_file(path)
        for path in (
            *(args.output_root / name for name in row_names),
            *figures.values(),
            args.report,
        )
    }
    metrics_path.write_bytes(_json_bytes(result))
    print(
        json.dumps(
            {
                "status": result["status"],
                "postprocessed_without_iq": True,
                "metrics": str(metrics_path),
                "report": str(args.report),
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    args = _arguments()
    repository_root = Path.cwd().resolve()
    if args.maximum_scenarios is not None and args.output_root == DEFAULT_OUTPUT:
        raise ValueError("canonical output refuses a partial scenario run")
    if args.maximum_scenarios is not None and args.maximum_scenarios < 1:
        raise ValueError("maximum scenarios must be positive")
    if _git_head(repository_root) != PREREGISTRATION_COMMIT:
        raise ValueError("experiment must start from the exact preregistration commit")
    if args.postprocess_existing:
        if args.maximum_scenarios is not None:
            raise ValueError("postprocessing refuses a partial scenario selection")
        _postprocess_existing(args, repository_root)
        return
    policy = load_doppler_dataset_policy(args.policy)
    inventory_path = verify_policy_inventory(policy, repository_root)
    protocol = load_polynomial_injection_protocol(
        args.protocol,
        dataset_policy=policy,
        repository_root=repository_root,
    )
    raw_config = json.loads(args.protocol.read_text(encoding="utf-8"))
    if not isinstance(raw_config, dict):
        raise ValueError("protocol document is not an object")
    scenarios = protocol.scenarios
    if args.maximum_scenarios is not None:
        scenarios = scenarios[: args.maximum_scenarios]
    started = time.monotonic()
    started_utc = datetime.now(UTC).isoformat()
    backgrounds: dict[str, VerifiedBackground] = {}
    dispositions = []
    for binding in protocol.backgrounds:
        verified = _read_verified_background(binding, policy=policy)
        backgrounds[binding.session_id] = verified
        dispositions.append(
            CaptureDisposition(
                capture=policy.capture(binding.session_id),
                status="evaluable",
                reason="exact manifest/chunk/span digest verified",
            )
        )
        print(f"verified {binding.session_id} span {verified.span_sha256}", flush=True)
    finalize_capture_dispositions(
        policy,
        experiment_role="polynomial_injection",
        dispositions=dispositions,
    )

    frame_rows: list[dict[str, object]] = []
    rate_rows: list[dict[str, object]] = []
    cubic_rows: list[dict[str, object]] = []
    injection_rows: list[dict[str, object]] = []
    for index, scenario in enumerate(scenarios, start=1):
        background = backgrounds[scenario.background_session_id]
        injected, occupancy, diagnostics = inject_exact_qin(
            background.samples,
            scenario,
            protocol,
        )
        evidence = evaluate_exact_qin_frames(
            injected,
            occupancy,
            scenario,
            protocol,
            absolute_span_start_sample=background.binding.sample_start,
        )
        rates = fixed_history_rate_estimates(evidence, scenario, protocol)
        cubic = fit_full_span_cubic(evidence, scenario, protocol)
        frame_rows.extend(_frame_row(item, scenario) for item in evidence)
        rate_rows.extend(_rate_row(item, scenario) for item in rates)
        cubic_rows.append(_cubic_row(cubic, scenario))
        injection_rows.append({"scenario_id": scenario.scenario_id, **asdict(diagnostics)})
        print(
            f"scenario {index}/{len(scenarios)} {scenario.scenario_id}: "
            f"supported={sum(item.training_supported for item in evidence)} "
            f"cubic={cubic.status}",
            flush=True,
        )

    frame_summary = _frame_summaries(frame_rows)
    rate_scenarios = _rate_scenario_metrics(rate_rows)
    rate_aggregate = []
    rate_aggregate.extend(
        _aggregate_scenario_metrics(
            rate_scenarios,
            selector=lambda row: True,
            scope_name="all",
        )
    )
    rate_aggregate.extend(
        _aggregate_scenario_metrics(
            rate_scenarios,
            selector=lambda row: float(row["cfo_step_hz"]) == 0.0,
            scope_name="no_step",
        )
    )
    promotion_selector = lambda row: (  # noqa: E731
        float(row["cfo_step_hz"]) == 0.0 and float(row["snr_db"]) >= -24.0
    )
    rate_aggregate.extend(
        _aggregate_scenario_metrics(
            rate_scenarios,
            selector=promotion_selector,
            scope_name="promotion",
        )
    )
    stratum_fields = (
        ("background_session_id", "background"),
        ("snr_db", "snr_db"),
        ("frame_occupancy", "frame_occupancy"),
        ("sample_clock_offset_ppm", "sample_clock_offset_ppm"),
        ("alias_change_hz", "alias_change"),
        ("cfo_step_hz", "cfo_step"),
    )
    for field, label in stratum_fields:
        levels = sorted({row[field] for row in rate_scenarios}, key=str)
        for level in levels:
            rate_aggregate.extend(
                _aggregate_scenario_metrics(
                    rate_scenarios,
                    selector=lambda row, field=field, level=level: row[field] == level,
                    scope_name=f"{label}={level}",
                    stratum=label,
                    stratum_value=level,
                )
            )
    for level in sorted({row["sample_clock_offset_ppm"] for row in rate_scenarios}, key=float):
        rate_aggregate.extend(
            _aggregate_scenario_metrics(
                rate_scenarios,
                selector=lambda row, level=level: (
                    row["sample_clock_offset_ppm"] == level and float(row["cfo_step_hz"]) == 0.0
                ),
                scope_name=f"sample_clock_offset_ppm_no_step={level}",
                stratum="sample_clock_offset_ppm_no_step",
                stratum_value=level,
            )
        )
    cubic_aggregate = []
    cubic_aggregate.extend(_cubic_metrics(cubic_rows, selector=lambda row: True, scope_name="all"))
    cubic_aggregate.extend(
        _cubic_metrics(
            cubic_rows,
            selector=lambda row: float(row["cfo_step_hz"]) == 0.0,
            scope_name="no_step",
        )
    )
    cubic_aggregate.extend(
        _cubic_metrics(cubic_rows, selector=promotion_selector, scope_name="promotion")
    )
    for field, label in stratum_fields:
        levels = sorted({row[field] for row in cubic_rows}, key=str)
        for level in levels:
            cubic_aggregate.extend(
                _cubic_metrics(
                    cubic_rows,
                    selector=lambda row, field=field, level=level: row[field] == level,
                    scope_name=f"{label}={level}",
                    stratum=label,
                    stratum_value=level,
                )
            )
    for level in sorted({row["sample_clock_offset_ppm"] for row in cubic_rows}, key=float):
        cubic_aggregate.extend(
            _cubic_metrics(
                cubic_rows,
                selector=lambda row, level=level: (
                    row["sample_clock_offset_ppm"] == level and float(row["cfo_step_hz"]) == 0.0
                ),
                scope_name=f"sample_clock_offset_ppm_no_step={level}",
                stratum="sample_clock_offset_ppm_no_step",
                stratum_value=level,
            )
        )
    promotion = _promotion(rate_aggregate, cubic_aggregate, raw_config)
    args.output_root.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_root / "frame-evidence.csv", frame_rows)
    _write_csv(args.output_root / "rate-estimates.csv", rate_rows)
    _write_csv(args.output_root / "cubic-estimates.csv", cubic_rows)
    _write_csv(args.output_root / "scenario-summary.csv", frame_summary)
    _write_csv(args.output_root / "rate-scenario-metrics.csv", rate_scenarios)

    figures = {
        "support": args.output_root / "01-frame-support-and-controls.png",
        "rate": args.output_root / "02-known-truth-rate-accuracy.png",
        "cubic": args.output_root / "03-cubic-acceleration-jerk.png",
        "step": args.output_root / "04-cfo-step-response.png",
        "scenario": args.output_root / "05-scenario-recovery-matrix.png",
    }
    _plot_frame_support(frame_summary, figures["support"])
    _plot_rate(rate_aggregate, figures["rate"])
    _plot_cubic(cubic_rows, figures["cubic"])
    _plot_step(rate_rows, figures["step"])
    _plot_scenario_recovery(frame_summary, rate_scenarios, cubic_rows, figures["scenario"])
    completed_utc = datetime.now(UTC).isoformat()
    runtime_s = time.monotonic() - started
    tool_path = Path(__file__).resolve()
    implementation_path = repository_root / "src/leo/analysis/research/polynomial_injection.py"
    protocol_loader_path = (
        repository_root / "src/leo/analysis/research/polynomial_injection_protocol.py"
    )
    result = {
        "schema": "org.leo.research.polynomial-qin-injection-evidence/v1",
        "status": promotion["status"],
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "runtime_s": runtime_s,
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "repository_head_at_execution": _git_head(repository_root),
        "policy_path": str(args.policy),
        "policy_sha256": _sha256_file(args.policy),
        "protocol_path": str(args.protocol),
        "protocol_sha256": _sha256_file(args.protocol),
        "inventory_path": str(inventory_path.relative_to(repository_root)),
        "inventory_sha256": _sha256_file(inventory_path),
        "implementation": {
            "tool_path": str(tool_path.relative_to(repository_root)),
            "tool_sha256": _sha256_file(tool_path),
            "kernel_path": str(implementation_path.relative_to(repository_root)),
            "kernel_sha256": _sha256_file(implementation_path),
            "protocol_loader_path": str(protocol_loader_path.relative_to(repository_root)),
            "protocol_loader_sha256": _sha256_file(protocol_loader_path),
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "zstandard": zstd.__version__,
            "platform": platform.platform(),
        },
        "sample_clock_factor_implementation": {
            "scope": "phase_coordinate_scale_only",
            "phase_polynomial_time_warped": True,
            "qin_waveform_resampled": False,
            "frame_lattice_resampled": False,
            "interpretation": (
                "not a full sample-clock or timing-offset simulation; fixed 3333/3334-sample "
                "frame boundaries are unchanged"
            ),
        },
        "inputs": [
            {
                "session_id": item.binding.session_id,
                "sample_start": item.binding.sample_start,
                "sample_count": item.binding.sample_count,
                "recording_manifest_sha256": item.binding.recording_manifest_sha256,
                "analysis_run_id": item.binding.analysis_run_id,
                "analysis_manifest_sha256": item.binding.analysis_manifest_sha256,
                "compressed_chunk_sha256": item.binding.chunk.compressed_sha256,
                "uncompressed_chunk_sha256": item.binding.chunk.uncompressed_sha256,
                "span_sha256": item.span_sha256,
                "background_power": item.background_power,
                "compressed_bytes_read": item.compressed_bytes_read,
                "uncompressed_bytes_verified": item.uncompressed_bytes_verified,
            }
            for item in backgrounds.values()
        ],
        "capture_dispositions": [asdict(item) for item in dispositions],
        "scenario_count": len(scenarios),
        "frame_row_count": len(frame_rows),
        "rate_row_count": len(rate_rows),
        "cubic_row_count": len(cubic_rows),
        "injection_diagnostics": injection_rows,
        "frame_summaries": frame_summary,
        "rate_scenario_metrics": rate_scenarios,
        "rate_aggregate": rate_aggregate,
        "cubic_aggregate": cubic_aggregate,
        "promotion": promotion,
        "artifacts": {},
    }
    metrics_path = args.output_root / "metrics.json"
    metrics_path.write_bytes(_json_bytes(result))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_report(
        args.report,
        evidence=result,
        rate_aggregate=rate_aggregate,
        cubic_aggregate=cubic_aggregate,
        frame_summary=frame_summary,
        rate_scenarios=rate_scenarios,
        rate_estimates=rate_rows,
        cubic_estimates=cubic_rows,
        figures=figures,
    )
    artifacts = {
        path.name: _sha256_file(path)
        for path in (
            args.output_root / "frame-evidence.csv",
            args.output_root / "rate-estimates.csv",
            args.output_root / "cubic-estimates.csv",
            args.output_root / "scenario-summary.csv",
            args.output_root / "rate-scenario-metrics.csv",
            *figures.values(),
            args.report,
        )
    }
    result["artifacts"] = artifacts
    metrics_path.write_bytes(_json_bytes(result))
    print(
        json.dumps(
            {
                "status": promotion["status"],
                "runtime_s": runtime_s,
                "scenario_count": len(scenarios),
                "frame_rows": len(frame_rows),
                "rate_rows": len(rate_rows),
                "metrics": str(metrics_path),
                "report": str(args.report),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
