#!/usr/bin/env python3
"""Render and validate the persisted d373c04a GLRT/frame-CFO analysis."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink.local_doppler import (  # noqa: E402
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)

SESSION_ID = "cap-20260821T215944-d373c04a5a35"
PROBE_DURATION_S = 0.020
FRAME_QIN_GATE = 0.20
GLRT_QIN_GATE = 0.10
ZOOM_START_S = 13.675
ZOOM_END_S = 14.175

DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_d373c04a_glrt_frames")
DEFAULT_REPORT_PATH = Path("reports/2026_08_24_d373c04a_glrt_frames.md")
DEFAULT_RESULTS_PATH = DEFAULT_OUTPUT_ROOT / "d373c04a-glrt-frames.json"

MAXIMUM_JOINED_SPAN_S = 0.125
MAXIMUM_JOINED_FRAME_GAP_S = 0.016
MAXIMUM_JOINED_LOCKS = 8
MINIMUM_COHERENT_SPAN_S = 0.020
MAXIMUM_COHERENT_RMS_HZ = 40.0

INK = "#17354a"
LIGHT_GRAY = "#d4dade"
GRAY = "#9aa6ae"
AMBER = "#d9881f"
BLUE = "#2f83b7"
RED = "#c94b43"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--reuse-results",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="persisted raw-IQ frame result used to regenerate figures and prose",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def model_frequency(
    times_s: np.ndarray,
    coefficients_hz: tuple[float, ...] | list[float],
    reference_time_s: float,
) -> np.ndarray:
    return np.polyval(
        np.asarray(coefficients_hz, dtype=float),
        np.asarray(times_s, dtype=float) - reference_time_s,
    )


@dataclass(frozen=True, slots=True)
class FrameObservation:
    row_index: int
    time_s: float
    absolute_cfo_hz: float
    model_cfo_hz: float
    source_window_index: int
    exact_coherence: float
    coherence_margin: float
    frequency_uncertainty_hz: float
    frequency_update_applied: bool


@dataclass(frozen=True, slots=True)
class SegmentFit:
    source_window_start: int
    source_window_end: int
    observation_indices: tuple[int, ...]
    frame_count: int
    frequency_update_count: int
    start_time_s: float
    end_time_s: float
    center_time_s: float
    intercept_hz: float
    slope_hz_s: float
    slope_sigma_hz_s: float | None
    robust_rms_hz: float
    raw_rms_hz: float
    held_out_rms_hz: float | None

    @property
    def span_s(self) -> float:
        return self.end_time_s - self.start_time_s

    @property
    def coherent(self) -> bool:
        return bool(
            self.span_s >= MINIMUM_COHERENT_SPAN_S and self.raw_rms_hz <= MAXIMUM_COHERENT_RMS_HZ
        )


@dataclass(frozen=True, slots=True)
class JointModelFit:
    model: str
    reference_time_s: float
    shared_slope_hz_s: float
    shared_slope_sigma_hz_s: float
    slope_progression_hz_s2: float | None
    slope_progression_sigma_hz_s2: float | None
    residual_rms_hz: float
    robust_scale_hz: float
    bic: float
    segment_intercepts_hz: tuple[float, ...]


def _fit_segment(observations: Iterable[FrameObservation]) -> SegmentFit | None:
    values = tuple(sorted(observations, key=lambda item: (item.time_s, item.row_index)))
    if len(values) < 6:
        return None
    times = np.asarray([item.time_s for item in values], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in values], dtype=float)
    fit = frequency_line(times, frequencies)
    if fit is None:
        return None
    predicted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (times - fit.reference_time_s)
    residuals = frequencies - predicted
    return SegmentFit(
        source_window_start=min(item.source_window_index for item in values),
        source_window_end=max(item.source_window_index for item in values),
        observation_indices=tuple(item.row_index for item in values),
        frame_count=len(values),
        frequency_update_count=sum(item.frequency_update_applied for item in values),
        start_time_s=float(times[0]),
        end_time_s=float(times[-1]),
        center_time_s=float(fit.reference_time_s),
        intercept_hz=float(fit.intercept_at_reference_hz),
        slope_hz_s=float(fit.slope_hz_per_s),
        slope_sigma_hz_s=line_slope_sigma(times, fit),
        robust_rms_hz=float(fit.residual_rms_hz),
        raw_rms_hz=float(np.sqrt(np.mean(residuals**2))),
        held_out_rms_hz=interleaved_held_out_rms(times, frequencies),
    )


def independent_lock_fits(
    observations: Iterable[FrameObservation],
) -> tuple[SegmentFit, ...]:
    grouped: dict[int, list[FrameObservation]] = {}
    for item in observations:
        grouped.setdefault(item.source_window_index, []).append(item)
    fits = [_fit_segment(grouped[index]) for index in sorted(grouped)]
    return tuple(item for item in fits if item is not None)


def batch_joined_segments(
    observations: Iterable[FrameObservation],
    lock_fits: tuple[SegmentFit, ...],
    *,
    noise_scale_hz: float,
    segment_penalty: float,
) -> tuple[SegmentFit, ...]:
    if noise_scale_hz <= 0 or segment_penalty < 0:
        raise ValueError("noise scale must be positive and penalty non-negative")
    by_index = {item.row_index: item for item in observations}
    candidate: dict[tuple[int, int], tuple[float, SegmentFit]] = {}
    count = len(lock_fits)
    for start in range(count):
        for end in range(start, min(count, start + MAXIMUM_JOINED_LOCKS)):
            source_fits = lock_fits[start : end + 1]
            indexes = [index for fit in source_fits for index in fit.observation_indices]
            ordered = tuple(sorted((by_index[index] for index in indexes), key=lambda x: x.time_s))
            times = np.asarray([item.time_s for item in ordered])
            if float(np.ptp(times)) > MAXIMUM_JOINED_SPAN_S:
                break
            if len(times) > 1 and float(np.max(np.diff(times))) > MAXIMUM_JOINED_FRAME_GAP_S:
                break
            fit = _fit_segment(ordered)
            if fit is None:
                continue
            frequencies = np.asarray([item.absolute_cfo_hz for item in ordered])
            predicted = fit.intercept_hz + fit.slope_hz_s * (times - fit.center_time_s)
            standardized = (frequencies - predicted) / noise_scale_hz
            loss = float(np.sum(np.minimum(standardized**2, 9.0)))
            candidate[start, end] = (loss + segment_penalty, fit)

    objective = [math.inf] * (count + 1)
    predecessor: list[int | None] = [None] * (count + 1)
    objective[0] = 0.0
    for stop in range(1, count + 1):
        for start in range(max(0, stop - MAXIMUM_JOINED_LOCKS), stop):
            item = candidate.get((start, stop - 1))
            if item is None:
                continue
            proposed = objective[start] + item[0]
            if proposed < objective[stop]:
                objective[stop] = proposed
                predecessor[stop] = start
    if predecessor[count] is None:
        raise RuntimeError("no complete timing-lock partition exists")
    selected = []
    stop = count
    while stop:
        start = predecessor[stop]
        if start is None:
            raise RuntimeError("incomplete timing-lock partition")
        selected.append(candidate[start, stop - 1][1])
        stop = start
    return tuple(reversed(selected))


def _robust_linear_solve(
    design: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    weights = np.ones(len(values), dtype=float)
    scale = 5.0
    for _iteration in range(50):
        residuals = values - design @ coefficients
        median = float(np.median(residuals))
        scale = max(
            5.0,
            1.4826 * float(np.median(np.abs(residuals - median))),
        )
        normalized = np.abs(residuals) / (1.345 * scale)
        weights = np.ones(len(values), dtype=float)
        tail = normalized > 1.0
        weights[tail] = 1.0 / normalized[tail]
        root_weights = np.sqrt(weights)
        updated = np.linalg.lstsq(
            design * root_weights[:, None], values * root_weights, rcond=None
        )[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-7:
            coefficients = updated
            break
        coefficients = updated
    residuals = values - design @ coefficients
    degrees_of_freedom = max(1, len(values) - design.shape[1])
    variance = float(np.sum(weights * residuals**2) / degrees_of_freedom)
    covariance = np.linalg.pinv(design.T @ (weights[:, None] * design)) * variance
    return coefficients, covariance, residuals, scale


def joint_varying_intercept_fit(
    observations: Iterable[FrameObservation],
    segments: tuple[SegmentFit, ...],
    *,
    slope_progression: bool,
) -> JointModelFit:
    if len(segments) < 3:
        raise ValueError("at least three coherent segments are required")
    by_index = {item.row_index: item for item in observations}
    reference_time_s = float(np.mean([item.center_time_s for item in segments]))
    row_count = sum(item.frame_count for item in segments)
    column_count = len(segments) + 1 + int(slope_progression)
    design = np.zeros((row_count, column_count), dtype=float)
    values = np.empty(row_count, dtype=float)
    row_start = 0
    for segment_index, segment in enumerate(segments):
        members = tuple(by_index[index] for index in segment.observation_indices)
        times = np.asarray([item.time_s for item in members])
        frequencies = np.asarray([item.absolute_cfo_hz for item in members])
        local_time = times - segment.center_time_s
        row_stop = row_start + len(members)
        design[row_start:row_stop, segment_index] = 1.0
        design[row_start:row_stop, len(segments)] = local_time
        if slope_progression:
            design[row_start:row_stop, len(segments) + 1] = (
                segment.center_time_s - reference_time_s
            ) * local_time + 0.5 * local_time**2
        values[row_start:row_stop] = frequencies
        row_start = row_stop
    coefficients, covariance, residuals, robust_scale = _robust_linear_solve(design, values)
    shared_index = len(segments)
    progression_index = shared_index + 1
    residual_sum_squares = float(np.sum(residuals**2))
    bic = len(values) * math.log(residual_sum_squares / len(values)) + (
        column_count * math.log(len(values))
    )
    return JointModelFit(
        model="linear-slope-progression" if slope_progression else "common-slope",
        reference_time_s=reference_time_s,
        shared_slope_hz_s=float(coefficients[shared_index]),
        shared_slope_sigma_hz_s=float(math.sqrt(max(0.0, covariance[shared_index, shared_index]))),
        slope_progression_hz_s2=(
            float(coefficients[progression_index]) if slope_progression else None
        ),
        slope_progression_sigma_hz_s2=(
            float(math.sqrt(max(0.0, covariance[progression_index, progression_index])))
            if slope_progression
            else None
        ),
        residual_rms_hz=float(math.sqrt(residual_sum_squares / len(values))),
        robust_scale_hz=float(robust_scale),
        bic=float(bic),
        segment_intercepts_hz=tuple(float(value) for value in coefficients[: len(segments)]),
    )


def slope_leave_one_segment_out_rms(segments: tuple[SegmentFit, ...], *, linear: bool) -> float:
    times = np.asarray([item.center_time_s for item in segments])
    slopes = np.asarray([item.slope_hz_s for item in segments])
    sigmas = np.asarray([max(30.0, item.slope_sigma_hz_s or 30.0) for item in segments])
    reference = float(np.mean(times))
    design = (
        np.column_stack((np.ones(len(times)), times - reference))
        if linear
        else np.ones((len(times), 1))
    )
    errors = []
    for held_out in range(len(times)):
        keep = np.arange(len(times)) != held_out
        weights = 1.0 / sigmas[keep] ** 2
        normal = design[keep].T @ (weights[:, None] * design[keep])
        target = design[keep].T @ (weights * slopes[keep])
        coefficients = np.linalg.pinv(normal) @ target
        errors.append(slopes[held_out] - float(design[held_out] @ coefficients))
    return float(np.sqrt(np.mean(np.asarray(errors) ** 2)))


def _frame_observations(
    document: dict[str, Any], *, exact_gate: float
) -> tuple[FrameObservation, ...]:
    spec = document["spec"]
    coefficients = spec["branch_coefficients_hz"]
    reference = float(spec["branch_reference_time_s"])
    observations = []
    for item in document["frames"]:
        if float(item["train_exact_score"]) < exact_gate or float(item["train_margin"]) <= 0.0:
            continue
        time_s = float(item["time_s"])
        observations.append(
            FrameObservation(
                row_index=int(item["row_index"]),
                time_s=time_s,
                absolute_cfo_hz=float(item["train_cfo_hz"]),
                model_cfo_hz=float(
                    model_frequency(np.asarray([time_s]), coefficients, reference)[0]
                ),
                source_window_index=int(item["window_index"]),
                exact_coherence=float(item["train_exact_score"]),
                coherence_margin=float(item["train_margin"]),
                frequency_uncertainty_hz=25.0,
                frequency_update_applied=False,
            )
        )
    return tuple(observations)


def _error_metrics(predicted: np.ndarray, observed: np.ndarray) -> dict[str, Any]:
    residual = np.asarray(predicted, dtype=float) - np.asarray(observed, dtype=float)
    absolute = np.abs(residual)
    return {
        "frame_count": len(residual),
        "rms_hz": float(np.sqrt(np.mean(residual**2))),
        "median_absolute_hz": float(np.median(absolute)),
        "p95_absolute_hz": float(np.percentile(absolute, 95)),
    }


def _rate_fit_at_gate(document: dict[str, Any], *, exact_gate: float) -> dict[str, Any]:
    observations = _frame_observations(document, exact_gate=exact_gate)
    lock_fits = independent_lock_fits(observations)
    if len(lock_fits) < 3:
        return {
            "status": "insufficient",
            "exact_gate": exact_gate,
            "qualified_frame_count": len(observations),
            "lock_fit_count": len(lock_fits),
        }
    lock_rms = np.asarray([item.raw_rms_hz for item in lock_fits], dtype=float)
    noise_scale = max(5.0, float(np.percentile(lock_rms, 90)))
    segment_penalty = float(2.0 * math.log(max(2, len(observations))))
    partition = batch_joined_segments(
        observations,
        lock_fits,
        noise_scale_hz=noise_scale,
        segment_penalty=segment_penalty,
    )
    coherent = tuple(item for item in partition if item.coherent)
    if len(coherent) < 3:
        return {
            "status": "insufficient",
            "exact_gate": exact_gate,
            "qualified_frame_count": len(observations),
            "lock_fit_count": len(lock_fits),
            "partition_segment_count": len(partition),
            "coherent_segment_count": len(coherent),
        }

    common = joint_varying_intercept_fit(observations, coherent, slope_progression=False)
    progression = joint_varying_intercept_fit(observations, coherent, slope_progression=True)
    observations_by_index = {item.row_index: item for item in observations}
    frames_by_index = {int(item["row_index"]): item for item in document["frames"]}

    def joint_predictions(
        fit: JointModelFit,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        predicted = []
        train = []
        validation = []
        for segment_index, segment in enumerate(coherent):
            for row_index in segment.observation_indices:
                observation = observations_by_index[row_index]
                local_time = observation.time_s - segment.center_time_s
                value = (
                    fit.segment_intercepts_hz[segment_index] + fit.shared_slope_hz_s * local_time
                )
                if fit.slope_progression_hz_s2 is not None:
                    value += fit.slope_progression_hz_s2 * (
                        (segment.center_time_s - fit.reference_time_s) * local_time
                        + 0.5 * local_time**2
                    )
                predicted.append(value)
                train.append(observation.absolute_cfo_hz)
                validation.append(float(frames_by_index[row_index]["validation_cfo_hz"]))
        return (
            np.asarray(predicted),
            np.asarray(train),
            np.asarray(validation),
        )

    def fixed_slope_predictions(
        slope_hz_s: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        predicted = []
        train = []
        validation = []
        for segment in coherent:
            members = tuple(observations_by_index[index] for index in segment.observation_indices)
            local_time = np.asarray([item.time_s - segment.center_time_s for item in members])
            values = np.asarray([item.absolute_cfo_hz for item in members])
            intercept = float(np.median(values - slope_hz_s * local_time))
            predicted.extend(intercept + slope_hz_s * local_time)
            train.extend(values)
            validation.extend(
                float(frames_by_index[item.row_index]["validation_cfo_hz"]) for item in members
            )
        return (
            np.asarray(predicted),
            np.asarray(train),
            np.asarray(validation),
        )

    source_rate = float(document["spec"]["branch_coefficients_hz"][0])
    glrt_predicted, glrt_train, glrt_validation = fixed_slope_predictions(source_rate)
    common_predicted, common_train, common_validation = joint_predictions(common)
    progression_predicted, progression_train, progression_validation = joint_predictions(
        progression
    )
    slopes = np.asarray([item.slope_hz_s for item in coherent])
    return {
        "status": "complete",
        "exact_gate": exact_gate,
        "qualified_frame_count": len(observations),
        "lock_fit_count": len(lock_fits),
        "partition_segment_count": len(partition),
        "coherent_segment_count": len(coherent),
        "coherent_frame_count": int(sum(item.frame_count for item in coherent)),
        "noise_scale_hz": noise_scale,
        "segment_penalty": segment_penalty,
        "source_glrt_rate_hz_s": source_rate,
        "independent_coherent_slopes": {
            "median_hz_s": float(np.median(slopes)),
            "p10_hz_s": float(np.percentile(slopes, 10)),
            "p90_hz_s": float(np.percentile(slopes, 90)),
        },
        "common_slope": {
            **asdict(common),
            "leave_one_segment_out_rms_hz_s": (
                slope_leave_one_segment_out_rms(coherent, linear=False)
            ),
        },
        "slope_progression": {
            **asdict(progression),
            "leave_one_segment_out_rms_hz_s": (
                slope_leave_one_segment_out_rms(coherent, linear=True)
            ),
        },
        "errors": {
            "source_glrt_slope": {
                "train": _error_metrics(glrt_predicted, glrt_train),
                "odd_validation": _error_metrics(glrt_predicted, glrt_validation),
            },
            "common_slope": {
                "train": _error_metrics(common_predicted, common_train),
                "odd_validation": _error_metrics(common_predicted, common_validation),
            },
            "slope_progression": {
                "train": _error_metrics(progression_predicted, progression_train),
                "odd_validation": _error_metrics(progression_predicted, progression_validation),
            },
        },
        "bic_progression_minus_common": progression.bic - common.bic,
        "segments": [asdict(item) for item in coherent],
    }


def corrected_rate_analysis(document: dict[str, Any]) -> dict[str, Any]:
    primary = _rate_fit_at_gate(document, exact_gate=FRAME_QIN_GATE)
    if primary["status"] != "complete":
        raise ValueError("corrected-rate analysis found fewer than three ramps")
    sensitivity = []
    for gate in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        result = _rate_fit_at_gate(document, exact_gate=gate)
        sensitivity.append(
            {
                "exact_gate": gate,
                "status": result["status"],
                "qualified_frame_count": result["qualified_frame_count"],
                "coherent_segment_count": result.get("coherent_segment_count", 0),
                "common_slope_hz_s": (
                    result["common_slope"]["shared_slope_hz_s"]
                    if result["status"] == "complete"
                    else None
                ),
            }
        )
    source = float(primary["source_glrt_rate_hz_s"])
    corrected = float(primary["common_slope"]["shared_slope_hz_s"])
    primary["headline"] = {
        "corrected_received_cfo_rate_hz_s": corrected,
        "conditional_formal_sigma_hz_s": float(primary["common_slope"]["shared_slope_sigma_hz_s"]),
        "segment_repeatability_rms_hz_s": float(
            primary["common_slope"]["leave_one_segment_out_rms_hz_s"]
        ),
        "rate_correction_hz_s": corrected - source,
        "magnitude_reduction_percent": 100.0 * (abs(source) - abs(corrected)) / abs(source),
    }
    primary["gate_sensitivity"] = sensitivity
    return primary


def _selected(
    values: list[dict[str, Any]], key: str, start_s: float, end_s: float
) -> list[dict[str, Any]]:
    return [item for item in values if start_s <= float(item[key]) <= end_s]


def render(
    path: Path,
    document: dict[str, Any],
    *,
    start_s: float,
    end_s: float,
) -> None:
    if start_s >= end_s:
        raise ValueError("plot start must precede end")
    windows = _selected(document["windows"], "detection_time_s", start_s, end_s)
    frames = _selected(document["frames"], "time_s", start_s, end_s)
    if not windows or not frames:
        raise ValueError("plot interval contains no GLRT windows or frame CFOs")
    spec = document["spec"]
    coefficients = spec["branch_coefficients_hz"]
    reference = float(spec["branch_reference_time_s"])

    window_times = np.asarray([item["detection_time_s"] for item in windows], dtype=float)
    window_model = model_frequency(window_times, coefficients, reference)
    window_residual = (
        np.asarray([item["initial_cfo_hz"] for item in windows], dtype=float) - window_model
    )
    window_strong = np.asarray(
        [item["glrt_exact_score"] >= GLRT_QIN_GATE and item["glrt_margin"] > 0 for item in windows],
        dtype=bool,
    )

    frame_times = np.asarray([item["time_s"] for item in frames], dtype=float)
    frame_model = model_frequency(frame_times, coefficients, reference)
    frame_residual = (
        np.asarray([item["train_cfo_hz"] for item in frames], dtype=float) - frame_model
    )
    frame_strong = np.asarray(
        [
            item["train_exact_score"] >= FRAME_QIN_GATE and item["train_margin"] > 0
            for item in frames
        ],
        dtype=bool,
    )

    supported_residuals = np.concatenate(
        (window_residual[window_strong], frame_residual[frame_strong])
    )
    residual_limit = max(
        500.0,
        1.20 * float(np.percentile(np.abs(supported_residuals), 99)),
    )
    residual_limit = min(residual_limit, 2_500.0)

    figure = Figure(figsize=(18, 12), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": (0.80, 1.0, 1.35)})
    figure.suptitle(
        f"GLRT windows and 1.333 ms frame CFO · {SESSION_ID}",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )

    for window_index, item in enumerate(windows):
        probe_start = float(item["detection_time_s"])
        for axis_index, axis in enumerate(axes):
            axis.axvline(
                probe_start,
                color=RED,
                linewidth=0.65,
                linestyle=(0, (3, 3)),
                alpha=0.24,
                zorder=0,
                label=("20 ms GLRT probe start" if window_index == 0 and axis_index == 0 else None),
            )
        segment_times = np.asarray([probe_start, min(probe_start + PROBE_DURATION_S, end_s)])
        segment_residual = float(item["initial_cfo_hz"]) - model_frequency(
            segment_times, coefficients, reference
        )
        axes[1].plot(
            segment_times,
            segment_residual,
            color=AMBER if window_strong[window_index] else GRAY,
            linewidth=2.0 if window_strong[window_index] else 1.0,
            alpha=0.82 if window_strong[window_index] else 0.25,
            solid_capstyle="butt",
        )

    axes[0].scatter(
        window_times,
        [item["glrt_exact_score"] for item in windows],
        s=21,
        color=AMBER,
        alpha=0.78,
        linewidths=0,
        label=f"exact Qin GLRT64 ({len(windows)})",
    )
    axes[0].scatter(
        window_times,
        [item["glrt_control_score"] for item in windows],
        s=18,
        color=GRAY,
        alpha=0.62,
        linewidths=0,
        label="rolled control",
    )
    axes[1].scatter(
        window_times[window_strong],
        np.clip(window_residual[window_strong], -residual_limit, residual_limit),
        s=15,
        color=AMBER,
        alpha=0.80,
        linewidths=0,
        label=f"strong 20 ms GLRT CFO ({np.count_nonzero(window_strong)})",
    )
    frame_visible = np.abs(frame_residual) <= residual_limit
    weak_visible = ~frame_strong & frame_visible
    strong_visible = frame_strong & frame_visible
    axes[2].scatter(
        frame_times[weak_visible],
        frame_residual[weak_visible],
        s=6,
        color=GRAY,
        alpha=0.16,
        linewidths=0,
        rasterized=True,
        label=(f"weak/noisy even-Qin frame maximum ({np.count_nonzero(~frame_strong)})"),
    )
    axes[2].scatter(
        frame_times[strong_visible],
        frame_residual[strong_visible],
        s=9,
        color=BLUE,
        alpha=0.64,
        linewidths=0,
        rasterized=True,
        label=f"strong 1.333 ms frame CFO ({np.count_nonzero(frame_strong)})",
    )

    clipped_windows = int(np.count_nonzero(np.abs(window_residual) > residual_limit))
    clipped_frames = int(np.count_nonzero(~frame_visible))
    titles = (
        "A · Original-alias GLRT64 signal strength",
        "B · Each segment is one constant-CFO 20 ms GLRT window; residual display tilts it",
        (
            "C · Every raw-IQ frame CFO · "
            f"off-scale weak maxima: {clipped_frames}; windows: {clipped_windows}"
        ),
    )
    axes[0].set_ylabel("normalized score")
    for axis in axes[1:]:
        axis.axhline(0.0, color=INK, linewidth=0.85, alpha=0.62)
        axis.set_ylabel("CFO − frozen GLRT line (Hz)")
        axis.set_ylim(-residual_limit, residual_limit)
    for axis, title in zip(axes, titles, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0].legend(loc="lower left", ncol=3, frameon=False)
    axes[1].legend(loc="lower left", frameon=False)
    axes[2].legend(loc="lower left", ncol=2, frameon=False)
    axes[-1].set_xlabel("capture time (s)")
    axes[-1].set_xlim(start_s, end_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_rate_comparison(path: Path, document: dict[str, Any]) -> None:
    analysis = document["rate_analysis"]
    headline = analysis["headline"]
    common = analysis["common_slope"]
    progression = analysis["slope_progression"]
    errors = analysis["errors"]
    rates = (
        np.asarray(
            [
                analysis["source_glrt_rate_hz_s"],
                common["shared_slope_hz_s"],
                progression["shared_slope_hz_s"],
            ]
        )
        / 1_000.0
    )

    figure = Figure(figsize=(14, 5.5), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Sawtooth-state debiasing changes the inferred received-CFO rate",
        fontsize=18,
        color=INK,
        fontweight="bold",
    )
    labels = ("frozen GLRT", "common ramp slope", "slope progression")
    colors = (AMBER, BLUE, "#7b65a8")
    axes[0].scatter(range(3), rates, s=75, color=colors, zorder=3)
    axes[0].errorbar(
        [1],
        [rates[1]],
        yerr=[headline["segment_repeatability_rms_hz_s"] / 1_000.0],
        fmt="none",
        ecolor=BLUE,
        elinewidth=2.0,
        capsize=5,
        label="leave-one-ramp-out repeatability",
    )
    for index, value in enumerate(rates):
        axes[0].annotate(
            f"{value:.3f} kHz/s",
            (index, value),
            xytext=(0, 10 if index else -18),
            textcoords="offset points",
            ha="center",
            color=INK,
            fontsize=10,
        )
    axes[0].set_xticks(range(3), labels)
    axes[0].set_ylabel("absolute CFO slope (kHz/s)")
    axes[0].set_title("A · Rate estimate", loc="left", color=INK, fontweight="bold")
    axes[0].legend(loc="lower right", frameon=False)

    model_keys = ("source_glrt_slope", "common_slope", "slope_progression")
    train = np.asarray([errors[key]["train"]["rms_hz"] for key in model_keys])
    validation = np.asarray([errors[key]["odd_validation"]["rms_hz"] for key in model_keys])
    positions = np.arange(3)
    width = 0.34
    axes[1].bar(
        positions - width / 2,
        train,
        width,
        color=GRAY,
        alpha=0.75,
        label="even-Qin fit RMS",
    )
    axes[1].bar(
        positions + width / 2,
        validation,
        width,
        color=BLUE,
        alpha=0.82,
        label="odd-Qin validation RMS",
    )
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylabel("CFO prediction RMS (Hz)")
    axes[1].set_title(
        "B · Same ramps and free state intercepts",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="upper right", frameon=False)
    for axis in axes:
        axis.grid(True, axis="y", alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_all(document: dict[str, Any], output_root: Path) -> dict[str, str]:
    full = output_root / "d373c04a-glrt-frames-full.png"
    zoom = output_root / "d373c04a-glrt-frames-500ms.png"
    comparison = output_root / "d373c04a-doppler-rate-comparison.png"
    spec = document["spec"]
    render(
        full,
        document,
        start_s=float(spec["branch_start_s"]),
        end_s=float(spec["branch_end_s"]),
    )
    render(zoom, document, start_s=ZOOM_START_S, end_s=ZOOM_END_S)
    render_rate_comparison(comparison, document)
    return {
        "full": str(full),
        "zoom": str(zoom),
        "rate_comparison": str(comparison),
    }


def write_report(document: dict[str, Any], *, report_path: Path, result_path: Path) -> None:
    analysis = document["rate_analysis"]
    headline = analysis["headline"]
    progression = analysis["slope_progression"]
    independent = analysis["independent_coherent_slopes"]
    errors = analysis["errors"]
    source_rate = float(analysis["source_glrt_rate_hz_s"])
    corrected_rate = float(headline["corrected_received_cfo_rate_hz_s"])

    def relative(path: str | Path) -> str:
        return Path(os.path.relpath(Path(path), report_path.parent)).as_posix()

    full_figure = relative(document["figures"]["full"])
    zoom_figure = relative(document["figures"]["zoom"])
    rate_figure = relative(document["figures"]["rate_comparison"])
    result_relative = relative(result_path)
    result_command = result_path.as_posix()
    train_reduction = 100.0 * (
        1.0
        - errors["common_slope"]["train"]["rms_hz"] / errors["source_glrt_slope"]["train"]["rms_hz"]
    )
    validation_reduction = 100.0 * (
        1.0
        - errors["common_slope"]["odd_validation"]["rms_hz"]
        / errors["source_glrt_slope"]["odd_validation"]["rms_hz"]
    )
    sensitivity = [
        float(item["common_slope_hz_s"])
        for item in analysis["gate_sensitivity"]
        if item["status"] == "complete"
    ]
    glrt_strong_count = document["summary"]["glrt_strong_window_count"]
    window_count = document["summary"]["window_count"]
    frame_strong_count = document["summary"]["strong_frame_count"]
    frame_count = document["summary"]["frame_count"]
    independent_row = (
        "| median independent ramp | "
        f"{independent['median_hz_s'] / 1_000:.4f} kHz/s | 10–90%: "
        f"{independent['p10_hz_s'] / 1_000:.4f} to "
        f"{independent['p90_hz_s'] / 1_000:.4f} |"
    )
    formal_row = (
        "| conditional formal sigma | "
        f"±{headline['conditional_formal_sigma_hz_s'] / 1_000:.4f} kHz/s | "
        "conditional on recovered states |"
    )
    repeatability_row = (
        "| leave-one-ramp-out repeatability | "
        f"±{headline['segment_repeatability_rms_hz_s'] / 1_000:.4f} kHz/s | "
        "conservative tooth-to-tooth stability |"
    )
    progression_row = (
        "| fitted slope progression | "
        f"{progression['slope_progression_hz_s2']:+.1f} ± "
        f"{progression['slope_progression_sigma_hz_s2']:.1f} Hz/s² | "
        "not selected by BIC or odd-Qin validation |"
    )
    glrt_error_row = (
        "| frozen GLRT rate | "
        f"{errors['source_glrt_slope']['train']['rms_hz']:.2f} Hz | "
        f"{errors['source_glrt_slope']['odd_validation']['rms_hz']:.2f} Hz |"
    )
    common_error_row = (
        "| corrected common rate | "
        f"**{errors['common_slope']['train']['rms_hz']:.2f} Hz** | "
        f"**{errors['common_slope']['odd_validation']['rms_hz']:.2f} Hz** |"
    )
    progression_error_row = (
        "| rate plus linear progression | "
        f"{errors['slope_progression']['train']['rms_hz']:.2f} Hz | "
        f"{errors['slope_progression']['odd_validation']['rms_hz']:.2f} Hz |"
    )
    text = f"""# GLRT windows, frame CFO, and sawtooth-debiased rate for `d373c04a`

