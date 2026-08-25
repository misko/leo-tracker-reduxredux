"""Parity-split downstream CFO-rate comparison for frozen V3/V4 anchors.

The functions in this module accept no acquisition likelihoods and no raw IQ.
They operate only on an already bound frame ordinal plus even-training and
odd-response CFO measurements.  Frame membership and every rate coefficient
are functions of even Qin alone; odd Qin is attached only after prediction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from leo.analysis.robust_linear import fit_huber_linear_irls


@dataclass(frozen=True, slots=True)
class V3V4SplitFrame:
    """One acquired-lattice frame with an even-only admission flag."""

    frame_ordinal: int
    frame_start_sample: int
    reference_time_s: float
    even_cfo_hz: float
    odd_cfo_hz: float
    even_frequency_uncertainty_hz: float
    even_exact_coherence: float
    even_control_coherence: float
    training_supported: bool
    even_search_boundary: bool
    odd_search_boundary: bool

    def __post_init__(self) -> None:
        integers = (self.frame_ordinal, self.frame_start_sample)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
            raise ValueError("frame ordinals and starts must be integers")
        if self.frame_ordinal < 0 or self.frame_start_sample < 0:
            raise ValueError("frame ordinals and starts must be nonnegative")
        numeric = (
            self.reference_time_s,
            self.even_cfo_hz,
            self.odd_cfo_hz,
            self.even_frequency_uncertainty_hz,
            self.even_exact_coherence,
            self.even_control_coherence,
        )
        if any(not math.isfinite(float(value)) for value in numeric):
            raise ValueError("split-frame CFO evidence must be finite")
        if self.even_frequency_uncertainty_hz <= 0.0:
            raise ValueError("even CFO uncertainty must be positive")


@dataclass(frozen=True, slots=True)
class V3V4ForecastConfig:
    """Frozen causal-history and robust-fit settings."""

    sample_rate_hz: int = 2_500_000
    frame_rate_hz: int = 750
    forecast_horizon_ms: int = 125
    target_offsets_ms: tuple[int, ...] = tuple(range(625, 1_000, 25))
    history_durations_ms: tuple[int, ...] = (20, 500)
    minimum_frames: tuple[int, ...] = (10, 300)
    minimum_spans_ms: tuple[int, ...] = (16, 450)
    huber_tuning: float = 1.345
    scale_floor_hz: float = 25.0
    maximum_iterations: int = 32
    prediction_tolerance_hz: float = 1e-6

    def __post_init__(self) -> None:
        if self.sample_rate_hz != 2_500_000 or self.frame_rate_hz != 750:
            raise ValueError("V3/V4 benchmark requires the frozen 2.5 Msps / 750 Hz lattice")
        if self.forecast_horizon_ms != 125:
            raise ValueError("V3/V4 forecast horizon is frozen at 125 ms")
        if self.target_offsets_ms != tuple(range(625, 1_000, 25)):
            raise ValueError("V3/V4 target offsets changed")
        if self.history_durations_ms != (20, 500):
            raise ValueError("V3/V4 histories are frozen at 20 and 500 ms")
        if self.minimum_frames != (10, 300) or self.minimum_spans_ms != (16, 450):
            raise ValueError("V3/V4 history support gates changed")
        positive = (
            self.huber_tuning,
            self.scale_floor_hz,
            self.prediction_tolerance_hz,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("robust-fit settings must be finite and positive")
        if self.maximum_iterations < 1:
            raise ValueError("maximum iterations must be positive")


@dataclass(frozen=True, slots=True)
class V3V4RatePrediction:
    """One past-even line prediction with a future-odd response."""

    method: str
    population: str
    anchor_key: str
    target_offset_ms: int
    target_ordinal: int
    target_frame_start_sample: int
    target_reference_time_s: float
    history_ms: int
    training_frame_count: int
    training_first_ordinal: int
    training_last_ordinal: int
    training_span_ms: float
    fit_reference_time_s: float
    fitted_cfo_hz: float
    fitted_rate_hz_s: float
    fit_rms_hz: float
    predicted_cfo_hz: float
    target_odd_cfo_hz: float
    odd_residual_hz: float


def method_forecasts(
    points: tuple[V3V4SplitFrame, ...],
    *,
    method: str,
    population: str,
    anchor_key: str,
    config: V3V4ForecastConfig | None = None,
) -> tuple[V3V4RatePrediction, ...]:
    """Fit one method on its own even-only mask and attach odd responses."""

    settings = config or V3V4ForecastConfig()
    by_ordinal = _validated_points(points)
    output: list[V3V4RatePrediction] = []
    for target_offset_ms in settings.target_offsets_ms:
        target_ordinal = _milliseconds_to_frames(target_offset_ms, settings.frame_rate_hz)
        target = by_ordinal.get(target_ordinal)
        if target is None or not target.training_supported:
            continue
        for history_ms, minimum_count, minimum_span_ms in zip(
            settings.history_durations_ms,
            settings.minimum_frames,
            settings.minimum_spans_ms,
            strict=True,
        ):
            training = _training_points(
                by_ordinal,
                target_ordinal=target_ordinal,
                history_ms=history_ms,
                settings=settings,
            )
            prediction = _fit_prediction(
                training,
                target,
                method=method,
                population=population,
                anchor_key=anchor_key,
                target_offset_ms=target_offset_ms,
                history_ms=history_ms,
                minimum_count=minimum_count,
                minimum_span_ms=minimum_span_ms,
                settings=settings,
            )
            if prediction is not None:
                output.append(prediction)
    return tuple(output)


def common_mode_forecasts(
    left: tuple[V3V4SplitFrame, ...],
    right: tuple[V3V4SplitFrame, ...],
    *,
    left_method: str,
    right_method: str,
    anchor_key: str,
    config: V3V4ForecastConfig | None = None,
) -> tuple[V3V4RatePrediction, ...]:
    """Fit two methods on the exact same even-supported frame ordinals.

    The paired mask is determined before either odd CFO is read by this
    function.  The returned predictions have the same target/history identities
    and training ordinals by construction.
    """

    settings = config or V3V4ForecastConfig()
    left_by_ordinal = _validated_points(left)
    right_by_ordinal = _validated_points(right)
    output: list[V3V4RatePrediction] = []
    for target_offset_ms in settings.target_offsets_ms:
        target_ordinal = _milliseconds_to_frames(target_offset_ms, settings.frame_rate_hz)
        left_target = left_by_ordinal.get(target_ordinal)
        right_target = right_by_ordinal.get(target_ordinal)
        if (
            left_target is None
            or right_target is None
            or not left_target.training_supported
            or not right_target.training_supported
        ):
            continue
        for history_ms, minimum_count, minimum_span_ms in zip(
            settings.history_durations_ms,
            settings.minimum_frames,
            settings.minimum_spans_ms,
            strict=True,
        ):
            left_training = _training_points(
                left_by_ordinal,
                target_ordinal=target_ordinal,
                history_ms=history_ms,
                settings=settings,
            )
            right_training = _training_points(
                right_by_ordinal,
                target_ordinal=target_ordinal,
                history_ms=history_ms,
                settings=settings,
            )
            common_ordinals = sorted(
                {item.frame_ordinal for item in left_training}
                & {item.frame_ordinal for item in right_training}
            )
            left_common = tuple(left_by_ordinal[index] for index in common_ordinals)
            right_common = tuple(right_by_ordinal[index] for index in common_ordinals)
            left_prediction = _fit_prediction(
                left_common,
                left_target,
                method=left_method,
                population="both_method_common_mode",
                anchor_key=anchor_key,
                target_offset_ms=target_offset_ms,
                history_ms=history_ms,
                minimum_count=minimum_count,
                minimum_span_ms=minimum_span_ms,
                settings=settings,
            )
            right_prediction = _fit_prediction(
                right_common,
                right_target,
                method=right_method,
                population="both_method_common_mode",
                anchor_key=anchor_key,
                target_offset_ms=target_offset_ms,
                history_ms=history_ms,
                minimum_count=minimum_count,
                minimum_span_ms=minimum_span_ms,
                settings=settings,
            )
            if left_prediction is None or right_prediction is None:
                continue
            if (
                left_prediction.training_frame_count != right_prediction.training_frame_count
                or left_prediction.training_first_ordinal != right_prediction.training_first_ordinal
                or left_prediction.training_last_ordinal != right_prediction.training_last_ordinal
            ):
                raise RuntimeError("common-mode forecasts lost their identical ordinal mask")
            output.extend((left_prediction, right_prediction))
    return tuple(output)


def _training_points(
    by_ordinal: dict[int, V3V4SplitFrame],
    *,
    target_ordinal: int,
    history_ms: int,
    settings: V3V4ForecastConfig,
) -> tuple[V3V4SplitFrame, ...]:
    horizon_frames = _milliseconds_to_frames(settings.forecast_horizon_ms, settings.frame_rate_hz)
    history_frames = _milliseconds_to_frames(history_ms, settings.frame_rate_hz)
    cutoff = target_ordinal - horizon_frames
    first = cutoff - history_frames
    return tuple(
        point
        for ordinal in range(first, cutoff + 1)
        if (point := by_ordinal.get(ordinal)) is not None and point.training_supported
    )


def _fit_prediction(
    training: tuple[V3V4SplitFrame, ...],
    target: V3V4SplitFrame,
    *,
    method: str,
    population: str,
    anchor_key: str,
    target_offset_ms: int,
    history_ms: int,
    minimum_count: int,
    minimum_span_ms: int,
    settings: V3V4ForecastConfig,
) -> V3V4RatePrediction | None:
    if len(training) < minimum_count:
        return None
    times = np.asarray([item.reference_time_s for item in training], dtype=float)
    values = np.asarray([item.even_cfo_hz for item in training], dtype=float)
    span_ms = float((times[-1] - times[0]) * 1_000.0)
    if span_ms + 1e-9 < minimum_span_ms:
        return None
    reference_time_s = float(times[-1])
    initial = np.polyfit(times - reference_time_s, values, 1)
    fit = fit_huber_linear_irls(
        times,
        values,
        initial_coefficients_hz=(float(initial[0]), float(initial[1])),
        reference_time_s=reference_time_s,
        tuning_constant=settings.huber_tuning,
        scale_floor_hz=settings.scale_floor_hz,
        maximum_iterations=settings.maximum_iterations,
        prediction_tolerance_hz=settings.prediction_tolerance_hz,
    )
    prediction = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (
        target.reference_time_s - fit.reference_time_s
    )
    return V3V4RatePrediction(
        method=method,
        population=population,
        anchor_key=anchor_key,
        target_offset_ms=target_offset_ms,
        target_ordinal=target.frame_ordinal,
        target_frame_start_sample=target.frame_start_sample,
        target_reference_time_s=target.reference_time_s,
        history_ms=history_ms,
        training_frame_count=len(training),
        training_first_ordinal=training[0].frame_ordinal,
        training_last_ordinal=training[-1].frame_ordinal,
        training_span_ms=span_ms,
        fit_reference_time_s=fit.reference_time_s,
        fitted_cfo_hz=fit.intercept_at_reference_hz,
        fitted_rate_hz_s=fit.slope_hz_per_s,
        fit_rms_hz=fit.residual_rms_hz,
        predicted_cfo_hz=float(prediction),
        target_odd_cfo_hz=target.odd_cfo_hz,
        odd_residual_hz=float(target.odd_cfo_hz - prediction),
    )


def _validated_points(
    points: tuple[V3V4SplitFrame, ...],
) -> dict[int, V3V4SplitFrame]:
    if not points:
        return {}
    by_ordinal = {item.frame_ordinal: item for item in points}
    if len(by_ordinal) != len(points):
        raise ValueError("split-frame ordinals must be unique")
    ordered = tuple(sorted(points, key=lambda item: item.frame_ordinal))
    if any(
        current.frame_start_sample <= previous.frame_start_sample
        or current.reference_time_s <= previous.reference_time_s
        for previous, current in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("split-frame coordinates must increase with ordinal")
    return by_ordinal


def _milliseconds_to_frames(milliseconds: int, frame_rate_hz: int) -> int:
    numerator = milliseconds * frame_rate_hz
    return (numerator + 500) // 1_000
