"""Pure candidate-only comparison of observed CFO and predicted TLE Doppler tracks.

The Standard pipeline's final trajectories are baseband and may have an
uncalibrated frequency origin.  This module therefore removes exactly one
constant intercept from every comparison and scores only frequency evolution.
It performs no catalog, artifact, TLE archive, HTTP, or CLI access.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ObservedCfoTrajectory:
    """One sealed Standard final trajectory with its capture-time bounds."""

    trajectory_id: str
    path_id: str
    polynomial_degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    start_s: float
    end_s: float
    first_estimate_utc_ns: int
    first_earliest_utc_ns: int
    first_latest_utc_ns: int

    def __post_init__(self) -> None:
        if self.polynomial_degree not in (1, 2, 3):
            raise ValueError("observed polynomial degree must be one, two, or three")
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("observed coefficient count disagrees with degree")
        if self.end_s <= self.start_s:
            raise ValueError("observed trajectory requires positive duration")
        if not (
            self.first_earliest_utc_ns <= self.first_estimate_utc_ns <= self.first_latest_utc_ns
        ):
            raise ValueError("observed first-sample timing bounds are inconsistent")
        values = (
            self.reference_time_s,
            self.start_s,
            self.end_s,
            *self.coefficients_hz,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("observed trajectory values must be finite")


@dataclass(frozen=True, slots=True)
class PredictedDopplerTrajectory:
    """One TLE prediction expressed as derivatives at a UTC reference."""

    object_name: str
    catalog_number: int
    reference_utc_ns: int
    start_utc_ns: int
    end_utc_ns: int
    frequency_at_reference_hz: float
    slope_hz_s: float
    acceleration_hz_s2: float
    jerk_hz_s3: float
    element_epoch_utc_ns: int
    element_age_s: float
    peak_elevation_deg: float
    boundary_uncertain: bool = False

    def __post_init__(self) -> None:
        if self.catalog_number <= 0:
            raise ValueError("predicted catalog number must be positive")
        if self.end_utc_ns <= self.start_utc_ns:
            raise ValueError("predicted trajectory requires positive duration")
        values = (
            self.frequency_at_reference_hz,
            self.slope_hz_s,
            self.acceleration_hz_s2,
            self.jerk_hz_s3,
            self.element_age_s,
            self.peak_elevation_deg,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("predicted trajectory values must be finite")


@dataclass(frozen=True, slots=True)
class AlignmentMetrics:
    """Intercept-invariant residuals over one observed/predicted overlap."""

    overlap_start_utc_ns: int
    overlap_end_utc_ns: int
    comparison_point_count: int
    fitted_frequency_offset_hz: float
    detrended_frequency_rms_hz: float
    slope_rms_difference_hz_s: float
    slope_max_difference_hz_s: float
    acceleration_rms_difference_hz_s2: float
    acceleration_max_difference_hz_s2: float
    jerk_rms_difference_hz_s3: float
    jerk_max_difference_hz_s3: float
    comparison_score: float


@dataclass(frozen=True, slots=True)
class RankedAlignment:
    """One nominal match plus sensitivity to the capture timing bracket."""

    rank: int
    prediction: PredictedDopplerTrajectory
    nominal: AlignmentMetrics
    earliest_score: float
    latest_score: float
    best_timing_score: float
    worst_timing_score: float


@dataclass(frozen=True, slots=True)
class ThresholdInterval:
    """One linearly interpolated interval at or above a sampled threshold."""

    start_s: float
    end_s: float
    clipped_at_start: bool
    clipped_at_end: bool


def threshold_intervals(
    sample_times_s: np.ndarray,
    values: np.ndarray,
    *,
    threshold: float,
) -> tuple[ThresholdInterval, ...]:
    """Find threshold intervals, interpolating entry and exit between samples."""

    times = np.asarray(sample_times_s, dtype=np.float64)
    samples = np.asarray(values, dtype=np.float64)
    if times.ndim != 1 or samples.ndim != 1 or times.size != samples.size:
        raise ValueError("threshold samples must be equal-length one-dimensional arrays")
    if times.size < 2 or np.any(np.diff(times) <= 0):
        raise ValueError("threshold sample times must be strictly increasing")
    if not math.isfinite(threshold) or not np.all(np.isfinite(times)):
        raise ValueError("threshold and sample times must be finite")

    inside = np.isfinite(samples) & (samples >= threshold)
    result = []
    index = 0
    while index < inside.size:
        if not inside[index]:
            index += 1
            continue
        first = index
        while index + 1 < inside.size and inside[index + 1]:
            index += 1
        last = index
        if first == 0:
            start = float(times[0])
        else:
            start = _threshold_crossing(
                float(times[first - 1]),
                float(samples[first - 1]),
                float(times[first]),
                float(samples[first]),
                threshold,
            )
        if last == inside.size - 1:
            end = float(times[-1])
        else:
            end = _threshold_crossing(
                float(times[last]),
                float(samples[last]),
                float(times[last + 1]),
                float(samples[last + 1]),
                threshold,
            )
        result.append(
            ThresholdInterval(
                start_s=start,
                end_s=end,
                clipped_at_start=first == 0,
                clipped_at_end=last == inside.size - 1,
            )
        )
        index += 1
    return tuple(result)


def _threshold_crossing(
    first_time_s: float,
    first_value: float,
    second_time_s: float,
    second_value: float,
    threshold: float,
) -> float:
    if not math.isfinite(first_value) or not math.isfinite(second_value):
        return second_time_s if second_value >= threshold else first_time_s
    difference = second_value - first_value
    if difference == 0.0:
        return (first_time_s + second_time_s) / 2.0
    fraction = (threshold - first_value) / difference
    return first_time_s + min(1.0, max(0.0, fraction)) * (second_time_s - first_time_s)


def compare_trajectory(
    observed: ObservedCfoTrajectory,
    predicted: PredictedDopplerTrajectory,
    *,
    first_sample_utc_ns: int | None = None,
    comparison_point_count: int = 128,
) -> AlignmentMetrics | None:
    """Compare frequency shape after fitting one nuisance CFO intercept."""

    if comparison_point_count < 3:
        raise ValueError("a trajectory comparison needs at least three points")
    origin_ns = (
        observed.first_estimate_utc_ns if first_sample_utc_ns is None else first_sample_utc_ns
    )
    observed_start_ns = origin_ns + round(observed.start_s * 1e9)
    observed_end_ns = origin_ns + round(observed.end_s * 1e9)
    overlap_start_ns = max(observed_start_ns, predicted.start_utc_ns)
    overlap_end_ns = min(observed_end_ns, predicted.end_utc_ns)
    if overlap_end_ns <= overlap_start_ns:
        return None

    duration_s = (overlap_end_ns - overlap_start_ns) / 1e9
    elapsed_s = np.linspace(0.0, duration_s, comparison_point_count)
    observed_relative_s = (
        (overlap_start_ns - origin_ns) / 1e9 + elapsed_s - observed.reference_time_s
    )
    predicted_relative_s = (overlap_start_ns - predicted.reference_utc_ns) / 1e9 + elapsed_s
    observed_coefficients = np.asarray(observed.coefficients_hz, dtype=np.float64)
    predicted_coefficients = np.asarray(
        (
            predicted.jerk_hz_s3 / 6.0,
            predicted.acceleration_hz_s2 / 2.0,
            predicted.slope_hz_s,
            predicted.frequency_at_reference_hz,
        ),
        dtype=np.float64,
    )

    observed_frequency = np.polyval(observed_coefficients, observed_relative_s)
    predicted_frequency = np.polyval(predicted_coefficients, predicted_relative_s)
    raw_frequency_residual = observed_frequency - predicted_frequency
    offset = float(np.median(raw_frequency_residual))
    detrended = raw_frequency_residual - offset

    derivative_differences: list[np.ndarray] = []
    for order in (1, 2, 3):
        observed_derivative = np.polyder(observed_coefficients, order)
        predicted_derivative = np.polyder(predicted_coefficients, order)
        observed_values = (
            np.zeros_like(elapsed_s)
            if observed_derivative.size == 0
            else np.polyval(observed_derivative, observed_relative_s)
        )
        predicted_values = (
            np.zeros_like(elapsed_s)
            if predicted_derivative.size == 0
            else np.polyval(predicted_derivative, predicted_relative_s)
        )
        derivative_differences.append(observed_values - predicted_values)

    rms = tuple(float(np.sqrt(np.mean(values**2))) for values in derivative_differences)
    maximum = tuple(float(np.max(np.abs(values))) for values in derivative_differences)
    score = rms[0] + rms[1] * duration_s + rms[2] * duration_s * duration_s
    return AlignmentMetrics(
        overlap_start_utc_ns=overlap_start_ns,
        overlap_end_utc_ns=overlap_end_ns,
        comparison_point_count=comparison_point_count,
        fitted_frequency_offset_hz=offset,
        detrended_frequency_rms_hz=float(np.sqrt(np.mean(detrended**2))),
        slope_rms_difference_hz_s=rms[0],
        slope_max_difference_hz_s=maximum[0],
        acceleration_rms_difference_hz_s2=rms[1],
        acceleration_max_difference_hz_s2=maximum[1],
        jerk_rms_difference_hz_s3=rms[2],
        jerk_max_difference_hz_s3=maximum[2],
        comparison_score=score,
    )


def rank_predictions(
    observed: ObservedCfoTrajectory,
    predictions: tuple[PredictedDopplerTrajectory, ...],
    *,
    limit: int = 5,
    comparison_point_count: int = 128,
) -> tuple[RankedAlignment, ...]:
    """Rank deterministic candidate matches and expose timing sensitivity."""

    if limit < 1:
        raise ValueError("alignment ranking limit must be positive")
    candidates = []
    for prediction in predictions:
        nominal = compare_trajectory(
            observed,
            prediction,
            comparison_point_count=comparison_point_count,
        )
        if nominal is None:
            continue
        earliest = compare_trajectory(
            observed,
            prediction,
            first_sample_utc_ns=observed.first_earliest_utc_ns,
            comparison_point_count=comparison_point_count,
        )
        latest = compare_trajectory(
            observed,
            prediction,
            first_sample_utc_ns=observed.first_latest_utc_ns,
            comparison_point_count=comparison_point_count,
        )
        timing_scores = [nominal.comparison_score]
        if earliest is not None:
            timing_scores.append(earliest.comparison_score)
        if latest is not None:
            timing_scores.append(latest.comparison_score)
        candidates.append(
            (
                nominal.comparison_score,
                prediction.catalog_number,
                prediction.object_name,
                prediction,
                nominal,
                nominal.comparison_score if earliest is None else earliest.comparison_score,
                nominal.comparison_score if latest is None else latest.comparison_score,
                min(timing_scores),
                max(timing_scores),
            )
        )
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return tuple(
        RankedAlignment(
            rank=rank,
            prediction=item[3],
            nominal=item[4],
            earliest_score=item[5],
            latest_score=item[6],
            best_timing_score=item[7],
            worst_timing_score=item[8],
        )
        for rank, item in enumerate(candidates[:limit], start=1)
    )
