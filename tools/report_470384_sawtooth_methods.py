#!/usr/bin/env python3
"""Compare offline line-family methods on the dense 470384 pilot CFOs.

This report consumes the already-persisted 1.333 ms known-pilot frame evidence.
It does not re-read IQ and does not use the online Kalman acceptance decision as
an observation-quality gate.  The three methods are:

1. one robust frequency line per 20 ms timing-lock window;
2. a batch dynamic-programming partition that joins adjacent windows when one
   robust line explains them;
3. a joint varying-intercept model comparing one shared slope with a slope that
   progresses linearly in capture time.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.starlink.local_doppler import (  # noqa: E402
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)

SESSION_ID = "cap-20260821T140820-470384cc9284"
DEFAULT_EVIDENCE = Path(
    "reports/figures/2026_08_22_edge_pilot_phase_slope/detailed-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_sawtooth_methods")
DEFAULT_REPORT_PATH = Path("reports/2026_08_23_470384_sawtooth_methods.md")

MINIMUM_EXACT_COHERENCE = 0.02
MINIMUM_COHERENCE_MARGIN = 0.0
MAXIMUM_JOINED_SPAN_S = 0.125
MAXIMUM_JOINED_FRAME_GAP_S = 0.016
MAXIMUM_JOINED_LOCKS = 8
MINIMUM_COHERENT_SPAN_S = 0.020
MAXIMUM_COHERENT_RMS_HZ = 40.0
ZOOM_LIMITS_S = (35.54, 36.05)

BLUE = "#2f83b7"
AMBER = "#d9881f"
GREEN = "#3f8f67"
PURPLE = "#7b65a8"
RED = "#bd5b52"
INK = "#17354a"
GRAY = "#8997a2"
LIGHT_GRAY = "#cbd3d8"
PALETTE = (GREEN, PURPLE, AMBER, "#4e91a8", "#a76f98")


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

    @property
    def residual_cfo_hz(self) -> float:
        return self.absolute_cfo_hz - self.model_cfo_hz


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
    def source_window_count(self) -> int:
        return self.source_window_end - self.source_window_start + 1

    @property
    def coherent(self) -> bool:
        return self.span_s >= MINIMUM_COHERENT_SPAN_S and self.raw_rms_hz <= MAXIMUM_COHERENT_RMS_HZ

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = self.intercept_hz + self.slope_hz_s * (np.asarray(time_s) - self.center_time_s)
        return float(value) if np.ndim(value) == 0 else value


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

    def slope_at(self, time_s: float | np.ndarray) -> float | np.ndarray:
        progression = 0.0 if self.slope_progression_hz_s2 is None else self.slope_progression_hz_s2
        value = self.shared_slope_hz_s + progression * (
            np.asarray(time_s) - self.reference_time_s
        )
        return float(value) if np.ndim(value) == 0 else value


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return document


def observations_from_document(document: dict[str, Any]) -> tuple[FrameObservation, ...]:
    """Bind the analysis to the worked example and return every dense row."""

    metadata = document["input"]
    if metadata["session_id"] != SESSION_ID:
        raise ValueError("dense evidence belongs to a different capture")
    expected = {"stream_id": "stream-0", "receiver_id": 0, "edge": "upper"}
    for key, value in expected.items():
        if metadata[key] != value:
            raise ValueError(f"dense evidence has unexpected {key}")
    rows = document["dense_tracking"]["frames"]
    return tuple(
        FrameObservation(
            row_index=index,
            time_s=float(row["reference_time_s"]),
            absolute_cfo_hz=float(row["absolute_cfo_measurement_hz"]),
            model_cfo_hz=float(row["model_cfo_hz"]),
            source_window_index=int(row["source_window_index"]),
            exact_coherence=float(row["exact_coherence"]),
            coherence_margin=float(row["coherence_margin"]),
            frequency_uncertainty_hz=float(row["frequency_uncertainty_hz"]),
            frequency_update_applied=bool(row["frequency_update_applied"]),
        )
        for index, row in enumerate(rows)
    )


def is_direct_quality(observation: FrameObservation) -> bool:
    """Use the direct pilot evidence, deliberately ignoring the Kalman gate."""

    return bool(
        math.isfinite(observation.absolute_cfo_hz)
        and observation.exact_coherence >= MINIMUM_EXACT_COHERENCE
        and observation.coherence_margin >= MINIMUM_COHERENCE_MARGIN
    )


def direct_quality_observations(
    observations: Iterable[FrameObservation],
) -> tuple[FrameObservation, ...]:
    return tuple(item for item in observations if is_direct_quality(item))


def _fit_segment(observations: Iterable[FrameObservation]) -> SegmentFit | None:
    values = tuple(sorted(observations, key=lambda item: (item.time_s, item.row_index)))
    if len(values) < 6:
        return None
    times = np.asarray([item.time_s for item in values], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in values], dtype=float)
    fit = frequency_line(times, frequencies)
    if fit is None:
        return None
    predicted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (
        times - fit.reference_time_s
    )
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
    """Method 1: fit each timing-lock acquisition window independently."""

    grouped: dict[int, list[FrameObservation]] = {}
    for item in observations:
        grouped.setdefault(item.source_window_index, []).append(item)
    fits = [_fit_segment(grouped[index]) for index in sorted(grouped)]
    return tuple(item for item in fits if item is not None)


def _observations_for_fits(
    fits: Iterable[SegmentFit], observations_by_index: dict[int, FrameObservation]
) -> tuple[FrameObservation, ...]:
    indices = [index for fit in fits for index in fit.observation_indices]
    return tuple(observations_by_index[index] for index in indices)


def batch_joined_segments(
    observations: Iterable[FrameObservation],
    lock_fits: tuple[SegmentFit, ...],
    *,
    noise_scale_hz: float,
    segment_penalty: float,
) -> tuple[SegmentFit, ...]:
    """Method 2: globally partition consecutive locks into robust CFO lines."""

    if noise_scale_hz <= 0 or segment_penalty < 0:
        raise ValueError("noise scale must be positive and penalty non-negative")
    by_index = {item.row_index: item for item in observations}
    candidate: dict[tuple[int, int], tuple[float, SegmentFit]] = {}
    count = len(lock_fits)
    for start in range(count):
        for end in range(start, min(count, start + MAXIMUM_JOINED_LOCKS)):
            source_fits = lock_fits[start : end + 1]
            values = _observations_for_fits(source_fits, by_index)
            ordered = tuple(sorted(values, key=lambda item: item.time_s))
            times = np.asarray([item.time_s for item in ordered])
            if float(np.ptp(times)) > MAXIMUM_JOINED_SPAN_S:
                break
            if len(times) > 1 and float(np.max(np.diff(times))) > MAXIMUM_JOINED_FRAME_GAP_S:
                break
            fit = _fit_segment(ordered)
            if fit is None:
                continue
            frequencies = np.asarray([item.absolute_cfo_hz for item in ordered])
            residuals = frequencies - np.asarray(fit.frequency_hz(times))
            standardized = residuals / noise_scale_hz
            capped_square_loss = float(np.sum(np.minimum(standardized**2, 9.0)))
            candidate[start, end] = (capped_square_loss + segment_penalty, fit)

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

    selected: list[SegmentFit] = []
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
        scale = max(5.0, 1.4826 * float(np.median(np.abs(residuals - median))))
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
    """Method 3: one free CFO intercept per segment plus shared rate terms."""

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
                (segment.center_time_s - reference_time_s) * local_time
                + 0.5 * local_time**2
            )
        values[row_start:row_stop] = frequencies
        row_start = row_stop

    coefficients, covariance, residuals, robust_scale = _robust_linear_solve(design, values)
    shared_index = len(segments)
    progression_index = shared_index + 1
    residual_sum_squares = float(np.sum(residuals**2))
    bic = len(values) * math.log(residual_sum_squares / len(values)) + column_count * math.log(
        len(values)
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


def slope_leave_one_segment_out_errors(
    segments: tuple[SegmentFit, ...], *, linear: bool
) -> np.ndarray:
    """Cross-predict each independently fitted segment slope in turn."""

    times = np.asarray([item.center_time_s for item in segments])
    slopes = np.asarray([item.slope_hz_s for item in segments])
    sigmas = np.asarray(
        [max(30.0, item.slope_sigma_hz_s or 30.0) for item in segments], dtype=float
    )
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
    return np.asarray(errors)


def slope_leave_one_segment_out_rms(segments: tuple[SegmentFit, ...], *, linear: bool) -> float:
    errors = slope_leave_one_segment_out_errors(segments, linear=linear)
    return float(np.sqrt(np.mean(errors**2)))


def _residual_metrics(residuals_hz: Iterable[float]) -> dict[str, float | int]:
    residuals = np.asarray(tuple(residuals_hz), dtype=float)
    if not len(residuals):
        raise ValueError("residual metrics require at least one observation")
    absolute = np.abs(residuals)
    return {
        "frame_count": len(residuals),
        "rms_hz": float(np.sqrt(np.mean(residuals**2))),
        "mae_hz": float(np.mean(absolute)),
        "median_absolute_hz": float(np.median(absolute)),
        "p95_absolute_hz": float(np.percentile(absolute, 95)),
        "maximum_absolute_hz": float(np.max(absolute)),
    }


def _probe_rms_summary(probe_rows: list[dict[str, Any]], model: str) -> dict[str, float | int]:
    values = np.asarray([item[model] for item in probe_rows], dtype=float)
    return {
        "probe_count": len(values),
        "mean_rms_hz": float(np.mean(values)),
        "p25_rms_hz": float(np.percentile(values, 25)),
        "median_rms_hz": float(np.median(values)),
        "p75_rms_hz": float(np.percentile(values, 75)),
        "p90_rms_hz": float(np.percentile(values, 90)),
        "p95_rms_hz": float(np.percentile(values, 95)),
        "maximum_rms_hz": float(np.max(values)),
    }


def _finalize_error_comparison(
    residuals: dict[str, list[float]], probe_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    models = ("independent_ramp", "joint_common_slope", "joint_slope_progression")
    common_rms = float(np.sqrt(np.mean(np.asarray(residuals[models[1]]) ** 2)))
    progression_rms = float(np.sqrt(np.mean(np.asarray(residuals[models[2]]) ** 2)))
    probe_deltas = np.asarray(
        [item[models[2]] - item[models[1]] for item in probe_rows], dtype=float
    )
    return {
        "overall": {model: _residual_metrics(residuals[model]) for model in models},
        "per_probe": {model: _probe_rms_summary(probe_rows, model) for model in models},
        "progression_minus_common": {
            "overall_rms_delta_hz": progression_rms - common_rms,
            "overall_rms_relative_percent": 100.0
            * (progression_rms - common_rms)
            / common_rms,
            "mean_probe_rms_delta_hz": float(np.mean(probe_deltas)),
            "median_probe_rms_delta_hz": float(np.median(probe_deltas)),
            "improved_probe_count": int(np.sum(probe_deltas < 0.0)),
            "worsened_probe_count": int(np.sum(probe_deltas > 0.0)),
        },
        "probes": probe_rows,
    }


def in_sample_model_error_comparison(
    observations: Iterable[FrameObservation],
    segments: tuple[SegmentFit, ...],
    common: JointModelFit,
    progression: JointModelFit,
) -> dict[str, Any]:
    """Compare frame residuals after fitting all evaluated observations."""

    by_index = {item.row_index: item for item in observations}
    residuals: dict[str, list[float]] = {
        "independent_ramp": [],
        "joint_common_slope": [],
        "joint_slope_progression": [],
    }
    per_probe_residuals: dict[int, dict[str, list[float]]] = {}
    per_probe_times: dict[int, list[float]] = {}
    for segment_index, segment in enumerate(segments):
        members = tuple(by_index[index] for index in segment.observation_indices)
        times = np.asarray([item.time_s for item in members])
        values = np.asarray([item.absolute_cfo_hz for item in members])
        predictions = {
            "independent_ramp": np.asarray(segment.frequency_hz(times)),
            "joint_common_slope": _joint_segment_line(
                segment, segment_index, common, times
            ),
            "joint_slope_progression": _joint_segment_line(
                segment, segment_index, progression, times
            ),
        }
        for model, predicted in predictions.items():
            model_residuals = values - predicted
            residuals[model].extend(model_residuals.tolist())
            for member, residual in zip(members, model_residuals, strict=True):
                per_probe_residuals.setdefault(member.source_window_index, {}).setdefault(
                    model, []
                ).append(float(residual))
        for member in members:
            per_probe_times.setdefault(member.source_window_index, []).append(member.time_s)
    probe_rows = []
    for probe in sorted(per_probe_residuals):
        row: dict[str, Any] = {
            "source_window_index": probe,
            "center_time_s": float(np.mean(per_probe_times[probe])),
            "frame_count": len(per_probe_times[probe]),
        }
        for model, values in per_probe_residuals[probe].items():
            row[model] = float(np.sqrt(np.mean(np.asarray(values) ** 2)))
        probe_rows.append(row)
    return _finalize_error_comparison(residuals, probe_rows)


def leave_one_probe_out_model_error_comparison(
    observations: Iterable[FrameObservation], segments: tuple[SegmentFit, ...]
) -> dict[str, Any]:
    """Refit after withholding every frame from one timing-lock probe."""

    values = tuple(observations)
    by_index = {item.row_index: item for item in values}
    probe_to_segment: dict[int, int] = {}
    for segment_index, segment in enumerate(segments):
        for index in segment.observation_indices:
            probe = by_index[index].source_window_index
            previous = probe_to_segment.setdefault(probe, segment_index)
            if previous != segment_index:
                raise ValueError("one source probe appears in multiple coherent segments")

    residuals: dict[str, list[float]] = {
        "independent_ramp": [],
        "joint_common_slope": [],
        "joint_slope_progression": [],
    }
    probe_rows = []
    for probe, segment_index in sorted(probe_to_segment.items()):
        target_segment = segments[segment_index]
        held_out = tuple(
            by_index[index]
            for index in target_segment.observation_indices
            if by_index[index].source_window_index == probe
        )
        remaining = tuple(
            by_index[index]
            for index in target_segment.observation_indices
            if by_index[index].source_window_index != probe
        )
        independent = _fit_segment(remaining)
        if independent is None:
            raise ValueError(f"probe {probe} leaves insufficient independent-line support")

        modified_segments = []
        for current_index, segment in enumerate(segments):
            indices = tuple(
                index
                for index in segment.observation_indices
                if not (
                    current_index == segment_index
                    and by_index[index].source_window_index == probe
                )
            )
            modified_segments.append(
                replace(
                    segment,
                    observation_indices=indices,
                    frame_count=len(indices),
                    frequency_update_count=sum(
                        by_index[index].frequency_update_applied for index in indices
                    ),
                )
            )
        modified = tuple(modified_segments)
        common = joint_varying_intercept_fit(values, modified, slope_progression=False)
        progression = joint_varying_intercept_fit(values, modified, slope_progression=True)

        times = np.asarray([item.time_s for item in held_out])
        frequencies = np.asarray([item.absolute_cfo_hz for item in held_out])
        predictions = {
            "independent_ramp": np.asarray(independent.frequency_hz(times)),
            "joint_common_slope": _joint_segment_line(
                modified[segment_index], segment_index, common, times
            ),
            "joint_slope_progression": _joint_segment_line(
                modified[segment_index], segment_index, progression, times
            ),
        }
        row: dict[str, Any] = {
            "source_window_index": probe,
            "center_time_s": float(np.mean(times)),
            "frame_count": len(times),
        }
        for model, predicted in predictions.items():
            model_residuals = frequencies - predicted
            residuals[model].extend(model_residuals.tolist())
            row[model] = float(np.sqrt(np.mean(model_residuals**2)))
        probe_rows.append(row)
    return _finalize_error_comparison(residuals, probe_rows)


def _model_polynomial(observations: tuple[FrameObservation, ...]) -> tuple[np.ndarray, float]:
    reference = float(np.mean([item.time_s for item in observations]))
    times = np.asarray([item.time_s for item in observations])
    values = np.asarray([item.model_cfo_hz for item in observations])
    return np.polyfit(times - reference, values, 3), reference


def _model_frequency(
    time_s: float | np.ndarray, polynomial: np.ndarray, reference_time_s: float
) -> float | np.ndarray:
    value = np.polyval(polynomial, np.asarray(time_s) - reference_time_s)
    return float(value) if np.ndim(value) == 0 else value


def _style_axis(axis: plt.Axes, *, x_limits: tuple[float, float] | None = None) -> None:
    axis.grid(True, alpha=0.18, linewidth=0.8)
    axis.axhline(0.0, color=INK, linewidth=1.0, alpha=0.75)
    if x_limits is not None:
        axis.set_xlim(*x_limits)
    axis.spines[["top", "right"]].set_visible(False)


def _scatter_observations(
    axis: plt.Axes,
    observations: tuple[FrameObservation, ...],
    *,
    x_limits: tuple[float, float] | None = None,
) -> None:
    values = [
        item
        for item in observations
        if x_limits is None or x_limits[0] <= item.time_s <= x_limits[1]
    ]
    rejected = [item for item in values if not is_direct_quality(item)]
    gray = [
        item for item in values if is_direct_quality(item) and not item.frequency_update_applied
    ]
    blue = [item for item in values if is_direct_quality(item) and item.frequency_update_applied]
    for group, color, size, alpha, label in (
        (rejected, LIGHT_GRAY, 8, 0.25, "fails direct pilot-quality gate"),
        (gray, GRAY, 10, 0.35, "direct-quality; online CFO gate rejected"),
        (blue, BLUE, 11, 0.72, "direct-quality; online CFO update accepted"),
    ):
        axis.scatter(
            [item.time_s for item in group],
            [item.residual_cfo_hz for item in group],
            s=size,
            color=color,
            alpha=alpha,
            edgecolors="none",
            label=label,
            zorder=2,
        )


def _draw_segment_lines(
    axis: plt.Axes,
    segments: Iterable[SegmentFit],
    polynomial: np.ndarray,
    model_reference_time_s: float,
    *,
    x_limits: tuple[float, float] | None = None,
    alternating: bool = False,
) -> None:
    for index, segment in enumerate(segments):
        start = segment.start_time_s
        end = segment.end_time_s
        if x_limits is not None:
            if end < x_limits[0] or start > x_limits[1]:
                continue
            start = max(start, x_limits[0])
            end = min(end, x_limits[1])
        times = np.linspace(start, end, 80)
        residual = np.asarray(segment.frequency_hz(times)) - np.asarray(
            _model_frequency(times, polynomial, model_reference_time_s)
        )
        if segment.coherent:
            color = PALETTE[index % len(PALETTE)] if alternating else AMBER
            axis.plot(times, residual, color=color, linewidth=2.2, alpha=0.95, zorder=4)
        else:
            axis.plot(
                times,
                residual,
                color=RED,
                linewidth=1.2,
                alpha=0.75,
                linestyle="--",
                zorder=3,
            )


def render_method_1(
    destination: Path,
    observations: tuple[FrameObservation, ...],
    lock_fits: tuple[SegmentFit, ...],
) -> None:
    polynomial, model_reference = _model_polynomial(observations)
    full_limits = (
        min(item.time_s for item in observations),
        max(item.time_s for item in observations),
    )
    figure, axes = plt.subplots(3, 1, figsize=(15.5, 12.2), constrained_layout=True)
    figure.suptitle(
        "Method 1 · Independent robust line per timing-lock window",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )
    for axis, limits, title in (
        (axes[0], full_limits, "A · Full dense-frame record"),
        (axes[1], ZOOM_LIMITS_S, "B · 35.54–36.05 s: locks remain artificially separate"),
    ):
        _scatter_observations(axis, observations, x_limits=limits)
        _draw_segment_lines(axis, lock_fits, polynomial, model_reference, x_limits=limits)
        _style_axis(axis, x_limits=limits)
        axis.set_ylabel("frame CFO − frozen GLRT model (Hz)")
        axis.set_title(title, loc="left", fontsize=13, color=INK)
    handles, labels = axes[1].get_legend_handles_labels()
    handles.append(Line2D([0], [0], color=AMBER, linewidth=2.2))
    labels.append("independent robust lock fit")
    axes[1].legend(handles, labels, loc="upper left", ncol=2, frameon=True, fontsize=9)

    slopes = np.asarray([item.slope_hz_s for item in lock_fits])
    centers = np.asarray([item.center_time_s for item in lock_fits])
    sigmas = np.asarray([item.slope_sigma_hz_s or np.nan for item in lock_fits])
    axes[2].errorbar(
        centers,
        slopes,
        yerr=sigmas,
        fmt="o",
        markersize=3.5,
        linewidth=0.7,
        color=BLUE,
        ecolor=LIGHT_GRAY,
        alpha=0.75,
        label=f"independent lock slopes ({len(lock_fits)})",
    )
    axes[2].axhline(float(np.median(slopes)), color=AMBER, linewidth=2.0, label="median")
    axes[2].set_ylim(-7_500, 0)
    axes[2].set_xlim(*full_limits)
    axes[2].set_ylabel("local Doppler rate (Hz/s)")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title(
        "C · Short locks give noisy, highly fragmented slope estimates",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[2].grid(True, alpha=0.18, linewidth=0.8)
    axes[2].spines[["top", "right"]].set_visible(False)
    axes[2].legend(loc="lower right", frameon=True, fontsize=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)


def render_method_2(
    destination: Path,
    observations: tuple[FrameObservation, ...],
    segments: tuple[SegmentFit, ...],
) -> None:
    polynomial, model_reference = _model_polynomial(observations)
    full_limits = (
        min(item.time_s for item in observations),
        max(item.time_s for item in observations),
    )
    figure, axes = plt.subplots(3, 1, figsize=(15.5, 12.2), constrained_layout=True)
    figure.suptitle(
        "Method 2 · Offline batch joining with explicit change points",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )
    for axis, limits, title in (
        (axes[0], full_limits, "A · Full record: colored lines are recovered coherent ramps"),
        (axes[1], ZOOM_LIMITS_S, "B · Gray-only locks near 35.8 s join the same 104 ms ramp"),
    ):
        _scatter_observations(axis, observations, x_limits=limits)
        _draw_segment_lines(
            axis,
            segments,
            polynomial,
            model_reference,
            x_limits=limits,
            alternating=True,
        )
        _style_axis(axis, x_limits=limits)
        axis.set_ylabel("frame CFO − frozen GLRT model (Hz)")
        axis.set_title(title, loc="left", fontsize=13, color=INK)
    handles, labels = axes[1].get_legend_handles_labels()
    handles.extend(
        (
            Line2D([0], [0], color=GREEN, linewidth=2.2),
            Line2D([0], [0], color=RED, linewidth=1.2, linestyle="--"),
        )
    )
    labels.extend(("batch-selected coherent ramp", "short/noisy fragment"))
    axes[1].legend(handles, labels, loc="upper left", ncol=2, frameon=True, fontsize=9)

    coherent = [item for item in segments if item.coherent]
    fragments = [item for item in segments if not item.coherent]
    axes[2].scatter(
        [item.center_time_s for item in coherent],
        [1_000 * item.span_s for item in coherent],
        s=[18 + item.frame_count * 0.7 for item in coherent],
        color=GREEN,
        alpha=0.8,
        label=f"coherent ≥20 ms, ≤40 Hz RMS ({len(coherent)})",
    )
    axes[2].scatter(
        [item.center_time_s for item in fragments],
        [1_000 * item.span_s for item in fragments],
        s=28,
        color=RED,
        marker="x",
        alpha=0.8,
        label=f"short/noisy fragments ({len(fragments)})",
    )
    axes[2].axhline(20.0, color=INK, linewidth=1.0, linestyle="--", alpha=0.7)
    axes[2].set_xlim(*full_limits)
    axes[2].set_ylim(0, 115)
    axes[2].set_ylabel("recovered ramp span (ms)")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title(
        "C · Batch joining converts acquisition locks into 20–104 ms ramps",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[2].grid(True, alpha=0.18, linewidth=0.8)
    axes[2].spines[["top", "right"]].set_visible(False)
    axes[2].legend(loc="lower right", frameon=True, fontsize=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)


def _joint_segment_line(
    segment: SegmentFit,
    segment_index: int,
    model: JointModelFit,
    times: np.ndarray,
) -> np.ndarray:
    local_time = times - segment.center_time_s
    progression = 0.0 if model.slope_progression_hz_s2 is None else model.slope_progression_hz_s2
    return (
        model.segment_intercepts_hz[segment_index]
        + model.shared_slope_hz_s * local_time
        + progression
        * ((segment.center_time_s - model.reference_time_s) * local_time + 0.5 * local_time**2)
    )


def render_method_3(
    destination: Path,
    observations: tuple[FrameObservation, ...],
    segments: tuple[SegmentFit, ...],
    common: JointModelFit,
    progression: JointModelFit,
    *,
    common_loo_rms_hz_s: float,
    progression_loo_rms_hz_s: float,
) -> None:
    polynomial, model_reference = _model_polynomial(observations)
    full_limits = (
        min(item.time_s for item in observations),
        max(item.time_s for item in observations),
    )
    figure, axes = plt.subplots(3, 1, figsize=(15.5, 12.2), constrained_layout=True)
    figure.suptitle(
        "Method 3 · Joint varying-intercept line family",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )

    centers = np.asarray([item.center_time_s for item in segments])
    slopes = np.asarray([item.slope_hz_s for item in segments])
    sigmas = np.asarray([item.slope_sigma_hz_s or np.nan for item in segments])
    axes[0].errorbar(
        centers,
        slopes,
        yerr=sigmas,
        fmt="o",
        markersize=5,
        linewidth=0.8,
        color=BLUE,
        ecolor=LIGHT_GRAY,
        alpha=0.85,
        label="independent recovered-ramp slopes",
    )
    grid = np.linspace(*full_limits, 300)
    axes[0].axhline(
        common.shared_slope_hz_s,
        color=GREEN,
        linewidth=2.4,
        label=f"common slope {common.shared_slope_hz_s / 1_000:.3f} kHz/s",
    )
    axes[0].plot(
        grid,
        progression.slope_at(grid),
        color=PURPLE,
        linewidth=2.4,
        label=(
            "linear progression "
            f"{progression.slope_progression_hz_s2:+.1f} ± "
            f"{progression.slope_progression_sigma_hz_s2:.1f} Hz/s²"
        ),
    )
    axes[0].set_xlim(*full_limits)
    axes[0].set_ylim(-4_500, -3_000)
    axes[0].set_ylabel("local Doppler rate (Hz/s)")
    axes[0].set_title(
        "A · One shared family; a linear slope progression is not resolved",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[0].grid(True, alpha=0.18, linewidth=0.8)
    axes[0].spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="lower right", frameon=True, fontsize=9)

    slope_common_errors = slope_leave_one_segment_out_errors(segments, linear=False)
    slope_progression_errors = slope_leave_one_segment_out_errors(segments, linear=True)
    axes[1].scatter(
        centers,
        slope_common_errors,
        color=GREEN,
        s=28,
        alpha=0.75,
        label="common-slope error",
    )
    axes[1].scatter(
        centers,
        slope_progression_errors,
        color=PURPLE,
        s=28,
        alpha=0.75,
        marker="s",
        label="progression error",
    )
    axes[1].axhline(0.0, color=INK, linewidth=1.0)
    axes[1].set_xlim(*full_limits)
    axes[1].set_ylabel("independent slope − family model (Hz/s)")
    axes[1].set_title(
        "B · Leave-one-segment-out RMS: "
        f"common {common_loo_rms_hz_s:.1f}, progression {progression_loo_rms_hz_s:.1f} Hz/s",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[1].grid(True, alpha=0.18, linewidth=0.8)
    axes[1].spines[["top", "right"]].set_visible(False)
    axes[1].legend(loc="upper right", frameon=True, fontsize=9)

    _scatter_observations(axes[2], observations, x_limits=ZOOM_LIMITS_S)
    for index, segment in enumerate(segments):
        if segment.end_time_s < ZOOM_LIMITS_S[0] or segment.start_time_s > ZOOM_LIMITS_S[1]:
            continue
        start = max(segment.start_time_s, ZOOM_LIMITS_S[0])
        end = min(segment.end_time_s, ZOOM_LIMITS_S[1])
        times = np.linspace(start, end, 80)
        absolute = _joint_segment_line(segment, index, common, times)
        residual = absolute - np.asarray(_model_frequency(times, polynomial, model_reference))
        axes[2].plot(times, residual, color=GREEN, linewidth=2.3, zorder=4)
    _style_axis(axes[2], x_limits=ZOOM_LIMITS_S)
    axes[2].set_ylabel("frame CFO − frozen GLRT model (Hz)")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title(
        "C · Shared-slope fit still follows the gray 35.8 s observations",
        loc="left",
        fontsize=13,
        color=INK,
    )
    handles, labels = axes[2].get_legend_handles_labels()
    handles.append(Line2D([0], [0], color=GREEN, linewidth=2.3))
    labels.append("joint common-slope family")
    axes[2].legend(handles, labels, loc="upper left", ncol=2, frameon=True, fontsize=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)


def render_model_error_comparison(
    destination: Path,
    in_sample: dict[str, Any],
    leave_one_probe_out: dict[str, Any],
    progression: JointModelFit,
) -> None:
    """Compare overall and per-probe CFO residuals for all line models."""

    models = ("independent_ramp", "joint_common_slope", "joint_slope_progression")
    labels = ("independent\nramp slopes", "joint\ncommon slope", "joint slope\nprogression")
    colors = (AMBER, GREEN, PURPLE)
    figure, axes = plt.subplots(3, 1, figsize=(14.5, 12.4), constrained_layout=True)
    figure.suptitle(
        "Model error comparison · same coherent frames and original probes",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )

    positions = np.arange(2, dtype=float)
    width = 0.23
    for model_index, (model, label, color) in enumerate(zip(models, labels, colors, strict=True)):
        values = (
            in_sample["overall"][model]["rms_hz"],
            leave_one_probe_out["overall"][model]["rms_hz"],
        )
        bars = axes[0].bar(
            positions + (model_index - 1) * width,
            values,
            width=width,
            color=color,
            alpha=0.88,
            label=label.replace("\n", " "),
        )
        axes[0].bar_label(bars, fmt="%.3f Hz", padding=3, fontsize=9)
    axes[0].set_xticks(positions, ("fit and score same frames", "leave one whole probe out"))
    axes[0].set_ylim(0, 20.5)
    axes[0].set_ylabel("overall frame CFO residual RMS (Hz)")
    axes[0].set_title(
        "A · Progression changes training RMS by millihertz and does not improve held-out RMS",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[0].grid(True, axis="y", alpha=0.18, linewidth=0.8)
    axes[0].spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=3, frameon=True, fontsize=9)

    probe_values = [
        [item[model] for item in leave_one_probe_out["probes"]] for model in models
    ]
    boxes = axes[1].boxplot(
        probe_values,
        tick_labels=labels,
        patch_artist=True,
        showfliers=True,
        widths=0.55,
        medianprops={"color": INK, "linewidth": 1.8},
        whiskerprops={"color": GRAY},
        capprops={"color": GRAY},
        flierprops={"marker": "o", "markersize": 3, "markerfacecolor": GRAY},
    )
    for patch, color in zip(boxes["boxes"], colors, strict=True):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
    for index, model in enumerate(models, start=1):
        median = leave_one_probe_out["per_probe"][model]["median_rms_hz"]
        axes[1].text(index, median + 1.0, f"median {median:.3f}", ha="center", fontsize=9)
    axes[1].set_ylim(0, 72)
    axes[1].set_ylabel("held-out probe CFO residual RMS (Hz)")
    axes[1].set_title(
        "B · Probe = one original timing-lock window; all its frames are withheld together",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[1].grid(True, axis="y", alpha=0.18, linewidth=0.8)
    axes[1].spines[["top", "right"]].set_visible(False)

    probe_rows = leave_one_probe_out["probes"]
    times = np.asarray([item["center_time_s"] for item in probe_rows])
    deltas = np.asarray(
        [item[models[2]] - item[models[1]] for item in probe_rows], dtype=float
    )
    axes[2].scatter(
        times[deltas <= 0],
        deltas[deltas <= 0],
        color=GREEN,
        s=30,
        alpha=0.8,
        label="progression improves probe RMS",
    )
    axes[2].scatter(
        times[deltas > 0],
        deltas[deltas > 0],
        color=RED,
        s=30,
        alpha=0.8,
        label="progression worsens probe RMS",
    )
    axes[2].axhline(0.0, color=INK, linewidth=1.0)
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_ylabel("progression RMS − common-slope RMS (Hz)")
    comparison = leave_one_probe_out["progression_minus_common"]
    axes[2].set_title(
        "C · Held-out progression: "
        f"{comparison['improved_probe_count']} probes improve, "
        f"{comparison['worsened_probe_count']} worsen; overall Δ "
        f"{comparison['overall_rms_delta_hz']:+.3f} Hz",
        loc="left",
        fontsize=13,
        color=INK,
    )
    axes[2].grid(True, alpha=0.18, linewidth=0.8)
    axes[2].spines[["top", "right"]].set_visible(False)
    axes[2].legend(loc="upper left", ncol=2, frameon=True, fontsize=9)
    acceleration = progression.slope_progression_hz_s2
    acceleration_sigma = progression.slope_progression_sigma_hz_s2
    axes[2].text(
        0.995,
        0.04,
        f"measured slope progression: {acceleration:+.2f} ± {acceleration_sigma:.2f} Hz/s²",
        transform=axes[2].transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        color=INK,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)


def _segment_result(segment: SegmentFit) -> dict[str, Any]:
    result = asdict(segment)
    result["span_s"] = segment.span_s
    result["source_window_count"] = segment.source_window_count
    result["coherent"] = segment.coherent
    return result


def _write_report(path: Path, results: dict[str, Any]) -> None:
    method_1 = results["methods"]["independent_timing_locks"]
    method_2 = results["methods"]["batch_joined_segments"]
    method_3 = results["methods"]["joint_line_family"]
    target = method_2["gray_interval_worked_example"]
    coherent = method_2["coherent_summary"]
    common = method_3["common_slope"]
    progression = method_3["linear_slope_progression"]
    bic_delta = method_3["progression_minus_common_bic"]
    progression_span = method_3["progression_over_observed_span"]
    error_comparison = results["model_error_comparison"]
    in_sample = error_comparison["in_sample"]
    probe_holdout = error_comparison["leave_one_probe_out"]
    in_overall = in_sample["overall"]
    holdout_overall = probe_holdout["overall"]
    holdout_probe = probe_holdout["per_probe"]
    independent_error_row = (
        "| independent ramp slopes | "
        f"{in_overall['independent_ramp']['rms_hz']:.3f} Hz | "
        f"{holdout_overall['independent_ramp']['rms_hz']:.3f} Hz | "
        f"{holdout_probe['independent_ramp']['median_rms_hz']:.3f} Hz |"
    )
    common_error_row = (
        "| joint common slope | "
        f"{in_overall['joint_common_slope']['rms_hz']:.3f} Hz | "
        f"{holdout_overall['joint_common_slope']['rms_hz']:.3f} Hz | "
        f"{holdout_probe['joint_common_slope']['median_rms_hz']:.3f} Hz |"
    )
    progression_error_row = (
        "| joint slope progression | "
        f"{in_overall['joint_slope_progression']['rms_hz']:.3f} Hz | "
        f"{holdout_overall['joint_slope_progression']['rms_hz']:.3f} Hz | "
        f"{holdout_probe['joint_slope_progression']['median_rms_hz']:.3f} Hz |"
    )
    figure_paths = results["figures"]

    def report_relative_figure(name: str) -> str:
        return Path(figure_paths[name]).relative_to(path.parent).as_posix()

    method_1_figure = report_relative_figure("method_1")
    method_2_figure = report_relative_figure("method_2")
    method_3_figure = report_relative_figure("method_3")
    error_figure = report_relative_figure("model_error_comparison")
    text = f"""# Offline sawtooth recovery on `470384`

