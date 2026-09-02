#!/usr/bin/env python3
"""Analyze independent native-25 PSS timing against paired dual-2.5 GLRT tracks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FRAME_RATE_HZ = 750.0
FRAME_PERIOD_S = 1.0 / FRAME_RATE_HZ
GLRT_ALIAS_SPACING_HZ = 2_500_000.0 / 11.0
LNB_LO_HZ = 9_750_000_000.0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--pss-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def circular_residual(observed: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    return (observed - predicted + FRAME_PERIOD_S / 2.0) % FRAME_PERIOD_S - (FRAME_PERIOD_S / 2.0)


def robust_polynomial(
    times_s: np.ndarray,
    phases_s: np.ndarray,
    *,
    degree: int,
    origin_s: float,
) -> dict[str, Any]:
    order = np.argsort(times_s)
    times_s = times_s[order]
    phases_s = phases_s[order]
    centered_s = times_s - origin_s
    unwrapped_s = np.unwrap(phases_s / FRAME_PERIOD_S * 2.0 * np.pi) * (
        FRAME_PERIOD_S / (2.0 * np.pi)
    )
    design = np.vander(centered_s, degree + 1)
    coefficients = np.linalg.lstsq(design, unwrapped_s, rcond=None)[0]
    weights = np.ones_like(unwrapped_s)
    for _ in range(50):
        residuals_s = unwrapped_s - design @ coefficients
        median_s = float(np.median(residuals_s))
        scale_s = 1.4826 * float(np.median(np.abs(residuals_s - median_s)))
        if not math.isfinite(scale_s) or scale_s <= 1e-12:
            break
        cutoff_s = 1.345 * scale_s
        absolute_s = np.abs(residuals_s - median_s)
        weights = np.where(
            absolute_s <= cutoff_s,
            1.0,
            cutoff_s / np.maximum(absolute_s, 1e-15),
        )
        updated = np.linalg.lstsq(
            design * np.sqrt(weights)[:, None],
            unwrapped_s * np.sqrt(weights),
            rcond=None,
        )[0]
        if np.allclose(updated, coefficients, rtol=0.0, atol=1e-14):
            coefficients = updated
            break
        coefficients = updated
    fitted_s = design @ coefficients
    residuals_s = circular_residual(phases_s, fitted_s)
    derivative = np.polyder(coefficients)
    second_derivative = np.polyder(coefficients, 2)
    phase_rate = float(np.polyval(derivative, 0.0))
    phase_acceleration = float(np.polyval(second_derivative, 0.0))
    return {
        "degree": degree,
        "origin_s": origin_s,
        "coefficients_descending_s": coefficients.tolist(),
        "phase_at_origin_s": float(np.polyval(coefficients, 0.0) % FRAME_PERIOD_S),
        "phase_rate_s_s": phase_rate,
        "phase_acceleration_s_s2": phase_acceleration,
        "physical_fractional_doppler": -phase_rate,
        "physical_fractional_doppler_rate_s_inverse": -phase_acceleration,
        "same_sign_fractional_doppler": phase_rate,
        "same_sign_fractional_doppler_rate_s_inverse": phase_acceleration,
        "rms_residual_us": rms(residuals_s) * 1e6,
        "maximum_absolute_residual_us": float(np.max(np.abs(residuals_s))) * 1e6,
        "robust_weight_below_one_count": int(np.count_nonzero(weights < 1.0)),
        "times_s": times_s,
        "phases_s": phases_s,
        "unwrapped_s": unwrapped_s,
        "fitted_s": fitted_s,
        "residuals_s": residuals_s,
    }


def json_fit(fit: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fit.items() if not isinstance(value, np.ndarray)}


def glrt_fit(
    times_s: np.ndarray,
    cfo_hz: np.ndarray,
    *,
    origin_s: float,
    degree: int | None = None,
) -> dict[str, Any]:
    centered_s = times_s - origin_s
    if degree is None:
        degree = 2 if times_s.size >= 6 else 1
    degree = min(degree, int(times_s.size) - 1)
    design = np.vander(centered_s, degree + 1)
    coefficients = np.linalg.lstsq(design, cfo_hz, rcond=None)[0]
    weights = np.ones_like(cfo_hz)
    for _ in range(40):
        residuals_hz = cfo_hz - design @ coefficients
        median_hz = float(np.median(residuals_hz))
        scale_hz = 1.4826 * float(np.median(np.abs(residuals_hz - median_hz)))
        if not math.isfinite(scale_hz) or scale_hz <= 1e-9:
            break
        cutoff_hz = 1.345 * scale_hz
        absolute_hz = np.abs(residuals_hz - median_hz)
        weights = np.where(
            absolute_hz <= cutoff_hz,
            1.0,
            cutoff_hz / np.maximum(absolute_hz, 1e-12),
        )
        updated = np.linalg.lstsq(
            design * np.sqrt(weights)[:, None],
            cfo_hz * np.sqrt(weights),
            rcond=None,
        )[0]
        if np.allclose(updated, coefficients, rtol=0.0, atol=1e-8):
            coefficients = updated
            break
        coefficients = updated
    fitted_hz = design @ coefficients
    residuals_hz = cfo_hz - fitted_hz
    derivative = np.polyder(coefficients)
    second_derivative = np.polyder(coefficients, 2)
    return {
        "degree": degree,
        "origin_s": origin_s,
        "coefficients_descending_hz": coefficients.tolist(),
        "cfo_at_origin_hz": float(np.polyval(coefficients, 0.0)),
        "cfo_rate_at_origin_hz_s": float(np.polyval(derivative, 0.0)),
        "cfo_acceleration_at_origin_hz_s2": float(np.polyval(second_derivative, 0.0)),
        "rms_residual_hz": rms(residuals_hz),
        "maximum_absolute_residual_hz": float(np.max(np.abs(residuals_hz))),
        "times_s": times_s,
        "cfo_hz": cfo_hz,
        "fitted_hz": fitted_hz,
        "residuals_hz": residuals_hz,
    }


def evaluate_glrt_fit(fit: dict[str, Any], times_s: np.ndarray) -> np.ndarray:
    return np.polyval(
        np.asarray(fit["coefficients_descending_hz"], dtype=float),
        times_s - float(fit["origin_s"]),
    )


def stitch_glrt_tracks(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Align independently seeded Hough episodes by integer GLRT alias classes."""
    if not tracks:
        return None
    anchor = max(tracks, key=lambda item: (item["observation_count"], item["span_s"]))
    anchor_fit = anchor["_fit"]
    shifts: dict[str, int] = {}
    active: list[dict[str, Any]] = []
    initial_limit_hz = 0.03 * GLRT_ALIAS_SPACING_HZ
    for track in tracks:
        predicted = evaluate_glrt_fit(anchor_fit, track["_times_s"])
        shift = round(
            float(np.median((predicted - track["_canonical_cfo_hz"]) / GLRT_ALIAS_SPACING_HZ))
        )
        residual_hz = track["_canonical_cfo_hz"] + shift * GLRT_ALIAS_SPACING_HZ - predicted
        if track is anchor or float(np.median(np.abs(residual_hz))) <= initial_limit_hz:
            shifts[track["track_label"]] = shift
            active.append(track)
    global_fit: dict[str, Any] | None = None
    final_limit_hz = 0.015 * GLRT_ALIAS_SPACING_HZ
    for _ in range(8):
        aligned_rows = np.concatenate(
            [
                np.column_stack(
                    (
                        track["_times_s"],
                        track["_canonical_cfo_hz"]
                        + shifts[track["track_label"]] * GLRT_ALIAS_SPACING_HZ,
                    )
                )
                for track in active
            ]
        )
        aligned_rows = np.unique(aligned_rows, axis=0)
        origin_s = float(np.mean(aligned_rows[:, 0]))
        global_fit = glrt_fit(
            aligned_rows[:, 0],
            aligned_rows[:, 1],
            origin_s=origin_s,
            degree=5,
        )
        updated_active: list[dict[str, Any]] = []
        updated_shifts: dict[str, int] = {}
        for track in tracks:
            predicted = evaluate_glrt_fit(global_fit, track["_times_s"])
            shift = round(
                float(np.median((predicted - track["_canonical_cfo_hz"]) / GLRT_ALIAS_SPACING_HZ))
            )
            residual_hz = track["_canonical_cfo_hz"] + shift * GLRT_ALIAS_SPACING_HZ - predicted
            if track is anchor or float(np.median(np.abs(residual_hz))) <= final_limit_hz:
                updated_active.append(track)
                updated_shifts[track["track_label"]] = shift
        if [track["track_label"] for track in updated_active] == [
            track["track_label"] for track in active
        ] and updated_shifts == shifts:
            active = updated_active
            shifts = updated_shifts
            break
        active = updated_active
        shifts = updated_shifts
    if global_fit is None:
        raise AssertionError("GLRT stitching did not fit an active family")
    aligned_rows = np.concatenate(
        [
            np.column_stack(
                (
                    track["_times_s"],
                    track["_canonical_cfo_hz"]
                    + shifts[track["track_label"]] * GLRT_ALIAS_SPACING_HZ,
                )
            )
            for track in active
        ]
    )
    aligned_rows = np.unique(aligned_rows, axis=0)
    order = np.argsort(aligned_rows[:, 0])
    times_s = aligned_rows[order, 0]
    aligned_cfo_hz = aligned_rows[order, 1]
    global_fit = glrt_fit(
        times_s,
        aligned_cfo_hz,
        origin_s=float(np.mean(times_s)),
        degree=5,
    )
    return {
        "selection": (
            "GLRT-only: anchor the largest Hough episode; iteratively align other episodes "
            "by integer 2.5 MHz/11 classes and retain episodes within 0.015 alias spacing "
            "of a robust quintic trajectory"
        ),
        "anchor_track_label": anchor["track_label"],
        "retained_track_count": len(active),
        "rejected_track_count": len(tracks) - len(active),
        "observation_count_after_exact_deduplication": int(times_s.size),
        "time_start_s": float(times_s.min()),
        "time_stop_s": float(times_s.max()),
        "span_s": float(times_s.max() - times_s.min()),
        "tracks": [
            {
                "track_label": track["track_label"],
                "integer_alias_shift": shifts[track["track_label"]],
                "shift_hz": shifts[track["track_label"]] * GLRT_ALIAS_SPACING_HZ,
                "observation_count": track["observation_count"],
            }
            for track in active
        ],
        "fit": {
            key: value for key, value in global_fit.items() if not isinstance(value, np.ndarray)
        },
        "_times_s": times_s,
        "_aligned_cfo_hz": aligned_cfo_hz,
        "_fit": global_fit,
    }


