"""Causal, reset-safe smoothing of independent even-Qin frame CFO points.

The tracker fits robust frequency lines over a small set of trailing histories
and selects the longest history that remains statistically compatible with
every shorter fit.  It deliberately connects frequency only: callers retain
authority for frame epoch, CFO alias, source identity, and device-counter
continuity.  A changed continuity segment or an excessive time gap starts a
new locklet; neither carrier phase nor receiver-relative timing is an input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np


class AdaptiveFrameCfoResetReason(StrEnum):
    """Why the causal history was empty before accepting this frame."""

    NONE = "none"
    START = "start"
    CONTINUITY_SEGMENT_CHANGED = "continuity_segment_changed"
    TIME_GAP = "time_gap"


class AdaptiveFrameCfoSelectionReason(StrEnum):
    """Why a particular trailing history was selected."""

    WARMUP = "warmup"
    LONGEST_AVAILABLE = "longest_available"
    LONGER_HISTORY_INCONSISTENT = "longer_history_inconsistent"


class AdaptiveFrameCfoHistoryChangeReason(StrEnum):
    """How the selected history changed relative to the previous estimate."""

    RESET = "reset"
    WARMUP = "warmup"
    INITIALIZED = "initialized"
    EXPANDED = "expanded"
    SHORTENED_BY_CHANGE = "shortened_by_change"
    LONGER_HISTORY_REJECTED = "longer_history_rejected"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class AdaptiveFrameCfoPoint:
    """One acquisition-bound, even-Qin frame-frequency measurement.

    ``even_cfo_sigma_hz`` is a conditional one-sigma measurement scale and
    ``even_weight`` is an optional dimensionless quality weight.  Both affect
    the fit.  No held-out/odd-Qin response is accepted by this API, preventing
    validation data from influencing history selection.
    """

    frame_start_sample: int
    reference_time_s: float
    continuity_segment: int
    even_cfo_hz: float
    even_cfo_sigma_hz: float
    even_weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.frame_start_sample, (int, np.integer)):
            raise ValueError("frame start must be an integer sample")
        if not isinstance(self.continuity_segment, (int, np.integer)):
            raise ValueError("continuity segment must be an integer")
        if self.frame_start_sample < 0 or self.continuity_segment < 0:
            raise ValueError("frame coordinates must be non-negative")
        finite = (
            self.reference_time_s,
            self.even_cfo_hz,
            self.even_cfo_sigma_hz,
            self.even_weight,
        )
        if any(not math.isfinite(float(value)) for value in finite):
            raise ValueError("frame CFO inputs must be finite")
        if self.even_cfo_sigma_hz <= 0.0 or self.even_weight <= 0.0:
            raise ValueError("frame CFO uncertainty and weight must be positive")


@dataclass(frozen=True, slots=True)
class AdaptiveFrameCfoConfig:
    """Frozen gates for causal multi-history robust line fits."""

    history_durations_s: tuple[float, ...] = (0.075, 0.125, 0.250, 0.500)
    minimum_history_coverage: float = 0.95
    minimum_frames: int = 12
    minimum_effective_frames: float = 8.0
    maximum_gap_s: float = 0.012
    huber_tuning: float = 1.345
    maximum_iterations: int = 24
    prediction_convergence_hz: float = 1e-6
    consistency_chi_square: float = 9.210340371976184
    standardized_scale_floor: float = 1.0
    maximum_normal_condition: float = 1e14

    def __post_init__(self) -> None:
        histories = tuple(float(value) for value in self.history_durations_s)
        if (
            not histories
            or any(not math.isfinite(value) or value <= 0.0 for value in histories)
            or any(
                current <= previous
                for previous, current in zip(histories, histories[1:], strict=False)
            )
        ):
            raise ValueError("history durations must be finite, positive, and strictly increasing")
        if not 0.0 < self.minimum_history_coverage <= 1.0:
            raise ValueError("minimum history coverage must lie in (0, 1]")
        if self.minimum_frames < 3:
            raise ValueError("adaptive CFO fits require at least three frames")
        if not 2.0 < self.minimum_effective_frames <= self.minimum_frames:
            raise ValueError("minimum effective frames must lie in (2, minimum_frames]")
        positive = (
            self.maximum_gap_s,
            self.huber_tuning,
            self.prediction_convergence_hz,
            self.consistency_chi_square,
            self.standardized_scale_floor,
            self.maximum_normal_condition,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("adaptive CFO gates must be finite and positive")
        if self.maximum_iterations < 1:
            raise ValueError("maximum iterations must be positive")
        object.__setattr__(self, "history_durations_s", histories)


@dataclass(frozen=True, slots=True)
class AdaptiveFrameCfoWindowFit:
    """Robust line and conditional covariance for one trailing history."""

    requested_history_s: float
    frame_count: int
    effective_frame_count: float
    span_s: float
    reference_time_s: float
    cfo_hz: float
    rate_hz_s: float
    cfo_sigma_hz: float
    rate_sigma_hz_s: float
    cfo_rate_covariance_hz2_s: float
    weighted_rms_hz: float
    robust_reduced_chi_square: float
    standardized_residual_scale: float
    downweighted_fraction: float
    iteration_count: int
    converged: bool
    consistency_chi_square_to_shorter: float | None = None
    consistent_with_all_shorter: bool = True


@dataclass(frozen=True, slots=True)
class AdaptiveFrameCfoEstimate:
    """One causal output at the time of the newest input frame."""

    frame_start_sample: int
    reference_time_s: float
    continuity_segment: int
    reset_reason: AdaptiveFrameCfoResetReason
    selection_reason: AdaptiveFrameCfoSelectionReason
    history_change_reason: AdaptiveFrameCfoHistoryChangeReason
    selected_history_s: float | None
    cfo_hz: float | None
    rate_hz_s: float | None
    cfo_sigma_hz: float | None
    rate_sigma_hz_s: float | None
    cfo_rate_covariance_hz2_s: float | None
    candidate_fits: tuple[AdaptiveFrameCfoWindowFit, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveFrameCfoTrack:
    """Complete causal trace and scope disclosure for one input sequence."""

    estimates: tuple[AdaptiveFrameCfoEstimate, ...]
    history_durations_s: tuple[float, ...]
    training_source: str = "independent even-Qin frame CFO"
    carrier_phase_connected: bool = False
    receiver_relative_timing_used_for_doppler: bool = False


def track_adaptive_frame_cfo(
    points: tuple[AdaptiveFrameCfoPoint, ...],
    *,
    config: AdaptiveFrameCfoConfig | None = None,
) -> AdaptiveFrameCfoTrack:
    """Return prefix-invariant adaptive estimates in input time order.

    Each output uses only measurements up to and including its own frame.  The
    input must already be ordered; sorting here would hide non-causal caller
    errors.  Continuity segment labels are authoritative device-counter
    partitions, while ``maximum_gap_s`` is an additional defensive reset.
    """

    settings = config or AdaptiveFrameCfoConfig()
    _validate_order(points)
    estimates: list[AdaptiveFrameCfoEstimate] = []
    history: list[AdaptiveFrameCfoPoint] = []
    previous_point: AdaptiveFrameCfoPoint | None = None
    previous_selected_history_s: float | None = None

    for point in points:
        reset_reason = _reset_reason(previous_point, point, settings)
        if reset_reason is not AdaptiveFrameCfoResetReason.NONE:
            history = []
            previous_selected_history_s = None
        history.append(point)
        oldest_allowed = point.reference_time_s - settings.history_durations_s[-1]
        history = [item for item in history if item.reference_time_s >= oldest_allowed - 1e-12]

        candidates = _candidate_fits(tuple(history), settings)
        annotated = _annotate_consistency(candidates, settings)
        selected = _select_longest_consistent(annotated)
        selection_reason = _selection_reason(annotated, selected)
        change_reason = _history_change_reason(
            reset_reason,
            previous_selected_history_s,
            selected,
            selection_reason,
        )
        estimates.append(
            AdaptiveFrameCfoEstimate(
                frame_start_sample=point.frame_start_sample,
                reference_time_s=point.reference_time_s,
                continuity_segment=point.continuity_segment,
                reset_reason=reset_reason,
                selection_reason=selection_reason,
                history_change_reason=change_reason,
                selected_history_s=(selected.requested_history_s if selected else None),
                cfo_hz=(selected.cfo_hz if selected else None),
                rate_hz_s=(selected.rate_hz_s if selected else None),
                cfo_sigma_hz=(selected.cfo_sigma_hz if selected else None),
                rate_sigma_hz_s=(selected.rate_sigma_hz_s if selected else None),
                cfo_rate_covariance_hz2_s=(
                    selected.cfo_rate_covariance_hz2_s if selected else None
                ),
                candidate_fits=annotated,
            )
        )
        previous_selected_history_s = selected.requested_history_s if selected else None
        previous_point = point

    return AdaptiveFrameCfoTrack(
        estimates=tuple(estimates),
        history_durations_s=settings.history_durations_s,
    )


def _validate_order(points: tuple[AdaptiveFrameCfoPoint, ...]) -> None:
    for previous, current in zip(points, points[1:], strict=False):
        if current.reference_time_s <= previous.reference_time_s:
            raise ValueError("frame reference times must be strictly increasing")
        if (
            current.continuity_segment == previous.continuity_segment
            and current.frame_start_sample <= previous.frame_start_sample
        ):
            raise ValueError("frame samples must increase within a continuity segment")


def _reset_reason(
    previous: AdaptiveFrameCfoPoint | None,
    current: AdaptiveFrameCfoPoint,
    config: AdaptiveFrameCfoConfig,
) -> AdaptiveFrameCfoResetReason:
    if previous is None:
        return AdaptiveFrameCfoResetReason.START
    if current.continuity_segment != previous.continuity_segment:
        return AdaptiveFrameCfoResetReason.CONTINUITY_SEGMENT_CHANGED
    if current.reference_time_s - previous.reference_time_s > config.maximum_gap_s:
        return AdaptiveFrameCfoResetReason.TIME_GAP
    return AdaptiveFrameCfoResetReason.NONE


def _candidate_fits(
    history: tuple[AdaptiveFrameCfoPoint, ...],
    config: AdaptiveFrameCfoConfig,
) -> tuple[AdaptiveFrameCfoWindowFit, ...]:
    newest_time_s = history[-1].reference_time_s
    output = []
    for duration_s in config.history_durations_s:
        start_s = newest_time_s - duration_s
        window = tuple(point for point in history if point.reference_time_s >= start_s - 1e-12)
        span_s = window[-1].reference_time_s - window[0].reference_time_s
        if len(window) < config.minimum_frames:
            continue
        if span_s + 1e-12 < duration_s * config.minimum_history_coverage:
            continue
        fit = _fit_robust_window(window, duration_s, config)
        if fit.effective_frame_count + 1e-12 < config.minimum_effective_frames:
            continue
        output.append(fit)
    return tuple(output)


def _fit_robust_window(
    points: tuple[AdaptiveFrameCfoPoint, ...],
    requested_history_s: float,
    config: AdaptiveFrameCfoConfig,
) -> AdaptiveFrameCfoWindowFit:
    reference_time_s = points[-1].reference_time_s
    relative_time = np.asarray(
        [point.reference_time_s - reference_time_s for point in points], dtype=float
    )
    values = np.asarray([point.even_cfo_hz for point in points], dtype=float)
    sigmas = np.asarray([point.even_cfo_sigma_hz for point in points], dtype=float)
    quality = np.asarray([point.even_weight for point in points], dtype=float)
    design = np.column_stack((np.ones(len(points), dtype=float), relative_time))
    base_precision = quality / sigmas**2
    coefficients = _weighted_solve(design, values, base_precision, config)
    robust_weight = np.ones(len(points), dtype=float)
    converged = False
    iteration_count = 0
    standardized_scale = config.standardized_scale_floor

    for iteration_number in range(1, config.maximum_iterations + 1):
        iteration_count = iteration_number
        residual = values - design @ coefficients
        standardized = residual / sigmas
        centered = standardized - float(np.median(standardized))
        standardized_scale = max(
            config.standardized_scale_floor,
            1.4826 * float(np.median(np.abs(centered))),
        )
        magnitude = np.abs(standardized) / standardized_scale
        robust_weight = np.ones_like(magnitude)
        tail = magnitude > config.huber_tuning
        robust_weight[tail] = config.huber_tuning / magnitude[tail]
        combined_precision = base_precision * robust_weight
        updated = _weighted_solve(design, values, combined_precision, config)
        prediction_change = float(np.max(np.abs(design @ (updated - coefficients))))
        coefficients = updated
        if prediction_change <= config.prediction_convergence_hz:
            converged = True
            break

    residual = values - design @ coefficients
    standardized = residual / sigmas
    centered = standardized - float(np.median(standardized))
    standardized_scale = max(
        config.standardized_scale_floor,
        1.4826 * float(np.median(np.abs(centered))),
    )
    magnitude = np.abs(standardized) / standardized_scale
    robust_weight = np.ones_like(magnitude)
    tail = magnitude > config.huber_tuning
    robust_weight[tail] = config.huber_tuning / magnitude[tail]
    combined_precision = base_precision * robust_weight
    effective_count = _effective_count(quality * robust_weight)
    degrees_of_freedom = max(float(np.sum(quality * robust_weight)) - 2.0, 1.0)
    reduced_chi_square = float(
        np.sum(quality * robust_weight * standardized**2) / degrees_of_freedom
    )
    covariance = np.linalg.inv(design.T @ (combined_precision[:, None] * design))
    covariance *= max(1.0, reduced_chi_square)
    rms_weights = quality * robust_weight
    weighted_rms = float(math.sqrt(float(np.sum(rms_weights * residual**2) / np.sum(rms_weights))))

    return AdaptiveFrameCfoWindowFit(
        requested_history_s=requested_history_s,
        frame_count=len(points),
        effective_frame_count=effective_count,
        span_s=float(relative_time[-1] - relative_time[0]),
        reference_time_s=reference_time_s,
        cfo_hz=float(coefficients[0]),
        rate_hz_s=float(coefficients[1]),
        cfo_sigma_hz=float(math.sqrt(max(float(covariance[0, 0]), 0.0))),
        rate_sigma_hz_s=float(math.sqrt(max(float(covariance[1, 1]), 0.0))),
        cfo_rate_covariance_hz2_s=float(covariance[0, 1]),
        weighted_rms_hz=weighted_rms,
        robust_reduced_chi_square=reduced_chi_square,
        standardized_residual_scale=standardized_scale,
        downweighted_fraction=float(np.mean(robust_weight < 0.999)),
        iteration_count=iteration_count,
        converged=converged,
    )


def _weighted_solve(
    design: np.ndarray,
    values: np.ndarray,
    precision: np.ndarray,
    config: AdaptiveFrameCfoConfig,
) -> np.ndarray:
    normal = design.T @ (precision[:, None] * design)
    if not np.all(np.isfinite(normal)) or np.linalg.cond(normal) > config.maximum_normal_condition:
        raise ValueError("adaptive CFO window has an ill-conditioned time geometry")
    return np.linalg.solve(normal, design.T @ (precision * values))


def _effective_count(weights: np.ndarray) -> float:
    return float(np.sum(weights) ** 2 / np.sum(weights**2))


def _annotate_consistency(
    candidates: tuple[AdaptiveFrameCfoWindowFit, ...],
    config: AdaptiveFrameCfoConfig,
) -> tuple[AdaptiveFrameCfoWindowFit, ...]:
    output: list[AdaptiveFrameCfoWindowFit] = []
    progression_open = True
    for index, candidate in enumerate(candidates):
        if index == 0:
            output.append(candidate)
            continue
        scores = [_parameter_disagreement(candidate, shorter) for shorter in output]
        score = max(scores)
        consistent = progression_open and score <= config.consistency_chi_square
        output.append(
            replace(
                candidate,
                consistency_chi_square_to_shorter=score,
                consistent_with_all_shorter=consistent,
            )
        )
        progression_open = consistent
    return tuple(output)


def _parameter_disagreement(
    first: AdaptiveFrameCfoWindowFit,
    second: AdaptiveFrameCfoWindowFit,
) -> float:
    delta = np.asarray((first.cfo_hz - second.cfo_hz, first.rate_hz_s - second.rate_hz_s))
    covariance = _covariance(first) + _covariance(second)
    if not np.all(np.isfinite(covariance)) or np.linalg.cond(covariance) > 1e16:
        return math.inf
    return float(delta @ np.linalg.solve(covariance, delta))


def _covariance(fit: AdaptiveFrameCfoWindowFit) -> np.ndarray:
    return np.asarray(
        (
            (fit.cfo_sigma_hz**2, fit.cfo_rate_covariance_hz2_s),
            (fit.cfo_rate_covariance_hz2_s, fit.rate_sigma_hz_s**2),
        ),
        dtype=float,
    )


def _select_longest_consistent(
    candidates: tuple[AdaptiveFrameCfoWindowFit, ...],
) -> AdaptiveFrameCfoWindowFit | None:
    selected = None
    for candidate in candidates:
        if candidate.consistent_with_all_shorter:
            selected = candidate
    return selected


def _selection_reason(
    candidates: tuple[AdaptiveFrameCfoWindowFit, ...],
    selected: AdaptiveFrameCfoWindowFit | None,
) -> AdaptiveFrameCfoSelectionReason:
    if selected is None:
        return AdaptiveFrameCfoSelectionReason.WARMUP
    if selected is candidates[-1]:
        return AdaptiveFrameCfoSelectionReason.LONGEST_AVAILABLE
    return AdaptiveFrameCfoSelectionReason.LONGER_HISTORY_INCONSISTENT


def _history_change_reason(
    reset_reason: AdaptiveFrameCfoResetReason,
    previous_history_s: float | None,
    selected: AdaptiveFrameCfoWindowFit | None,
    selection_reason: AdaptiveFrameCfoSelectionReason,
) -> AdaptiveFrameCfoHistoryChangeReason:
    if reset_reason is not AdaptiveFrameCfoResetReason.NONE:
        return AdaptiveFrameCfoHistoryChangeReason.RESET
    if selected is None:
        return AdaptiveFrameCfoHistoryChangeReason.WARMUP
    if previous_history_s is None:
        return AdaptiveFrameCfoHistoryChangeReason.INITIALIZED
    if selected.requested_history_s > previous_history_s:
        return AdaptiveFrameCfoHistoryChangeReason.EXPANDED
    if selected.requested_history_s < previous_history_s:
        return AdaptiveFrameCfoHistoryChangeReason.SHORTENED_BY_CHANGE
    if selection_reason is AdaptiveFrameCfoSelectionReason.LONGER_HISTORY_INCONSISTENT:
        return AdaptiveFrameCfoHistoryChangeReason.LONGER_HISTORY_REJECTED
    return AdaptiveFrameCfoHistoryChangeReason.UNCHANGED