## Bottom line

The gray 1.333 ms frame CFOs are useful observations.  The best of the three
methods is the offline batch partition: it joins the 125 timing-lock acquisition
windows into {method_2['partition_segment_count']} line segments, of which
{coherent['segment_count']} pass the explicit 20 ms / 40 Hz-RMS coherence gate.
Those coherent ramps contain {coherent['frame_count']} of the
{results['observation_inventory']['direct_quality_frame_count']} direct-quality
frames.

In the disputed interval, source locks {target['source_window_start']}–
{target['source_window_end']} become one {1_000 * target['span_s']:.1f} ms ramp:
{target['frame_count']} frames, {target['frequency_update_count']} accepted by the
online CFO gate, Doppler rate {target['slope_hz_s'] / 1_000:.3f} kHz/s, raw line
RMS {target['raw_rms_hz']:.1f} Hz, and interleaved held-out RMS
{target['held_out_rms_hz']:.1f} Hz.  In other words, the offline result recovers
the gray-only coast instead of treating the online Kalman decision as truth.

## Scope and ordinate

- Capture: `{SESSION_ID}`, `stream-0`, receiver 0, upper edge, 33.701–37.720 s.
- Input: the persisted dense known-pilot evidence; no new IQ collection and no
  re-use of the online Kalman state as a fit prior.