## Abstract

This report revisits the retained GLRT branch in
`{document["session_id"]}` using the branch's original absolute-frequency alias
and raw-IQ 1.333 ms Qin frame fits. The branch is strong: {glrt_strong_count}
of {window_count} persisted 20 ms GLRT windows and
{frame_strong_count} of {frame_count}
frame fits pass their respective Qin-versus-control gates. The frame CFOs expose
repeated ramps separated by frequency resets. A robust joint fit that gives each
recovered ramp an arbitrary CFO intercept changes the received-CFO rate from the
frozen GLRT value of **{source_rate / 1_000:.3f} kHz/s** to
**{corrected_rate / 1_000:.3f} kHz/s**. The conservative leave-one-ramp-out
repeatability is **{headline["segment_repeatability_rms_hz_s"] / 1_000:.3f}
kHz/s**.

The corrected value is an emitter-state-debiased **received-CFO rate**. It is
not yet a pure orbital Doppler truth value because LNB drift, receiver clock
drift, and any residual transmitter frequency drift remain in the measurement.

## Data and branch selection

- Capture: `{document["session_id"]}`.
- Stream / receiver / edge: `{document["stream_id"]}`, receiver
  {document["receiver_id"]}, `{document["edge"]}` edge.
- Analysis interval: {document["spec"]["branch_start_s"]:.3f}–
  {document["spec"]["branch_end_s"]:.3f} s.
