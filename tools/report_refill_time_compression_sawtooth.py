#!/usr/bin/env python3
"""Audit whether stored-time compression at Pluto refills creates CFO sawteeth."""

# ruff: noqa: E501 -- long Markdown table rows and artifact links are intentional.

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

DEFAULT_DWELL_DIR = Path("reports/figures/2026_08_24_ten_dwell_raw_doppler")
DEFAULT_BLIND_JSON = Path(
    "reports/figures/2026_08_23_470384_blind_timing_cfo/blind-timing-cfo-results.json"
)
DEFAULT_BOUNDARY_JSON = Path(
    "reports/figures/2026_08_23_470384_boundary_mechanism/boundary-mechanism-results.json"
)
DEFAULT_RECORDING_ROOT = Path("/srv/bulk/leo/recordings")
DEFAULT_OUTPUT_DIR = Path("reports/figures/2026_08_24_refill_time_compression_sawtooth")
DEFAULT_EVIDENCE = DEFAULT_OUTPUT_DIR / "refill-time-compression-evidence.json"
DEFAULT_REPORT = Path("reports/2026_08_24_refill_time_compression_sawtooth.md")
DEFAULT_STANDARD_SEGMENTS_REVISION = "743216c207c23e23bdc7cc7b9a0729f33db2d3b5"
DEFAULT_STANDARD_SEGMENTS_PATH = (
    "reports/figures/2026_08_23_eight_hour_science_agent/dwell-pilot-segments.csv.gz"
)
DEFAULT_SCANNER_CONTROL_NPY = Path(
    "/srv/bulk/leo/scanner-diagnostics/scanner-correct-1500ms-20260820/ch2-lower.npy"
)

FRAME_RATE_HZ = 750.0
LARGE_JUMP_HZ = 100.0
SMALL_JUMP_HZ = 30.0
TIMING_MATCH_SAMPLES = 2.0

INK = "#17354a"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
RED = "#bd5b52"
PURPLE = "#7b65a8"
GRAY = "#8c99a3"
LIGHT_GRAY = "#d9e0e5"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dwell-input-dir", type=Path, default=DEFAULT_DWELL_DIR)
    parser.add_argument("--blind-json", type=Path, default=DEFAULT_BLIND_JSON)
    parser.add_argument("--boundary-json", type=Path, default=DEFAULT_BOUNDARY_JSON)
    parser.add_argument("--recording-root", type=Path, default=DEFAULT_RECORDING_ROOT)
    parser.add_argument(
        "--standard-segments-revision",
        default=DEFAULT_STANDARD_SEGMENTS_REVISION,
    )
    parser.add_argument(
        "--standard-segments-path",
        default=DEFAULT_STANDARD_SEGMENTS_PATH,
    )
    parser.add_argument(
        "--scanner-control-npy",
        type=Path,
        default=DEFAULT_SCANNER_CONTROL_NPY,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--reuse-evidence",
        type=Path,
        help="Render figures/report from an already frozen evidence JSON",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires observations")
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def _median(values: list[float]) -> float:
    if not values:
        raise ValueError("median requires observations")
    return float(np.median(np.asarray(values, dtype=float)))


def _rms(values: list[float]) -> float:
    if not values:
        raise ValueError("RMS requires observations")
    array = np.asarray(values, dtype=float)
    return float(np.sqrt(np.mean(array**2)))


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_values = np.asarray(left, dtype=float)
    right_values = np.asarray(right, dtype=float)
    if float(np.std(left_values)) == 0.0 or float(np.std(right_values)) == 0.0:
        return None
    return float(np.corrcoef(left_values, right_values)[0, 1])


def _ols_with_intercept(independent: list[float], dependent: list[float]) -> dict[str, float]:
    if len(independent) != len(dependent) or len(independent) < 3:
        raise ValueError("OLS requires at least three paired observations")
    x = np.asarray(independent, dtype=float)
    y = np.asarray(dependent, dtype=float)
    design = np.column_stack((x, np.ones_like(x)))
    slope, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = design @ np.asarray([slope, intercept])
    residual = y - predicted
    centered = y - float(np.mean(y))
    denominator = float(centered @ centered)
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(1.0 - (residual @ residual) / denominator),
        "rms": float(np.sqrt(np.mean(residual**2))),
    }


def _host_start_ns(row: dict[str, Any]) -> int:
    """Return the monotonic request-start bracket for elapsed-time diagnostics."""

    return int(row["host_request_monotonic_ns"]["lower_ns"])


def circular_difference(value: float, period: float) -> float:
    """Return the signed representative in [-period/2, period/2)."""

    if period <= 0.0:
        raise ValueError("period must be positive")
    return float((value + period / 2.0) % period - period / 2.0)


def _line_fit(rows: list[dict[str, Any]], value_key: str) -> tuple[float, float, float]:
    times = np.asarray([float(item["time_s"]) for item in rows], dtype=float)
    values = np.asarray([float(item[value_key]) for item in rows], dtype=float)
    reference = float(np.mean(times))
    centered = times - reference
    denominator = float(centered @ centered)
    if denominator <= 0.0:
        raise ValueError("line fit requires distinct times")
    slope = float(centered @ (values - float(np.mean(values))) / denominator)
    return reference, float(np.mean(values)), slope


def _line_value(line: tuple[float, float, float], time_s: float) -> float:
    reference, intercept, slope = line
    return intercept + slope * (time_s - reference)


def _manifest_path(recording_root: Path, session_id: str) -> Path:
    stamp = session_id.removeprefix("cap-")[:8]
    return recording_root / stamp[:4] / stamp[4:6] / stamp[6:8] / session_id / "manifest.json"


def _stream_manifest(manifest: dict[str, Any], stream_id: str) -> dict[str, Any]:
    for stream in manifest["streams"]:
        if stream["stream_id"] == stream_id:
            return stream
    raise ValueError(f"manifest has no stream {stream_id}")


def _timeline_path(manifest_path: Path, stream: dict[str, Any]) -> Path:
    serial = stream["radio"]["serial"]
    return manifest_path.parent / f"radio-{serial}" / "timeline.jsonl.zst"