- Every direct-quality frame has exact pilot coherence ≥
  {MINIMUM_EXACT_COHERENCE:.2f} and non-negative exact-minus-control margin.
- The figures display frame CFO minus the frozen cubic GLRT trajectory so the
  sawtooth is visible.  Every reported line slope is fit in **absolute CFO
  space**, so subtracting the display model does not define the Doppler rate.
- Blue/gray records only whether the online CFO update was accepted.  Both are
  observations for all three offline methods.

## Method 1 — independent timing-lock lines

![Independent timing-lock fits]({method_1_figure})

This is the least-assumptive baseline: robustly fit each of the
{method_1['fit_count']} timing locks by itself.  It confirms that local slopes
exist, but the typical lock spans only {1_000 * method_1['median_span_s']:.1f} ms.
The resulting slope spread is {method_1['slope_p05_hz_s'] / 1_000:.3f} to
{method_1['slope_p95_hz_s'] / 1_000:.3f} kHz/s (5th–95th percentile), much of it
from short-baseline slope uncertainty.  This method cannot answer which adjacent
locks are samples of the same physical ramp.

## Method 2 — batch joining with change points

![Batch joined segments]({method_2_figure})

An exact dynamic program partitions the ordered locks.  A candidate may join at
most {MAXIMUM_JOINED_LOCKS} locks, span at most
{1_000 * MAXIMUM_JOINED_SPAN_S:.0f} ms, and contain no inter-frame gap above
{1_000 * MAXIMUM_JOINED_FRAME_GAP_S:.0f} ms.  Its cost is a capped-square robust
line residual plus a BIC-like per-segment penalty of
{method_2['configuration']['segment_penalty']:.2f}.  The noise normalization,
{method_2['configuration']['noise_scale_hz']:.2f} Hz, is the 90th percentile of
the independent-lock robust RMS values.