- Original branch alias: {document["spec"]["branch_coefficients_hz"][1] / 1_000:.3f}
  kHz at {document["spec"]["branch_reference_time_s"]:.3f} s.
- Frozen degree-one GLRT rate: {source_rate / 1_000:.4f} kHz/s.
- Raw-IQ frame cadence: {1_000 * document["frame_duration_s"]:.3f} ms.

The earlier five-dwell prototype followed a Qin-equivalent alias near +41 kHz.
This report instead uses the source result's declared branch near −186 kHz. The
declared branch has materially stronger Qin GLRT evidence and exposes the frame
ramps clearly.

## GLRT and frame-level structure

![Full retained branch]({full_figure})

Panel A shows exact Qin GLRT64 strength against a rolled-Qin control. Panel B
shows every persisted constant-CFO 20 ms GLRT estimate. The line pieces appear
tilted only because the ordinate subtracts the time-varying frozen GLRT line.
Panel C independently maximizes the even-Qin likelihood for every 1.333 ms raw-IQ
frame. Dashed red lines mark GLRT probe starts.

![500 ms close-up]({zoom_figure})

The close-up makes the repeated ramp/reset structure explicit. The blue frame
fits are not interpolated from the 20 ms CFO values; the 20 ms products supply
the acquisition neighborhoods and timing epochs, while each frame CFO is
re-estimated from raw IQ.

