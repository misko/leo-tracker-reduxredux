"""Causal CFO/rate/acceleration state with change-mode hysteresis.

The public point contract contains even-Qin CFO only.  Held-out odd-Qin CFO is
therefore structurally unable to update the state, select a history, trigger a
mode transition, or define a segment.  Source, epoch, alias, and continuity
remain caller-owned frozen hypotheses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class CausalCfoMode(StrEnum):
    """History mode used for the selected three-component state."""

    STABLE_500MS = "stable_500ms"
    CHANGE_125MS = "change_125ms"


class CausalCfoResetReason(StrEnum):
    """Why a point begins a new causal locklet."""

    NONE = "none"
    START = "start"
    CONTINUITY_SEGMENT_CHANGED = "continuity_segment_changed"
    SUPPORTED_POINT_GAP = "supported_point_gap"


class CausalCfoTransition(StrEnum):
    """Mode transition applied after observing the current even-Qin point."""

    NONE = "none"
    RESET = "reset"
    ENTER_CHANGE = "enter_change"
    LEAVE_CHANGE = "leave_change"


class LikelihoodGateMethod(StrEnum):
    """Per-frame profile method selected by the response-blind gate."""

    ORDINARY_CONTINUOUS_PROFILE = "ordinary_continuous_profile"
    SUMMED_FULL_LIKELIHOOD = "summed_full_likelihood"


@dataclass(frozen=True, slots=True)
class CausalCfoPoint:
    """One caller-qualified even-Qin CFO measurement."""

    frame_start_sample: int
    reference_time_s: float
    continuity_segment: int
    even_cfo_hz: float
    even_cfo_sigma_hz: float = 50.0

    def __post_init__(self) -> None:
        if not isinstance(self.frame_start_sample, (int, np.integer)):
            raise ValueError("frame_start_sample must be an integer")
        if not isinstance(self.continuity_segment, (int, np.integer)):
            raise ValueError("continuity_segment must be an integer")
        if self.frame_start_sample < 0 or self.continuity_segment < 0:
            raise ValueError("frame coordinates must be non-negative")
        values = (self.reference_time_s, self.even_cfo_hz, self.even_cfo_sigma_hz)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("CFO point values must be finite")
        if self.even_cfo_sigma_hz <= 0.0:
            raise ValueError("even_cfo_sigma_hz must be positive")


@dataclass(frozen=True, slots=True)
class CausalCfoAccelerationConfig:
    """Frozen robust-fit and hysteresis settings."""

    stable_history_s: float = 0.500
    change_history_s: float = 0.125
    baseline_histories_s: tuple[float, ...] = (0.020, 0.125, 0.500)
    maximum_supported_point_gap_s: float = 0.100
    minimum_history_coverage: float = 0.95
    minimum_frames: int = 12
    minimum_effective_frames: float = 8.0
    huber_tuning: float = 1.345
    maximum_iterations: int = 24
    prediction_convergence_hz: float = 1e-6
    standardized_scale_floor: float = 1.0
    maximum_normal_condition: float = 1e14
    acceleration_zero_prior_sigma_hz_s2: float = 1000.0
    enter_residual_hz: float = 125.0
    enter_rate_disagreement_hz_s: float = 350.0
    enter_consecutive_points: int = 8
    enter_minimum_span_s: float = 0.008
    leave_residual_hz: float = 75.0
    leave_rate_disagreement_hz_s: float = 175.0
    leave_minimum_calm_points: int = 32
    leave_minimum_calm_span_s: float = 0.250
    minimum_change_hold_s: float = 0.250

    def __post_init__(self) -> None:
        histories = tuple(float(value) for value in self.baseline_histories_s)
        positive = (
            self.stable_history_s,
            self.change_history_s,
            self.maximum_supported_point_gap_s,
            self.minimum_history_coverage,
            self.huber_tuning,
            self.prediction_convergence_hz,
            self.standardized_scale_floor,
            self.maximum_normal_condition,
            self.acceleration_zero_prior_sigma_hz_s2,
            self.enter_residual_hz,
            self.enter_rate_disagreement_hz_s,
            self.enter_minimum_span_s,
            self.leave_residual_hz,
            self.leave_rate_disagreement_hz_s,
            self.leave_minimum_calm_span_s,
            self.minimum_change_hold_s,
            *histories,
        )
        if any(not math.isfinite(float(value)) or float(value) <= 0.0 for value in positive):
            raise ValueError("causal CFO scales must be finite and positive")
        if self.stable_history_s <= self.change_history_s:
            raise ValueError("stable history must exceed change history")
        if histories != tuple(sorted(set(histories))):
            raise ValueError("baseline histories must be sorted and unique")
        if histories != (0.020, 0.125, 0.500):
            raise ValueError("baseline histories are frozen at 20/125/500 ms")
        if not 0.0 < self.minimum_history_coverage <= 1.0:
            raise ValueError("minimum history coverage must lie in (0, 1]")
        if self.minimum_frames < 3:
            raise ValueError("minimum_frames must be at least three")
        if not 2.0 < self.minimum_effective_frames <= self.minimum_frames:
            raise ValueError("minimum_effective_frames is outside its valid range")
        integers = (
            self.maximum_iterations,
            self.enter_consecutive_points,
            self.leave_minimum_calm_points,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integers
        ):
            raise ValueError("iteration and hysteresis counts must be positive integers")
        if self.leave_residual_hz >= self.enter_residual_hz:
            raise ValueError("leave residual threshold must be below enter threshold")
        if self.leave_rate_disagreement_hz_s >= self.enter_rate_disagreement_hz_s:
            raise ValueError("leave rate threshold must be below enter threshold")
        object.__setattr__(self, "baseline_histories_s", histories)


@dataclass(frozen=True, slots=True)
class CausalPolynomialFit:
    """One robust local polynomial fit centered at its newest point."""

    requested_history_s: float
    degree: int
    frame_count: int
    effective_frame_count: float
    span_s: float
    reference_time_s: float
    cfo_hz: float
    rate_hz_s: float
    acceleration_hz_s2: float
    weighted_rms_hz: float
    downweighted_fraction: float
    iteration_count: int
    converged: bool

    def predict_cfo(self, reference_time_s: float) -> float:
        """Predict CFO at one time without mutating the fit."""

        delta_s = float(reference_time_s) - self.reference_time_s
        return float(
            self.cfo_hz + self.rate_hz_s * delta_s + 0.5 * self.acceleration_hz_s2 * delta_s**2
        )


@dataclass(frozen=True, slots=True)
class CausalCfoAccelerationEstimate:
    """One causal output after accepting the current even-Qin point."""

    frame_start_sample: int
    reference_time_s: float
    continuity_segment: int
    reset_reason: CausalCfoResetReason
    mode: CausalCfoMode
    transition: CausalCfoTransition
    long_one_step_residual_hz: float | None
    short_minus_long_rate_hz_s: float | None
    selected_fit: CausalPolynomialFit | None
    stable_fit: CausalPolynomialFit | None
    change_fit: CausalPolynomialFit | None
    baseline_fits: tuple[CausalPolynomialFit, ...]


@dataclass(frozen=True, slots=True)
class CausalCfoAccelerationTrack:
    """Complete prefix-invariant trace for one ordered point sequence."""

    estimates: tuple[CausalCfoAccelerationEstimate, ...]
    training_source: str = "independent even-Qin frame CFO"
    covariance_claimed: bool = False
    carrier_phase_connected: bool = False


@dataclass(frozen=True, slots=True)
class LikelihoodGateFeatures:
    """Even-Qin-only features for one causal likelihood decision."""

    even_exact_minus_control_log_likelihood: float
    even_top_minus_second_log_likelihood: float

    def __post_init__(self) -> None:
        values = (
            self.even_exact_minus_control_log_likelihood,
            self.even_top_minus_second_log_likelihood,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("likelihood gate features must be finite")


@dataclass(frozen=True, slots=True)
class LikelihoodGateDecision:
    """Auditable weak/ambiguous decision for one frame."""

    method: LikelihoodGateMethod
    weak: bool
    ambiguous: bool


def choose_causal_likelihood_method(
    features: LikelihoodGateFeatures,
    *,
    weak_threshold: float = 4.605170185988092,
    ambiguity_threshold: float = 4.605170185988092,
) -> LikelihoodGateDecision:
    """Select summed likelihood only when current even-Qin evidence requires it."""

    if not math.isfinite(weak_threshold) or not math.isfinite(ambiguity_threshold):
        raise ValueError("likelihood thresholds must be finite")
    weak = features.even_exact_minus_control_log_likelihood < weak_threshold
    ambiguous = features.even_top_minus_second_log_likelihood < ambiguity_threshold
    method = (
        LikelihoodGateMethod.SUMMED_FULL_LIKELIHOOD
        if weak or ambiguous
        else LikelihoodGateMethod.ORDINARY_CONTINUOUS_PROFILE
    )
    return LikelihoodGateDecision(method=method, weak=weak, ambiguous=ambiguous)


def track_causal_cfo_acceleration(
    points: tuple[CausalCfoPoint, ...],
    *,
    config: CausalCfoAccelerationConfig | None = None,
) -> CausalCfoAccelerationTrack:
    """Fit the frozen state and baselines using ordered even-Qin points only."""

    settings = config or CausalCfoAccelerationConfig()
    _validate_order(points)
    history: list[CausalCfoPoint] = []
    estimates: list[CausalCfoAccelerationEstimate] = []
    previous_point: CausalCfoPoint | None = None
    previous_stable_fit: CausalPolynomialFit | None = None
    mode = CausalCfoMode.STABLE_500MS
    entered_change_at_s: float | None = None
    evidence_times: list[float] = []
    calm_times: list[float] = []

    for point in points:
        reset_reason = _reset_reason(previous_point, point, settings)
        if reset_reason is not CausalCfoResetReason.NONE:
            history = []
            previous_stable_fit = None
            mode = CausalCfoMode.STABLE_500MS
            entered_change_at_s = None
            evidence_times = []
            calm_times = []
        one_step_residual = (
            None
            if previous_stable_fit is None
            else point.even_cfo_hz - previous_stable_fit.predict_cfo(point.reference_time_s)
        )

        history.append(point)
        oldest_s = point.reference_time_s - settings.stable_history_s
        history = [item for item in history if item.reference_time_s >= oldest_s - 1e-12]
        stable_fit = _fit_history(
            history,
            requested_history_s=settings.stable_history_s,
            degree=2,
            config=settings,
        )
        change_fit = _fit_history(
            history,
            requested_history_s=settings.change_history_s,
            degree=2,
            config=settings,
        )
        baselines = tuple(
            fit
            for duration_s in settings.baseline_histories_s
            if (
                fit := _fit_history(
                    history,
                    requested_history_s=duration_s,
                    degree=1,
                    config=settings,
                )
            )
            is not None
        )
        rate_disagreement = (
            None
            if stable_fit is None or change_fit is None
            else change_fit.rate_hz_s - stable_fit.rate_hz_s
        )
        transition = (
            CausalCfoTransition.RESET
            if reset_reason is not CausalCfoResetReason.NONE
            else CausalCfoTransition.NONE
        )

        if mode is CausalCfoMode.STABLE_500MS:
            evidence = _change_evidence(one_step_residual, rate_disagreement, settings)
            if evidence:
                if evidence_times and point.reference_time_s - evidence_times[-1] > (
                    settings.maximum_supported_point_gap_s + 1e-12
                ):
                    evidence_times = []
                evidence_times.append(point.reference_time_s)
            else:
                evidence_times = []
            if (
                len(evidence_times) >= settings.enter_consecutive_points
                and evidence_times[-1] - evidence_times[0] >= settings.enter_minimum_span_s - 1e-12
            ):
                mode = CausalCfoMode.CHANGE_125MS
                entered_change_at_s = point.reference_time_s
                calm_times = []
                transition = CausalCfoTransition.ENTER_CHANGE
        else:
            calm = _recovery_evidence(one_step_residual, rate_disagreement, settings)
            if calm:
                if calm_times and point.reference_time_s - calm_times[-1] > (
                    settings.maximum_supported_point_gap_s + 1e-12
                ):
                    calm_times = []
                calm_times.append(point.reference_time_s)
            else:
                calm_times = []
            assert entered_change_at_s is not None
            if (
                point.reference_time_s - entered_change_at_s
                >= settings.minimum_change_hold_s - 1e-12
                and len(calm_times) >= settings.leave_minimum_calm_points
                and calm_times[-1] - calm_times[0] >= settings.leave_minimum_calm_span_s - 1e-12
            ):
                mode = CausalCfoMode.STABLE_500MS
                entered_change_at_s = None
                evidence_times = []
                transition = CausalCfoTransition.LEAVE_CHANGE

        selected = change_fit if mode is CausalCfoMode.CHANGE_125MS else stable_fit
        estimates.append(
            CausalCfoAccelerationEstimate(
                frame_start_sample=point.frame_start_sample,
                reference_time_s=point.reference_time_s,
                continuity_segment=point.continuity_segment,
                reset_reason=reset_reason,
                mode=mode,
                transition=transition,
                long_one_step_residual_hz=(
                    None if one_step_residual is None else float(one_step_residual)
                ),
                short_minus_long_rate_hz_s=(
                    None if rate_disagreement is None else float(rate_disagreement)
                ),
                selected_fit=selected,
                stable_fit=stable_fit,
                change_fit=change_fit,
                baseline_fits=baselines,
            )
        )
        previous_stable_fit = stable_fit
        previous_point = point

    return CausalCfoAccelerationTrack(estimates=tuple(estimates))


def _validate_order(points: tuple[CausalCfoPoint, ...]) -> None:
    for previous, current in zip(points, points[1:], strict=False):
        if current.reference_time_s <= previous.reference_time_s:
            raise ValueError("point reference times must be strictly increasing")
        if (
            current.continuity_segment == previous.continuity_segment
            and current.frame_start_sample <= previous.frame_start_sample
        ):
            raise ValueError("frame samples must increase within a continuity segment")


def _reset_reason(
    previous: CausalCfoPoint | None,
    current: CausalCfoPoint,
    config: CausalCfoAccelerationConfig,
) -> CausalCfoResetReason:
    if previous is None:
        return CausalCfoResetReason.START
    if previous.continuity_segment != current.continuity_segment:
        return CausalCfoResetReason.CONTINUITY_SEGMENT_CHANGED
    if current.reference_time_s - previous.reference_time_s > (
        config.maximum_supported_point_gap_s + 1e-12
    ):
        return CausalCfoResetReason.SUPPORTED_POINT_GAP
    return CausalCfoResetReason.NONE


def _change_evidence(
    residual_hz: float | None,
    rate_disagreement_hz_s: float | None,
    config: CausalCfoAccelerationConfig,
) -> bool:
    if residual_hz is None or rate_disagreement_hz_s is None:
        return False
    return bool(
        abs(residual_hz) >= config.enter_residual_hz
        and abs(rate_disagreement_hz_s) >= config.enter_rate_disagreement_hz_s
        and residual_hz * rate_disagreement_hz_s > 0.0
    )


def _recovery_evidence(
    residual_hz: float | None,
    rate_disagreement_hz_s: float | None,
    config: CausalCfoAccelerationConfig,
) -> bool:
    if residual_hz is None or rate_disagreement_hz_s is None:
        return False
    return bool(
        abs(residual_hz) <= config.leave_residual_hz
        and abs(rate_disagreement_hz_s) <= config.leave_rate_disagreement_hz_s
    )


def _fit_history(
    history: list[CausalCfoPoint],
    *,
    requested_history_s: float,
    degree: int,
    config: CausalCfoAccelerationConfig,
) -> CausalPolynomialFit | None:
    newest_s = history[-1].reference_time_s
    start_s = newest_s - requested_history_s
    points = tuple(item for item in history if item.reference_time_s >= start_s - 1e-12)
    if len(points) < config.minimum_frames:
        return None
    span_s = points[-1].reference_time_s - points[0].reference_time_s
    if span_s + 1e-12 < requested_history_s * config.minimum_history_coverage:
        return None
    return _fit_robust_polynomial(
        points,
        requested_history_s=requested_history_s,
        degree=degree,
        config=config,
    )


def _fit_robust_polynomial(
    points: tuple[CausalCfoPoint, ...],
    *,
    requested_history_s: float,
    degree: int,
    config: CausalCfoAccelerationConfig,
) -> CausalPolynomialFit | None:
    if degree not in (1, 2):
        raise ValueError("causal CFO polynomial degree must be one or two")
    reference_time_s = points[-1].reference_time_s
    relative_time = np.asarray(
        [point.reference_time_s - reference_time_s for point in points], dtype=float
    )
    values = np.asarray([point.even_cfo_hz for point in points], dtype=float)
    sigmas = np.asarray([point.even_cfo_sigma_hz for point in points], dtype=float)
    columns = [np.ones(len(points), dtype=float), relative_time]
    if degree == 2:
        columns.append(0.5 * relative_time**2)
    design = np.column_stack(columns)
    base_precision = 1.0 / sigmas**2
    ridge = np.zeros((degree + 1, degree + 1), dtype=float)
    if degree == 2:
        ridge[2, 2] = 1.0 / config.acceleration_zero_prior_sigma_hz_s2**2
    coefficients = _weighted_solve(design, values, base_precision, ridge, config)
    robust_weight = np.ones(len(points), dtype=float)
    converged = False
    iteration_count = 0

    for iteration in range(1, config.maximum_iterations + 1):
        iteration_count = iteration
        residual = values - design @ coefficients
        standardized = residual / sigmas
        centered = standardized - float(np.median(standardized))
        scale = max(
            config.standardized_scale_floor,
            1.4826 * float(np.median(np.abs(centered))),
        )
        magnitude = np.abs(standardized) / scale
        robust_weight = np.ones_like(magnitude)
        tail = magnitude > config.huber_tuning
        robust_weight[tail] = config.huber_tuning / magnitude[tail]
        updated = _weighted_solve(
            design,
            values,
            base_precision * robust_weight,
            ridge,
            config,
        )
        prediction_change_hz = float(np.max(np.abs(design @ (updated - coefficients))))
        coefficients = updated
        if prediction_change_hz <= config.prediction_convergence_hz:
            converged = True
            break

    residual = values - design @ coefficients
    standardized = residual / sigmas
    centered = standardized - float(np.median(standardized))
    scale = max(
        config.standardized_scale_floor,
        1.4826 * float(np.median(np.abs(centered))),
    )
    magnitude = np.abs(standardized) / scale
    robust_weight = np.ones_like(magnitude)
    tail = magnitude > config.huber_tuning
    robust_weight[tail] = config.huber_tuning / magnitude[tail]
    effective_count = float(np.sum(robust_weight) ** 2 / np.sum(robust_weight**2))
    if effective_count + 1e-12 < config.minimum_effective_frames:
        return None
    weighted_rms_hz = float(
        math.sqrt(float(np.sum(robust_weight * residual**2) / np.sum(robust_weight)))
    )
    acceleration = float(coefficients[2]) if degree == 2 else 0.0
    return CausalPolynomialFit(
        requested_history_s=requested_history_s,
        degree=degree,
        frame_count=len(points),
        effective_frame_count=effective_count,
        span_s=float(relative_time[-1] - relative_time[0]),
        reference_time_s=reference_time_s,
        cfo_hz=float(coefficients[0]),
        rate_hz_s=float(coefficients[1]),
        acceleration_hz_s2=acceleration,
        weighted_rms_hz=weighted_rms_hz,
        downweighted_fraction=float(np.mean(robust_weight < 0.999)),
        iteration_count=iteration_count,
        converged=converged,
    )


def _weighted_solve(
    design: np.ndarray,
    values: np.ndarray,
    precision: np.ndarray,
    ridge: np.ndarray,
    config: CausalCfoAccelerationConfig,
) -> np.ndarray:
    normal = design.T @ (precision[:, None] * design) + ridge
    if not np.all(np.isfinite(normal)) or np.linalg.cond(normal) > config.maximum_normal_condition:
        raise ValueError("causal CFO history has ill-conditioned time geometry")
    return np.linalg.solve(normal, design.T @ (precision * values))
