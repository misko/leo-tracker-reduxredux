#!/usr/bin/env python3
"""Render the 7fea7427619d native-PSS versus dual-GLRT deep-dive figures.

This capture-specific diagnostic consumes only persisted Standard products.  It
does not reread IQ or rerun acquisition.  PSS and GLRT selections remain
independent; UTC estimates are used only to place their results on one clock.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

Json = dict[str, Any]
FloatArray = npt.NDArray[np.float64]

CAPTURE_ID = "cap-20260902T152702-7fea7427619d"
ANALYSIS_RUN_ID = "native-capture-71829dc4471b474c9a9322e26c5c6f26"
PSS_COLOR = "#f97316"
RX_COLORS = {0: "#2563eb", 1: "#0891b2"}
SEGMENT_COLORS = (
    "#2563eb",
    "#7c3aed",
    "#0891b2",
    "#be123c",
    "#16a34a",
    "#d97706",
    "#db2777",
)


def _load(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return value


def _first_estimate_s(product: Json) -> float:
    return float(product["source"]["timing"]["first_estimate_utc_ns"]) / 1e9


def _high_time_offset_s(product: Json, pss: Json) -> float:
    return _first_estimate_s(product) - _first_estimate_s(pss)


def _primary_pss_track(pss: Json) -> Json:
    tracks = [item for item in pss["tracks"] if item["origin"] == "independent_blind"]
    if not tracks:
        raise ValueError("PSS product has no independent blind track")
    return max(
        tracks,
        key=lambda item: (
            len(item["mode_ids"]),
            item["time_stop_s"] - item["time_start_s"],
            -item["rms_residual_us"],
            item["track_id"],
        ),
    )


def _track_arrays(pss: Json, track: Json) -> tuple[tuple[Json, ...], FloatArray, FloatArray]:
    by_id = {item["mode_id"]: item for item in pss["modes"]}
    modes = tuple(by_id[item] for item in track["mode_ids"])
    times = np.asarray([item["center_time_s"] for item in modes], dtype=float)
    if len(times) < 3 or np.any(np.diff(times) <= 0):
        raise ValueError("PSS track is too short or not time ordered")
    model = np.polyval(
        np.asarray(track["coefficients_descending_s"], dtype=float),
        times - float(track["time_origin_s"]),
    )
    phases = model + np.asarray(track["residuals_us"], dtype=float) * 1e-6
    return modes, times, phases


def _complete_locklets(product: Json) -> list[Json]:
    return [
        item
        for item in product["locklets"]
        if item["status"] == "complete"
        and item.get("linear_fit") is not None
        and item.get("quadratic_fit") is not None
    ]


def _inlier_observations(locklet: Json) -> list[Json]:
    return [item for item in locklet["observations"] if item["epoch_fit_inlier"]]


def polynomial_validation(
    times_s: FloatArray,
    values_s: FloatArray,
    *,
    degrees: tuple[int, ...] = (1, 2, 3, 4, 5),
    block_s: float = 1.0,
) -> Json:
    """Return in-sample and five-fold time-blocked prediction metrics."""

    if len(times_s) != len(values_s) or len(times_s) < max(degrees) + 2:
        raise ValueError("polynomial validation input is incomplete")
    reference_s = float(np.mean(times_s))
    folds = np.floor(times_s / block_s).astype(int) % 5
    result: Json = {}
    for degree in degrees:
        coefficients = np.polyfit(times_s - reference_s, values_s, degree)
        residual_us = (values_s - np.polyval(coefficients, times_s - reference_s)) * 1e6
        held_out: list[float] = []
        for fold in range(5):
            train = folds != fold
            test = ~train
            if np.count_nonzero(train) <= degree or not np.any(test):
                continue
            fit = np.polyfit(times_s[train] - reference_s, values_s[train], degree)
            held_out.extend((values_s[test] - np.polyval(fit, times_s[test] - reference_s)) * 1e6)
        held = np.asarray(held_out, dtype=float)
        result[str(degree)] = {
            "in_sample_rms_us": float(np.sqrt(np.mean(residual_us**2))),
            "blocked_cv_rms_us": float(np.sqrt(np.mean(held**2))),
            "blocked_cv_p95_absolute_us": float(np.quantile(np.abs(held), 0.95)),
            "coefficients_descending_s": [float(item) for item in coefficients],
            "reference_time_s": reference_s,
        }
    return result


def transition_statistics(
    residuals_us: FloatArray,
    segment_ids: npt.NDArray[np.int64],
    frequency_offsets_hz: FloatArray,
) -> Json:
    """Separate ordinary, counter-gap, and PSS-search-hypothesis transitions."""

    if not (
        len(residuals_us) == len(segment_ids) == len(frequency_offsets_hz)
        and len(residuals_us) >= 2
    ):
        raise ValueError("transition vectors must be equally sized and nontrivial")
    jumps = np.abs(np.diff(residuals_us))
    crosses_segment = segment_ids[1:] != segment_ids[:-1]
    changes_frequency = frequency_offsets_hz[1:] != frequency_offsets_hz[:-1]

    def metrics(selected: npt.NDArray[np.bool_]) -> Json:
        values = jumps[selected]
        return {
            "count": int(len(values)),
            "median_absolute_residual_jump_us": (float(np.median(values)) if len(values) else None),
            "p95_absolute_residual_jump_us": (
                float(np.quantile(values, 0.95)) if len(values) else None
            ),
            "maximum_absolute_residual_jump_us": (float(np.max(values)) if len(values) else None),
        }

    return {
        "ordinary": metrics(~crosses_segment & ~changes_frequency),
        "counter_gap_crossing": metrics(crosses_segment),
        "frequency_hypothesis_change": metrics(changes_frequency),
    }


def _best_piecewise_quadratic(times_s: FloatArray, values_s: FloatArray) -> Json:
    best: tuple[float, int, FloatArray, FloatArray] | None = None
    for split in range(24, len(times_s) - 24):
        left_reference = float(np.mean(times_s[:split]))
        right_reference = float(np.mean(times_s[split:]))
        left = np.polyfit(times_s[:split] - left_reference, values_s[:split], 2)
        right = np.polyfit(times_s[split:] - right_reference, values_s[split:], 2)
        residuals = np.concatenate(
            (
                values_s[:split] - np.polyval(left, times_s[:split] - left_reference),
                values_s[split:] - np.polyval(right, times_s[split:] - right_reference),
            )
        )
        rms = float(np.sqrt(np.mean(residuals**2)))
        if best is None or rms < best[0]:
            best = (rms, split, np.append(left, left_reference), np.append(right, right_reference))
    if best is None:
        raise ValueError("PSS track is too short for piecewise fitting")
    rms, split, left, right = best
    midpoint = float((times_s[split - 1] + times_s[split]) / 2.0)
    left_value = float(np.polyval(left[:3], midpoint - left[3]))
    right_value = float(np.polyval(right[:3], midpoint - right[3]))
    return {
        "split_left_s": float(times_s[split - 1]),
        "split_right_s": float(times_s[split]),
        "split_midpoint_s": midpoint,
        "rms_us": rms * 1e6,
        "fitted_step_us": (right_value - left_value) * 1e6,
    }


def _alias_statistics(product: Json) -> Json:
    transition_values: list[tuple[float, float, float]] = []
    by_locklet: list[Json] = []
    for locklet in _complete_locklets(product):
        rows = _inlier_observations(locklet)
        count = 0
        for left, right in zip(rows, rows[1:], strict=False):
            if left["hough_alias_index"] == right["hough_alias_index"]:
                continue
            count += 1
            transition_values.append(
                (
                    abs(float(right["raw_cfo_hz"]) - float(left["raw_cfo_hz"])),
                    abs(float(right["canonical_cfo_hz"]) - float(left["canonical_cfo_hz"])),
                    abs(float(right["quadratic_residual_s"]) - float(left["quadratic_residual_s"]))
                    * 1e6,
                )
            )
        by_locklet.append(
            {
                "hough_label": locklet["source_hough_track_label"],
                "locklet_index": locklet["locklet_index"],
                "transition_count": count,
            }
        )
    values = np.asarray(transition_values, dtype=float)
    return {
        "transition_count": len(transition_values),
        "median_absolute_raw_cfo_jump_hz": (
            float(np.median(values[:, 0])) if len(values) else None
        ),
        "median_absolute_canonical_cfo_jump_hz": (
            float(np.median(values[:, 1])) if len(values) else None
        ),
        "median_absolute_timing_residual_jump_us": (
            float(np.median(values[:, 2])) if len(values) else None
        ),
        "by_locklet": by_locklet,
        "_transition_values": transition_values,
    }


def epoch_quantization_statistics(locklet: Json, sample_rate_hz: float) -> Json:
    """Compare selected integer epochs with the nearest fitted-model sample."""

    fit = locklet["quadratic_fit"]
    frame_period_s = 1.0 / 750.0
    sample_offsets: list[int] = []
    model_rounding_errors_us: list[float] = []
    for item in _inlier_observations(locklet):
        time_s = float(item["global_center_time_s"])
        delta_s = time_s - float(fit["reference_time_s"])
        predicted_phase_s = (
            float(fit["phase_at_reference_s"])
            + float(fit["timing_drift_s_s"]) * delta_s
            + 0.5 * float(fit["timing_curvature_s_s2"]) * delta_s**2
        )
        selected_epoch_s = float(item["global_epoch_device_sample"]) / sample_rate_hz
        frame_index = round((selected_epoch_s - predicted_phase_s) / frame_period_s)
        predicted_epoch_s = predicted_phase_s + frame_index * frame_period_s
        nearest_sample = round(predicted_epoch_s * sample_rate_hz)
        sample_offsets.append(int(item["global_epoch_device_sample"]) - nearest_sample)
        model_rounding_errors_us.append((nearest_sample / sample_rate_hz - predicted_epoch_s) * 1e6)
    offsets = np.asarray(sample_offsets, dtype=int)
    rounding = np.asarray(model_rounding_errors_us, dtype=float)
    return {
        "point_count": len(offsets),
        "nearest_model_sample_fraction": float(np.mean(offsets == 0)),
        "nearest_or_adjacent_model_sample_fraction": float(np.mean(np.abs(offsets) <= 1)),
        "sample_offset_counts": {str(int(key)): value for key, value in Counter(offsets).items()},
        "model_rounding_error_rms_us": float(np.sqrt(np.mean(rounding**2))),
    }


def _full_windows(product: Json) -> list[Json]:
    return [item for segment in product["segments"] for item in segment["windows"]]


def _margin_statistics(product: Json, low_start_s: float, low_stop_s: float) -> Json:
    rows = [
        item
        for item in _full_windows(product)
        if low_start_s <= float(item["global_center_time_s"]) <= low_stop_s
        and item["glrt_margin"] is not None
    ]
    margins = np.asarray([item["glrt_margin"] for item in rows], dtype=float)
    if not len(margins):
        raise ValueError("GLRT full-capture product has no comparison windows")
    return {
        "window_count": len(margins),
        "margin_pass_count": int(np.count_nonzero(margins >= 0.025)),
        "margin_pass_fraction": float(np.mean(margins >= 0.025)),
        "median_margin": float(np.median(margins)),
        "p90_margin": float(np.quantile(margins, 0.90)),
        "p99_margin": float(np.quantile(margins, 0.99)),
    }


def _rate_statistics(product: Json, pss: Json, start_s: float, stop_s: float) -> Json | None:
    rates: list[float] = []
    for locklet in _complete_locklets(product):
        selection = locklet["cfo_selection"]
        coefficients = selection.get("quadratic_coefficients_hz")
        reference_s = selection.get("reference_time_s")
        if coefficients is None or reference_s is None:
            continue
        for row in _inlier_observations(locklet):
            high_time_s = float(row["global_center_time_s"]) + _high_time_offset_s(product, pss)
            if start_s <= high_time_s <= stop_s:
                rates.append(
                    float(coefficients[1])
                    + float(coefficients[2])
                    * (float(row["global_center_time_s"]) - float(reference_s))
                )
    if not rates:
        return None
    return {
        "support_point_count": len(rates),
        "mean_hz_s": float(np.mean(rates)),
        "median_hz_s": float(np.median(rates)),
        "minimum_hz_s": float(np.min(rates)),
        "maximum_hz_s": float(np.max(rates)),
    }


def _quadratic_epoch_refit(rows: list[Json], rf_reference_hz: float) -> Json:
    times_s = np.asarray([item["global_center_time_s"] for item in rows], dtype=float)
    phases_s = np.asarray([item["unwrapped_frame_phase_s"] for item in rows], dtype=float)
    reference_s = float(np.mean(times_s))
    coefficients = np.polyfit(times_s - reference_s, phases_s, 2)
    residuals_us = (phases_s - np.polyval(coefficients, times_s - reference_s)) * 1e6
    return {
        "point_count": len(rows),
        "physical_rate_hz_s": -rf_reference_hz * 2.0 * float(coefficients[0]),
        "rms_us": float(np.sqrt(np.mean(residuals_us**2))),
    }


def _u_structure_statistics(epoch: Json, full: Json, pss: Json) -> Json:
    representative = max(
        _complete_locklets(epoch), key=lambda item: len(_inlier_observations(item))
    )
    rows = _inlier_observations(representative)
    fit = representative["quadratic_fit"]
    curvature = float(fit["timing_curvature_s_s2"])
    vertex_s = float(fit["reference_time_s"]) - float(fit["timing_drift_s_s"]) / curvature
    nearby = [
        item
        for item in rows
        if vertex_s - 1.1 <= float(item["global_center_time_s"]) <= vertex_s + 1.2
    ]
    windows = {item["opportunity_index"]: item for item in _full_windows(full)}
    groups: Counter[tuple[int, float, int]] = Counter()
    for item in nearby:
        window = windows[item["opportunity_index"]]
        groups[
            (
                int(item["opportunity_index"]) % 2,
                round(float(item["frame_phase_s"]) * 1e6, 6),
                int(item["global_epoch_device_sample"]) - int(window["global_device_sample_start"]),
            )
        ] += 1
    (parity, phase_us, local_epoch_sample), _ = groups.most_common(1)[0]
    plateau = [
        item
        for item in nearby
        if int(item["opportunity_index"]) % 2 == parity
        and math.isclose(float(item["frame_phase_s"]) * 1e6, phase_us, abs_tol=1e-9)
        and int(item["global_epoch_device_sample"])
        - int(windows[item["opportunity_index"]]["global_device_sample_start"])
        == local_epoch_sample
    ]
    rf_reference_hz = float(epoch["rf_reference_hz"])
    excluded_vertex = [
        item
        for item in rows
        if not vertex_s - 1.1 <= float(item["global_center_time_s"]) <= vertex_s + 1.2
    ]
    return {
        "hough_label": representative["source_hough_track_label"],
        "locklet_index": representative["locklet_index"],
        "quadratic_vertex_s_low_rate_clock": vertex_s,
        "quadratic_vertex_s_native25_clock": vertex_s + _high_time_offset_s(epoch, pss),
        "residual_branch_curvature_us_s2": -curvature * 1e6,
        "dominant_plateau": {
            "point_count": len(plateau),
            "opportunity_parity": parity,
            "frame_phase_us": phase_us,
            "unwrapped_frame_phase_us": float(
                np.median([item["unwrapped_frame_phase_s"] for item in plateau]) * 1e6
            ),
            "local_epoch_sample": local_epoch_sample,
            "start_s_low_rate_clock": float(min(item["global_center_time_s"] for item in plateau)),
            "stop_s_low_rate_clock": float(max(item["global_center_time_s"] for item in plateau)),
            "minimum_residual_us": float(
                min(item["quadratic_residual_s"] for item in plateau) * 1e6
            ),
            "maximum_residual_us": float(
                max(item["quadratic_residual_s"] for item in plateau) * 1e6
            ),
        },
        "rate_robustness": {
            "all_inliers": _quadratic_epoch_refit(rows, rf_reference_hz),
            "excluding_vertex_interval": _quadratic_epoch_refit(excluded_vertex, rf_reference_hz),
            "even_nonoverlap_parity": _quadratic_epoch_refit(
                [item for item in rows if int(item["opportunity_index"]) % 2 == 0],
                rf_reference_hz,
            ),
            "odd_nonoverlap_parity": _quadratic_epoch_refit(
                [item for item in rows if int(item["opportunity_index"]) % 2 == 1],
                rf_reference_hz,
            ),
        },
    }


def _stateful_replay_inventory(product: Json) -> Json:
    segments = [item for item in product["segments"] if item.get("local_science") is not None]
    rows: list[Json] = []
    final: list[Json] = []
    branch_count = 0
    for segment in segments:
        science = segment["local_science"]
        branch_count += len(science["dealiased_trajectory_bank"]["branches"])
        rows.extend(science["cfo_lift_replay"]["rows"])
        final.extend(science["final_trajectory_bank"]["trajectories"])
    multiplicity = Counter(item["branch_id"] for item in rows)
    return {
        "dealiased_branch_count": branch_count,
        "replay_candidate_count": len(rows),
        "final_candidate_count": len(final),
        "branches_with_multiple_alias_candidates": sum(
            value > 1 for value in multiplicity.values()
        ),
        "replay_candidates": [
            {
                "branch_id": item["branch_id"],
                "alias_index": item["alias_index"],
                "tier": item["tier"],
                "evaluated_probe_count": item["evaluated_probe_count"],
                "median_block_corrected_margin": item["median_block_corrected_margin"],
            }
            for item in rows
        ],
    }


def analyze(
    pss: Json,
    glrt_epoch_products: list[Json],
    glrt_full_products: list[Json],
    stateful_products: list[Json],
) -> tuple[Json, tuple[Json, ...], FloatArray, FloatArray]:
    products = [pss, *glrt_epoch_products, *glrt_full_products, *stateful_products]
    sessions = {item["source"]["session_id"] for item in products}
    if sessions != {CAPTURE_ID}:
        raise ValueError(f"unexpected or crossed sessions: {sorted(sessions)}")
    epoch_by_rx = {int(item["source"]["receiver_id"]): item for item in glrt_epoch_products}
    full_by_rx = {int(item["source"]["receiver_id"]): item for item in glrt_full_products}
    stateful_by_rx = {int(item["source"]["receiver_id"]): item for item in stateful_products}
    if set(epoch_by_rx) != {0, 1} or set(full_by_rx) != {0, 1} or set(stateful_by_rx) != {0, 1}:
        raise ValueError("exactly one RX0 and RX1 product of each GLRT kind is required")
    if int(pss["source"]["sample_rate_hz"]) != 25_000_000:
        raise ValueError("PSS source is not native 25 MS/s")

    track = _primary_pss_track(pss)
    modes, times_s, phases_s = _track_arrays(pss, track)
    primary_modes_by_time = {round(float(item["center_time_s"]), 9): item for item in modes}
    secondary_tracks: list[Json] = []
    for candidate in pss["tracks"]:
        if candidate["track_id"] == track["track_id"]:
            continue
        candidate_modes, candidate_times, _ = _track_arrays(pss, candidate)
        common_times = sorted(
            set(primary_modes_by_time).intersection(
                round(float(item), 9) for item in candidate_times
            )
        )
        phase_differences_us: list[float] = []
        candidate_by_time = {
            round(float(item["center_time_s"]), 9): item for item in candidate_modes
        }
        frame_period_s = 1.0 / 750.0
        for common_time in common_times:
            difference_s = float(primary_modes_by_time[common_time]["frame_phase_s"]) - float(
                candidate_by_time[common_time]["frame_phase_s"]
            )
            circular_difference_s = (
                difference_s + frame_period_s / 2.0
            ) % frame_period_s - frame_period_s / 2.0
            phase_differences_us.append(circular_difference_s * 1e6)
        phase_differences = np.asarray(phase_differences_us, dtype=float)
        secondary_tracks.append(
            {
                "track_id": candidate["track_id"],
                "mode_count": len(candidate_modes),
                "time_count_also_present_in_primary": len(common_times),
                "shared_time_fraction": len(common_times) / len(candidate_modes),
                "shared_time_phase_difference_rms_us": (
                    float(np.sqrt(np.mean(phase_differences**2)))
                    if len(phase_differences)
                    else None
                ),
                "frequency_hypothesis_counts": {
                    str(int(key)): value
                    for key, value in Counter(
                        float(item["selected_frequency_offset_hz"]) for item in candidate_modes
                    ).items()
                },
            }
        )
    residuals_us = np.asarray(track["residuals_us"], dtype=float)
    segment_ids = np.asarray([item["continuity_segment_index"] for item in modes], dtype=np.int64)
    frequency_offsets = np.asarray(
        [item["selected_frequency_offset_hz"] for item in modes], dtype=float
    )
    validation = polynomial_validation(times_s, phases_s)
    piecewise = _best_piecewise_quadratic(times_s, phases_s)
    rf_reference_hz = float(np.median([item["rf_reference_hz"] for item in glrt_epoch_products]))
    timing_curvature = 2.0 * float(track["coefficients_descending_s"][0])
    pss_physical_rate = -rf_reference_hz * timing_curvature

    complete_window_centers = {
        round(
            (float(item["input_device_sample_start"]) + float(item["input_device_sample_stop"]))
            / (2.0 * float(pss["source"]["sample_rate_hz"])),
            9,
        )
        for item in pss["blocks"]
        if times_s[0]
        <= (float(item["input_device_sample_start"]) + float(item["input_device_sample_stop"]))
        / (2.0 * float(pss["source"]["sample_rate_hz"]))
        <= times_s[-1]
    }
    selected_window_centers = {round(float(item["center_time_s"]), 9) for item in modes}
    nominal_wall_stride_opportunities = (
        math.floor((float(times_s[-1]) - float(times_s[0])) / 0.0625) + 1
    )

    glrt: Json = {}
    for receiver_id in (0, 1):
        epoch = epoch_by_rx[receiver_id]
        offset = _high_time_offset_s(epoch, pss)
        complete = _complete_locklets(epoch)
        overlaps = [
            item
            for item in complete
            if float(item["global_end_time_s"]) + offset >= times_s[0]
            and float(item["global_start_time_s"]) + offset <= times_s[-1]
        ]
        glrt[f"RX{receiver_id}"] = {
            "complete_locklet_count": len(complete),
            "insufficient_locklet_count": sum(
                item["status"] == "insufficient" for item in epoch["locklets"]
            ),
            "overlapping_complete_locklets": [
                {
                    "hough_label": item["source_hough_track_label"],
                    "locklet_index": item["locklet_index"],
                    "candidate_start_s_on_native25_clock": float(item["global_start_time_s"])
                    + offset,
                    "candidate_stop_s_on_native25_clock": float(item["global_end_time_s"]) + offset,
                    "inlier_start_s_on_native25_clock": float(
                        min(
                            observation["global_center_time_s"]
                            for observation in _inlier_observations(item)
                        )
                    )
                    + offset,
                    "inlier_stop_s_on_native25_clock": float(
                        max(
                            observation["global_center_time_s"]
                            for observation in _inlier_observations(item)
                        )
                    )
                    + offset,
                    "point_count": item["quadratic_fit"]["point_count"],
                    "quadratic_rms_us": item["quadratic_fit"]["residual_rms_s"] * 1e6,
                    "timing_derived_physical_rate_hz_s": item["quadratic_fit"][
                        "equivalent_doppler_rate_hz_s"
                    ],
                }
                for item in overlaps
            ],
            "cfo_rate_over_pss_support": _rate_statistics(
                epoch, pss, float(times_s[0]), float(times_s[-1])
            ),
            "alias_transitions": {
                key: value
                for key, value in _alias_statistics(epoch).items()
                if not key.startswith("_")
            },
            "margin_over_pss_wall_interval": _margin_statistics(
                full_by_rx[receiver_id],
                float(times_s[0] - offset),
                float(times_s[-1] - offset),
            ),
            "stateful_replay": _stateful_replay_inventory(stateful_by_rx[receiver_id]),
            "complete_locklet_quantization": [
                {
                    "hough_label": item["source_hough_track_label"],
                    "locklet_index": item["locklet_index"],
                    **epoch_quantization_statistics(item, float(epoch["source"]["sample_rate_hz"])),
                }
                for item in complete
            ],
        }
        if receiver_id == 0:
            glrt[f"RX{receiver_id}"]["u_structure_diagnostic"] = _u_structure_statistics(
                epoch, full_by_rx[receiver_id], pss
            )

    logical = int(pss["source"]["logical_sample_count"])
    observed = int(pss["source"]["observed_sample_count"])
    missing = int(pss["source"]["missing_sample_count"])
    glrt_rx0_rate = glrt["RX0"]["cfo_rate_over_pss_support"]
    assert glrt_rx0_rate is not None
    summary: Json = {
        "schema_version": 1,
        "analysis_kind": "7fea7427619d-pss-glrt-deep-dive",
        "capture_id": CAPTURE_ID,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "source_product_digests": {
            "pss": pss["result_digest"],
            **{f"glrt_epoch_RX{rx}": epoch_by_rx[rx]["result_digest"] for rx in (0, 1)},
            **{f"glrt_full_RX{rx}": full_by_rx[rx]["result_digest"] for rx in (0, 1)},
        },
        "capture_geometry": {
            "native25_observed_samples": observed,
            "native25_missing_samples": missing,
            "native25_logical_samples": logical,
            "native25_observed_density": observed / logical,
            "native25_continuity_segment_count": len(pss["source"]["continuity_segments"]),
            "native25_counter_gap_count": len(pss["source"]["continuity_segments"]) - 1,
            "native25_bandwidth_hz": 25_000_000,
            "native25_center_frequency_hz": pss["source"]["tuned_center_frequency_hz"],
            "low_rate_center_frequency_hz": epoch_by_rx[0]["source"]["tuned_center_frequency_hz"],
            "low_rate_offset_inside_native25_hz": (
                epoch_by_rx[0]["source"]["tuned_center_frequency_hz"]
                - pss["source"]["tuned_center_frequency_hz"]
            ),
            "cross_stream_first_estimate_offset_s": _high_time_offset_s(epoch_by_rx[0], pss),
            "native25_first_timestamp_half_width_ms": (
                pss["source"]["timing"]["first_latest_utc_ns"]
                - pss["source"]["timing"]["first_earliest_utc_ns"]
            )
            / 2e6,
            "low_rate_first_timestamp_half_width_ms": (
                epoch_by_rx[0]["source"]["timing"]["first_latest_utc_ns"]
                - epoch_by_rx[0]["source"]["timing"]["first_earliest_utc_ns"]
            )
            / 2e6,
        },
        "configuration": {
            "pss_decimation_factor": pss["projections"][0]["decimation_factor"],
            "pss_window_ms": 125.0,
            "pss_stride_ms": 62.5,
            "glrt_window_ms": 20.0,
            "glrt_stride_ms": 10.0,
            "glrt_epoch_sample_spacing_us": 0.4,
            "glrt_uniform_quantization_rms_us": 1e6 / (2_500_000 * math.sqrt(12)),
            "cfo_alias_spacing_hz": epoch_by_rx[0]["cfo_alias_spacing_hz"],
        },
        "pss": {
            "track_count": len(pss["tracks"]),
            "track_mode_counts": [len(item["mode_ids"]) for item in pss["tracks"]],
            "secondary_track_comparison": secondary_tracks,
            "selected_track_id": track["track_id"],
            "selected_mode_count": len(modes),
            "selected_start_s": float(times_s[0]),
            "selected_stop_s": float(times_s[-1]),
            "selected_wall_span_s": float(times_s[-1] - times_s[0]),
            "selected_continuity_segment_count": len(set(segment_ids)),
            "selected_counter_gap_crossings": int(np.count_nonzero(np.diff(segment_ids))),
            "available_unique_complete_window_count": len(complete_window_centers),
            "selected_available_complete_window_fraction": len(selected_window_centers)
            / len(complete_window_centers),
            "nominal_wall_stride_opportunity_count": nominal_wall_stride_opportunities,
            "selected_nominal_wall_stride_fraction": len(selected_window_centers)
            / nominal_wall_stride_opportunities,
            "global_quadratic_rms_us": track["rms_residual_us"],
            "global_quadratic_maximum_absolute_residual_us": track["maximum_absolute_residual_us"],
            "robust_z_median": float(np.median([item["robust_z"] for item in modes])),
            "robust_z_minimum": float(np.min([item["robust_z"] for item in modes])),
            "strong_window_fraction_median": float(
                np.median([item["strong_window_count"] / item["window_count"] for item in modes])
            ),
            "frequency_hypothesis_counts": {
                str(int(key)): value for key, value in Counter(frequency_offsets).items()
            },
            "transition_statistics": transition_statistics(
                residuals_us, segment_ids, frequency_offsets
            ),
            "polynomial_validation": validation,
            "best_piecewise_quadratic": piecewise,
        },
        "frequency_rate": {
            "rf_reference_hz": rf_reference_hz,
            "pss_physical_arrival_delay_rate_hz_s": pss_physical_rate,
            "pss_same_observed_coordinate_rate_hz_s": -pss_physical_rate,
            "glrt_rx0_canonical_cfo_mean_rate_hz_s": glrt_rx0_rate["mean_hz_s"],
            "same_coordinate_magnitude_difference_percent": (
                abs(abs(glrt_rx0_rate["mean_hz_s"]) - pss_physical_rate) / pss_physical_rate * 100.0
            ),
            "interpretation": (
                "PSS physical arrival-delay sign is mirrored relative to observed-IQ GLRT. "
                "After an explicit coordinate mirror, their mean rates agree closely; absolute "
                "received-RF sign remains uncalibrated."
            ),
        },
        "glrt": glrt,
        "conclusions": [
            "Native-25 PSS retains one high-quality quadratic track across six counter gaps.",
            "PSS search-frequency changes and counter-gap crossings do not produce elevated "
            "timing jumps relative to ordinary adjacent modes.",
            "The RX0 GLRT CFO rate agrees with the same-coordinate PSS rate to substantially "
            "better than one percent.",
            "RX1 does not provide a complete GLRT locklet over the PSS interval; its margin-pass "
            "density is much lower than RX0, so absence is receiver evidence rather than a "
            "cross-rate contradiction.",
            "Every complete GLRT locklet is close to the 2.5 MS/s integer-epoch quantization "
            "floor; visible fans are quantization structure rather than resolved timing waves.",
            "The best PSS piecewise split is smaller than one native-25 sample and is not shared "
            "by both GLRT receivers, unlike the event in 6f8ad3b4fb91.",
        ],
    }
    return summary, modes, times_s, phases_s


def _plot_frequency_and_support(
    destination: Path,
    summary: Json,
    pss: Json,
    modes: tuple[Json, ...],
    times_s: FloatArray,
    glrt_products: list[Json],
) -> None:
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        constrained_layout=True,
        gridspec_kw={"height_ratios": (1.0, 1.35, 0.75)},
    )
    physical = summary["frequency_rate"]["pss_physical_arrival_delay_rate_hz_s"] / 1e3
    same = summary["frequency_rate"]["pss_same_observed_coordinate_rate_hz_s"] / 1e3
    axes[0].axhline(
        physical, color=PSS_COLOR, lw=2.4, label=f"PSS physical sign {physical:+.3f} kHz/s"
    )
    axes[0].axhline(
        same,
        color=PSS_COLOR,
        lw=2.0,
        ls="--",
        label=f"PSS same observed coordinate {same:+.3f} kHz/s",
    )
    for product in sorted(glrt_products, key=lambda item: item["source"]["receiver_id"]):
        receiver_id = int(product["source"]["receiver_id"])
        first = True
        for locklet in _complete_locklets(product):
            selection = locklet["cfo_selection"]
            coefficients = selection["quadratic_coefficients_hz"]
            reference = float(selection["reference_time_s"])
            observations = _inlier_observations(locklet)
            local_times = np.asarray([item["global_center_time_s"] for item in observations])
            high_times = local_times + _high_time_offset_s(product, pss)
            keep = (high_times >= times_s[0]) & (high_times <= times_s[-1])
            if not np.any(keep):
                continue
            rate = float(coefficients[1]) + float(coefficients[2]) * (local_times - reference)
            axes[0].plot(
                high_times[keep],
                rate[keep] / 1e3,
                color=RX_COLORS[receiver_id],
                lw=1.8,
                label=f"RX{receiver_id} canonical CFO derivative" if first else None,
            )
            first = False
    axes[0].axhline(0, color="#111827", lw=0.8)
    axes[0].set_ylabel("Frequency rate (kHz/s)")
    axes[0].set_title("A · Sign mirroring exposes close native-PSS/RX0-GLRT rate agreement")
    axes[0].legend(loc="center left", fontsize=8)

    track = _primary_pss_track(pss)
    axes[1].scatter(
        times_s,
        np.asarray(track["residuals_us"]),
        marker="x",
        s=24,
        color=PSS_COLOR,
        label=f"native-25 PSS quadratic residual · RMS {track['rms_residual_us']:.3f} µs",
        zorder=3,
    )
    for product in glrt_products:
        receiver_id = int(product["source"]["receiver_id"])
        for locklet in _complete_locklets(product):
            observations = _inlier_observations(locklet)
            high_times = np.asarray(
                [
                    item["global_center_time_s"] + _high_time_offset_s(product, pss)
                    for item in observations
                ]
            )
            keep = (high_times >= times_s[0]) & (high_times <= times_s[-1])
            if not np.any(keep):
                continue
            axes[1].scatter(
                high_times[keep],
                np.asarray([item["quadratic_residual_s"] for item in observations])[keep] * 1e6,
                s=8,
                alpha=0.5,
                color=RX_COLORS[receiver_id],
                label=(
                    f"RX{receiver_id} {locklet['source_hough_track_label']}/"
                    f"L{locklet['locklet_index']} quadratic residual"
                ),
            )
    axes[1].axhspan(-0.2, 0.2, color="#94a3b8", alpha=0.12, label="±0.5 low-rate sample")
    axes[1].axhline(0, color="#111827", lw=0.8)
    axes[1].set_ylabel("Independent quadratic residual (µs)")
    axes[1].set_title("B · PSS is smooth across gaps; only RX0 supplies shared GLRT timing")
    axes[1].legend(loc="upper left", fontsize=8, ncol=2)

    sample_rate = float(pss["source"]["sample_rate_hz"])
    for segment in pss["source"]["continuity_segments"]:
        start = float(segment["device_sample_start"]) / sample_rate
        stop = float(segment["device_sample_stop"]) / sample_rate
        axes[2].plot([start, stop], [2, 2], color=PSS_COLOR, lw=8, solid_capstyle="butt")
    axes[2].scatter(
        times_s,
        np.full(len(times_s), 2.0),
        marker="|",
        s=28,
        color="#7c2d12",
        label="native-25 selected PSS modes",
    )
    for row, receiver_id in ((1.0, 0), (0.0, 1)):
        product = next(
            item for item in glrt_products if item["source"]["receiver_id"] == receiver_id
        )
        offset = _high_time_offset_s(product, pss)
        for locklet in _complete_locklets(product):
            start = float(locklet["global_start_time_s"]) + offset
            stop = float(locklet["global_end_time_s"]) + offset
            axes[2].plot(
                [start, stop],
                [row, row],
                color=RX_COLORS[receiver_id],
                lw=7,
                solid_capstyle="butt",
            )
    axes[2].set_yticks((0, 1, 2), ("GLRT RX1", "GLRT RX0", "PSS native-25"))
    axes[2].set_xlabel("Seconds from native 25 MS/s stream start")
    axes[2].set_title("C · Complete-locklet support is strongly receiver-asymmetric")
    axes[2].set_xlim(float(times_s[0]) - 1, float(times_s[-1]) + 1)
    for axis in axes:
        axis.grid(True, alpha=0.22)
    figure.suptitle(f"{CAPTURE_ID} · frequency, timing, and support alignment")
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_gap_robustness(
    destination: Path,
    summary: Json,
    pss: Json,
    modes: tuple[Json, ...],
    times_s: FloatArray,
) -> None:
    track = _primary_pss_track(pss)
    residuals = np.asarray(track["residuals_us"], dtype=float)
    segment_ids = np.asarray([item["continuity_segment_index"] for item in modes])
    frequencies = np.asarray([item["selected_frequency_offset_hz"] for item in modes])
    figure, axes = plt.subplots(2, 1, figsize=(14, 8), constrained_layout=True)
    for color_index, segment_id in enumerate(np.unique(segment_ids)):
        keep = segment_ids == segment_id
        axes[0].scatter(
            times_s[keep],
            residuals[keep],
            marker="x",
            s=28,
            color=SEGMENT_COLORS[color_index % len(SEGMENT_COLORS)],
            label=f"continuity segment {segment_id}",
        )
    axes[0].axhline(0, color="#111827", lw=0.8)
    axes[0].set_ylabel("Global-quadratic residual (µs)")
    axes[0].set_title(
        "A · One PSS trajectory remains phase-consistent through six counter-gap crossings"
    )
    axes[0].legend(loc="upper right", fontsize=8, ncol=2)

    jumps = np.abs(np.diff(residuals))
    crosses = segment_ids[1:] != segment_ids[:-1]
    changes = frequencies[1:] != frequencies[:-1]
    categories = (
        ("ordinary", ~crosses & ~changes, "#64748b"),
        ("counter gap", crosses, PSS_COLOR),
        ("PSS frequency\nhypothesis change", changes, "#7c3aed"),
    )
    for index, (_label, keep, color) in enumerate(categories):
        values = jumps[keep]
        x = np.full(len(values), float(index)) + np.linspace(-0.08, 0.08, len(values))
        axes[1].scatter(x, values, s=16, alpha=0.55, color=color)
        axes[1].plot(
            [index - 0.22, index + 0.22],
            [np.median(values), np.median(values)],
            color="#111827",
            lw=2,
        )
    axes[1].axhline(0.04, color="#111827", ls="--", label="one native-25 sample = 0.04 µs")
    axes[1].set_xticks(range(3), [item[0] for item in categories])
    axes[1].set_ylabel("Adjacent absolute residual jump (µs)")
    axes[1].set_title("B · Gap and search-hypothesis transitions are not timing outliers")
    axes[1].legend(loc="upper right")
    for axis in axes:
        axis.grid(True, alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · native-25 gap robustness · observed density "
        f"{summary['capture_geometry']['native25_observed_density']:.1%}"
    )
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_quantization_alias(
    destination: Path,
    summary: Json,
    pss: Json,
    glrt_products: list[Json],
) -> None:
    candidates = [
        (len(_inlier_observations(locklet)), product, locklet)
        for product in glrt_products
        for locklet in _complete_locklets(product)
    ]
    _, representative_product, representative = max(candidates, key=lambda item: item[0])
    observations = _inlier_observations(representative)
    times = np.asarray(
        [
            item["global_center_time_s"] + _high_time_offset_s(representative_product, pss)
            for item in observations
        ]
    )
    residuals = np.asarray([item["quadratic_residual_s"] * 1e6 for item in observations])
    fit = representative["quadratic_fit"]
    sample_rate_hz = float(representative_product["source"]["sample_rate_hz"])
    frame_period_s = 1.0 / 750.0
    sample_offsets: list[int] = []
    for item in observations:
        delta_s = float(item["global_center_time_s"]) - float(fit["reference_time_s"])
        predicted_phase_s = (
            float(fit["phase_at_reference_s"])
            + float(fit["timing_drift_s_s"]) * delta_s
            + 0.5 * float(fit["timing_curvature_s_s2"]) * delta_s**2
        )
        selected_epoch_s = float(item["global_epoch_device_sample"]) / sample_rate_hz
        frame_index = round((selected_epoch_s - predicted_phase_s) / frame_period_s)
        predicted_epoch_s = predicted_phase_s + frame_index * frame_period_s
        sample_offsets.append(
            int(item["global_epoch_device_sample"]) - round(predicted_epoch_s * sample_rate_hz)
        )
    sample_offsets_array = np.asarray(sample_offsets, dtype=int)
    figure = plt.figure(figsize=(14, 9), constrained_layout=True)
    grid = figure.add_gridspec(2, 2, height_ratios=(1.2, 1.0))
    top = figure.add_subplot(grid[0, :])
    left = figure.add_subplot(grid[1, 0])
    right = figure.add_subplot(grid[1, 1])
    for value, color in ((-1, "#a855f7"), (0, "#2563eb"), (1, "#db2777")):
        keep = sample_offsets_array == value
        top.scatter(
            times[keep],
            residuals[keep],
            s=10,
            alpha=0.65,
            color=color,
            label=f"selected epoch is nearest-model sample {value:+d}",
        )
    top.axhspan(-0.2, 0.2, color="#94a3b8", alpha=0.13, label="±0.5 input sample")
    top.axhline(0, color="#111827", lw=0.8)
    top.set_ylabel("Quadratic residual (µs)")
    top.set_title(
        f"A · RX{representative_product['source']['receiver_id']} "
        f"{representative['source_hough_track_label']}/L{representative['locklet_index']} "
        "fan is entirely nearest/adjacent integer-sample selection"
    )
    top.legend(loc="upper left", fontsize=8)

    labels: list[str] = []
    rms: list[float] = []
    colors: list[str] = []
    for receiver_id in (0, 1):
        product = next(
            item for item in glrt_products if item["source"]["receiver_id"] == receiver_id
        )
        for locklet in _complete_locklets(product):
            labels.append(
                f"RX{receiver_id}\n{locklet['source_hough_track_label']}/L{locklet['locklet_index']}"
            )
            rms.append(float(locklet["quadratic_fit"]["residual_rms_s"]) * 1e6)
            colors.append(RX_COLORS[receiver_id])
    left.bar(np.arange(len(labels)), rms, color=colors, alpha=0.82)
    floor = summary["configuration"]["glrt_uniform_quantization_rms_us"]
    left.axhline(floor, color="#111827", ls="--", label=f"uniform sample floor {floor:.3f} µs")
    left.set_xticks(np.arange(len(labels)), labels, fontsize=8)
    left.set_ylabel("Quadratic residual RMS (µs)")
    left.set_title("B · All four complete locklets are quantization-limited")
    left.legend(loc="upper left", fontsize=8)

    offsets = {0: -0.08, 1: 0.08}
    for receiver_id in (0, 1):
        product = next(
            item for item in glrt_products if item["source"]["receiver_id"] == receiver_id
        )
        alias = _alias_statistics(product)
        values = np.asarray(alias["_transition_values"], dtype=float)
        if not len(values):
            continue
        right.scatter(
            np.full(len(values), offsets[receiver_id]),
            values[:, 0],
            s=30,
            color=RX_COLORS[receiver_id],
            label=f"RX{receiver_id}",
        )
        right.scatter(
            np.full(len(values), 1 + offsets[receiver_id]),
            values[:, 1],
            s=30,
            color=RX_COLORS[receiver_id],
        )
    right.axhline(
        summary["configuration"]["cfo_alias_spacing_hz"],
        color="#111827",
        ls="--",
        label="2.5M/11 alias spacing",
    )
    right.set_yscale("log")
    right.set_xticks((0, 1), ("raw CFO jump", "canonical CFO jump"))
    right.set_ylabel("Absolute adjacent jump (Hz)")
    right.set_title("C · Integer alias removal collapses the raw 227 kHz jumps")
    right.legend(loc="best", fontsize=8)
    for axis in (top, left, right):
        axis.grid(True, alpha=0.22)
    figure.suptitle(f"{CAPTURE_ID} · GLRT quantization and CFO-alias audit")
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_stride_plateau(
    destination: Path,
    pss: Json,
    epoch: Json,
    full: Json,
) -> None:
    representative = max(
        _complete_locklets(epoch), key=lambda item: len(_inlier_observations(item))
    )
    rows = _inlier_observations(representative)
    fit = representative["quadratic_fit"]
    curvature = float(fit["timing_curvature_s_s2"])
    vertex_s = float(fit["reference_time_s"]) - float(fit["timing_drift_s_s"]) / curvature
    selected = [
        item
        for item in rows
        if vertex_s - 1.25 <= float(item["global_center_time_s"]) <= vertex_s + 1.25
    ]
    offset_s = _high_time_offset_s(epoch, pss)
    times_s = np.asarray([float(item["global_center_time_s"]) + offset_s for item in selected])
    phases_us = np.asarray([float(item["unwrapped_frame_phase_s"]) * 1e6 for item in selected])
    frame_phases_us = np.asarray([float(item["frame_phase_s"]) * 1e6 for item in selected])
    residuals_us = np.asarray([float(item["quadratic_residual_s"]) * 1e6 for item in selected])
    parity = np.asarray([int(item["opportunity_index"]) % 2 for item in selected])
    windows = {item["opportunity_index"]: item for item in _full_windows(full)}
    local_epochs = np.asarray(
        [
            int(item["global_epoch_device_sample"])
            - int(windows[item["opportunity_index"]]["global_device_sample_start"])
            for item in selected
        ]
    )
    grid_low_s = np.linspace(vertex_s - 1.25, vertex_s + 1.25, 500)
    local_s = grid_low_s - float(fit["reference_time_s"])
    prediction_us = (
        float(fit["phase_at_reference_s"])
        + float(fit["timing_drift_s_s"]) * local_s
        + 0.5 * curvature * local_s**2
    ) * 1e6
    grid_native_s = grid_low_s + offset_s
    plateau_points = (parity == 0) & np.isclose(frame_phases_us, 42.4)
    plateau_phase_us = float(np.median(phases_us[plateau_points]))

    figure, axes = plt.subplots(3, 1, figsize=(14, 10), constrained_layout=True)
    for value, color, label in (
        (0, "#2563eb", "even windows · mutually non-overlapping"),
        (1, "#a855f7", "odd windows · mutually non-overlapping"),
    ):
        keep = parity == value
        axes[0].scatter(
            times_s[keep],
            phases_us[keep],
            s=19,
            alpha=0.72,
            color=color,
            label=label,
        )
        axes[1].scatter(times_s[keep], residuals_us[keep], s=19, alpha=0.72, color=color)
        axes[2].scatter(times_s[keep], local_epochs[keep], s=19, alpha=0.72, color=color)
    axes[0].plot(
        grid_native_s,
        prediction_us,
        color=PSS_COLOR,
        lw=2.0,
        label="continuous global quadratic",
    )
    axes[0].set_ylabel("Unwrapped frame phase (µs)")
    axes[0].ticklabel_format(style="plain", axis="y", useOffset=False)
    axes[0].set_title(
        "A · Raw epochs sit on horizontal integer-sample plateaus near the timing vertex"
    )
    axes[0].legend(loc="best", fontsize=8)

    axes[1].plot(
        grid_native_s,
        plateau_phase_us - prediction_us,
        color="#1d4ed8",
        lw=2.0,
        label="constant even-window plateau minus quadratic prediction",
    )
    axes[1].axhspan(-0.2, 0.2, color="#94a3b8", alpha=0.13, label="±0.5 input sample")
    axes[1].axhline(0, color="#111827", lw=0.8)
    axes[1].set_ylabel("Quadratic residual (µs)")
    axes[1].set_title("B · Subtraction converts the fixed 42.400 µs plateau into the blue U")
    axes[1].legend(loc="best", fontsize=8)

    axes[2].set_ylabel("Epoch sample inside 20 ms window")
    axes[2].set_xlabel("Seconds from native 25 MS/s stream start")
    axes[2].set_title("C · The 10 ms stride advances 7.5 frames, creating two parity coordinates")
    for axis in axes:
        axis.axvline(vertex_s + offset_s, color="#111827", ls="--", lw=1.0)
        axis.grid(True, alpha=0.22)
    figure.suptitle(f"{CAPTURE_ID} · anatomy of the apparent GLRT residual U")
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_receiver_and_model_selection(
    destination: Path,
    summary: Json,
    pss: Json,
    modes: tuple[Json, ...],
    times_s: FloatArray,
    full_products: list[Json],
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(14, 10), constrained_layout=True)
    for receiver_id in (0, 1):
        product = next(
            item for item in full_products if item["source"]["receiver_id"] == receiver_id
        )
        offset = _high_time_offset_s(product, pss)
        windows = _full_windows(product)
        local_times = np.asarray([item["global_center_time_s"] for item in windows])
        high_times = local_times + offset
        margins = np.asarray(
            [
                float(item["glrt_margin"]) if item["glrt_margin"] is not None else np.nan
                for item in windows
            ]
        )
        bins = np.floor(high_times).astype(int)
        x: list[float] = []
        fractions: list[float] = []
        for bin_index in np.unique(bins):
            keep = (bins == bin_index) & np.isfinite(margins)
            if not np.any(keep):
                continue
            x.append(float(bin_index) + 0.5)
            fractions.append(float(np.mean(margins[keep] >= 0.025)))
        axes[0].plot(
            x,
            fractions,
            marker="o",
            ms=3,
            lw=1.5,
            color=RX_COLORS[receiver_id],
            label=f"RX{receiver_id}",
        )
    axes[0].axvspan(times_s[0], times_s[-1], color=PSS_COLOR, alpha=0.08, label="selected PSS span")
    axes[0].set_ylabel("GLRT margin-pass fraction per second")
    axes[0].set_title("A · RX0, not RX1, carries sustained GLRT support during the PSS track")
    axes[0].legend(loc="upper right")

    validation = summary["pss"]["polynomial_validation"]
    degrees = np.asarray([int(key) for key in validation])
    cv = np.asarray([validation[str(value)]["blocked_cv_rms_us"] for value in degrees])
    training = np.asarray([validation[str(value)]["in_sample_rms_us"] for value in degrees])
    axes[1].plot(degrees, cv, marker="o", color="#be123c", label="1 s-blocked validation")
    axes[1].plot(degrees, training, marker="s", color="#64748b", label="in-sample")
    axes[1].set_yscale("log")
    axes[1].set_xticks(degrees)
    axes[1].set_xlabel("PSS timing polynomial degree")
    axes[1].set_ylabel("Residual RMS (µs, log scale)")
    axes[1].set_title(
        "B · Quadratic is strong; cubic/quartic absorb smaller segment-correlated structure"
    )
    axes[1].legend(loc="upper right")

    primary = _primary_pss_track(pss)
    primary_ids = set(primary["mode_ids"])
    for track in pss["tracks"]:
        track_modes, track_times, track_phases = _track_arrays(pss, track)
        reference = float(np.mean(track_times))
        affine = np.polyfit(track_times - reference, track_phases, 1)
        residual = (track_phases - np.polyval(affine, track_times - reference)) * 1e6
        selected = track["track_id"] == primary["track_id"]
        axes[2].scatter(
            track_times,
            residual,
            marker="x",
            s=24 if selected else 18,
            alpha=0.85 if selected else 0.45,
            color=PSS_COLOR if selected else "#64748b",
            label=(
                f"primary · {len(track_modes)} modes"
                if selected
                else f"secondary hypothesis · {len(track_modes)} modes"
            ),
        )
        if not selected and primary_ids.intersection(track["mode_ids"]):
            raise ValueError("PSS tracks unexpectedly share mode identities")
    axes[2].set_xlabel("Seconds from native 25 MS/s stream start")
    axes[2].set_ylabel("Independent affine residual (µs)")
    axes[2].set_title(
        "C · The secondary PSS track is a sparse search-hypothesis duplicate, not extra support"
    )
    axes[2].legend(loc="upper left")
    for axis in axes:
        axis.grid(True, alpha=0.22)
    figure.suptitle(f"{CAPTURE_ID} · receiver asymmetry and timing-model diagnostics")
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def generate(
    *,
    pss_path: Path,
    glrt_epoch_paths: list[Path],
    glrt_full_paths: list[Path],
    stateful_paths: list[Path],
    production_png: Path,
    output_dir: Path,
) -> Json:
    pss = _load(pss_path)
    epochs = [_load(path) for path in glrt_epoch_paths]
    full = [_load(path) for path in glrt_full_paths]
    stateful = [_load(path) for path in stateful_paths]
    summary, modes, times_s, _ = analyze(pss, epochs, full, stateful)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(production_png, output_dir / "production-pss-glrt-frame-comparison.png")
    _plot_frequency_and_support(
        output_dir / "frequency-timing-support-alignment.png",
        summary,
        pss,
        modes,
        times_s,
        epochs,
    )
    _plot_gap_robustness(output_dir / "native25-gap-robustness.png", summary, pss, modes, times_s)
    _plot_quantization_alias(output_dir / "glrt-quantization-and-alias.png", summary, pss, epochs)
    epoch_by_rx = {int(item["source"]["receiver_id"]): item for item in epochs}
    full_by_rx = {int(item["source"]["receiver_id"]): item for item in full}
    _plot_stride_plateau(
        output_dir / "glrt-stride-plateau-u-structure.png",
        pss,
        epoch_by_rx[0],
        full_by_rx[0],
    )
    _plot_receiver_and_model_selection(
        output_dir / "receiver-asymmetry-and-model-selection.png",
        summary,
        pss,
        modes,
        times_s,
        full,
    )
    (output_dir / "analysis-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pss", required=True, type=Path)
    parser.add_argument("--glrt-epoch", required=True, action="append", type=Path)
    parser.add_argument("--glrt-full", required=True, action="append", type=Path)
    parser.add_argument("--stateful", required=True, action="append", type=Path)
    parser.add_argument("--production-png", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not (len(args.glrt_epoch) == len(args.glrt_full) == len(args.stateful) == 2):
        raise SystemExit("exactly two GLRT epoch, full-capture, and stateful products are required")
    summary = generate(
        pss_path=args.pss,
        glrt_epoch_paths=args.glrt_epoch,
        glrt_full_paths=args.glrt_full,
        stateful_paths=args.stateful,
        production_png=args.production_png,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