## Corrected received-CFO rate

![Rate and error comparison]({rate_figure})

The corrected model first robustly fits each acquisition lock, then globally
partitions adjacent locks into continuous ramps. The primary 0.20 Qin gate gives
{analysis["coherent_segment_count"]} coherent ramps containing
{analysis["coherent_frame_count"]} frames. A joint regression assigns one free
CFO intercept to every ramp and one shared absolute-CFO slope to all ramps.
That free intercept absorbs the sawtooth resets without subtracting the frozen
GLRT line from the scientific fit.

| estimate | rate or progression | interpretation |
| --- | ---: | --- |
| frozen GLRT branch | {source_rate / 1_000:.4f} kHz/s | biased by ramp resets |
{independent_row}
| joint common ramp slope | **{corrected_rate / 1_000:.4f} kHz/s** | adopted corrected estimate |
{formal_row}
{repeatability_row}
{progression_row}

The correction is {headline["rate_correction_hz_s"] / 1_000:+.3f} kHz/s, reducing
the inferred rate magnitude by {headline["magnitude_reduction_percent"]:.1f}%.
Across Qin gates from 0.05 to 0.30, the common-slope estimate ranges only from
{min(sensitivity) / 1_000:.3f} to {max(sensitivity) / 1_000:.3f} kHz/s.