def native_gap_spans(manifest_path: Path, stream_id: str) -> list[tuple[float, float]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["stream_id"] == stream_id)
    sample_rate_hz = float(stream["applied_settings"]["sample_rate_hz"])
    spans = sorted(
        (
            float(chunk["device_sample_start"]) / sample_rate_hz,
            float(chunk["device_sample_start"] + chunk["sample_count"]) / sample_rate_hz,
        )
        for chunk in stream["chunks"]
        if chunk["content_kind"] == "zero_fill"
    )
    merged: list[tuple[float, float]] = []
    for start_s, stop_s in spans:
        if merged and start_s <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop_s))
        else:
            merged.append((start_s, stop_s))
    return merged


def native_observed_spans(manifest_path: Path, stream_id: str) -> list[tuple[float, float]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["stream_id"] == stream_id)
    sample_rate_hz = float(stream["applied_settings"]["sample_rate_hz"])
    spans = sorted(
        (
            float(chunk["device_sample_start"]) / sample_rate_hz,
            float(chunk["device_sample_start"] + chunk["sample_count"]) / sample_rate_hz,
        )
        for chunk in stream["chunks"]
        if chunk["content_kind"] == "observed"
    )
    merged: list[tuple[float, float]] = []
    for start_s, stop_s in spans:
        if merged and start_s <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop_s))
        else:
            merged.append((start_s, stop_s))
    return merged


def add_track_coverage(
    pss: dict[str, Any],
    observed_spans: list[tuple[float, float]],
) -> None:
    track = pss["independent_track"]
    if track is None:
        return
    start_s = float(track["time_start_s"])
    stop_s = float(track["time_stop_s"])
    observed_duration_s = sum(
        max(0.0, min(stop_s, span_stop) - max(start_s, span_start))
        for span_start, span_stop in observed_spans
    )
    complete_centers: list[float] = []
    window_s = 0.250
    stride_s = 0.125
    for span_start, span_stop in observed_spans:
        cursor_s = span_start
        while cursor_s + window_s <= span_stop + 1e-12:
            center_s = cursor_s + window_s / 2.0
            if start_s - 1e-12 <= center_s <= stop_s + 1e-12:
                complete_centers.append(center_s)
            cursor_s += stride_s
    unique_frames = int(track["dense_frame_accounting"]["unique_strong_frame_epoch_count"])
    approximate_available_frames = observed_duration_s * FRAME_RATE_HZ
    track["coverage"] = {
        "observed_source_duration_inside_track_s": observed_duration_s,
        "complete_250ms_stride125ms_block_count_inside_track": len(complete_centers),
        "associated_block_median_count": track["mode_count"],
        "associated_complete_block_fraction": (
            track["mode_count"] / len(complete_centers) if complete_centers else None
        ),
        "approximate_available_frame_epoch_count": approximate_available_frames,
        "unique_strong_frame_epoch_count": unique_frames,
        "unique_strong_frame_fraction_of_observed_support": (
            unique_frames / approximate_available_frames
            if approximate_available_frames > 0.0
            else None
        ),
        "available_frame_denominator_note": (
            "750 times observed source duration inside selected track support; ignores only "
            "the few template/local-search edge samples at each continuity boundary"
        ),
    }