This finds {coherent['segment_count']} coherent 20–104 ms ramps with median raw
RMS {coherent['median_raw_rms_hz']:.1f} Hz and median interleaved held-out RMS
{coherent['median_held_out_rms_hz']:.1f} Hz.  The red dashed pieces are retained
as honest short/noisy fragments, not silently discarded measurements.

## Method 3 — varying intercepts, shared slope family

![Joint line family]({method_3_figure})

For recovered ramp `j`, with center `tau_j`, the joint model is

```text
f_ij = a_j + beta_0*x_ij
       + beta_1*((tau_j - T0)*x_ij + 0.5*x_ij^2) + robust error,
x_ij = t_ij - tau_j.
```

Every ramp receives its own CFO intercept `a_j`; `beta_0` is the shared Doppler
rate and `beta_1` is a linear progression of that rate in time.  The common-rate
fit is {common['shared_slope_hz_s'] / 1_000:.4f} ±
{common['shared_slope_sigma_hz_s'] / 1_000:.4f} kHz/s.  Allowing progression gives
`beta_1 = {progression['slope_progression_hz_s2']:+.2f} ±
{progression['slope_progression_sigma_hz_s2']:.2f} Hz/s²`.

This recording does **not** resolve the proposed progression: adding it worsens
BIC by {bic_delta:.2f}, and leave-one-ramp-out slope prediction changes from
{method_3['common_slope_loo_rms_hz_s']:.1f} Hz/s (common) to
{method_3['linear_progression_loo_rms_hz_s']:.1f} Hz/s (progression).  A single
shared-slope family is therefore the more defensible description of these four
seconds.  A progression remains physically plausible; it needs a longer span or
multiple captures to estimate without confusing real acceleration with
tooth-to-tooth slope scatter.