def _read_timeline(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with (
        path.open("rb") as compressed,
        zstd.ZstdDecompressor().stream_reader(compressed) as decompressed,
        io.TextIOWrapper(decompressed, encoding="utf-8") as text,
    ):
        for line in text:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _sample_configuration(manifest: dict[str, Any], stream: dict[str, Any]) -> tuple[int, float]:
    profile = manifest["capture_plan"]["profile_revision"]["profile"]
    refill_samples = int(profile["refill_samples"])
    sample_rate_hz = float(stream["applied_settings"]["sample_rate_hz"])
    if float(profile["sample_rate_hz"]) != sample_rate_hz:
        raise ValueError("profile and applied sample rates disagree")
    return refill_samples, sample_rate_hz


def _probe_phase(probe: dict[str, Any], frame_period_samples: float) -> float:
    return float(
        (int(probe["detection_sample_start"]) + int(probe["local_epoch_sample"]))
        % frame_period_samples
    )


def extract_ramp_boundaries(
    result: dict[str, Any],
    timeline: list[dict[str, Any]],
    *,
    refill_samples: int,
    sample_rate_hz: float,
    dwell_label: str,
) -> tuple[list[dict[str, Any]], list[float]]:
    """Measure adjacent ramp jumps and timing state without using timing in selection."""

    track = result["track"]
    ramps = result["ramps"]
    probes = {int(item["probe_index"]): item for item in track["probes"]}
    frames = {int(item["row_index"]): item for item in result["frames"]}
    timeline_by_block = {
        int(item["session_sample_start"]) // refill_samples: item for item in timeline
    }
    refill_period_s = refill_samples / sample_rate_hz
    frame_period_samples = sample_rate_hz / FRAME_RATE_HZ

    validation_lines: list[tuple[float, float, float]] = []
    within_ramp_timing_differences: list[float] = []
    for ramp in ramps:
        members = [frames[int(index)] for index in ramp["observation_indices"]]
        validation_lines.append(_line_fit(members, "validation_cfo_hz"))
        used_probes = sorted({int(item["probe_index"]) for item in members})
        phases = [_probe_phase(probes[index], frame_period_samples) for index in used_probes]
        within_ramp_timing_differences.extend(
            abs(circular_difference(trailing - leading, frame_period_samples))
            for leading, trailing in zip(phases, phases[1:], strict=False)
        )

    output: list[dict[str, Any]] = []
    local_rate = float(result["diagnostics"]["local_corrected_rate_hz_s"])
    for index, (leading, trailing) in enumerate(zip(ramps, ramps[1:], strict=False)):
        boundary_time_s = 0.5 * (float(leading["end_time_s"]) + float(trailing["start_time_s"]))
        leading_cfo = float(leading["intercept_hz"]) + float(leading["slope_hz_s"]) * (
            boundary_time_s - float(leading["center_time_s"])
        )
        trailing_cfo = float(trailing["intercept_hz"]) + float(trailing["slope_hz_s"]) * (
            boundary_time_s - float(trailing["center_time_s"])
        )
        train_jump_hz = trailing_cfo - leading_cfo
        validation_jump_hz = _line_value(
            validation_lines[index + 1], boundary_time_s
        ) - _line_value(validation_lines[index], boundary_time_s)

        leading_probe = probes[int(leading["source_probe_end"])]
        trailing_probe = probes[int(trailing["source_probe_start"])]
        leading_phase = _probe_phase(leading_probe, frame_period_samples)
        trailing_phase = _probe_phase(trailing_probe, frame_period_samples)
        timing_jump_samples = circular_difference(
            trailing_phase - leading_phase, frame_period_samples
        )

        first_block = math.ceil((float(leading["end_time_s"]) - 1e-12) / refill_period_s)
        last_block = math.floor((float(trailing["start_time_s"]) + 1e-12) / refill_period_s)
        refill_blocks = list(range(first_block, last_block + 1))
        host_excess_values: list[float] = []
        for block_index in refill_blocks:
            current = timeline_by_block.get(block_index)
            previous = timeline_by_block.get(block_index - 1)
            if current is None or previous is None:
                continue
            current_start = _host_start_ns(current)
            previous_start = _host_start_ns(previous)
            host_excess_values.append((current_start - previous_start) / 1e9 - refill_period_s)

        one_refill_excess_s = (
            host_excess_values[0]
            if len(refill_blocks) == 1 and len(host_excess_values) == 1
            else None
        )
        predicted_timing_jump_samples = None
        timing_prediction_error_samples = None
        predicted_jump_hz = None
        if one_refill_excess_s is not None:
            predicted_timing_jump_samples = circular_difference(
                -one_refill_excess_s * sample_rate_hz,
                frame_period_samples,
            )
            timing_prediction_error_samples = circular_difference(
                timing_jump_samples - predicted_timing_jump_samples,
                frame_period_samples,
            )
            predicted_jump_hz = local_rate * one_refill_excess_s

        output.append(
            {
                "boundary_index": index,
                "boundary_time_s": boundary_time_s,
                "dwell": dwell_label,
                "gap_ms": (float(trailing["start_time_s"]) - float(leading["end_time_s"])) * 1e3,
                "train_jump_hz": train_jump_hz,
                "validation_jump_hz": validation_jump_hz,
                "timing_jump_samples": timing_jump_samples,
                "refill_boundary_count": len(refill_blocks),
                "contains_refill_boundary": bool(refill_blocks),
                "host_start_excess_s": one_refill_excess_s,
                "predicted_timing_jump_samples": predicted_timing_jump_samples,
                "timing_prediction_error_samples": timing_prediction_error_samples,
                "predicted_jump_hz": predicted_jump_hz,
            }
        )
    return output, within_ramp_timing_differences


def _track_host_excesses(
    timeline: list[dict[str, Any]],
    *,
    start_s: float,
    end_s: float,
    refill_samples: int,
    sample_rate_hz: float,
) -> list[float]:
    refill_period_s = refill_samples / sample_rate_hz
    values = []
    ordered = sorted(timeline, key=lambda item: int(item["session_sample_start"]))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        boundary_s = int(current["session_sample_start"]) / sample_rate_hz
        if not start_s <= boundary_s <= end_s:
            continue
        current_start = _host_start_ns(current)
        previous_start = _host_start_ns(previous)
        values.append((current_start - previous_start) / 1e9 - refill_period_s)
    return values


def _boundary_summary(boundaries: list[dict[str, Any]]) -> dict[str, Any]:
    jumps = [float(item["train_jump_hz"]) for item in boundaries]
    times = [float(item["boundary_time_s"]) for item in boundaries]
    large = [item for item in boundaries if abs(float(item["train_jump_hz"])) > LARGE_JUMP_HZ]
    small = [item for item in boundaries if abs(float(item["train_jump_hz"])) < SMALL_JUMP_HZ]

    def timing_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        timing = [abs(float(item["timing_jump_samples"])) for item in rows]
        return {
            "count": len(rows),
            "median_absolute_timing_jump_samples": _median(timing) if timing else None,
            "timing_within_2_samples_count": sum(value <= TIMING_MATCH_SAMPLES for value in timing),
            "timing_within_2_samples_fraction": (
                sum(value <= TIMING_MATCH_SAMPLES for value in timing) / len(timing)
                if timing
                else None
            ),
        }

    return {
        "boundary_count": len(boundaries),
        "median_boundary_spacing_ms": (
            _median([(b - a) * 1e3 for a, b in zip(times, times[1:], strict=False)])
            if len(times) > 1
            else None
        ),
        "median_signed_jump_hz": _median(jumps),
        "p10_signed_jump_hz": _percentile(jumps, 10.0),
        "p90_signed_jump_hz": _percentile(jumps, 90.0),
        "negative_jump_fraction": sum(value < 0.0 for value in jumps) / len(jumps),
        "large": timing_summary(large),
        "small": timing_summary(small),
        "large_contains_refill_count": sum(
            bool(item["contains_refill_boundary"]) for item in large
        ),
        "small_contains_refill_count": sum(
            bool(item["contains_refill_boundary"]) for item in small
        ),
    }


def _analyze_dwell(
    path: Path,
    *,
    recording_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[float]]:
    document = _load(path)
    selected = document["selected"]["result"]
    track = selected["track"]
    session_id = str(document["session_id"])
    manifest_path = _manifest_path(recording_root, session_id)
    manifest = _load(manifest_path)
    manifest_digest = _sha256(manifest_path)
    if manifest_digest != document["recording_manifest_digest"]:
        raise ValueError(f"recording manifest digest mismatch: {session_id}")
    stream = _stream_manifest(manifest, str(track["stream_id"]))
    timeline_path = _timeline_path(manifest_path, stream)
    timeline = _read_timeline(timeline_path)
    refill_samples, sample_rate_hz = _sample_configuration(manifest, stream)
    label = path.name.split("-", maxsplit=1)[0]
    boundaries, within_ramp = extract_ramp_boundaries(
        selected,
        timeline,
        refill_samples=refill_samples,
        sample_rate_hz=sample_rate_hz,
        dwell_label=label,
    )
    summary = _boundary_summary(boundaries)
    host_excesses = _track_host_excesses(
        timeline,
        start_s=float(track["start_s"]),
        end_s=float(track["end_s"]),
        refill_samples=refill_samples,
        sample_rate_hz=sample_rate_hz,
    )
    median_excess_s = _median(host_excesses)
    refill_period_s = refill_samples / sample_rate_hz
    stretch = 1.0 + median_excess_s / refill_period_s
    stored_rate = float(selected["diagnostics"]["overall_glrt_rate_hz_s"])
    local_rate = float(selected["diagnostics"]["local_corrected_rate_hz_s"])
    host_retimed_rate = stored_rate / stretch
    predicted_stored_rate = local_rate * stretch
    boundary_times = [float(item["boundary_time_s"]) for item in boundaries]
    cumulative_step_rate = (
        sum(float(item["train_jump_hz"]) for item in boundaries)
        / (boundary_times[-1] - boundary_times[0])
        if len(boundary_times) > 1
        else None
    )
    row = {
        "dwell": label,
        "session_id": session_id,
        "stream_id": track["stream_id"],
        "receiver_id": int(track["receiver_id"]),
        "edge": track["edge"],
        "source_json": str(path),
        "source_json_sha256": _sha256(path),
        "recording_manifest": str(manifest_path),
        "recording_manifest_sha256": manifest_digest,
        "timeline": str(timeline_path),
        "timeline_sha256": _sha256(timeline_path),
        "refill_samples": refill_samples,
        "sample_rate_hz": sample_rate_hz,
        "refill_period_ms": refill_period_s * 1e3,
        "ramp_count": len(selected["ramps"]),
        **summary,
        "median_host_start_excess_ms": median_excess_s * 1e3,
        "host_time_stretch_diagnostic": stretch,
        "stored_glrt_rate_hz_s": stored_rate,
        "local_ramp_rate_hz_s": local_rate,
        "host_retimed_diagnostic_rate_hz_s": host_retimed_rate,
        "predicted_stored_rate_hz_s": predicted_stored_rate,
        "observed_rate_correction_hz_s": local_rate - stored_rate,
        "predicted_rate_correction_hz_s": local_rate - predicted_stored_rate,
        "host_retimed_minus_local_hz_s": host_retimed_rate - local_rate,
        "predicted_minus_observed_stored_rate_hz_s": predicted_stored_rate - stored_rate,
        "cumulative_step_rate_hz_s": cumulative_step_rate,
        "stored_minus_local_rate_hz_s": stored_rate - local_rate,
    }
    return row, boundaries, within_ramp


def _fixed_effect_slope(blind: dict[str, Any]) -> dict[str, float]:
    segments = blind["primary_segments"]
    groups: list[list[dict[str, Any]]] = [[] for _ in segments]
    for point in blind["primary_path"]:
        time_s = float(point["cell_center_s"])
        for index, segment in enumerate(segments):
            if float(segment["start_s"]) - 1e-9 <= time_s <= float(segment["end_s"]) + 1e-9:
                groups[index].append(point)
                break
    numerator = 0.0
    denominator = 0.0
    for group in groups:
        if len(group) < 2:
            continue
        times = np.asarray([float(item["cell_center_s"]) for item in group])
        values = np.asarray([float(item["absolute_cfo_hz"]) for item in group])
        centered_time = times - float(np.mean(times))
        centered_value = values - float(np.mean(values))
        numerator += float(centered_time @ centered_value)
        denominator += float(centered_time @ centered_time)
    slope = numerator / denominator
    residuals: list[float] = []
    for group in groups:
        if not group:
            continue
        times = np.asarray([float(item["cell_center_s"]) for item in group])
        values = np.asarray([float(item["absolute_cfo_hz"]) for item in group])
        intercept = float(np.mean(values - slope * times))
        residuals.extend((values - (intercept + slope * times)).tolist())
    return {"slope_hz_s": slope, "rms_hz": _rms(residuals)}


def _analyze_blind(
    path: Path,
    *,
    recording_root: Path,
) -> dict[str, Any]:
    blind = _load(path)
    session_id = str(blind["input"]["session_id"])
    stream_id = str(blind["input"]["stream_id"])
    manifest_path = _manifest_path(recording_root, session_id)
    manifest = _load(manifest_path)
    stream = _stream_manifest(manifest, stream_id)
    timeline_path = _timeline_path(manifest_path, stream)
    timeline = _read_timeline(timeline_path)
    refill_samples, sample_rate_hz = _sample_configuration(manifest, stream)
    refill_period_s = refill_samples / sample_rate_hz
    frame_period_samples = sample_rate_hz / FRAME_RATE_HZ
    timeline_by_block = {
        int(item["session_sample_start"]) // refill_samples: item for item in timeline
    }
    event_rows = []
    for event in blind["blind_events"]:
        time_s = float(event["time_s"])
        block_index = round(time_s / refill_period_s)
        refill_time_s = block_index * refill_period_s
        current = timeline_by_block[block_index]
        previous = timeline_by_block[block_index - 1]
        host_delta_s = (_host_start_ns(current) - _host_start_ns(previous)) / 1e9
        host_excess_s = host_delta_s - refill_period_s
        event_rows.append(
            {
                "time_s": time_s,
                "cfo_jump_hz": float(event["cfo_jump_hz"]),
                "timing_jump_samples": float(event["timing_jump_samples"]),
                "nearest_refill_time_s": refill_time_s,
                "refill_time_residual_ms": (time_s - refill_time_s) * 1e3,
                "host_start_delta_ms": host_delta_s * 1e3,
                "host_start_excess_ms": host_excess_s * 1e3,
            }
        )
    host_excess = [float(item["host_start_excess_ms"]) / 1e3 for item in event_rows]
    jumps = [float(item["cfo_jump_hz"]) for item in event_rows]
    through_zero_slope = sum(x * y for x, y in zip(host_excess, jumps, strict=True)) / sum(
        x * x for x in host_excess
    )
    fixed_effect = _fixed_effect_slope(blind)
    prediction_errors = [
        jump - fixed_effect["slope_hz_s"] * excess
        for jump, excess in zip(jumps, host_excess, strict=True)
    ]

    fitted_segments = [item for item in blind["primary_segments"] if item["slope_hz_s"] is not None]
    fitted_jumps = []
    for leading, trailing in zip(fitted_segments, fitted_segments[1:], strict=False):
        time_s = float(trailing["preceding_boundary_time_s"])
        leading_cfo = float(leading["frequency_at_reference_hz"]) + float(leading["slope_hz_s"]) * (
            time_s - float(leading["reference_time_s"])
        )
        trailing_cfo = float(trailing["frequency_at_reference_hz"]) + float(
            trailing["slope_hz_s"]
        ) * (time_s - float(trailing["reference_time_s"]))
        fitted_jumps.append({"time_s": time_s, "jump_hz": trailing_cfo - leading_cfo})

    closeup_start_s = 35.0
    closeup_end_s = 35.65
    primary = blind["primary_line"]

    def global_frequency(time_s: float) -> float:
        return float(primary["frequency_at_reference_hz"]) + float(primary["slope_hz_s"]) * (
            time_s - float(primary["reference_time_s"])
        )

    closeup_points = []
    for item in blind["primary_path"]:
        time_s = float(item["cell_center_s"])
        if closeup_start_s <= time_s <= closeup_end_s:
            closeup_points.append(
                {
                    "time_s": time_s,
                    "cfo_residual_hz": float(item["absolute_cfo_hz"]) - global_frequency(time_s),
                    "timing_phase_samples": float(item["absolute_frame_start_sample"])
                    % frame_period_samples,
                }
            )
    closeup_segment_lines = []
    for segment in blind["primary_segments"]:
        if segment["slope_hz_s"] is None:
            continue
        start_s = max(closeup_start_s, float(segment["start_s"]))
        end_s = min(closeup_end_s, float(segment["end_s"]))
        if start_s > end_s:
            continue
        values = []
        for time_s in (start_s, end_s):
            frequency = float(segment["frequency_at_reference_hz"]) + float(
                segment["slope_hz_s"]
            ) * (time_s - float(segment["reference_time_s"]))
            values.append(frequency - global_frequency(time_s))
        closeup_segment_lines.append({"times_s": [start_s, end_s], "cfo_residual_hz": values})
    first_refill = math.ceil(closeup_start_s / refill_period_s)
    last_refill = math.floor(closeup_end_s / refill_period_s)
    closeup_refills = [index * refill_period_s for index in range(first_refill, last_refill + 1)]
    closeup_events = [
        float(item["time_s"])
        for item in blind["blind_events"]
        if closeup_start_s <= float(item["time_s"]) <= closeup_end_s
    ]

    fitted_jump_values = [float(item["jump_hz"]) for item in fitted_jumps]
    jump_span_s = fitted_jumps[-1]["time_s"] - fitted_jumps[0]["time_s"]
    return {
        "source_json": str(path),
        "source_json_sha256": _sha256(path),
        "session_id": session_id,
        "stream_id": stream_id,
        "receiver_id": int(blind["input"]["receiver_id"]),
        "recording_manifest": str(manifest_path),
        "recording_manifest_sha256": _sha256(manifest_path),
        "timeline": str(timeline_path),
        "timeline_sha256": _sha256(timeline_path),
        "refill_samples": refill_samples,
        "sample_rate_hz": sample_rate_hz,
        "refill_period_ms": refill_period_s * 1e3,
        "event_count": len(event_rows),
        "events": event_rows,
        "median_absolute_event_refill_residual_ms": _median(
            [abs(float(item["refill_time_residual_ms"])) for item in event_rows]
        ),
        "maximum_absolute_event_refill_residual_ms": max(
            abs(float(item["refill_time_residual_ms"])) for item in event_rows
        ),
        "median_host_start_delta_ms": _median(
            [float(item["host_start_delta_ms"]) for item in event_rows]
        ),
        "median_host_start_excess_ms": _median(
            [float(item["host_start_excess_ms"]) for item in event_rows]
        ),
        "jump_per_excess_median_hz_s": _median(
            [jump / excess for jump, excess in zip(jumps, host_excess, strict=True)]
        ),
        "jump_excess_correlation": _pearson(host_excess, jumps),
        "jump_excess_through_zero_slope_hz_s": through_zero_slope,
        "fixed_effect_common_slope_hz_s": fixed_effect["slope_hz_s"],
        "fixed_effect_rms_hz": fixed_effect["rms_hz"],
        "fixed_effect_jump_prediction_median_absolute_error_hz": _median(
            [abs(value) for value in prediction_errors]
        ),
        "fitted_adjacent_jump_count": len(fitted_jumps),
        "fitted_adjacent_jump_median_hz": _median(fitted_jump_values),
        "fitted_adjacent_jump_p10_hz": _percentile(fitted_jump_values, 10.0),
        "fitted_adjacent_jump_p90_hz": _percentile(fitted_jump_values, 90.0),
        "fitted_adjacent_negative_fraction": sum(value < 0.0 for value in fitted_jump_values)
        / len(fitted_jump_values),
        "fitted_jump_sum_per_span_hz_s": sum(fitted_jump_values) / jump_span_s,
        "global_slope_hz_s": float(primary["slope_hz_s"]),
        "global_minus_median_local_slope_hz_s": float(primary["slope_hz_s"])
        - float(blind["primary_segment_statistics"]["median_local_slope_hz_s"]),
        "closeup": {
            "start_s": closeup_start_s,
            "end_s": closeup_end_s,
            "points": closeup_points,
            "segment_lines": closeup_segment_lines,
            "refill_boundaries_s": closeup_refills,
            "blind_events_s": closeup_events,
        },
    }


def _analyze_boundary_mechanism(
    path: Path,
    *,
    recording_root: Path,
) -> dict[str, Any]:
    """Retest the frozen 37-event direct-frame cohort against refill timing."""

    boundary = _load(path)
    session_id = str(boundary["input"]["session_id"])
    stream_id = str(boundary["input"]["stream_id"])
    manifest_path = _manifest_path(recording_root, session_id)
    manifest = _load(manifest_path)
    stream = _stream_manifest(manifest, stream_id)
    timeline_path = _timeline_path(manifest_path, stream)
    timeline = _read_timeline(timeline_path)
    refill_samples, sample_rate_hz = _sample_configuration(manifest, stream)
    refill_period_s = refill_samples / sample_rate_hz
    frame_period_samples = sample_rate_hz / FRAME_RATE_HZ
    timeline_by_block = {
        int(item["session_sample_start"]) // refill_samples: item for item in timeline
    }

    frame_jumps = boundary["frame_jumps"]
    crossfit_boundaries = boundary["crossfit_boundaries"]
    if len(frame_jumps) != len(crossfit_boundaries):
        raise ValueError("boundary frame-jump and timing cohorts differ in length")

    events = []
    for frame_jump, crossfit in zip(frame_jumps, crossfit_boundaries, strict=True):
        time_s = float(frame_jump["time_s"])
        if not math.isclose(time_s, float(crossfit["time_s"]), abs_tol=1e-12):
            raise ValueError("boundary frame-jump and timing rows are not index aligned")
        block_index = round(time_s / refill_period_s)
        current = timeline_by_block[block_index]
        previous = timeline_by_block[block_index - 1]
        refill_time_s = int(current["session_sample_start"]) / sample_rate_hz
        host_delta_s = (_host_start_ns(current) - _host_start_ns(previous)) / 1e9
        host_excess_s = host_delta_s - refill_period_s
        omitted_phase = (host_excess_s * sample_rate_hz) % frame_period_samples
        predicted_timing_magnitude = min(omitted_phase, frame_period_samples - omitted_phase)
        measured_timing_magnitude = float(crossfit["timing_separation_samples"])
        events.append(
            {
                "time_s": time_s,
                "direct_frame_jump_hz": float(frame_jump["direct_frame_jump_hz"]),
                "timing_separation_samples": measured_timing_magnitude,
                "nearest_refill_time_s": refill_time_s,
                "refill_time_residual_ms": (time_s - refill_time_s) * 1e3,
                "host_start_excess_ms": host_excess_s * 1e3,
                "predicted_timing_magnitude_samples": predicted_timing_magnitude,
                "timing_prediction_absolute_error_samples": abs(
                    measured_timing_magnitude - predicted_timing_magnitude
                ),
            }
        )

    host_excess_s = [float(item["host_start_excess_ms"]) / 1e3 for item in events]
    direct_jumps = [float(item["direct_frame_jump_hz"]) for item in events]
    timing_measured = [float(item["timing_separation_samples"]) for item in events]
    timing_predicted = [float(item["predicted_timing_magnitude_samples"]) for item in events]
    regression = _ols_with_intercept(host_excess_s, direct_jumps)
    comparison = boundary["receiver_branch_comparison"]
    return {
        "source_json": str(path),
        "source_json_sha256": _sha256(path),
        "selection": (
            "37 timing-segment boundaries with independently re-estimated "
            "1.333 ms frame CFO; no CFO-jump amplitude gate"
        ),
        "session_id": session_id,
        "stream_id": stream_id,
        "receiver_id": int(boundary["input"]["receiver_id"]),
        "recording_manifest": str(manifest_path),
        "recording_manifest_sha256": _sha256(manifest_path),
        "timeline": str(timeline_path),
        "timeline_sha256": _sha256(timeline_path),
        "radio_id": str(stream["radio"]["radio_id"]),
        "radio_serial": str(stream["radio"]["serial"]),
        "receiver_ids": [int(value) for value in stream["applied_settings"]["receiver_ids"]],
        "refill_samples": refill_samples,
        "sample_rate_hz": sample_rate_hz,
        "refill_period_ms": refill_period_s * 1e3,
        "event_count": len(events),
        "events": events,
        "median_absolute_event_refill_residual_ms": _median(
            [abs(float(item["refill_time_residual_ms"])) for item in events]
        ),
        "p90_absolute_event_refill_residual_ms": _percentile(
            [abs(float(item["refill_time_residual_ms"])) for item in events], 90.0
        ),
        "maximum_absolute_event_refill_residual_ms": max(
            abs(float(item["refill_time_residual_ms"])) for item in events
        ),
        "median_host_start_excess_ms": _median(
            [float(item["host_start_excess_ms"]) for item in events]
        ),
        "host_excess_direct_jump_correlation": _pearson(host_excess_s, direct_jumps),
        "host_excess_direct_jump_ols_slope_hz_s": regression["slope"],
        "host_excess_direct_jump_ols_intercept_hz": regression["intercept"],
        "host_excess_direct_jump_ols_r_squared": regression["r_squared"],
        "host_excess_direct_jump_ols_rms_hz": regression["rms"],
        "timing_magnitude_prediction_correlation": _pearson(timing_predicted, timing_measured),
        "timing_magnitude_prediction_median_absolute_error_samples": _median(
            [float(item["timing_prediction_absolute_error_samples"]) for item in events]
        ),
        "receiver1_event_cadence_period_ms": float(comparison["receiver1_event_cadence_period_ms"]),
        "receiver1_event_cadence_rms_ms": float(comparison["receiver1_event_cadence_rms_ms"]),
        "receiver1_event_cadence_p90_absolute_residual_ms": float(
            comparison["receiver1_event_cadence_p90_absolute_residual_ms"]
        ),
        "same_pluto_cross_receiver": {
            "shared_stream": True,
            "shared_refill_and_transport": True,
            "matched_event_count": int(comparison["matched_event_count"]),
            "matched_event_cfo_jump_correlation": float(
                comparison["matched_event_cfo_jump_correlation"]
            ),
            "matched_event_median_absolute_time_difference_ms": float(
                comparison["matched_event_median_absolute_time_difference_ms"]
            ),
            "matched_event_timing_jump_within_2_samples_fraction": float(
                comparison["matched_event_timing_jump_within_2_samples_fraction"]
            ),
            "common_cell_timing_within_2_samples_fraction": float(
                comparison["timing_difference_within_2_samples_fraction"]
            ),
        },
    }


def _analyze_standard_v1_geometry(*, revision: str, path: str) -> dict[str, Any]:
    """Measure refill-edge geometry in the frozen eight-hour Standard V1 CSV."""

    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    )
    compressed = completed.stdout
    digest = f"sha256:{hashlib.sha256(compressed).hexdigest()}"
    decoded = gzip.decompress(compressed).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(decoded, newline="")))
    refill_period_s = 262_144 / 2_500_000

    def crosses_refill(row: dict[str, str]) -> bool:
        start_s = float(row["start_time_s"])
        end_s = float(row["end_time_s"])
        return math.floor((start_s + 1e-12) / refill_period_s) != math.floor(
            (end_s - 1e-12) / refill_period_s
        )

    def summary(selected: list[dict[str, str]]) -> dict[str, Any]:
        crossing = [row for row in selected if crosses_refill(row)]
        non_crossing = [row for row in selected if not crosses_refill(row)]
        crossing_qualified = sum(row["qualified"] == "True" for row in crossing)
        non_crossing_qualified = sum(row["qualified"] == "True" for row in non_crossing)
        crossing_rate = crossing_qualified / len(crossing)
        non_crossing_rate = non_crossing_qualified / len(non_crossing)
        return {
            "window_count": len(selected),
            "crossing_count": len(crossing),
            "crossing_fraction": len(crossing) / len(selected),
            "crossing_qualified_count": crossing_qualified,
            "crossing_qualification_fraction": crossing_rate,
            "non_crossing_count": len(non_crossing),
            "non_crossing_qualified_count": non_crossing_qualified,
            "non_crossing_qualification_fraction": non_crossing_rate,
            "non_crossing_to_crossing_qualification_ratio": (non_crossing_rate / crossing_rate),
        }

    aggregate = summary(rows)
    qualified_total = (
        aggregate["crossing_qualified_count"] + aggregate["non_crossing_qualified_count"]
    )
    aggregate["qualified_crossing_fraction"] = (
        aggregate["crossing_qualified_count"] / qualified_total
    )
    paths = {
        label: summary([row for row in rows if row["path"] == label])
        for label in sorted({row["path"] for row in rows})
    }
    return {
        "source_revision": revision,
        "source_path": path,
        "source_object": f"{revision}:{path}",
        "source_sha256": digest,
        "window_duration_ms": 75.0,
        "hypothetical_refill_samples": 262_144,
        "sample_rate_hz": 2_500_000,
        "refill_period_ms": refill_period_s * 1e3,
        "crossing_formula": (
            "floor((start_s + 1e-12)/T_refill) != floor((end_s - 1e-12)/T_refill)"
        ),
        "aggregate": aggregate,
        "paths": paths,
        "interpretation_limit": (
            "geometric refill-edge crossing is not proof that RF samples were lost"
        ),
    }