def validate_pss(document: dict[str, Any], capture: dict[str, Any]) -> None:
    if document["capture_id"] != capture["session_id"]:
        raise ValueError("PSS capture ID does not match the cohort")
    projection = document["projection"]
    expected = capture["stream_25m"]
    checks = {
        "input sample rate": projection["input_sample_rate_hz"] == 25_000_000,
        "output sample rate": projection["output_sample_rate_hz"] == 25_000_000,
        "decimation factor": projection["decimation_factor"] == 1,
        "edge trim": projection["edge_trim_output_samples"] == 0,
        "input center": math.isclose(
            projection["input_center_frequency_hz"],
            expected["center_frequency_hz"],
            rel_tol=0.0,
            abs_tol=1e-6,
        ),
        "untranslated output center": math.isclose(
            projection["output_center_frequency_hz"],
            projection["input_center_frequency_hz"],
            rel_tol=0.0,
            abs_tol=1e-6,
        ),
        "native stream rate": expected["sample_rate_hz"] == 25_000_000,
        "window duration": math.isclose(
            document["configuration"]["maximum_block_duration_s"], 0.250
        ),
        "window stride": math.isclose(document["configuration"]["block_stride_duration_s"], 0.125),
    }
    failed = [label for label, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"invalid native PSS replay: {', '.join(failed)}")