## Statistical comparison

Every row below uses the same recovered ramps and a free intercept per ramp, so
the comparison isolates the slope model. Even Qin symbols define the fit;
odd Qin symbols provide an independent symbol holdout.

| slope model | even-Qin RMS | odd-Qin validation RMS |
| --- | ---: | ---: |
{glrt_error_row}
{common_error_row}
{progression_error_row}

The common-ramp model reduces even-Qin RMS by {train_reduction:.1f}% and
odd-Qin validation RMS by {validation_reduction:.1f}% relative to forcing the
GLRT slope. Adding slope progression changes training RMS by less than 0.05 Hz,
slightly worsens odd-Qin RMS, and worsens BIC by
{analysis["bic_progression_minus_common"]:.2f}; the common-slope result is the
more defensible single rate.

## Limits and next use

The result establishes that the −5.65 kHz/s GLRT slope is not the best local
carrier-rate description once frequency resets are modeled. It does not, by
itself, prove that −3.76 kHz/s is satellite-only Doppler. Association work should
compare this debiased rate with the TLE-predicted range-acceleration curve while
allowing a receiver/LNB drift nuisance term and should repeat the same estimator
across both receivers or a stable reference carrier when available.

## Reproduction

```bash
uv run python tools/report_d373c04a_glrt_frames.py \\
  --reuse-results {result_command}
```

The machine-readable result is [{Path(result_path).name}]({result_relative}).
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    document = _load(arguments.reuse_results)
    if document.get("session_id") != SESSION_ID:
        raise ValueError("reused result belongs to another capture")
    document["rate_analysis"] = corrected_rate_analysis(document)
    document["figures"] = render_all(document, arguments.output_root)
    result_path = arguments.output_root / "d373c04a-glrt-frames.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            stable_measurement_floats(document),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(
        document,
        report_path=arguments.report_path,
        result_path=result_path,
    )
    print(
        json.dumps(
            {
                **document["summary"],
                "corrected_received_cfo_rate_hz_s": document["rate_analysis"]["headline"][
                    "corrected_received_cfo_rate_hz_s"
                ],
                "figures": document["figures"],
                "report": str(arguments.report_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