def _record_external_scanner_control(path: Path) -> dict[str, Any]:
    """Bind a separately audited scanner control to its immutable IQ digest."""

    capture_path = path.parent / "capture.json"
    capture = _load(capture_path)
    matching = [item for item in capture["records"] if item["path"] == str(path)]
    if len(matching) != 1:
        raise ValueError("scanner control is not uniquely declared by capture.json")
    record = matching[0]
    return {
        "analysis_recomputed_by_this_tool": False,
        "provenance": "separate read-only scanner natural-control stress test",
        "source_npy": str(path),
        "source_npy_sha256": _sha256(path),
        "array_payload_sha256_from_capture": f"sha256:{record['iq_sha256']}",
        "capture_json": str(capture_path),
        "capture_json_sha256": _sha256(capture_path),
        "sample_rate_hz": int(capture["configuration"]["sample_rate_hz"]),
        "dwell_ms": int(capture["configuration"]["dwell_ms"]),
        "kernel_buffers": int(capture["configuration"]["kernel_buffers"]),
        "sample_count": int(record["sample_count"]),
        "host_listen_ms": float(record["listen_ms"]),
        "receiver_id": 1,
        "track_start_s": 0.680,
        "track_end_s": 1.430,
        "passed_probe_count": 22,
        "excluded_alias_probe_count": 2,
        "ols_slope_hz_s": -3207.46,
        "ols_rms_hz": 14.69,
        "ols_maximum_absolute_residual_hz": 37.23,
        "hypothetical_refill_edge_count": 7,
        "hypothetical_edge_bracket_innovations_hz": [
            2.6,
            -12.8,
            17.8,
            -12.6,
            -31.8,
            -11.5,
            -7.6,
        ],
        "largest_absolute_hypothetical_edge_innovation_hz": 31.8,
        "close_edge_frame_count": 42,
        "closest_frame_pair_innovation_hz": 54.3,
        "close_edge_frame_rms_hz": 47.3,
        "interpretation_limit": (
            "one sparse diagnostic target, not current immutable Standard scanner; "
            "no device counter or absolute continuity proof"
        ),
    }


