"""Deterministic research prototypes for piecewise known-pilot tracking.

This module intentionally has no dependency on recordings, Starlink templates,
pipeline products, or persisted contracts.  It accepts already-extracted frame
observations and provides three small building blocks for offline experiments:

* robust, non-overlapping block CFO estimates followed by a calibrated
  polynomial fit;
* a causal acquire/track/coast/reacquire state machine that never carries phase
  continuity across a declared change point; and
* a fair radio-only polynomial comparison in which every degree is scored on
  exactly the same blocks.

The covariance returned by the blockwise fitter is deliberately empirical.  A
weighted least-squares covariance is enlarged by the robust reduced chi-square
computed from the effective (Huber-weighted) number of blocks.  It is therefore
not the unrealistically small frame-by-frame covariance produced by treating
overlapping or correlated frame measurements as independent.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class PilotFrameObservation:
    """One generic frame observation, independent of any IQ implementation."""

    time_s: float
    cfo_hz: float
    cfo_sigma_hz: float
    support: float
    phase_modulo_pi_rad: float | None = None
    phase_sigma_rad: float | None = None

    def __post_init__(self) -> None:
        values = (self.time_s, self.cfo_hz, self.cfo_sigma_hz, self.support)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("frame time, CFO, uncertainty, and support must be finite")
        if self.cfo_sigma_hz <= 0.0:
            raise ValueError("frame CFO uncertainty must be positive")
        if not 0.0 <= self.support <= 1.0:
            raise ValueError("frame support must lie in [0, 1]")
        if self.phase_modulo_pi_rad is None:
            if self.phase_sigma_rad is not None:
                raise ValueError("phase uncertainty requires a phase observation")
        else:
            if not math.isfinite(self.phase_modulo_pi_rad):
                raise ValueError("frame phase must be finite")
            if self.phase_sigma_rad is None or not math.isfinite(self.phase_sigma_rad):
                raise ValueError("a finite phase uncertainty is required with phase")
            if self.phase_sigma_rad <= 0.0:
                raise ValueError("frame phase uncertainty must be positive")


@dataclass(frozen=True, slots=True)
class RobustBlockConfig:
    """Controls for independent block formation and robust regression."""

    block_duration_s: float = 0.075
    minimum_observations_per_block: int = 6
    minimum_support: float = 0.10
    uncertainty_floor_hz: float = 10.0
    residual_scale_floor_hz: float = 5.0
    huber_k: float = 1.5
    maximum_iterations: int = 25

    def __post_init__(self) -> None:
        values = (
            self.block_duration_s,
            self.uncertainty_floor_hz,
            self.residual_scale_floor_hz,
            self.huber_k,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("block durations, scales, and Huber threshold must be positive")
        if self.minimum_observations_per_block < 2:
            raise ValueError("a CFO block needs at least two observations")
        if not 0.0 < self.minimum_support <= 1.0:
            raise ValueError("minimum support must lie in (0, 1]")
        if not 1 <= self.maximum_iterations <= 1_000:
            raise ValueError("maximum iterations must lie in 1..1000")


@dataclass(frozen=True, slots=True)
class CfoBlockEstimate:
    """One robust estimate from a non-overlapping time block."""

    block_index: int
    start_s: float
    end_s: float
    time_s: float
    cfo_hz: float
    cfo_sigma_hz: float
    local_rate_hz_s: float
    observation_count: int
    effective_observation_count: float
    residual_scale_hz: float
    downweighted_fraction: float


@dataclass(frozen=True, slots=True)
class RobustPolynomialFit:
    """A polynomial CFO fit with coefficients ascending in time power."""

    degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    blocks: tuple[CfoBlockEstimate, ...]
    residual_hz: tuple[float, ...]
    standardized_residual: tuple[float, ...]
    robust_weights: tuple[float, ...]
    full_rms_hz: float
    weighted_rms_hz: float
    residual_scale_hz: float
    effective_block_count: float
    reduced_chi_squared: float
    one_sigma_coverage: float
    two_sigma_coverage: float

    @property
    def rate_at_reference_hz_s(self) -> float:
        return self.coefficients_hz[1] if self.degree >= 1 else 0.0

    @property
    def rate_sigma_at_reference_hz_s(self) -> float:
        return math.sqrt(max(self.covariance[1][1], 0.0)) if self.degree >= 1 else 0.0

    def predict(self, times_s: npt.ArrayLike) -> np.ndarray:
        relative = np.asarray(times_s, dtype=float) - self.reference_time_s
        design = np.vander(relative, N=self.degree + 1, increasing=True)
        return design @ np.asarray(self.coefficients_hz)

    def mean_prediction_sigma(self, times_s: npt.ArrayLike) -> np.ndarray:
        """Return uncertainty of the fitted mean, excluding new-frame noise."""

        relative = np.asarray(times_s, dtype=float) - self.reference_time_s
        design = np.vander(relative, N=self.degree + 1, increasing=True)
        covariance = np.asarray(self.covariance)
        variance = np.einsum("ij,jk,ik->i", design, covariance, design)
        return np.sqrt(np.maximum(variance, 0.0))


@dataclass(frozen=True, slots=True)
class PolynomialComparisonRow:
    """Full-training score for one degree on a shared block population."""

    degree: int
    parameter_count: int
    block_count: int
    full_rms_hz: float
    weighted_rms_hz: float
    reduced_chi_squared: float
    effective_block_count: float
    aicc: float
    bic: float
    one_sigma_coverage: float
    two_sigma_coverage: float
    fit: RobustPolynomialFit


@dataclass(frozen=True, slots=True)
class RadioOnlyPolynomialComparison:
    """Same-data comparison of radio-only polynomial CFO models."""

    shared_blocks: tuple[CfoBlockEstimate, ...]
    rows: tuple[PolynomialComparisonRow, ...]
    preferred_degree_by_bic: int


class LockletState(StrEnum):
    ACQUIRE = "acquire"
    TRACK = "track"
    COAST = "coast"
    REACQUIRE = "reacquire"


@dataclass(frozen=True, slots=True)
class PiecewiseLockletConfig:
    """Causal lifecycle and innovation gates for the locklet prototype."""

    minimum_support: float = 0.20
    acquisition_observations: int = 5
    maximum_acquisition_gap_s: float = 0.010
    maximum_coast_s: float = 0.020
    frequency_gate_sigma: float = 5.0
    acquisition_gate_sigma: float = 4.0
    phase_gate_rad: float = 0.65
    frequency_noise_floor_hz: float = 25.0
    rate_process_sigma_hz_s_sqrt_s: float = 750.0
    change_point_confirmations: int = 3
    maximum_fit_history: int = 128
    huber_k: float = 1.5
    maximum_iterations: int = 20

    def __post_init__(self) -> None:
        if not 0.0 < self.minimum_support <= 1.0:
            raise ValueError("minimum support must lie in (0, 1]")
        values = (
            self.maximum_acquisition_gap_s,
            self.maximum_coast_s,
            self.frequency_gate_sigma,
            self.acquisition_gate_sigma,
            self.phase_gate_rad,
            self.frequency_noise_floor_hz,
            self.rate_process_sigma_hz_s_sqrt_s,
            self.huber_k,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("locklet timing, gates, and scales must be finite and positive")
        if self.phase_gate_rad > math.pi / 2:
            raise ValueError("a modulo-pi phase gate cannot exceed pi/2")
        if self.acquisition_observations < 3:
            raise ValueError("acquisition needs at least three observations")
        if self.change_point_confirmations < 2:
            raise ValueError("change-point confirmation needs at least two observations")
        if self.maximum_fit_history < self.acquisition_observations:
            raise ValueError("fit history must cover acquisition")
        if not 1 <= self.maximum_iterations <= 1_000:
            raise ValueError("maximum iterations must lie in 1..1000")


@dataclass(frozen=True, slots=True)
class LockletFrameDecision:
    """One causal state-machine decision."""

    time_s: float
    state: LockletState
    accepted: bool
    locklet_index: int | None
    predicted_cfo_hz: float | None
    frequency_innovation_hz: float | None
    normalized_frequency_innovation: float | None
    phase_innovation_modulo_pi_rad: float | None
    change_point: bool


@dataclass(frozen=True, slots=True)
class PiecewiseLocklet:
    """One independently acquired, frequency-continuous episode."""

    locklet_index: int
    start_s: float
    end_s: float
    accepted_observation_count: int
    rejected_observation_count: int
    reacquired: bool
    ended_by_change_point: bool
    reference_time_s: float
    cfo_at_reference_hz: float
    rate_hz_s: float
    rate_sigma_hz_s: float
    full_rms_hz: float
    phase_observation_fraction: float


@dataclass(frozen=True, slots=True)
class PiecewiseLockletResult:
    """Complete causal decisions and fitted summaries for all locklets."""

    decisions: tuple[LockletFrameDecision, ...]
    locklets: tuple[PiecewiseLocklet, ...]
    accepted_observation_count: int
    rejected_observation_count: int
    reacquisition_count: int
    change_point_count: int


def robust_blockwise_cfo_rate(
    observations: Iterable[PilotFrameObservation],
    *,
    degree: int = 1,
    config: RobustBlockConfig | None = None,
) -> RobustPolynomialFit:
    """Fit a radio-only CFO polynomial to robust non-overlapping blocks."""

    selected = _canonical_observations(observations)
    settings = config or RobustBlockConfig()
    blocks = _form_blocks(selected, settings)
    return _fit_blocks(blocks, degree=degree, config=settings)


def compare_radio_only_polynomials(
    observations: Iterable[PilotFrameObservation],
    *,
    degrees: tuple[int, ...] = (0, 1, 2),
    config: RobustBlockConfig | None = None,
) -> RadioOnlyPolynomialComparison:
    """Compare degrees with identical blocks, weights, and full-training data."""

    if not degrees or len(set(degrees)) != len(degrees):
        raise ValueError("polynomial degrees must be nonempty and unique")
    if any(degree < 0 or degree > 3 for degree in degrees):
        raise ValueError("research comparison supports polynomial degrees zero through three")
    settings = config or RobustBlockConfig()
    blocks = _form_blocks(_canonical_observations(observations), settings)
    fits = tuple(_fit_blocks(blocks, degree=degree, config=settings) for degree in degrees)
    count = len(blocks)
    rows: list[PolynomialComparisonRow] = []
    for fit in fits:
        parameter_count = fit.degree + 1
        standardized = np.asarray(fit.standardized_residual)
        robust = np.asarray(fit.robust_weights)
        robust_rss = float(np.sum(robust * standardized**2))
        effective_n = max(fit.effective_block_count, parameter_count + 1e-9)
        log_likelihood_term = effective_n * math.log(max(robust_rss / effective_n, 1e-12))
        aic = log_likelihood_term + 2.0 * parameter_count
        denominator = effective_n - parameter_count - 1.0
        aicc = (
            aic + 2.0 * parameter_count * (parameter_count + 1.0) / denominator
            if denominator > 0.0
            else math.inf
        )
        bic = log_likelihood_term + parameter_count * math.log(effective_n)
        rows.append(
            PolynomialComparisonRow(
                degree=fit.degree,
                parameter_count=parameter_count,
                block_count=count,
                full_rms_hz=fit.full_rms_hz,
                weighted_rms_hz=fit.weighted_rms_hz,
                reduced_chi_squared=fit.reduced_chi_squared,
                effective_block_count=fit.effective_block_count,
                aicc=aicc,
                bic=bic,
                one_sigma_coverage=fit.one_sigma_coverage,
                two_sigma_coverage=fit.two_sigma_coverage,
                fit=fit,
            )
        )
    preferred = min(rows, key=lambda row: (row.bic, row.degree)).degree
    return RadioOnlyPolynomialComparison(
        shared_blocks=blocks,
        rows=tuple(rows),
        preferred_degree_by_bic=preferred,
    )


def track_piecewise_locklets(
    observations: Iterable[PilotFrameObservation],
    *,
    config: PiecewiseLockletConfig | None = None,
) -> PiecewiseLockletResult:
    """Run an explicit causal acquire/track/coast/reacquire lifecycle.

    Frequency and rate use a two-state Kalman recursion only inside an active
    locklet.  A sustained innovation or an expired coast closes that episode;
    reacquisition starts from observations alone and never inherits phase.
    """

    values = _canonical_observations(observations)
    settings = config or PiecewiseLockletConfig()
    decisions: list[LockletFrameDecision] = []
    completed: list[PiecewiseLocklet] = []
    candidate: list[PilotFrameObservation] = []
    rejected_candidate: list[PilotFrameObservation] = []
    active_accepted: list[PilotFrameObservation] = []
    active_rejected = 0
    active_index: int | None = None
    active_reacquired = False
    mode = LockletState.ACQUIRE
    state = np.zeros(2, dtype=float)
    covariance = np.eye(2, dtype=float)
    state_time = 0.0
    last_accepted_time: float | None = None
    phase_state: float | None = None
    phase_time: float | None = None
    reacquisition_count = 0
    change_point_count = 0

    def finish_active(*, change_point: bool) -> None:
        nonlocal active_accepted, active_rejected, active_index
        nonlocal phase_state, phase_time, last_accepted_time
        if active_index is None or not active_accepted:
            return
        completed.append(
            _summarize_locklet(
                active_index,
                active_accepted,
                rejected_count=active_rejected,
                reacquired=active_reacquired,
                ended_by_change_point=change_point,
                config=settings,
            )
        )
        active_accepted = []
        active_rejected = 0
        active_index = None
        phase_state = None
        phase_time = None
        last_accepted_time = None

    def attempt_acquisition(observation: PilotFrameObservation) -> bool:
        nonlocal active_index, active_accepted, active_rejected, active_reacquired
        nonlocal state, covariance, state_time, last_accepted_time
        nonlocal phase_state, phase_time, mode, candidate, reacquisition_count
        if (
            candidate
            and observation.time_s - candidate[-1].time_s > settings.maximum_acquisition_gap_s
        ):
            candidate = []
        candidate.append(observation)
        if len(candidate) > settings.maximum_fit_history:
            candidate = candidate[-settings.maximum_fit_history :]
        minimum = settings.acquisition_observations
        if len(candidate) < minimum:
            return False
        window = candidate[-minimum:]
        fit = _fit_direct_observations(window, settings)
        sigma = np.asarray([item.cfo_sigma_hz for item in window])
        scale = np.sqrt(sigma**2 + settings.frequency_noise_floor_hz**2)
        if np.max(np.abs(np.asarray(fit.residual_hz)) / scale) > settings.acquisition_gate_sigma:
            candidate = candidate[-(minimum - 1) :]
            return False
        current = window[-1]
        predicted = float(fit.predict((current.time_s,))[0])
        state = np.asarray((predicted, fit.rate_at_reference_hz_s), dtype=float)
        design = np.asarray((1.0, current.time_s - fit.reference_time_s))
        fit_covariance = np.asarray(fit.covariance)
        frequency_variance = float(design @ fit_covariance @ design)
        rate_variance = max(float(fit_covariance[1, 1]), 1.0)
        covariance = np.diag((max(frequency_variance, 1.0), rate_variance))
        state_time = current.time_s
        active_index = len(completed)
        active_reacquired = bool(completed)
        if active_reacquired:
            reacquisition_count += 1
        active_accepted = list(window)
        active_rejected = 0
        last_accepted_time = current.time_s
        phases = [item for item in window if item.phase_modulo_pi_rad is not None]
        if phases:
            phase_state = phases[-1].phase_modulo_pi_rad
            phase_time = phases[-1].time_s
        candidate = []
        mode = LockletState.TRACK
        return True

    for observation in values:
        usable = observation.support >= settings.minimum_support
        if (
            active_index is not None
            and last_accepted_time is not None
            and observation.time_s - last_accepted_time > settings.maximum_coast_s
        ):
            finish_active(change_point=False)
            mode = LockletState.REACQUIRE
            candidate = []
            rejected_candidate = []

        if active_index is None:
            acquired = usable and attempt_acquisition(observation)
            decisions.append(
                LockletFrameDecision(
                    time_s=observation.time_s,
                    state=mode,
                    accepted=acquired,
                    locklet_index=active_index if acquired else None,
                    predicted_cfo_hz=None,
                    frequency_innovation_hz=None,
                    normalized_frequency_innovation=None,
                    phase_innovation_modulo_pi_rad=None,
                    change_point=False,
                )
            )
            continue

        dt_s = observation.time_s - state_time
        transition = np.asarray(((1.0, dt_s), (0.0, 1.0)))
        process_power = settings.rate_process_sigma_hz_s_sqrt_s**2
        process = process_power * np.asarray(
            ((dt_s**3 / 3.0, dt_s**2 / 2.0), (dt_s**2 / 2.0, dt_s))
        )
        predicted_state = transition @ state
        predicted_covariance = transition @ covariance @ transition.T + process
        measurement_variance = (
            observation.cfo_sigma_hz**2 / max(observation.support, 1e-6)
            + settings.frequency_noise_floor_hz**2
        )
        innovation = observation.cfo_hz - predicted_state[0]
        innovation_variance = predicted_covariance[0, 0] + measurement_variance
        normalized = innovation / math.sqrt(max(innovation_variance, 1e-12))
        phase_innovation: float | None = None
        phase_ok = True
        predicted_phase: float | None = None
        if phase_state is not None:
            phase_dt = observation.time_s - state_time
            predicted_phase = phase_state + 2.0 * math.pi * (
                state[0] * phase_dt + 0.5 * state[1] * phase_dt**2
            )
        if observation.phase_modulo_pi_rad is not None and predicted_phase is not None:
            phase_innovation = _wrap_modulo_pi(observation.phase_modulo_pi_rad - predicted_phase)
            phase_ok = abs(phase_innovation) <= settings.phase_gate_rad
        accepted = usable and abs(normalized) <= settings.frequency_gate_sigma and phase_ok
        change_point = False
        if accepted:
            gain = predicted_covariance[:, 0] / innovation_variance
            state = predicted_state + gain * innovation
            covariance = predicted_covariance - np.outer(gain, predicted_covariance[0])
            covariance = 0.5 * (covariance + covariance.T)
            state_time = observation.time_s
            last_accepted_time = observation.time_s
            active_accepted.append(observation)
            rejected_candidate = []
            if observation.phase_modulo_pi_rad is not None:
                if predicted_phase is None or phase_innovation is None:
                    phase_state = observation.phase_modulo_pi_rad
                else:
                    assert observation.phase_sigma_rad is not None
                    phase_variance = observation.phase_sigma_rad**2
                    phase_gain = min(0.8, max(0.1, 0.25 / (0.25 + phase_variance)))
                    phase_state = predicted_phase + phase_gain * phase_innovation
                phase_time = observation.time_s
            elif predicted_phase is not None:
                phase_state = predicted_phase
                phase_time = observation.time_s
            mode = LockletState.TRACK
        else:
            active_rejected += 1
            mode = LockletState.COAST
            if usable:
                if (
                    rejected_candidate
                    and observation.time_s - rejected_candidate[-1].time_s
                    > settings.maximum_acquisition_gap_s
                ):
                    rejected_candidate = []
                rejected_candidate.append(observation)
                rejected_candidate = rejected_candidate[-settings.change_point_confirmations :]
                if len(rejected_candidate) == settings.change_point_confirmations:
                    trial = _fit_direct_observations(rejected_candidate, settings)
                    trial_scale = np.sqrt(
                        np.asarray([item.cfo_sigma_hz for item in rejected_candidate]) ** 2
                        + settings.frequency_noise_floor_hz**2
                    )
                    coherent_shift = (
                        np.max(np.abs(np.asarray(trial.residual_hz)) / trial_scale)
                        <= settings.acquisition_gate_sigma
                    )
                    if coherent_shift:
                        seeds = list(rejected_candidate)
                        finish_active(change_point=True)
                        change_point_count += 1
                        change_point = True
                        mode = LockletState.REACQUIRE
                        candidate = seeds
                        rejected_candidate = []

        decisions.append(
            LockletFrameDecision(
                time_s=observation.time_s,
                state=mode,
                accepted=accepted,
                locklet_index=active_index,
                predicted_cfo_hz=float(predicted_state[0]),
                frequency_innovation_hz=float(innovation),
                normalized_frequency_innovation=float(normalized),
                phase_innovation_modulo_pi_rad=phase_innovation,
                change_point=change_point,
            )
        )

    finish_active(change_point=False)
    accepted_count = sum(locklet.accepted_observation_count for locklet in completed)
    rejected_count = sum(locklet.rejected_observation_count for locklet in completed)
    return PiecewiseLockletResult(
        decisions=tuple(decisions),
        locklets=tuple(completed),
        accepted_observation_count=accepted_count,
        rejected_observation_count=rejected_count,
        reacquisition_count=reacquisition_count,
        change_point_count=change_point_count,
    )


def _canonical_observations(
    observations: Iterable[PilotFrameObservation],
) -> tuple[PilotFrameObservation, ...]:
    values = tuple(observations)
    if not values:
        raise ValueError("at least one frame observation is required")
    times = np.asarray([value.time_s for value in values])
    if np.any(np.diff(times) <= 0.0):
        raise ValueError("frame observation times must be strictly increasing")
    return values


def _form_blocks(
    observations: tuple[PilotFrameObservation, ...],
    config: RobustBlockConfig,
) -> tuple[CfoBlockEstimate, ...]:
    eligible = [item for item in observations if item.support >= config.minimum_support]
    if not eligible:
        raise ValueError("no observations pass the block support gate")
    origin = eligible[0].time_s
    groups: dict[int, list[PilotFrameObservation]] = {}
    for observation in eligible:
        index = int(math.floor((observation.time_s - origin) / config.block_duration_s + 1e-12))
        groups.setdefault(index, []).append(observation)
    blocks: list[CfoBlockEstimate] = []
    for index, group in groups.items():
        if len(group) < config.minimum_observations_per_block:
            continue
        times = np.asarray([item.time_s for item in group])
        cfo = np.asarray([item.cfo_hz for item in group])
        sigmas = np.sqrt(
            np.asarray([item.cfo_sigma_hz for item in group]) ** 2 + config.uncertainty_floor_hz**2
        )
        support = np.asarray([item.support for item in group])
        reference = float(np.average(times, weights=support / sigmas**2))
        design = np.column_stack((np.ones(len(group)), times - reference))
        coefficients, covariance, residual, robust, residual_scale, _, _ = _robust_regression(
            design,
            cfo,
            sigmas,
            support,
            huber_k=config.huber_k,
            maximum_iterations=config.maximum_iterations,
            residual_scale_floor=config.residual_scale_floor_hz,
        )
        effective = _effective_count(robust * support)
        blocks.append(
            CfoBlockEstimate(
                block_index=index,
                start_s=group[0].time_s,
                end_s=group[-1].time_s,
                time_s=reference,
                cfo_hz=float(coefficients[0]),
                cfo_sigma_hz=math.sqrt(max(float(covariance[0, 0]), 1e-12)),
                local_rate_hz_s=float(coefficients[1]),
                observation_count=len(group),
                effective_observation_count=effective,
                residual_scale_hz=residual_scale,
                downweighted_fraction=float(np.mean(robust < 0.999)),
            )
        )
    if not blocks:
        raise ValueError("no complete CFO blocks remain after support gating")
    return tuple(blocks)


def _fit_blocks(
    blocks: tuple[CfoBlockEstimate, ...],
    *,
    degree: int,
    config: RobustBlockConfig,
) -> RobustPolynomialFit:
    if degree < 0 or degree > 3:
        raise ValueError("research block fit supports degrees zero through three")
    if len(blocks) <= degree + 1:
        raise ValueError("polynomial fit needs more blocks than parameters")
    times = np.asarray([block.time_s for block in blocks])
    cfo = np.asarray([block.cfo_hz for block in blocks])
    sigmas = np.asarray([block.cfo_sigma_hz for block in blocks])
    reference = float(np.median(times))
    design = np.vander(times - reference, N=degree + 1, increasing=True)
    coefficients, covariance, residual, robust, residual_scale, reduced_chi, effective = (
        _robust_regression(
            design,
            cfo,
            sigmas,
            np.ones(len(blocks)),
            huber_k=config.huber_k,
            maximum_iterations=config.maximum_iterations,
            residual_scale_floor=config.residual_scale_floor_hz,
        )
    )
    standardized = residual / sigmas
    prediction_variance = np.einsum("ij,jk,ik->i", design, covariance, design)
    predictive_sigma = np.sqrt(
        np.maximum(sigmas**2 * max(reduced_chi, 1.0) + prediction_variance, 1e-12)
    )
    absolute_predictive = np.abs(residual) / predictive_sigma
    base_weights = 1.0 / sigmas**2
    return RobustPolynomialFit(
        degree=degree,
        reference_time_s=reference,
        coefficients_hz=tuple(float(value) for value in coefficients),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        blocks=blocks,
        residual_hz=tuple(float(value) for value in residual),
        standardized_residual=tuple(float(value) for value in standardized),
        robust_weights=tuple(float(value) for value in robust),
        full_rms_hz=float(np.sqrt(np.mean(residual**2))),
        weighted_rms_hz=float(np.sqrt(np.sum(base_weights * residual**2) / np.sum(base_weights))),
        residual_scale_hz=residual_scale,
        effective_block_count=effective,
        reduced_chi_squared=reduced_chi,
        one_sigma_coverage=float(np.mean(absolute_predictive <= 1.0)),
        two_sigma_coverage=float(np.mean(absolute_predictive <= 2.0)),
    )


def _fit_direct_observations(
    observations: list[PilotFrameObservation],
    config: PiecewiseLockletConfig,
) -> RobustPolynomialFit:
    times = np.asarray([item.time_s for item in observations])
    cfo = np.asarray([item.cfo_hz for item in observations])
    sigmas = np.sqrt(
        np.asarray([item.cfo_sigma_hz for item in observations]) ** 2
        + config.frequency_noise_floor_hz**2
    )
    support = np.asarray([item.support for item in observations])
    reference = float(np.median(times))
    design = np.column_stack((np.ones(len(times)), times - reference))
    coefficients, covariance, residual, robust, residual_scale, reduced_chi, effective = (
        _robust_regression(
            design,
            cfo,
            sigmas,
            support,
            huber_k=config.huber_k,
            maximum_iterations=config.maximum_iterations,
            residual_scale_floor=config.frequency_noise_floor_hz,
        )
    )
    standardized = residual / sigmas
    prediction_variance = np.einsum("ij,jk,ik->i", design, covariance, design)
    predictive_sigma = np.sqrt(
        np.maximum(sigmas**2 * max(reduced_chi, 1.0) + prediction_variance, 1e-12)
    )
    absolute_predictive = np.abs(residual) / predictive_sigma
    base_weights = support / sigmas**2
    return RobustPolynomialFit(
        degree=1,
        reference_time_s=reference,
        coefficients_hz=tuple(float(value) for value in coefficients),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        blocks=(),
        residual_hz=tuple(float(value) for value in residual),
        standardized_residual=tuple(float(value) for value in standardized),
        robust_weights=tuple(float(value) for value in robust),
        full_rms_hz=float(np.sqrt(np.mean(residual**2))),
        weighted_rms_hz=float(np.sqrt(np.sum(base_weights * residual**2) / np.sum(base_weights))),
        residual_scale_hz=residual_scale,
        effective_block_count=effective,
        reduced_chi_squared=reduced_chi,
        one_sigma_coverage=float(np.mean(absolute_predictive <= 1.0)),
        two_sigma_coverage=float(np.mean(absolute_predictive <= 2.0)),
    )


def _summarize_locklet(
    index: int,
    accepted: list[PilotFrameObservation],
    *,
    rejected_count: int,
    reacquired: bool,
    ended_by_change_point: bool,
    config: PiecewiseLockletConfig,
) -> PiecewiseLocklet:
    fit = _fit_direct_observations(accepted, config)
    phase_count = sum(item.phase_modulo_pi_rad is not None for item in accepted)
    return PiecewiseLocklet(
        locklet_index=index,
        start_s=accepted[0].time_s,
        end_s=accepted[-1].time_s,
        accepted_observation_count=len(accepted),
        rejected_observation_count=rejected_count,
        reacquired=reacquired,
        ended_by_change_point=ended_by_change_point,
        reference_time_s=fit.reference_time_s,
        cfo_at_reference_hz=fit.coefficients_hz[0],
        rate_hz_s=fit.rate_at_reference_hz_s,
        rate_sigma_hz_s=fit.rate_sigma_at_reference_hz_s,
        full_rms_hz=fit.full_rms_hz,
        phase_observation_fraction=phase_count / len(accepted),
    )


def _robust_regression(
    design: np.ndarray,
    values: np.ndarray,
    sigmas: np.ndarray,
    support: np.ndarray,
    *,
    huber_k: float,
    maximum_iterations: int,
    residual_scale_floor: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float, float]:
    if design.ndim != 2 or values.ndim != 1 or design.shape[0] != values.size:
        raise ValueError("regression design and values have incompatible shapes")
    if design.shape[0] <= design.shape[1]:
        raise ValueError("regression needs more observations than parameters")
    base_weights = support / np.maximum(sigmas**2, 1e-24)
    robust = np.ones(len(values), dtype=float)
    coefficients = _weighted_solve(design, values, base_weights)
    for _ in range(maximum_iterations):
        residual = values - design @ coefficients
        residual_scale = max(
            _mad_scale(residual),
            residual_scale_floor,
            float(np.median(sigmas)),
        )
        standardized = residual / np.sqrt(sigmas**2 + residual_scale**2)
        absolute = np.abs(standardized)
        updated_robust = np.ones_like(absolute)
        mask = absolute > huber_k
        updated_robust[mask] = huber_k / absolute[mask]
        updated = _weighted_solve(design, values, base_weights * updated_robust)
        if np.max(np.abs(updated - coefficients)) <= 1e-10 * max(
            1.0, float(np.max(np.abs(coefficients)))
        ):
            coefficients = updated
            robust = updated_robust
            break
        coefficients = updated
        robust = updated_robust
    residual = values - design @ coefficients
    residual_scale = max(_mad_scale(residual), residual_scale_floor)
    weights = base_weights * robust
    information = design.T @ (weights[:, None] * design)
    covariance_base = np.linalg.pinv(information, rcond=1e-12)
    effective = _effective_count(robust * support)
    degrees_of_freedom = max(effective - design.shape[1], 1.0)
    reduced_chi = float(np.sum(robust * (residual / sigmas) ** 2) / degrees_of_freedom)
    covariance = covariance_base * max(reduced_chi, 1.0)
    return coefficients, covariance, residual, robust, residual_scale, reduced_chi, effective


def _weighted_solve(design: np.ndarray, values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    square_root = np.sqrt(np.maximum(weights, 0.0))
    weighted_design = design * square_root[:, None]
    weighted_values = values * square_root
    return np.linalg.lstsq(weighted_design, weighted_values, rcond=None)[0]


def _mad_scale(values: np.ndarray) -> float:
    if not len(values):
        return 0.0
    median = float(np.median(values))
    return 1.4826 * float(np.median(np.abs(values - median)))


def _effective_count(weights: np.ndarray) -> float:
    total = float(np.sum(weights))
    squared = float(np.sum(weights**2))
    return total**2 / squared if squared > 0.0 else 0.0


def _wrap_modulo_pi(value: float) -> float:
    return float((value + math.pi / 2) % math.pi - math.pi / 2)


__all__ = [
    "CfoBlockEstimate",
    "LockletFrameDecision",
    "LockletState",
    "PiecewiseLocklet",
    "PiecewiseLockletConfig",
    "PiecewiseLockletResult",
    "PilotFrameObservation",
    "PolynomialComparisonRow",
    "RadioOnlyPolynomialComparison",
    "RobustBlockConfig",
    "RobustPolynomialFit",
    "compare_radio_only_polynomials",
    "robust_blockwise_cfo_rate",
    "track_piecewise_locklets",
]