def flatten_modes(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {mode["mode_id"]: mode for block in document["blocks"] for mode in block["modes"]}


def select_independent_pss_track(document: dict[str, Any]) -> dict[str, Any] | None:
    tracks = document["tracks"]
    if not tracks:
        return None
    return max(
        tracks,
        key=lambda item: (
            float(item["time_stop_s"] - item["time_start_s"]),
            len(item["mode_ids"]),
            -float(item["rms_residual_s"]),
        ),
    )


def utc_phase_uncertainty(
    phase_s: float,
    timing: dict[str, Any],
) -> dict[str, Any]:
    earliest_ns = int(timing["earliest_utc_ns"])
    estimate_ns = int(timing["estimate_utc_ns"])
    latest_ns = int(timing["latest_utc_ns"])
    width_s = (latest_ns - earliest_ns) / 1e9
    # The frame rate is exactly 750 Hz, so every whole UTC second contains an
    # integer number of periods.  Reduce the epoch in integer nanoseconds before
    # converting to float; converting the full ~1.8e9-second epoch would discard
    # a material fraction of the sub-microsecond phase precision.
    estimate_subsecond_s = (estimate_ns % 1_000_000_000) / 1e9
    estimate_phase_s = (estimate_subsecond_s + phase_s) % FRAME_PERIOD_S
    return {
        "first_sample_uncertainty_width_us": width_s * 1e6,
        "frame_period_us": FRAME_PERIOD_S * 1e6,
        "unique_absolute_frame_cycle_resolved": width_s < FRAME_PERIOD_S,
        "absolute_utc_phase_at_estimate_us_modulo_frame": estimate_phase_s * 1e6,
        "allowed_absolute_phase": (
            "full 0..frame_period circle"
            if width_s >= FRAME_PERIOD_S
            else "bounded circular interval; inspect timing endpoints"
        ),
    }


def deduplicate_frame_windows(
    modes: list[dict[str, Any]],
    track: dict[str, Any],
    *,
    sample_rate_hz: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    period_samples = sample_rate_hz / FRAME_RATE_HZ
    coefficients = np.asarray(track["coefficients_descending_s"], dtype=float)
    origin_s = float(track["time_origin_s"])
    grouped: dict[int, list[tuple[float, float]]] = defaultdict(list)
    raw_count = 0
    strong_count = 0
    for mode in modes:
        for window in mode["windows"]:
            raw_count += 1
            if float(window["peak_to_local_median"]) < 5.0:
                continue
            strong_count += 1
            sample = float(window["fractional_global_device_sample"])
            time_s = sample / sample_rate_hz
            expected_phase_samples = (
                float(np.polyval(coefficients, time_s - origin_s)) % FRAME_PERIOD_S
            ) * sample_rate_hz
            frame_number = round((sample - expected_phase_samples) / period_samples)
            grouped[frame_number].append((sample, float(window["normalized_match_power"])))
    frame_rows = sorted(grouped.items())
    samples = np.asarray(
        [np.median([sample for sample, _ in values]) for _, values in frame_rows],
        dtype=float,
    )
    times_s = samples / sample_rate_hz
    phases_s = np.mod(samples / sample_rate_hz, FRAME_PERIOD_S)
    return (
        times_s,
        phases_s,
        {
            "raw_refined_window_count": raw_count,
            "strong_refined_window_count": strong_count,
            "unique_strong_frame_epoch_count": len(frame_rows),
            "overlap_duplicate_count": strong_count - len(frame_rows),
        },
    )


def pss_summary(document: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    modes_by_id = flatten_modes(document)
    track = select_independent_pss_track(document)
    inventory = {
        "blind_block_count": len(document["blocks"]),
        "candidate_block_count": sum(bool(block["modes"]) for block in document["blocks"]),
        "retained_mode_count": len(modes_by_id),
        "published_track_count": len(document["tracks"]),
        "strong_window_count": sum(mode["strong_window_count"] for mode in modes_by_id.values()),
        "refined_window_count": sum(mode["window_count"] for mode in modes_by_id.values()),
    }
    if track is None:
        return {"inventory": inventory, "independent_track": None}
    selected_modes = sorted(
        (modes_by_id[mode_id] for mode_id in track["mode_ids"]),
        key=lambda item: item["center_time_s"],
    )
    times_s = np.asarray([item["center_time_s"] for item in selected_modes], dtype=float)
    phases_s = np.asarray([item["median_frame_phase_s"] for item in selected_modes], dtype=float)
    origin_s = float(np.mean(times_s))
    fits = {
        str(degree): robust_polynomial(
            times_s,
            phases_s,
            degree=degree,
            origin_s=origin_s,
        )
        for degree in (1, 2, 3)
    }
    overlap_grids: dict[str, Any] = {}
    for parity in (0, 1):
        mask = np.asarray([item["block_index"] % 2 == parity for item in selected_modes])
        if int(mask.sum()) >= 4:
            overlap_grids[str(parity)] = json_fit(
                robust_polynomial(
                    times_s[mask],
                    phases_s[mask],
                    degree=min(3, int(mask.sum()) - 1),
                    origin_s=origin_s,
                )
            )
    dense_times_s, dense_phases_s, dense_accounting = deduplicate_frame_windows(
        selected_modes,
        track,
        sample_rate_hz=float(document["projection"]["input_sample_rate_hz"]),
    )
    dense_fit = None
    if dense_times_s.size >= 4:
        dense_fit = robust_polynomial(
            dense_times_s,
            dense_phases_s,
            degree=3,
            origin_s=origin_s,
        )
    quadratic = fits["2"]
    pss_rf_hz = LNB_LO_HZ + float(document["projection"]["channel_reference_hz"])
    return {
        "inventory": inventory,
        "independent_track": {
            "selection": ("PSS-only: maximum published time span, then mode count, then lower RMS"),
            "track_id": track["track_id"],
            "mode_count": len(selected_modes),
            "time_start_s": float(track["time_start_s"]),
            "time_stop_s": float(track["time_stop_s"]),
            "span_s": float(track["time_stop_s"] - track["time_start_s"]),
            "published_rms_residual_us": float(track["rms_residual_s"]) * 1e6,
            "published_maximum_absolute_residual_us": float(track["maximum_absolute_residual_s"])
            * 1e6,
            "pss_rf_reference_hz": pss_rf_hz,
            "quadratic_physical_equivalent_doppler_hz_at_reference": (
                quadratic["physical_fractional_doppler"] * pss_rf_hz
            ),
            "quadratic_physical_equivalent_doppler_rate_hz_s_at_reference": (
                quadratic["physical_fractional_doppler_rate_s_inverse"] * pss_rf_hz
            ),
            "quadratic_same_sign_equivalent_doppler_hz_at_reference": (
                quadratic["same_sign_fractional_doppler"] * pss_rf_hz
            ),
            "quadratic_same_sign_equivalent_doppler_rate_hz_s_at_reference": (
                quadratic["same_sign_fractional_doppler_rate_s_inverse"] * pss_rf_hz
            ),
            "fits": {degree: json_fit(fit) for degree, fit in fits.items()},
            "overlap_grid_fits": overlap_grids,
            "dense_frame_accounting": dense_accounting,
            "dense_frame_cubic_fit": None if dense_fit is None else json_fit(dense_fit),
            "local_frame_phase_at_reference_us": quadratic["phase_at_origin_s"] * 1e6,
            "absolute_utc_phase": utc_phase_uncertainty(
                quadratic["phase_at_origin_s"],
                capture["stream_25m"]["first_sample_timing"],
            ),
            "mode_ids": track["mode_ids"],
        },
        "_selected_modes": selected_modes,
        "_fits": fits,
        "_dense_fit": dense_fit,
    }


def glrt_tracks(product: dict[str, Any], *, native_first_utc_ns: int) -> list[dict[str, Any]]:
    source = product["source"]
    start_offset_s = (int(source["timing"]["first_estimate_utc_ns"]) - native_first_utc_ns) / 1e9
    rf_hz = LNB_LO_HZ + float(source["tuned_center_frequency_hz"])
    rows: list[dict[str, Any]] = []
    track_number = 0
    for segment in product["segments"]:
        hough = segment.get("hough")
        if not hough:
            continue
        for track in hough["tracks"]:
            track_number += 1
            observations = track["observations"]
            times_s = np.asarray(
                [float(item["global_time_s"]) + start_offset_s for item in observations]
            )
            raw_cfo_hz = np.asarray([float(item["raw_cfo_hz"]) for item in observations])
            alias = np.asarray([int(item["alias_index"]) for item in observations])
            canonical_cfo_hz = raw_cfo_hz - alias * GLRT_ALIAS_SPACING_HZ
            origin_s = float(np.mean(times_s))
            fit = glrt_fit(times_s, canonical_cfo_hz, origin_s=origin_s)
            rows.append(
                {
                    "track_label": f"H{track_number}",
                    "observation_count": len(observations),
                    "time_start_s": float(times_s.min()),
                    "time_stop_s": float(times_s.max()),
                    "span_s": float(times_s.max() - times_s.min()),
                    "alias_index_counts": {
                        str(index): int(np.count_nonzero(alias == index))
                        for index in sorted(set(alias.tolist()))
                    },
                    "alias_switch_count": int(np.count_nonzero(np.diff(alias))),
                    "rf_reference_hz": rf_hz,
                    "fit": {
                        key: value
                        for key, value in fit.items()
                        if not isinstance(value, np.ndarray)
                    },
                    "_times_s": times_s,
                    "_raw_cfo_hz": raw_cfo_hz,
                    "_alias": alias,
                    "_canonical_cfo_hz": canonical_cfo_hz,
                    "_fit": fit,
                }
            )
    return rows


def summarize_glrt(
    capture: dict[str, Any],
    *,
    pss_track: dict[str, Any] | None,
) -> dict[str, Any]:
    native_first = int(capture["stream_25m"]["first_sample_timing"]["estimate_utc_ns"])
    paths: list[dict[str, Any]] = []
    for product_meta in sorted(capture["glrt_2p5m"], key=lambda item: item["receiver_id"]):
        path = Path(product_meta["path"])
        if sha256(path) != product_meta["digest"]:
            raise ValueError(f"GLRT digest mismatch: {path}")
        product = json.loads(path.read_text(encoding="utf-8"))
        tracks = glrt_tracks(product, native_first_utc_ns=native_first)
        stitched_family = stitch_glrt_tracks(tracks)
        independent = max(
            tracks,
            key=lambda item: (item["observation_count"], item["span_s"]),
            default=None,
        )
        joint = None
        if pss_track is not None and tracks:
            pss_start = float(pss_track["time_start_s"])
            pss_stop = float(pss_track["time_stop_s"])
            candidate_joint = max(
                tracks,
                key=lambda item: (
                    max(
                        0.0,
                        min(pss_stop, item["time_stop_s"]) - max(pss_start, item["time_start_s"]),
                    ),
                    item["observation_count"],
                ),
            )
            overlap_s = max(
                0.0,
                min(pss_stop, candidate_joint["time_stop_s"])
                - max(pss_start, candidate_joint["time_start_s"]),
            )
            joint = candidate_joint if overlap_s > 0.0 else None
        paths.append(
            {
                "receiver_id": product_meta["receiver_id"],
                "physical_receiver_id": product_meta["physical_receiver_id"],
                "path": str(path),
                "sha256": product_meta["digest"],
                "passing_fraction": product_meta["passing_fraction"],
                "passing_window_count": product_meta["passing_window_count"],
                "valid_window_count": product_meta["valid_window_count"],
                "rf_reference_hz": LNB_LO_HZ
                + float(product["source"]["tuned_center_frequency_hz"]),
                "independent_track": independent,
                "joint_temporal_overlap_track": joint,
                "stitched_family": stitched_family,
                "tracks": tracks,
            }
        )
    return {
        "best_receiver_id_from_cohort_selection": capture["rank_fields"]["best_receiver_id"],
        "paths": paths,
    }


def clean_glrt(summary: dict[str, Any]) -> dict[str, Any]:
    def clean_track(track: dict[str, Any] | None) -> dict[str, Any] | None:
        if track is None:
            return None
        return {key: value for key, value in track.items() if not key.startswith("_")}

    return {
        "best_receiver_id_from_cohort_selection": summary["best_receiver_id_from_cohort_selection"],
        "paths": [
            {
                **{
                    key: value
                    for key, value in path.items()
                    if key not in {"tracks", "stitched_family"}
                },
                "independent_track": clean_track(path["independent_track"]),
                "joint_temporal_overlap_track": clean_track(path["joint_temporal_overlap_track"]),
                "stitched_family": clean_track(path["stitched_family"]),
                "tracks": [clean_track(track) for track in path["tracks"]],
            }
            for path in summary["paths"]
        ],
    }


def affine_phase_alignment(
    times_s: np.ndarray,
    observed_s: np.ndarray,
    predicted_s: np.ndarray,
) -> dict[str, Any]:
    origin_s = float(np.mean(times_s))
    matrix = np.column_stack((np.ones(times_s.size), times_s - origin_s))

    def fitted(selected: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        coefficients = np.linalg.lstsq(
            matrix[selected],
            (observed_s - predicted_s)[selected],
            rcond=None,
        )[0]
        values = predicted_s + matrix @ coefficients
        return coefficients, values, observed_s - values

    all_rows = np.ones(times_s.size, dtype=bool)
    coefficients, _, residuals_s = fitted(all_rows)
    training_count = math.ceil(0.60 * times_s.size)
    indexes = np.arange(times_s.size)
    folds: list[dict[str, Any]] = []
    for label, training, evaluation in (
        ("forward", indexes < training_count, indexes >= training_count),
        (
            "reverse",
            indexes >= times_s.size - training_count,
            indexes < times_s.size - training_count,
        ),
    ):
        fold_coefficients, _, fold_residuals_s = fitted(training)
        folds.append(
            {
                "label": label,
                "training_count": int(np.count_nonzero(training)),
                "evaluation_count": int(np.count_nonzero(evaluation)),
                "nuisance_coefficients_ascending_s": fold_coefficients.tolist(),
                "evaluation_rms_us": rms(fold_residuals_s[evaluation]) * 1e6,
            }
        )
    holdout_rms_us = float(np.sqrt(np.mean([fold["evaluation_rms_us"] ** 2 for fold in folds])))
    return {
        "nuisance_origin_s": origin_s,
        "full_nuisance_coefficients_ascending_s": coefficients.tolist(),
        "full_rms_us": rms(residuals_s) * 1e6,
        "bidirectional_holdout_rms_us": holdout_rms_us,
        "bidirectional_holdout": folds,
        "residuals_us": (residuals_s * 1e6).tolist(),
    }


def comparison(pss: dict[str, Any], glrt: dict[str, Any]) -> dict[str, Any] | None:
    pss_track = pss["independent_track"]
    if pss_track is None:
        return None
    pss_fit = pss_track["fits"]["2"]
    selected_modes = pss.get("_selected_modes", [])
    rows: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    for path in glrt["paths"]:
        family = path["stitched_family"]
        if family is None:
            continue
        overlap_s = max(
            0.0,
            min(pss_track["time_stop_s"], family["time_stop_s"])
            - max(pss_track["time_start_s"], family["time_start_s"]),
        )
        if overlap_s <= 0.0:
            continue
        pss_origin_s = float(pss_fit["origin_s"])
        coefficients = np.asarray(family["fit"]["coefficients_descending_hz"], dtype=float)
        glrt_rate_hz_s = float(
            np.polyval(
                np.polyder(coefficients),
                pss_origin_s - float(family["fit"]["origin_s"]),
            )
        )
        glrt_rate_fractional = glrt_rate_hz_s / path["rf_reference_hz"]
        pss_physical = pss_fit["physical_fractional_doppler_rate_s_inverse"]
        pss_same = pss_fit["same_sign_fractional_doppler_rate_s_inverse"]
        rows.append(
            {
                "receiver_id": path["receiver_id"],
                "glrt_source": "GLRT-only integer-alias-stitched Hough family",
                "glrt_anchor_track_label": family["anchor_track_label"],
                "glrt_retained_track_count": family["retained_track_count"],
                "overlap_s": overlap_s,
                "comparison_origin_s": pss_origin_s,
                "pss_physical_fractional_doppler_rate_s_inverse": pss_physical,
                "pss_same_sign_fractional_doppler_rate_s_inverse": pss_same,
                "glrt_fractional_cfo_rate_s_inverse": glrt_rate_fractional,
                "glrt_cfo_rate_hz_s": glrt_rate_hz_s,
                "pss_physical_equivalent_doppler_rate_hz_s_at_glrt_rf": (
                    pss_physical * path["rf_reference_hz"]
                ),
                "pss_same_sign_equivalent_doppler_rate_hz_s_at_glrt_rf": (
                    pss_same * path["rf_reference_hz"]
                ),
                "physical_pss_minus_glrt_s_inverse": pss_physical - glrt_rate_fractional,
                "same_sign_pss_minus_glrt_s_inverse": pss_same - glrt_rate_fractional,
                "opposite_iq_glrt_rate_s_inverse": -glrt_rate_fractional,
            }
        )
        aligned_modes = [
            mode
            for mode in selected_modes
            if family["time_start_s"] <= float(mode["center_time_s"]) <= family["time_stop_s"]
        ]
        if len(aligned_modes) < 6:
            continue
        alignment_times_s = np.asarray(
            [float(mode["center_time_s"]) for mode in aligned_modes],
            dtype=float,
        )
        alignment_phases_s = np.asarray(
            [float(mode["median_frame_phase_s"]) for mode in aligned_modes],
            dtype=float,
        )
        observed_unwrapped_s = np.unwrap(alignment_phases_s / FRAME_PERIOD_S * 2.0 * np.pi) * (
            FRAME_PERIOD_S / (2.0 * np.pi)
        )
        primitive = np.polyint(coefficients) / float(path["rf_reference_hz"])
        centered_s = alignment_times_s - float(family["fit"]["origin_s"])
        integrated_fractional_cfo_s = np.polyval(primitive, centered_s)
        null = affine_phase_alignment(
            alignment_times_s,
            observed_unwrapped_s,
            np.zeros_like(observed_unwrapped_s),
        )
        physical = affine_phase_alignment(
            alignment_times_s,
            observed_unwrapped_s,
            -integrated_fractional_cfo_s,
        )
        same_sign = affine_phase_alignment(
            alignment_times_s,
            observed_unwrapped_s,
            integrated_fractional_cfo_s,
        )
        null_holdout_us = float(null["bidirectional_holdout_rms_us"])
        physical["holdout_rms_ratio_to_affine_null"] = (
            float(physical["bidirectional_holdout_rms_us"]) / null_holdout_us
        )
        same_sign["holdout_rms_ratio_to_affine_null"] = (
            float(same_sign["bidirectional_holdout_rms_us"]) / null_holdout_us
        )
        alignment_rows.append(
            {
                "receiver_id": path["receiver_id"],
                "measurement_count": len(aligned_modes),
                "time_start_s": float(alignment_times_s.min()),
                "time_stop_s": float(alignment_times_s.max()),
                "times_s": alignment_times_s.tolist(),
                "affine_only_null": null,
                "physical_pss_vs_recorded_glrt_iq": physical,
                "same_sign_pss_vs_recorded_glrt_iq_control": same_sign,
            }
        )
    return {
        "track_pairing": (
            "PSS track and GLRT integer-alias-stitched family are each selected independently; "
            "the GLRT family uses no PSS, TLE, or rate values"
        ),
        "rate_rows": rows,
        "integrated_phase_alignment_by_receiver": alignment_rows,
        "integrated_phase_alignment_method": (
            "integrate the independently alias-stitched GLRT CFO/RF polynomial; fit only "
            "constant phase and linear clock drift to PSS block medians; report both physical "
            "arrival-delay sign and same-sign control with bidirectional 60/40 holdout"
        ),
        "sign_convention": {
            "physical_pss": "fractional Doppler = -d(arrival delay)/dt",
            "glrt": (
                "canonical complex-baseband CFO divided by RF; receiver IQ/mixer physical sign "
                "is not independently calibrated"
            ),
            "same_sign_pss": "diagnostic +d(frame phase)/dt convention used by older reports",
        },
    }


def add_gap_shading(axis: plt.Axes, gaps: list[tuple[float, float]]) -> None:
    for start_s, stop_s in gaps:
        axis.axvspan(start_s, stop_s, color="#d1d5db", alpha=0.45, linewidth=0)


def render_capture(
    capture: dict[str, Any],
    pss: dict[str, Any],
    glrt: dict[str, Any],
    comparison_row: dict[str, Any] | None,
    gaps: list[tuple[float, float]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(6, 1, figsize=(15, 20), sharex=True, constrained_layout=True)
    all_modes = [mode for block in pss["_document"]["blocks"] for mode in block["modes"]]
    axes[0].scatter(
        [item["center_time_s"] for item in all_modes],
        [item["median_frame_phase_s"] * 1e6 for item in all_modes],
        s=10,
        color="#9ca3af",
        alpha=0.35,
        label="all retained PSS modes",
    )
    track = pss["independent_track"]
    if track is not None:
        modes = pss["_selected_modes"]
        axes[0].scatter(
            [item["center_time_s"] for item in modes],
            [item["median_frame_phase_s"] * 1e6 for item in modes],
            s=22,
            color="#ea580c",
            label="independent PSS track",
        )
        cubic = pss["_fits"]["3"]
        axes[1].scatter(cubic["times_s"], cubic["unwrapped_s"] * 1e6, s=14, color="#111827")
        axes[1].plot(cubic["times_s"], cubic["fitted_s"] * 1e6, color="#ea580c", linewidth=2)
        quadratic = pss["_fits"]["2"]
        axes[2].scatter(
            quadratic["times_s"],
            quadratic["residuals_s"] * 1e6,
            s=18,
            color="#2563eb",
            label=f"quadratic RMS {quadratic['rms_residual_us']:.3f} µs",
        )
        axes[2].scatter(
            cubic["times_s"],
            cubic["residuals_s"] * 1e6,
            s=14,
            color="#ea580c",
            label=f"cubic RMS {cubic['rms_residual_us']:.3f} µs",
        )
    best_receiver = glrt["best_receiver_id_from_cohort_selection"]
    best_path = next(item for item in glrt["paths"] if item["receiver_id"] == best_receiver)
    colors = plt.get_cmap("tab10")
    for index, hough in enumerate(best_path["tracks"]):
        axes[3].scatter(
            hough["_times_s"],
            hough["_canonical_cfo_hz"] / 1e3,
            s=5,
            alpha=0.38,
            color=colors(index % 10),
            label=hough["track_label"] if index < 10 else None,
        )
    stitched = best_path["stitched_family"]
    if stitched is not None:
        axes[4].scatter(
            stitched["_times_s"],
            stitched["_aligned_cfo_hz"] / 1e3,
            s=4,
            alpha=0.28,
            color="#2563eb",
            rasterized=True,
            label=(f"{stitched['retained_track_count']} GLRT episodes after integer-class shifts"),
        )
        order = np.argsort(stitched["_times_s"])
        axes[4].plot(
            stitched["_times_s"][order],
            stitched["_fit"]["fitted_hz"][order] / 1e3,
            color="#111827",
            linewidth=1.8,
            label=f"robust quintic; RMS {stitched['_fit']['rms_residual_hz']:.1f} Hz",
        )
    alignment_available = False
    if comparison_row is not None:
        alignment = next(
            (
                row
                for row in comparison_row["integrated_phase_alignment_by_receiver"]
                if row["receiver_id"] == best_receiver
            ),
            None,
        )
        if alignment is not None:
            alignment_available = True
            alignment_times_s = np.asarray(alignment["times_s"], dtype=float)
            physical = alignment["physical_pss_vs_recorded_glrt_iq"]
            same_sign = alignment["same_sign_pss_vs_recorded_glrt_iq_control"]
            axes[5].scatter(
                alignment_times_s,
                physical["residuals_us"],
                s=16,
                color="#2563eb",
                label=(
                    "physical −∫CFO/RF; holdout/null "
                    f"{physical['holdout_rms_ratio_to_affine_null']:.3f}"
                ),
            )
            axes[5].scatter(
                alignment_times_s,
                same_sign["residuals_us"],
                s=13,
                color="#ea580c",
                alpha=0.75,
                label=(
                    "same-sign +∫CFO/RF control; holdout/null "
                    f"{same_sign['holdout_rms_ratio_to_affine_null']:.3f}"
                ),
            )
    for axis in axes:
        add_gap_shading(axis, gaps)
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("PSS phase\n(µs modulo 1/750 s)")
    axes[0].legend(loc="best")
    axes[1].set_ylabel("Unwrapped PSS\nphase (µs)")
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_ylabel("PSS fit residual\n(µs)")
    axes[2].legend(loc="best")
    axes[3].set_ylabel(f"RX{best_receiver} canonical\nGLRT CFO (kHz)")
    axes[3].legend(loc="upper right", ncol=5, fontsize=8)
    axes[4].set_ylabel(f"RX{best_receiver} alias-stitched\nGLRT CFO (kHz)")
    axes[4].legend(loc="best", fontsize=9)
    axes[5].axhline(0.0, color="black", linewidth=0.8)
    axes[5].set_ylabel("Integrated GLRT/PSS\nalignment residual (µs)")
    axes[5].set_xlabel("Seconds from native 25 MS/s first sample")
    if alignment_available:
        axes[5].legend(loc="best", fontsize=9)
    else:
        axes[5].text(
            0.5,
            0.5,
            "No common-support PSS/GLRT alignment",
            transform=axes[5].transAxes,
            ha="center",
            va="center",
        )
    figure.suptitle(
        f"{capture['session_id']} — full-rate native-25 PSS vs paired 2.5 GLRT\n"
        "gray bands are counter-proven missing native-25 source intervals",
        fontsize=15,
    )
    figure.savefig(path, dpi=170)
    plt.close(figure)


def render_frame_offset(
    capture: dict[str, Any],
    pss: dict[str, Any],
    gaps: list[tuple[float, float]],
    path: Path,
) -> None:
    track = pss["independent_track"]
    dense = pss["_dense_fit"]
    if track is None or dense is None:
        raise ValueError("frame-offset figure requires an independent dense PSS track")
    block = pss["_fits"]["3"]
    figure, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
    axes[0].scatter(
        dense["times_s"],
        (dense["fitted_s"] + dense["residuals_s"]) * 1e6,
        s=2,
        alpha=0.10,
        color="#2563eb",
        rasterized=True,
        label=(
            f"{track['dense_frame_accounting']['unique_strong_frame_epoch_count']:,} "
            "deduplicated strong frame epochs"
        ),
    )
    axes[0].scatter(
        block["times_s"],
        (block["fitted_s"] + block["residuals_s"]) * 1e6,
        s=20,
        color="#111827",
        label=f"{track['mode_count']} block medians",
    )
    order = np.argsort(dense["times_s"])
    axes[0].plot(
        dense["times_s"][order],
        dense["fitted_s"][order] * 1e6,
        color="#ea580c",
        linewidth=1.8,
        label="robust dense-frame cubic",
    )
    axes[1].scatter(
        dense["times_s"],
        dense["residuals_s"] * 1e6,
        s=2,
        alpha=0.10,
        color="#2563eb",
        rasterized=True,
        label=f"dense RMS {dense['rms_residual_us']:.3f} µs",
    )
    axes[1].scatter(
        block["times_s"],
        block["residuals_s"] * 1e6,
        s=18,
        color="#ea580c",
        label=f"block-median RMS {block['rms_residual_us']:.3f} µs",
    )
    grid_s = np.linspace(track["time_start_s"], track["time_stop_s"], 800)
    full_prediction_s = np.polyval(
        np.asarray(block["coefficients_descending_s"]),
        grid_s - float(block["origin_s"]),
    )
    for parity, color in (("0", "#16a34a"), ("1", "#7c3aed")):
        fit = track["overlap_grid_fits"].get(parity)
        if fit is None:
            continue
        prediction_s = np.polyval(
            np.asarray(fit["coefficients_descending_s"]),
            grid_s - float(fit["origin_s"]),
        )
        delta_us = circular_residual(prediction_s, full_prediction_s) * 1e6
        axes[2].plot(
            grid_s,
            delta_us,
            color=color,
            label=f"block-index parity {parity} minus full fit",
        )
    for axis in axes:
        add_gap_shading(axis, gaps)
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Unwrapped frame phase (µs)")
    axes[0].legend(loc="best")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Cubic residual (µs)")
    axes[1].legend(loc="best")
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_ylabel("Overlap-grid fit\nsensitivity (µs)")
    axes[2].set_xlabel("Seconds from native 25 MS/s first sample")
    axes[2].legend(loc="best")
    utc = track["absolute_utc_phase"]
    figure.suptitle(
        f"{capture['session_id']} — native-25 PSS frame-offset evidence\n"
        f"local phase {track['local_frame_phase_at_reference_us']:.3f} µs at "
        f"t={track['fits']['2']['origin_s']:.3f}s; first-sample uncertainty "
        f"{utc['first_sample_uncertainty_width_us']:.1f} µs vs "
        f"{utc['frame_period_us']:.1f} µs frame",
        fontsize=14,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def render_rate_summary(captures: list[dict[str, Any]], path: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(21, 6), constrained_layout=True)
    labels: list[str] = []
    pss_physical: list[float] = []
    pss_same: list[float] = []
    glrt_rates: list[float] = []
    physical_alignment_scores: list[float] = []
    same_sign_alignment_scores: list[float] = []
    for capture in captures:
        comparison_row = capture["comparison"]
        if comparison_row is None or not comparison_row["rate_rows"]:
            continue
        best_receiver = capture["glrt"]["best_receiver_id_from_cohort_selection"]
        rate = next(
            (row for row in comparison_row["rate_rows"] if row["receiver_id"] == best_receiver),
            comparison_row["rate_rows"][0],
        )
        labels.append(capture["capture_id"].split("-")[-1])
        pss_physical.append(rate["pss_physical_fractional_doppler_rate_s_inverse"] * 1e9)
        pss_same.append(rate["pss_same_sign_fractional_doppler_rate_s_inverse"] * 1e9)
        glrt_rates.append(rate["glrt_fractional_cfo_rate_s_inverse"] * 1e9)
        alignment = next(
            (
                row
                for row in comparison_row["integrated_phase_alignment_by_receiver"]
                if row["receiver_id"] == best_receiver
            ),
            None,
        )
        physical_alignment_scores.append(
            math.nan
            if alignment is None
            else alignment["physical_pss_vs_recorded_glrt_iq"]["holdout_rms_ratio_to_affine_null"]
        )
        same_sign_alignment_scores.append(
            math.nan
            if alignment is None
            else alignment["same_sign_pss_vs_recorded_glrt_iq_control"][
                "holdout_rms_ratio_to_affine_null"
            ]
        )
    positions = np.arange(len(labels))
    axes[0].scatter(
        positions - 0.14,
        pss_physical,
        marker="D",
        s=80,
        label="PSS physical −delay sign",
    )
    axes[0].scatter(positions, pss_same, marker="s", s=70, label="PSS same-sign diagnostic")
    axes[0].scatter(positions + 0.14, glrt_rates, marker="o", s=70, label="GLRT canonical CFO")
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_xticks(positions, labels, rotation=25)
    axes[0].set_ylabel("Fractional frequency rate (10⁻⁹ s⁻¹)")
    axes[0].set_title("PSS arrival-phase curvature vs temporally overlapping GLRT")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=9)
    for capture in captures:
        track = capture["pss"]["independent_track"]
        if track is None:
            continue
        axes[1].scatter(
            track["span_s"],
            track["fits"]["3"]["rms_residual_us"],
            s=max(45.0, track["mode_count"] * 0.8),
            label=capture["capture_id"].split("-")[-1],
        )
    axes[1].set_xlabel("Independent PSS track span (s)")
    axes[1].set_ylabel("Cubic timing-fit RMS (µs)")
    axes[1].set_title("PSS timing fitness (marker area follows mode count)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=9)
    axes[2].scatter(
        positions - 0.08,
        physical_alignment_scores,
        marker="D",
        s=80,
        label="physical −∫CFO/RF",
    )
    axes[2].scatter(
        positions + 0.08,
        same_sign_alignment_scores,
        marker="s",
        s=75,
        label="same-sign +∫CFO/RF control",
    )
    axes[2].axhline(1.0, color="black", linewidth=0.8, linestyle="--")
    axes[2].set_xticks(positions, labels, rotation=25)
    axes[2].set_ylabel("Bidirectional holdout RMS / affine-only null")
    axes[2].set_title("Integrated cross-observable phase alignment")
    axes[2].grid(axis="y", alpha=0.25)
    axes[2].legend(fontsize=9)
    figure.suptitle("Five-capture native-25 PSS / paired-2.5 GLRT comparison")
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = arguments()
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    capture_results: list[dict[str, Any]] = []
    for capture in cohort["selected"]:
        capture_id = capture["session_id"]
        pss_path = args.pss_root / capture_id / "native25-blind-250ms-stride125ms.json"
        document = json.loads(pss_path.read_text(encoding="utf-8"))
        validate_pss(document, capture)
        pss = pss_summary(document, capture)
        pss["_document"] = document
        glrt = summarize_glrt(capture, pss_track=pss["independent_track"])
        comparison_row = comparison(pss, glrt)
        manifest_path = Path(capture["manifest_path"])
        stream_id = capture["stream_25m"]["stream_id"]
        gaps = native_gap_spans(manifest_path, stream_id)
        observed_spans = native_observed_spans(manifest_path, stream_id)
        add_track_coverage(pss, observed_spans)
        figure_name = f"{capture_id}-pss-glrt-diagnostic.png"
        figure_path = args.output_dir / figure_name
        render_capture(capture, pss, glrt, comparison_row, gaps, figure_path)
        frame_figure_name = f"{capture_id}-pss-frame-offset.png"
        frame_figure_path = args.output_dir / frame_figure_name
        if pss["independent_track"] is not None and pss["_dense_fit"] is not None:
            render_frame_offset(capture, pss, gaps, frame_figure_path)
            frame_figure = {
                "path": frame_figure_name,
                "sha256": sha256(frame_figure_path),
            }
        else:
            frame_figure = None
        clean_pss = {key: value for key, value in pss.items() if not key.startswith("_")}
        clean_glrt_row = clean_glrt(glrt)
        capture_results.append(
            {
                "capture_id": capture_id,
                "rank_fields": capture["rank_fields"],
                "native25": {
                    **capture["stream_25m"],
                    "gap_spans_s": [list(span) for span in gaps],
                },
                "paired_2p5m": capture["stream_2p5m"],
                "pss_input": {"path": str(pss_path), "sha256": sha256(pss_path)},
                "pss": clean_pss,
                "glrt": clean_glrt_row,
                "comparison": comparison_row,
                "figure": {"path": figure_name, "sha256": sha256(figure_path)},
                "frame_offset_figure": frame_figure,
            }
        )
    rate_figure = args.output_dir / "cohort-pss-glrt-rate-and-fitness.png"
    render_rate_summary(capture_results, rate_figure)
    evidence = {
        "schema_version": 1,
        "analysis_kind": "five-paired-native25-pss-vs-dual2p5-glrt",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__)),
        },
        "cohort": {"path": str(args.cohort), "sha256": sha256(args.cohort)},
        "method": {
            "pss_search_rate": "native 25 MS/s; decimation factor 1; no edge trim",
            "pss_window_geometry": "complete 250 ms windows with 125 ms stride",
            "pss_track_selection": (
                "independent: maximum published span, then mode count, then lower RMS"
            ),
            "pss_fit": (
                "Huber-IRLS polynomial on unwrapped block-median phase; circular residuals"
            ),
            "dense_frame_fit": (
                "strong local windows only; overlapping detections deduplicated by global "
                "750 Hz frame epoch before cubic fit"
            ),
            "glrt_alias_canonicalization": ("canonical_cfo = raw_cfo - alias_index*(2.5 MHz/11)"),
            "glrt_independent_track_selection": (
                "maximum published Hough observation count, then span"
            ),
            "glrt_global_alias_stitching": (
                "anchor largest Hough episode, align other episodes by integer 2.5 MHz/11 "
                "classes against an iterated robust quintic, and reject incompatible episodes; "
                "uses GLRT only"
            ),
            "joint_pairing": (
                "compare the independently selected PSS track with each independently "
                "alias-stitched GLRT family over common temporal support"
            ),
            "integrated_cross_observable_alignment": (
                "integrate each GLRT-only CFO/RF family and compare it with unwrapped PSS "
                "phase after fitting only constant phase and linear clock drift; physical "
                "and same-sign control use bidirectional 60/40 holdout"
            ),
        },
        "captures": capture_results,
        "artifacts": {
            "rate_and_fitness_figure": {
                "path": rate_figure.name,
                "sha256": sha256(rate_figure),
            }
        },
        "limitations": [
            (
                "Adjacent PSS block medians share 125 ms of IQ; even/odd fits measure "
                "this sensitivity."
            ),
            "Native-25 source gaps are excluded from search and shown as shaded intervals.",
            (
                "PSS and GLRT use different radio/LNB chains; absolute CFO and phase "
                "offsets are not shared."
            ),
            "First-sample UTC uncertainty can exceed one 1.333 ms frame period.",
            "GLRT complex-baseband CFO physical sign is not independently calibrated.",
            (
                "PSS is template-relative; no SSS/payload decode establishes a complete "
                "OFDM frame boundary."
            ),
        ],
    }
    output = args.output_dir / "pss-glrt-cohort-analysis.json"
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "capture_count": len(capture_results),
                "pss_track_count": sum(
                    item["pss"]["independent_track"] is not None for item in capture_results
                ),
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