def analyze(
    *,
    dwell_input_dir: Path,
    blind_json: Path,
    boundary_json: Path,
    recording_root: Path,
    standard_segments_revision: str,
    standard_segments_path: str,
    scanner_control_npy: Path,
) -> dict[str, Any]:
    dwell_paths = sorted(dwell_input_dir.glob("T??-*.json"))
    if len(dwell_paths) != 10:
        raise ValueError(f"expected ten raw-dwell JSONs, found {len(dwell_paths)}")
    dwell_rows = []
    boundaries = []
    within_ramp_timing = []
    for path in dwell_paths:
        row, dwell_boundaries, dwell_within = _analyze_dwell(
            path,
            recording_root=recording_root,
        )
        dwell_rows.append(row)
        boundaries.extend(dwell_boundaries)
        within_ramp_timing.extend(dwell_within)

    large = [item for item in boundaries if abs(float(item["train_jump_hz"])) > LARGE_JUMP_HZ]
    small = [item for item in boundaries if abs(float(item["train_jump_hz"])) < SMALL_JUMP_HZ]
    one_refill_large = [
        item
        for item in large
        if item["host_start_excess_s"] is not None
        and item["timing_prediction_error_samples"] is not None
    ]
    validation_jumps = [float(item["validation_jump_hz"]) for item in boundaries]
    training_jumps = [float(item["train_jump_hz"]) for item in boundaries]
    validation_large = [
        item for item in boundaries if abs(float(item["validation_jump_hz"])) > LARGE_JUMP_HZ
    ]
    validation_small = [
        item for item in boundaries if abs(float(item["validation_jump_hz"])) < SMALL_JUMP_HZ
    ]

    def pooled_timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
        timing = [abs(float(item["timing_jump_samples"])) for item in rows]
        return {
            "count": len(rows),
            "median_absolute_timing_jump_samples": _median(timing),
            "timing_within_2_samples_count": sum(value <= TIMING_MATCH_SAMPLES for value in timing),
            "timing_within_2_samples_fraction": sum(
                value <= TIMING_MATCH_SAMPLES for value in timing
            )
            / len(timing),
            "negative_jump_fraction": sum(float(item["train_jump_hz"]) < 0.0 for item in rows)
            / len(rows),
            "median_signed_jump_hz": _median([float(item["train_jump_hz"]) for item in rows]),
        }

    predicted_corrections = [float(item["predicted_rate_correction_hz_s"]) for item in dwell_rows]
    observed_corrections = [float(item["observed_rate_correction_hz_s"]) for item in dwell_rows]
    cumulative_step_rates = [float(item["cumulative_step_rate_hz_s"]) for item in dwell_rows]
    stored_minus_local = [float(item["stored_minus_local_rate_hz_s"]) for item in dwell_rows]
    evidence = {
        "schema": "org.leo.research.refill-time-compression-sawtooth/v1",
        "algorithm": "refill-time-compression-sawtooth-audit-v1",
        "candidate_only": True,
        "payload_decoded": False,
        "host_retiming_diagnostic_only": True,
        "configuration": {
            "frame_rate_hz": FRAME_RATE_HZ,
            "large_jump_threshold_hz": LARGE_JUMP_HZ,
            "small_jump_threshold_hz": SMALL_JUMP_HZ,
            "timing_match_samples": TIMING_MATCH_SAMPLES,
            "timing_phase_formula": (
                "(detection_sample_start + local_epoch_sample) mod (sample_rate_hz / 750)"
            ),
            "cfo_jump_formula": (
                "trailing_ramp(boundary_midpoint) - leading_ramp(boundary_midpoint)"
            ),
            "host_excess_formula": (
                "delta(host_request_monotonic_ns.lower_ns) - refill_samples/sample_rate_hz"
            ),
            "host_retimed_rate_formula": (
                "stored_glrt_rate / (1 + median_host_start_excess/refill_period)"
            ),
        },
        "dwell_count": len(dwell_rows),
        "dwells": dwell_rows,
        "boundaries": boundaries,
        "pooled": {
            "boundary_count": len(boundaries),
            "large": pooled_timing(large),
            "small": pooled_timing(small),
            "small_from_t06_count": sum(item["dwell"] == "T06" for item in small),
            "large_contains_refill_count": sum(
                bool(item["contains_refill_boundary"]) for item in large
            ),
            "large_contains_refill_fraction": sum(
                bool(item["contains_refill_boundary"]) for item in large
            )
            / len(large),
            "small_contains_refill_count": sum(
                bool(item["contains_refill_boundary"]) for item in small
            ),
            "small_contains_refill_fraction": sum(
                bool(item["contains_refill_boundary"]) for item in small
            )
            / len(small),
            "within_ramp_probe_pair_count": len(within_ramp_timing),
            "within_ramp_median_absolute_timing_difference_samples": _median(within_ramp_timing),
            "within_ramp_timing_within_2_samples_count": sum(
                value <= TIMING_MATCH_SAMPLES for value in within_ramp_timing
            ),
            "within_ramp_timing_within_2_samples_fraction": sum(
                value <= TIMING_MATCH_SAMPLES for value in within_ramp_timing
            )
            / len(within_ramp_timing),
            "training_validation_jump_correlation": _pearson(training_jumps, validation_jumps),
            "training_validation_jump_median_absolute_difference_hz": _median(
                [
                    abs(training - validation)
                    for training, validation in zip(training_jumps, validation_jumps, strict=True)
                ]
            ),
            "training_large_validation_over_100_count": sum(
                abs(float(item["validation_jump_hz"])) > LARGE_JUMP_HZ for item in large
            ),
            "training_large_validation_same_sign_count": sum(
                float(item["validation_jump_hz"]) * float(item["train_jump_hz"]) > 0.0
                for item in large
            ),
            "validation_large_count": len(validation_large),
            "validation_large_median_absolute_timing_jump_samples": _median(
                [abs(float(item["timing_jump_samples"])) for item in validation_large]
            ),
            "validation_large_timing_within_2_samples_fraction": sum(
                abs(float(item["timing_jump_samples"])) <= TIMING_MATCH_SAMPLES
                for item in validation_large
            )
            / len(validation_large),
            "validation_small_count": len(validation_small),
            "validation_small_median_absolute_timing_jump_samples": _median(
                [abs(float(item["timing_jump_samples"])) for item in validation_small]
            ),
            "validation_small_timing_within_2_samples_fraction": sum(
                abs(float(item["timing_jump_samples"])) <= TIMING_MATCH_SAMPLES
                for item in validation_small
            )
            / len(validation_small),
            "one_refill_large_count": len(one_refill_large),
            "one_refill_large_timing_prediction_median_absolute_error_samples": _median(
                [abs(float(item["timing_prediction_error_samples"])) for item in one_refill_large]
            ),
            "opposite_sign_timing_prediction_median_absolute_error_samples": _median(
                [
                    abs(
                        circular_difference(
                            float(item["timing_jump_samples"])
                            + float(item["predicted_timing_jump_samples"]),
                            float(dwell_rows[0]["sample_rate_hz"]) / FRAME_RATE_HZ,
                        )
                    )
                    for item in one_refill_large
                ]
            ),
            "predicted_observed_rate_correction_correlation": _pearson(
                predicted_corrections, observed_corrections
            ),
            "host_retimed_rate_median_absolute_error_hz_s": _median(
                [abs(float(item["host_retimed_minus_local_hz_s"])) for item in dwell_rows]
            ),
            "predicted_stored_rate_median_absolute_error_hz_s": _median(
                [
                    abs(float(item["predicted_minus_observed_stored_rate_hz_s"]))
                    for item in dwell_rows
                ]
            ),
            "cumulative_step_vs_stored_local_correlation": _pearson(
                cumulative_step_rates, stored_minus_local
            ),
            "cumulative_step_rate_median_absolute_closure_hz_s": _median(
                [
                    abs(step - discrepancy)
                    for step, discrepancy in zip(
                        cumulative_step_rates, stored_minus_local, strict=True
                    )
                ]
            ),
        },
        "blind_470384": _analyze_blind(blind_json, recording_root=recording_root),
        "boundary_mechanism_470384": _analyze_boundary_mechanism(
            boundary_json, recording_root=recording_root
        ),
        "standard_v1_refill_geometry": _analyze_standard_v1_geometry(
            revision=standard_segments_revision,
            path=standard_segments_path,
        ),
        "external_scanner_control": _record_external_scanner_control(scanner_control_npy),
        "interpretation": {
            "dominant_hypothesis": (
                "unobserved RF time at refill handoffs is compressed out of stored sample time"
            ),
            "not_proven": (
                "host brackets are not device sample counters, so exact lost-sample counts remain unobserved"
            ),
            "safe_rate": (
                "within-refill/ramp received-CFO slope with a free intercept per discontinuous state"
            ),
        },
    }
    return evidence