Across the observed ramp centers, the fitted rate changes from
{progression_span['first_slope_hz_s']:.1f} to
{progression_span['last_slope_hz_s']:.1f} Hz/s: a progression of
{progression_span['slope_change_hz_s']:+.1f} ±
{progression_span['slope_change_sigma_hz_s']:.1f} Hz/s over
{progression_span['span_s']:.3f} s.  This is a change in **Doppler rate**, not a
carrier-frequency shift.

## Overall and per-probe error comparison

![Model error comparison]({error_figure})

All models below are scored on the same {coherent['frame_count']} frames from
{probe_holdout['per_probe']['independent_ramp']['probe_count']} original probe
windows.  “Leave one probe out” removes every frame from one probe, refits, and
then predicts that complete probe.  The recovered ramp partition is held fixed,
so this tests CFO-model prediction conditional on segment membership rather than
re-running end-to-end segment discovery.

| model | in-sample frame RMS | held-out frame RMS | median held-out probe RMS |
| --- | ---: | ---: | ---: |
{independent_error_row}
{common_error_row}
{progression_error_row}

Progression reduces same-frame RMS by only
{-in_sample['progression_minus_common']['overall_rms_delta_hz']:.4f} Hz, or
{-in_sample['progression_minus_common']['overall_rms_relative_percent']:.3f}%.
That tiny training improvement disappears under probe holdout: overall RMS is
{probe_holdout['progression_minus_common']['overall_rms_delta_hz']:+.4f} Hz
({probe_holdout['progression_minus_common']['overall_rms_relative_percent']:+.3f}%)
worse than the common-slope model.  It improves
{probe_holdout['progression_minus_common']['improved_probe_count']} probes and
worsens {probe_holdout['progression_minus_common']['worsened_probe_count']}.
The common-slope model is therefore the useful regularizer; the progression
term does not provide measurable predictive value in this record.