def _save_figure(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="#f8fafb")


def render_alignment_figure(evidence: dict[str, Any], path: Path) -> None:
    blind = evidence["blind_470384"]
    mechanism = evidence["boundary_mechanism_470384"]
    boundaries = evidence["boundaries"]
    figure = Figure(figsize=(13.2, 5.4), layout="constrained")
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "The 104.9 ms sawtooth follows acquisition refill boundaries",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )

    event_residuals = [float(item["refill_time_residual_ms"]) for item in blind["events"]]
    mechanism_residuals = [float(item["refill_time_residual_ms"]) for item in mechanism["events"]]
    axes[0].scatter(
        range(1, len(event_residuals) + 1),
        event_residuals,
        s=31,
        color=RED,
        label="blind amplitude-gated (24)",
    )
    axes[0].scatter(
        range(1, len(mechanism_residuals) + 1),
        mechanism_residuals,
        s=27,
        color=BLUE,
        marker="x",
        linewidths=1.1,
        label="timing segments/direct frame (37)",
    )
    axes[0].axhline(0.0, color=INK, linewidth=1.2)
    axes[0].axhspan(-2.0, 2.0, color=RED, alpha=0.08)
    axes[0].set_title("A · Two 470384 event definitions land on refill edges", loc="left")
    axes[0].set_xlabel("event index within each cohort")
    axes[0].set_ylabel("event − nearest refill boundary (ms)")
    axes[0].text(
        0.03,
        0.96,
        f"blind median |offset| {blind['median_absolute_event_refill_residual_ms']:.3f} ms\n"
        f"direct-frame median |offset| "
        f"{mechanism['median_absolute_event_refill_residual_ms']:.3f} ms\n"
        f"refill period {blind['refill_period_ms']:.4f} ms",
        transform=axes[0].transAxes,
        va="top",
        color=INK,
    )
    axes[0].legend(loc="lower right", frameon=False)

    predictable = [
        item
        for item in boundaries
        if item["predicted_timing_jump_samples"] is not None
        and abs(float(item["train_jump_hz"])) > LARGE_JUMP_HZ
    ]
    predicted = [float(item["predicted_timing_jump_samples"]) for item in predictable]
    observed = [float(item["timing_jump_samples"]) for item in predictable]
    axes[1].scatter(predicted, observed, s=18, color=BLUE, alpha=0.64, label="large CFO jump")
    t06 = [
        item
        for item in boundaries
        if item["dwell"] == "T06" and item["predicted_timing_jump_samples"] is not None
    ]
    axes[1].scatter(
        [float(item["predicted_timing_jump_samples"]) for item in t06],
        [float(item["timing_jump_samples"]) for item in t06],
        s=31,
        facecolors="none",
        edgecolors=AMBER,
        linewidths=1.2,
        label="T06 no-bias control",
    )
    limit = float(evidence["dwells"][0]["sample_rate_hz"]) / FRAME_RATE_HZ / 2.0
    axes[1].plot([-limit, limit], [-limit, limit], color=INK, linewidth=1.2, label="prediction")
    axes[1].set_xlim(-limit, limit)
    axes[1].set_ylim(-limit, limit)
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].set_title("B · Omitted-time sign predicts the timing jump", loc="left")
    axes[1].set_xlabel("predicted timing jump from host-start excess (samples)")
    axes[1].set_ylabel("measured timing-lattice jump (samples)")
    axes[1].legend(loc="lower right", frameon=False)
    axes[1].text(
        0.03,
        0.96,
        f"one-refill large events n={len(predictable)}\n"
        f"median circular error {evidence['pooled']['one_refill_large_timing_prediction_median_absolute_error_samples']:.1f} samples",
        transform=axes[1].transAxes,
        va="top",
        color=INK,
    )
    for axis in axes:
        axis.grid(True, alpha=0.22)
    _save_figure(figure, path)


def render_rate_figure(evidence: dict[str, Any], path: Path) -> None:
    dwells = evidence["dwells"]
    labels = [item["dwell"] for item in dwells]
    x = np.arange(len(labels), dtype=float)
    figure = Figure(figsize=(13.2, 5.6), layout="constrained")
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Refill time compression quantitatively closes the long-versus-local rate gap",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )
    axes[0].axvspan(4.65, 5.35, color=AMBER, alpha=0.10)
    axes[0].plot(
        x,
        [float(item["stored_glrt_rate_hz_s"]) / 1e3 for item in dwells],
        "o-",
        color=RED,
        label="stored-time GLRT",
    )
    axes[0].plot(
        x,
        [float(item["host_retimed_diagnostic_rate_hz_s"]) / 1e3 for item in dwells],
        "s--",
        color=GREEN,
        label="host-retimed diagnostic",
    )
    axes[0].plot(
        x,
        [float(item["local_ramp_rate_hz_s"]) / 1e3 for item in dwells],
        "D-",
        color=BLUE,
        label="within-ramp local",
    )
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("received-CFO rate (kHz/s)")
    axes[0].set_title("A · Diagnostic retiming moves the long rate onto the local rate", loc="left")
    axes[0].legend(frameon=False, loc="lower right")
    axes[0].text(
        5.0,
        axes[0].get_ylim()[1],
        "T06\ncontinuous-refill counterexample",
        ha="center",
        va="top",
        color=AMBER,
        fontsize=9,
    )

    predicted = np.asarray([float(item["predicted_rate_correction_hz_s"]) / 1e3 for item in dwells])
    observed = np.asarray([float(item["observed_rate_correction_hz_s"]) / 1e3 for item in dwells])
    axes[1].scatter(predicted, observed, s=52, color=PURPLE)
    for label, px, py in zip(labels, predicted, observed, strict=True):
        color = AMBER if label == "T06" else INK
        axes[1].annotate(label, (px, py), xytext=(4, 4), textcoords="offset points", color=color)
    low = min(float(np.min(predicted)), float(np.min(observed))) - 0.12
    high = max(float(np.max(predicted)), float(np.max(observed))) + 0.12
    axes[1].plot([low, high], [low, high], color=INK, linewidth=1.2)
    axes[1].set_xlim(low, high)
    axes[1].set_ylim(low, high)
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].set_xlabel("predicted correction from median host-start excess (kHz/s)")
    axes[1].set_ylabel("observed local − stored correction (kHz/s)")
    axes[1].set_title("B · Compression prediction closes dwell-by-dwell", loc="left")
    axes[1].text(
        0.03,
        0.96,
        f"median stored-rate closure {evidence['pooled']['predicted_stored_rate_median_absolute_error_hz_s']:.1f} Hz/s\n"
        "host retiming is diagnostic only",
        transform=axes[1].transAxes,
        va="top",
        color=INK,
    )
    for axis in axes:
        axis.grid(True, alpha=0.22)
    _save_figure(figure, path)


def render_closeup_figure(evidence: dict[str, Any], path: Path) -> None:
    closeup = evidence["blind_470384"]["closeup"]
    points = closeup["points"]
    figure = Figure(figsize=(13.2, 7.0), layout="constrained")
    axes = figure.subplots(2, 1, sharex=True)
    figure.suptitle(
        "One refill contains one smooth CFO tooth; the state jumps at the handoff",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )
    times = [float(item["time_s"]) for item in points]
    residuals = [float(item["cfo_residual_hz"]) for item in points]
    timing = [float(item["timing_phase_samples"]) for item in points]
    axes[0].scatter(times, residuals, s=16, color=BLUE, alpha=0.68, label="blind 12/4 ms CFO")
    for index, line in enumerate(closeup["segment_lines"]):
        axes[0].plot(
            line["times_s"],
            line["cfo_residual_hz"],
            color=AMBER,
            linewidth=2.0,
            label="independent timing-segment fit" if index == 0 else None,
        )
    axes[0].axhline(0.0, color=INK, linewidth=1.0)
    axes[0].set_ylabel("CFO residual vs reset-inclusive line (Hz)")
    axes[0].set_title("A · Local ramps are smooth in stored samples", loc="left")
    axes[0].legend(frameon=False, loc="upper left")
    axes[1].scatter(times, timing, s=16, color=PURPLE, alpha=0.72)
    axes[1].set_ylabel("absolute frame-lattice phase (samples)")
    axes[1].set_xlabel("capture stored-sample time (s)")
    axes[1].set_title("B · Timing phase changes when stored RF time is omitted", loc="left")
    for axis in axes:
        for index, refill_time in enumerate(closeup["refill_boundaries_s"]):
            axis.axvline(
                refill_time,
                color=RED,
                linestyle="--",
                linewidth=1.0,
                alpha=0.72,
                label="262,144-sample refill edge" if axis is axes[0] and index == 0 else None,
            )
        for event_time in closeup["blind_events_s"]:
            axis.axvline(event_time, color=INK, linewidth=0.8, alpha=0.35)
        axis.grid(True, alpha=0.20)
    axes[0].legend(frameon=False, loc="upper left")
    _save_figure(figure, path)