## Interpretation and next use

The important conceptual separation is now explicit:

1. a **timing lock** says where a short pilot-frame lattice was acquired;
2. the batch partition decides which locks lie on one continuous CFO ramp;
3. the line family estimates the common Doppler rate after giving every ramp an
   arbitrary CFO intercept.

That arbitrary intercept is exactly what makes the approach compatible with an
unknown LNB offset and unknown per-satellite carrier assignment.  Association to
a TLE should compare the measured **rate (and eventually rate progression)** to
predicted range-rate derivatives, not compare absolute received frequency.

These thresholds were tested on one worked example, so this is a diagnostic
analysis rather than a frozen production contract.  The next honest validation
is to hold the configuration fixed and run it on other captures, especially
passes with weaker or crossing sawtooth families.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    document = _load_json(arguments.evidence)
    observations = observations_from_document(document)
    quality = direct_quality_observations(observations)
    lock_fits = independent_lock_fits(quality)
    robust_rms = np.asarray([item.robust_rms_hz for item in lock_fits])
    noise_scale_hz = float(np.percentile(robust_rms, 90))
    segment_penalty = float(2.0 * math.log(len(quality)))
    partition = batch_joined_segments(
        quality,
        lock_fits,
        noise_scale_hz=noise_scale_hz,
        segment_penalty=segment_penalty,
    )
    coherent = tuple(item for item in partition if item.coherent)
    common = joint_varying_intercept_fit(quality, coherent, slope_progression=False)
    progression = joint_varying_intercept_fit(quality, coherent, slope_progression=True)
    common_loo = slope_leave_one_segment_out_rms(coherent, linear=False)
    progression_loo = slope_leave_one_segment_out_rms(coherent, linear=True)
    in_sample_errors = in_sample_model_error_comparison(
        quality, coherent, common, progression
    )
    probe_holdout_errors = leave_one_probe_out_model_error_comparison(quality, coherent)

    method_1_path = arguments.output_root / "method-1-independent-lock-lines.png"
    method_2_path = arguments.output_root / "method-2-batch-joined-segments.png"
    method_3_path = arguments.output_root / "method-3-joint-slope-family.png"
    error_path = arguments.output_root / "model-error-comparison.png"
    render_method_1(method_1_path, observations, lock_fits)
    render_method_2(method_2_path, observations, partition)
    render_method_3(
        method_3_path,
        observations,
        coherent,
        common,
        progression,
        common_loo_rms_hz_s=common_loo,
        progression_loo_rms_hz_s=progression_loo,
    )
    render_model_error_comparison(
        error_path,
        in_sample_errors,
        probe_holdout_errors,
        progression,
    )

    target_matches = [
        item
        for item in coherent
        if item.start_time_s <= 35.77 and item.end_time_s >= 35.82
    ]
    if len(target_matches) != 1:
        raise RuntimeError(f"expected one recovered 35.8 s ramp, found {len(target_matches)}")
    held_out = [item.held_out_rms_hz for item in coherent if item.held_out_rms_hz is not None]
    results = stable_measurement_floats(
        {
            "schema_version": 2,
            "algorithm": "470384-offline-sawtooth-method-comparison-v2",
            "input": document["input"],
            "observation_inventory": {
                "dense_frame_count": len(observations),
                "direct_quality_frame_count": len(quality),
                "online_frequency_update_count_within_direct_quality": sum(
                    item.frequency_update_applied for item in quality
                ),
                "online_rejected_count_within_direct_quality": sum(
                    not item.frequency_update_applied for item in quality
                ),
            },
            "methods": {
                "independent_timing_locks": {
                    "fit_count": len(lock_fits),
                    "median_span_s": float(np.median([item.span_s for item in lock_fits])),
                    "median_raw_rms_hz": float(
                        np.median([item.raw_rms_hz for item in lock_fits])
                    ),
                    "slope_p05_hz_s": float(
                        np.percentile([item.slope_hz_s for item in lock_fits], 5)
                    ),
                    "slope_median_hz_s": float(
                        np.median([item.slope_hz_s for item in lock_fits])
                    ),
                    "slope_p95_hz_s": float(
                        np.percentile([item.slope_hz_s for item in lock_fits], 95)
                    ),
                    "fits": [_segment_result(item) for item in lock_fits],
                },
                "batch_joined_segments": {
                    "configuration": {
                        "noise_scale_hz": noise_scale_hz,
                        "segment_penalty": segment_penalty,
                        "maximum_joined_span_s": MAXIMUM_JOINED_SPAN_S,
                        "maximum_joined_frame_gap_s": MAXIMUM_JOINED_FRAME_GAP_S,
                        "maximum_joined_locks": MAXIMUM_JOINED_LOCKS,
                        "minimum_coherent_span_s": MINIMUM_COHERENT_SPAN_S,
                        "maximum_coherent_rms_hz": MAXIMUM_COHERENT_RMS_HZ,
                    },
                    "partition_segment_count": len(partition),
                    "coherent_summary": {
                        "segment_count": len(coherent),
                        "frame_count": sum(item.frame_count for item in coherent),
                        "online_frequency_update_count": sum(
                            item.frequency_update_count for item in coherent
                        ),
                        "median_span_s": float(np.median([item.span_s for item in coherent])),
                        "maximum_span_s": max(item.span_s for item in coherent),
                        "median_slope_hz_s": float(
                            np.median([item.slope_hz_s for item in coherent])
                        ),
                        "median_raw_rms_hz": float(
                            np.median([item.raw_rms_hz for item in coherent])
                        ),
                        "median_held_out_rms_hz": float(np.median(held_out)),
                    },
                    "gray_interval_worked_example": _segment_result(target_matches[0]),
                    "segments": [_segment_result(item) for item in partition],
                },
                "joint_line_family": {
                    "common_slope": asdict(common),
                    "linear_slope_progression": asdict(progression),
                    "progression_over_observed_span": {
                        "first_center_time_s": coherent[0].center_time_s,
                        "last_center_time_s": coherent[-1].center_time_s,
                        "span_s": coherent[-1].center_time_s - coherent[0].center_time_s,
                        "first_slope_hz_s": progression.slope_at(
                            coherent[0].center_time_s
                        ),
                        "last_slope_hz_s": progression.slope_at(
                            coherent[-1].center_time_s
                        ),
                        "slope_change_hz_s": progression.slope_progression_hz_s2
                        * (coherent[-1].center_time_s - coherent[0].center_time_s),
                        "slope_change_sigma_hz_s": (
                            progression.slope_progression_sigma_hz_s2
                            * (coherent[-1].center_time_s - coherent[0].center_time_s)
                        ),
                    },
                    "progression_minus_common_bic": progression.bic - common.bic,
                    "common_slope_loo_rms_hz_s": common_loo,
                    "linear_progression_loo_rms_hz_s": progression_loo,
                },
            },
            "model_error_comparison": {
                "evaluated_frame_count": sum(item.frame_count for item in coherent),
                "probe_definition": "one original source_window_index timing-lock window",
                "in_sample": in_sample_errors,
                "leave_one_probe_out": probe_holdout_errors,
            },
            "figures": {
                "method_1": str(method_1_path),
                "method_2": str(method_2_path),
                "method_3": str(method_3_path),
                "model_error_comparison": str(error_path),
            },
        }
    )
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    result_path = arguments.output_root / "sawtooth-method-results.json"
    result_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_report(arguments.report_path, results)
    print(json.dumps({"results": str(result_path), "report": str(arguments.report_path)}, indent=2))


if __name__ == "__main__":
    main()