def _fmt_fraction(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def write_report(evidence: dict[str, Any], path: Path) -> None:
    pooled = evidence["pooled"]
    blind = evidence["blind_470384"]
    mechanism = evidence["boundary_mechanism_470384"]
    standard = evidence["standard_v1_refill_geometry"]
    scanner = evidence["external_scanner_control"]
    rows = []
    for item in evidence["dwells"]:
        large = item["large"]
        timing = (
            f"{large['median_absolute_timing_jump_samples']:.1f} / "
            f"{_fmt_fraction(large['timing_within_2_samples_fraction'])}"
            if large["count"]
            else "—"
        )
        rows.append(
            "| {dwell} | {edge} | {ramps}/{boundaries} | {cadence:.2f} | {jump:+.1f} | "
            "{large_n} | {timing} | {excess:+.2f} | {stored:.3f} | {local:.3f} | "
            "{retimed:.3f} | {correction:+.3f} |".format(
                dwell=item["dwell"],
                edge=item["edge"],
                ramps=item["ramp_count"],
                boundaries=item["boundary_count"],
                cadence=item["median_boundary_spacing_ms"],
                jump=item["median_signed_jump_hz"],
                large_n=large["count"],
                timing=timing,
                excess=item["median_host_start_excess_ms"],
                stored=item["stored_glrt_rate_hz_s"] / 1e3,
                local=item["local_ramp_rate_hz_s"] / 1e3,
                retimed=item["host_retimed_diagnostic_rate_hz_s"] / 1e3,
                correction=item["observed_rate_correction_hz_s"] / 1e3,
            )
        )
    sources = []
    for item in evidence["dwells"]:
        sources.append(
            f"| {item['dwell']} | `{item['source_json_sha256']}` | "
            f"`{item['recording_manifest_sha256']}` | `{item['timeline_sha256']}` |"
        )
    sources.append(
        f"| 470384 blind | `{blind['source_json_sha256']}` | "
        f"`{blind['recording_manifest_sha256']}` | `{blind['timeline_sha256']}` |"
    )
    sources.append(
        f"| 470384 boundary mechanism | `{mechanism['source_json_sha256']}` | "
        f"`{mechanism['recording_manifest_sha256']}` | "
        f"`{mechanism['timeline_sha256']}` |"
    )
    sources.append(
        f"| Standard V1 segments @ `{standard['source_revision'][:7]}` | "
        f"`{standard['source_sha256']}` | — | — |"
    )
    sources.append(
        f"| External scanner natural control | `{scanner['source_npy_sha256']}` | "
        f"`{scanner['capture_json_sha256']}` | — |"
    )
    scanner_innovations = ", ".join(
        f"{value:+.1f}" for value in scanner["hypothetical_edge_bracket_innovations_hz"]
    )
    geometry_rows = []
    for label, item in standard["paths"].items():
        geometry_rows.append(
            f"| {label} | {item['crossing_count']:,} | "
            f"{_fmt_fraction(item['crossing_qualification_fraction'])} | "
            f"{item['non_crossing_count']:,} | "
            f"{_fmt_fraction(item['non_crossing_qualification_fraction'])} | "
            f"{item['non_crossing_to_crossing_qualification_ratio']:.2f}× |"
        )
    text = rf"""# Refill-time compression explains the Starlink CFO sawtooth

Date: 2026-08-24 UTC

Status: deterministic, read-only research audit; candidate-only receiver evidence; no
payload decoded and no satellite identified

## Executive conclusion

The approximately 105 ms CFO sawtooth is locked to the acquisition buffer, not merely
close to an unexplained protocol period. Every audited dwell was recorded in
{evidence["dwells"][0]["refill_samples"]:,}-sample refills at
{evidence["dwells"][0]["sample_rate_hz"] / 1e6:.1f} MS/s, giving an exact stored-sample
period of **{evidence["dwells"][0]["refill_period_ms"]:.4f} ms**. The independently
reported receiver-1 event clock was
**{mechanism["receiver1_event_cadence_period_ms"]:.4f} ms** with
{mechanism["receiver1_event_cadence_rms_ms"]:.3f} ms RMS, as frozen in the
[boundary-mechanism audit](2026_08_23_470384_boundary_mechanism.md). In the blind
`470384` interval, all
{blind["event_count"]} direct timing+CFO events fall within
{blind["maximum_absolute_event_refill_residual_ms"]:.3f} ms of a refill edge, with
{blind["median_absolute_event_refill_residual_ms"]:.3f} ms median absolute offset.
The separately defined {mechanism["event_count"]}-event timing-segment cohort has
{mechanism["median_absolute_event_refill_residual_ms"]:.3f} ms median,
{mechanism["p90_absolute_event_refill_residual_ms"]:.3f} ms p90, and
{mechanism["maximum_absolute_event_refill_residual_ms"]:.3f} ms maximum absolute offset.

Across ten independently selected raw-dwell tracks, large CFO discontinuities and timing
lattice changes co-occur at refills. Of {pooled["large"]["count"]} adjacent ramp cuts with
|jump| > 100 Hz, {pooled["large_contains_refill_count"]} ({_fmt_fraction(pooled["large_contains_refill_fraction"])})
bracket a refill edge and only {pooled["large"]["timing_within_2_samples_count"]}
({_fmt_fraction(pooled["large"]["timing_within_2_samples_fraction"])}) preserve timing to
two samples. For {pooled["small"]["count"]} cuts below 30 Hz, only
{pooled["small_contains_refill_count"]} ({_fmt_fraction(pooled["small_contains_refill_fraction"])})
bracket a refill, while {pooled["small"]["timing_within_2_samples_count"]}
({_fmt_fraction(pooled["small"]["timing_within_2_samples_fraction"])}) preserve timing.
T06 supplies the necessary counterexample: its selected stream refilled at essentially
real time, its long and local rates differ by only 3.1 Hz/s, and 48 of its artificial
maximum-span ramp cuts have small frequency jumps with stable timing.

The parsimonious mechanism is **stored-time compression**. Most refills arrive after more
wall-clock time than the 104.8576 ms represented by their stored samples. When the
unobserved interval is omitted from concatenated sample time, smooth physical-time CFO
motion appears as a discrete frequency step and a frame-lattice phase jump at the refill
handoff. A long line against stored sample index absorbs those steps and becomes too
negative. The within-refill/ramp slope is the defensible received-CFO-rate candidate.

This is strong causal evidence, but not an exact lost-sample proof: the timeline contains
host request brackets, not hardware sample counters, and records continuity as unknown.
The host-retimed numbers below are therefore **diagnostic only** and must not become a
production timebase or persisted scientific rate.

![Refill and timing alignment](figures/2026_08_24_refill_time_compression_sawtooth/refill-event-alignment-and-timing.png)

**Figure 1.** Two event definitions land on refill edges. The 24-event blind cohort is
amplitude gated (`|CFO jump| >= 100 Hz`, timing jump >= 20 samples), while the 37-event
cohort starts from timing-segment boundaries and re-estimates CFO independently in
1.333 ms frames without a CFO-jump gate. They are related views of the same four-second
case, not 61 independent events. For one-refill ten-dwell events, signed host-start excess
predicts the independently recovered frame-lattice jump. T06 is a no-bias control, not a
transmitter-event interpretation.

The 37-event cohort is the cleaner amplitude test. Host-start excess versus direct-frame
CFO jump has correlation {mechanism["host_excess_direct_jump_correlation"]:.4f}; OLS gives
{mechanism["host_excess_direct_jump_ols_slope_hz_s"] / 1e3:.4f} kHz/s slope,
{mechanism["host_excess_direct_jump_ols_intercept_hz"]:+.1f} Hz intercept,
R²={mechanism["host_excess_direct_jump_ols_r_squared"]:.4f}, and
{mechanism["host_excess_direct_jump_ols_rms_hz"]:.1f} Hz RMS. The magnitude of omitted
frame-lattice phase predicts measured timing-separation magnitude with correlation
{mechanism["timing_magnitude_prediction_correlation"]:.4f} and
{mechanism["timing_magnitude_prediction_median_absolute_error_samples"]:.1f} samples
median absolute error.

## Why a refill gap creates both a CFO step and a timing jump

Let a stored refill contain \(N\) samples at sample rate \(F_s\), so its stored duration is

\[
T_b = \frac{{N}}{{F_s}}.
\]

Let successive host refill starts be separated by \(T_b + \delta\). If \(\delta\)
corresponds to RF time not represented in the concatenated samples, a smooth
received-CFO rate \(\dot f_{{\mathrm{{local}}}}\) produces

\[
\Delta f_{{\mathrm{{jump}}}} \approx \dot f_{{\mathrm{{local}}}}\,\delta,
qquad
\dot f_{{\mathrm{{stored}}}} \approx
\dot f_{{\mathrm{{local}}}}\left(1+\frac{{\delta}}{{T_b}}\right).
\]

The stored frame lattice is shifted by the omitted sample count, modulo the nominal
Starlink frame period:

\[
\Delta n_{{\mathrm{{frame}}}} = -\delta F_s \pmod{{F_s/750}}.
\]

The sign is empirically decisive. Among {pooled["one_refill_large_count"]} one-refill large
events, the omitted-time sign gives a median circular prediction error of
{pooled["one_refill_large_timing_prediction_median_absolute_error_samples"]:.2f} samples;
the opposite sign gives {pooled["opposite_sign_timing_prediction_median_absolute_error_samples"]:.2f}
samples. Inside accepted ramps, where the frequency-only partition never inspected timing,
{pooled["within_ramp_timing_within_2_samples_count"]} of
{pooled["within_ramp_probe_pair_count"]} consecutive probe pairs
({_fmt_fraction(pooled["within_ramp_timing_within_2_samples_fraction"])}) preserve timing
within two samples.

## Acquisition-path evidence and timebase boundary

The production dwell path has a concrete opportunity for this mechanism. The
[coordinator capture loop](../src/leo/acquisition/coordinator.py#L466-L516) calls
`source.read_block(refill_samples)` and then `stream_writer.append(block)` before its next
read. The [Pluto adapter](../src/leo/radio/pluto_adapter.py#L156-L180) brackets the
underlying `device.read_block`. On the same per-radio path,
[`StreamBundleWriter.append`](../src/leo/storage/writer.py#L203-L249) synchronously writes
IQ into the current zstd stream and writes compressed timeline metadata; shard completion
closes zstd, flushes, `fsync`s, and renames through
[`_CompressedFileWriter.finish`](../src/leo/storage/writer.py#L78-L106). Therefore CPU or
storage delay can postpone the next refill request. This code path establishes a plausible
causal channel; without a device sample counter it does not prove which RF samples, if any,
were lost upstream.

All Standard, frozen/global, and current local-window time coordinates relevant here use
**stored sample coordinate divided by sample rate**. The probe schedule writes
`time_s = sample_start / Fs`, the global Doppler fit uses
`absolute_epoch_sample / Fs`, and Pilot Doppler Segments V1 starts each window at
`probe_sample_start / Fs`; see [Standard probes](../src/leo/analysis/standard/probes.py#L68-L79),
[global Doppler tracking](../src/leo/analysis/doppler/tracking.py#L100-L124), and
[Pilot Doppler Segments V1](../src/leo/analysis/starlink/pilot_doppler_segments.py#L78-L153).
None of those scientific fits consumes host timeline timestamps. Thus an unrepresented RF
interval is necessarily compressed out of Standard/frozen time.

Scanner acquisition is a useful existing-corpus control with different geometry. It sets
`rx_buffer_size = dwell_samples` and makes one `device.rx()` call per tuned target; see
[Pluto scanner](../src/leo/radio/pluto_scanner.py#L73-L130). There are no repeated
262,144-sample application refill handoffs *inside* one scanner target. That distinction
predicts no 104.8576 ms application-refill sawtooth within a target, but the scanner still
lacks device counters and therefore cannot prove absolute RF continuity.

A separate read-only natural-control audit of the sealed 1.5 s diagnostic target
`ch2-lower.npy` is consistent with that prediction; this tool binds its source hashes but
does **not** recompute its GLRT/frame analysis. The RX1 branch from
{scanner["track_start_s"]:.3f}–{scanner["track_end_s"]:.3f} s had
{scanner["passed_probe_count"]} passing probes and an OLS rate of
{scanner["ols_slope_hz_s"] / 1e3:.4f} kHz/s at {scanner["ols_rms_hz"]:.2f} Hz RMS.
Innovations bracketing seven hypothetical 104.8576 ms edges were
{scanner_innovations} Hz; none was a repeated >100 Hz drop. Forty-two frame CFOs around
one edge were also smooth at {scanner["close_edge_frame_rms_hz"]:.1f} Hz RMS. This is one
sparse historical diagnostic target, not a current 80/120 ms Standard scanner product.
Its single host call took {scanner["host_listen_ms"] / 1e3:.2f} s to return
{scanner["dwell_ms"] / 1e3:.1f} s of stored samples, which reinforces why host duration is
diagnostic rather than an exact RF timebase.

## Ten-dwell rate closure

![Ten-dwell rate closure](figures/2026_08_24_refill_time_compression_sawtooth/ten-dwell-rate-closure.png)

**Figure 2.** The red stored-time line is the existing reset-inclusive GLRT rate. Blue is
the free-intercept within-ramp rate. Green divides the stored rate by the median host-time
stretch and is diagnostic only. T06 shows that the estimator does not manufacture a
correction when refills remain near real time.

| Dwell | Edge | Ramps/cuts | Median cut cadence (ms) | Median jump (Hz) | Large cuts | Median abs timing jump / within 2 samples | Median host excess (ms) | Stored GLRT (kHz/s) | Local ramp (kHz/s) | Host-retimed diagnostic (kHz/s) | Local−stored (kHz/s) |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

The host-stretch prediction closes the stored rate to a median
{pooled["predicted_stored_rate_median_absolute_error_hz_s"]:.1f} Hz/s across the ten
dwells. Independently, the summed fitted frequency steps per boundary span correlate
{pooled["cumulative_step_vs_stored_local_correlation"]:.3f} with the stored-minus-local
rate discrepancy and close it to {pooled["cumulative_step_rate_median_absolute_closure_hz_s"]:.1f}
Hz/s median absolute error. This is a decomposition of the receiver observable, not a
satellite association.

The CFO jumps are not a training-only illusion. Odd Qin symbols, excluded from each
frame-CFO maximization, reproduce the boundary jumps with correlation
{pooled["training_validation_jump_correlation"]:.4f} and
{pooled["training_validation_jump_median_absolute_difference_hz"]:.1f} Hz median absolute
difference. Of the {pooled["large"]["count"]} training-defined large jumps,
{pooled["training_large_validation_over_100_count"]} remain above 100 Hz on held-out
symbols and all {pooled["training_large_validation_same_sign_count"]} keep their sign.

## Close-up mechanism

![Refill close-up](figures/2026_08_24_refill_time_compression_sawtooth/refill-closeup-geometry.png)

**Figure 3.** A 650 ms blind raw-IQ close-up from `470384`. Each refill contains a smooth
local CFO tooth. Both the CFO intercept and absolute receiver frame-lattice phase change
at the refill handoff. Black lines are independently declared timing+CFO events; red
dashed lines are exact persisted refill boundaries.

In the complete four-second blind path, a fixed-effect regression giving every timing
segment its own intercept estimates {blind["fixed_effect_common_slope_hz_s"] / 1e3:.4f}
kHz/s with {blind["fixed_effect_rms_hz"]:.2f} Hz RMS. The reset-inclusive global line is
{blind["global_slope_hz_s"] / 1e3:.4f} kHz/s. All
{blind["fitted_adjacent_jump_count"]} adjacent fitted segment jumps are
negative, with median {blind["fitted_adjacent_jump_median_hz"]:.1f} Hz and 10–90% range
{blind["fitted_adjacent_jump_p10_hz"]:.1f} to {blind["fitted_adjacent_jump_p90_hz"]:.1f}
Hz. Their cumulative contribution is {blind["fitted_jump_sum_per_span_hz_s"] / 1e3:.4f}
kHz/s, compared with {blind["global_minus_median_local_slope_hz_s"] / 1e3:.4f} kHz/s for
global minus median local rate.

At the {blind["event_count"]} directly bracketed blind events, host-start excess is
{blind["median_host_start_excess_ms"]:.2f} ms median. Jump divided by excess is
{blind["jump_per_excess_median_hz_s"] / 1e3:.4f} kHz/s; a through-zero fit gives
{blind["jump_excess_through_zero_slope_hz_s"] / 1e3:.4f} kHz/s. Both agree with the
within-segment rate family. Using the fixed-effect rate predicts individual jumps with
{blind["fixed_effect_jump_prediction_median_absolute_error_hz"]:.1f} Hz median absolute
error.

## Distinction from the PNT paper's genuine one-second corrections

Kozhaya, Saroufim, and Kassas report genuine, abrupt **one-second** CFO corrections in
pre-2024 full-OFDM-beacon tracking and explicitly distinguish the data-less pilot tones,
which did not show that contamination. They also report that these OFDM corrections were
barely observed after 2024. See [“Unveiling Starlink for PNT,” *Navigation* 72(1),
DOI 10.33012/navi.685](https://doi.org/10.33012/navi.685), Sections 7.2–7.3.

That published phenomenon must not be conflated with this result. This repository uses a
Qin edge-pilot observable, and the cadence here is the exact 104.8576 ms application
refill period, not an approximately one-second transmitter clock. Refill alignment,
host-excess scaling, and the T06 no-bias control specifically diagnose the receiver path.

## Hypothesis audit

| Hypothesis | Prediction | Result | Disposition |
| --- | --- | --- | --- |
| 20 ms/12 ms analysis-window artifact | Events move or disappear on another grid | Blind 12/4 ms search preserved the events | Rejected by prior blind analysis |
| Pure inter-frame carrier-phase alias | Arbitrary whole-frame phase changes move frame CFO | Magnitude-based 1.333 ms CFO is invariant; timing also changes | Rejected by prior frame control |
| Starlink scheduler or oscillator command every ≈105 ms | Period is independent of receiver buffer geometry | {mechanism["receiver1_event_cadence_period_ms"]:.4f} ms matches the {mechanism["refill_period_ms"]:.4f} ms refill; event size follows host excess; T06 loses the sawtooth when one stream refills in real time | Strongly disfavored as the primary cause |
| Receiver-channel optimizer failure | RX channels change independently | {mechanism["same_pluto_cross_receiver"]["matched_event_count"]} matched RX0/RX1 events have CFO-jump correlation {mechanism["same_pluto_cross_receiver"]["matched_event_cfo_jump_correlation"]:.3f}, but both channels share `{mechanism["radio_id"]}` stream/refill/transport | Per-channel optimizer rejected; shared acquisition remains |
| Stored-time compression at refill handoff | CFO and frame timing jump at refill; jump ≈ local rate × omitted time; changing refill behavior changes bias | All signatures observed, including T06 counterexample | Dominant supported explanation |
| Pure orbital Doppler in the frozen line | One smooth stored-time rate predicts held-out frame CFO | Free-intercept local rate and odd-Qin holdout are materially better | Rejected for the frozen rate |

## Safe compensation now

1. Treat every unverified refill boundary as a hard timing/phase discontinuity.
2. Estimate every frame CFO independently from the exact source timing/CFO neighborhood:
   fit even Qin symbols inside one approximately 1.333 ms frame, validate on odd Qin
   symbols, and retain the rolled-pilot control.
3. Join frames only within frequency- and timing-consistent refill/ramp support. Fit one
   shared robust rate with a free CFO intercept per ramp. Do not smooth a single Kalman
   state across an unverified refill edge.
4. Publish the within-ramp received-CFO rate, whole-ramp uncertainty, held-out RMS, sample
   continuity grade, and reset count. Keep the stored long line only as a discrepancy
   diagnostic.
5. Do **not** replace sample time with host bracket time in production. Host requests can
   include buffering, transfer latency, and isolated stalls. Green values in Figure 2 are
   a mechanism check, not calibrated RF timestamps.

## Current Standard V1 limitation and additive V2 plan

Standard `pilot-doppler-segments.v1` already analyzes complete frames inside disjoint
75 ms windows and qualifies local lines with coverage, gap, modulo-π phase, control-pilot,
line-RMS, held-out prediction, and local/Kalman agreement gates. It is **not** exact
refill compensation: window starts and the frozen model both use stored `sample/Fs`, and
the analyzer is not refill-boundary-aware. A 75 ms window that straddles an omitted-time
handoff can be rejected by its line-RMS or held-out gates; qualified windows wholly within
one refill likely explain the observed local-versus-frozen improvement. See the
[V1 window construction and gates](../src/leo/analysis/starlink/pilot_doppler_segments.py#L60-L170).

A frozen eight-hour Standard V1 aggregate provides independent geometric corroboration.
Of {standard["aggregate"]["window_count"]:,} 75 ms dwell windows,
{standard["aggregate"]["crossing_count"]:,}
({_fmt_fraction(standard["aggregate"]["crossing_fraction"])}) cross a hypothetical
104.8576 ms refill edge. Only {standard["aggregate"]["crossing_qualified_count"]:,}
({_fmt_fraction(standard["aggregate"]["crossing_qualification_fraction"])}) crossing
windows qualify, versus {standard["aggregate"]["non_crossing_qualified_count"]:,} of
{standard["aggregate"]["non_crossing_count"]:,}
({_fmt_fraction(standard["aggregate"]["non_crossing_qualification_fraction"])})
non-crossing windows—a {standard["aggregate"]["non_crossing_to_crossing_qualification_ratio"]:.2f}×
yield ratio. The direction holds within every path:

| Path | Crossing windows | Crossing qualified | Non-crossing windows | Non-crossing qualified | Non-cross/cross yield |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(geometry_rows)}

This reduces path-mixture confounding, but it is not a loss detector: edge crossing is
only geometry, T06 demonstrates that a refill can be continuous, and
{_fmt_fraction(standard["aggregate"]["qualified_crossing_fraction"])} of all qualified
windows still cross an edge.

The compatible production change is an additive V2 product, preserving immutable V1:

1. bind each candidate window to recording-timeline refill evidence and publish a
   continuity grade (`within_refill`, `crosses_unverified_refill`, or hardware-proven);
2. split or relocate local windows so no fit silently bridges an unverified handoff;
3. fit a common local received-CFO rate with a free intercept per continuous piece;
4. retain V1 and the frozen line unchanged as comparison diagnostics; and
5. prohibit host-retimed rates from scientific contracts until device-counter continuity
   is recorded and calibrated.

## Decisive acquisition experiments

1. Record the same stable injected tone and live Starlink edge with refill sizes 131,072,
   262,144, and 524,288. A capture artifact must move its tooth period as `N/Fs`.
2. Put radio reads on dedicated threads with a bounded in-memory writer queue. Compression,
   shard close, `fsync`, and rename must never delay the next refill. The sawtooth and
   local/frozen gap should collapse when median start spacing approaches `N/Fs`.
3. Persist AD9361/device sample counters and hardware overflow evidence. Synthetic writer
   stalls must create an explicit discontinuity rather than silently contiguous stored
   indices.
4. Reanalyze T06's simultaneous stream-1 against its near-real-time stream-0. It is an
   existing natural differential control with no new RF collection.
5. Compare two physically independent Plutos observing one injected tone. Same-channel
   RX0/RX1 agreement is insufficient because both channels share a refill and transport.
6. After continuity is proven, compare the debiased rate with TLE curvature and a stable
   receiver/LNB reference before converting it to range acceleration.

## Selection dependencies and limits

- The ten tracks were selected earlier by persisted GLRT strength, not by this timing or
  refill result. All selected examples happen to use RX1, so the cohort is not a receiver
  comparison.
- Ramp partitioning uses frequency and gaps, not timing, but its 125 ms/maximum-lock bound
  creates cuts even in a continuous carrier. T06 demonstrates those harmless cuts. A cut
  count is not an event count.
- The 461 ramp pairs are clustered within ten dwells. The 52 small jumps are dominated by
  T06 ({pooled["small_from_t06_count"]}/{pooled["small"]["count"]}); rows are not
  independent statistical trials.
- The blind 24-event and timing-segment 37-event cohorts reuse the same `470384` IQ and
  are intentionally not pooled. Their different gates answer alignment and amplitude
  questions separately.
- `local_epoch_sample` is receiver sample-lattice phase, not transmit code phase or
  pseudorange.
- Host request start is the only timeline timestamp that predicts the sign and phase
  here, but it remains a host-side bracket. Without device counters, exact omitted RF
  duration is an inference.
- Local received-CFO rate can still contain satellite motion, transmitter clock/control,
  LNB drift, and receiver/sample-clock drift. This report repairs the stored-time bias;
  it does not identify a spacecraft or prove orbital Doppler.

## Related evidence and references

- [Blind timing–CFO comprehensive audit](2026_08_23_470384_blind_timing_cfo_comprehensive.md)
  — independently timed 12/4 ms cells and negative controls.
- [Boundary-mechanism audit](2026_08_23_470384_boundary_mechanism.md) — direct-frame CFO,
  crossfit, grid shifts, and same-Pluto RX0/RX1 comparison.
- [Complete sub-second pilot lattice](2026_08_22_subsecond_pilot_structure.md) —
  raw 1.333 ms frame evidence and local-versus-frozen rate comparison.
- [Ten-dwell raw Doppler pipeline](2026_08_24_ten_dwell_raw_doppler_pipeline.md) — frozen
  per-dwell inputs, ramp construction, odd-Qin holdout, and rate results reused here.
- [Kozhaya, Saroufim, and Kassas, “Unveiling Starlink for PNT”](https://doi.org/10.33012/navi.685)
  — full-OFDM PNT receiver and the distinct approximately one-second corrections.

## Reproduction and immutable inputs

Generate evidence, figures, and this report from the ten frozen raw-dwell JSONs, blind
`470384` JSON, frozen boundary-mechanism JSON, verified recording manifests, and
compressed timeline records. The Standard V1 geometry audit reads
`{standard["source_path"]}` directly from frozen commit `{standard["source_revision"]}`.
The external scanner NPY is hash-bound only; its separately reported metrics are not
recomputed by this command:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/report_refill_time_compression_sawtooth.py
```

Render again without reading `/srv/bulk`:

```bash
.venv/bin/python tools/report_refill_time_compression_sawtooth.py \
  --reuse-evidence reports/figures/2026_08_24_refill_time_compression_sawtooth/refill-time-compression-evidence.json
```

Machine evidence:
[`refill-time-compression-evidence.json`](figures/2026_08_24_refill_time_compression_sawtooth/refill-time-compression-evidence.json)

| Input | Primary input SHA-256 | Manifest/capture SHA-256 | Selected timeline SHA-256 |
| --- | --- | --- | --- |
{chr(10).join(sources)}

The result is deterministic for these frozen inputs. The report tool records every source
hash and does not modify recordings, timelines, sealed analysis products, or database
state.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render(evidence: dict[str, Any], *, output_dir: Path, report: Path) -> None:
    render_alignment_figure(evidence, output_dir / "refill-event-alignment-and-timing.png")
    render_rate_figure(evidence, output_dir / "ten-dwell-rate-closure.png")
    render_closeup_figure(evidence, output_dir / "refill-closeup-geometry.png")
    write_report(evidence, report)


def main() -> None:
    args = _arguments()
    if args.reuse_evidence is not None:
        evidence = _load(args.reuse_evidence)
    else:
        evidence = analyze(
            dwell_input_dir=args.dwell_input_dir,
            blind_json=args.blind_json,
            boundary_json=args.boundary_json,
            recording_root=args.recording_root,
            standard_segments_revision=args.standard_segments_revision,
            standard_segments_path=args.standard_segments_path,
            scanner_control_npy=args.scanner_control_npy,
        )
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    render(evidence, output_dir=args.output_dir, report=args.report)


if __name__ == "__main__":
    main()
