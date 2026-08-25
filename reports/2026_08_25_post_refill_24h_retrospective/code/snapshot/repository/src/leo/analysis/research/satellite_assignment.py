"""Pure lane-scoped, duration-constrained satellite association primitives.

Upstream radio-only path cover is responsible for separating simultaneous CFO
branches.  This module assigns one such frozen lane to sampled satellite Doppler
hypotheses.  It deliberately does not query a catalogue, propagate TLEs, read
recordings, or publish identity claims.

Frequency and rate observations carry a ``source_group_id``.  A 20 ms search
and the 1.333 ms frame measurements derived from it must share that identity.
Their combined robust-loss weight is capped, preventing nested measurements
from masquerading as independent probes.

The dynamic program profiles delay and a nuisance independently in each active
episode.  A second, explicit refit then estimates one delay for all selected
episodes of a catalog object while retaining per-episode CFO/rate nuisances.
The latter distinction matters for Pluto recordings whose refill continuity is
not authoritative: one global CFO intercept would be a false constraint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import numpy as np

from leo.analysis.research.satellite_activity import huber_loss


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be nonnegative")


@dataclass(frozen=True, slots=True)
class FrequencyProbe:
    """One CFO measurement in a frozen TLE-blind lane."""

    observation_id: str
    lane_id: str
    source_group_id: str
    source_time_s: float
    time_s: float
    cfo_hz: float
    sigma_hz: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.observation_id or not self.lane_id or not self.source_group_id:
            raise ValueError("frequency probe identities must be nonempty")
        for value, label in (
            (self.source_time_s, "source time"),
            (self.time_s, "frequency time"),
            (self.cfo_hz, "CFO"),
        ):
            _finite(value, label)
        _positive(self.sigma_hz, "CFO uncertainty")
        _positive(self.weight, "frequency-probe weight")


@dataclass(frozen=True, slots=True)
class RateProbe:
    """One reset-debiased received-CFO-rate measurement in a frozen lane."""

    observation_id: str
    lane_id: str
    source_group_id: str
    source_time_s: float
    time_s: float
    rate_hz_s: float
    sigma_hz_s: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.observation_id or not self.lane_id or not self.source_group_id:
            raise ValueError("rate probe identities must be nonempty")
        for value, label in (
            (self.source_time_s, "source time"),
            (self.time_s, "rate time"),
            (self.rate_hz_s, "CFO rate"),
        ):
            _finite(value, label)
        _positive(self.sigma_hz_s, "rate uncertainty")
        _positive(self.weight, "rate-probe weight")


type Probe = FrequencyProbe | RateProbe


@dataclass(frozen=True, slots=True)
class SatellitePrediction:
    """Caller-supplied sampled geometric Doppler curve for one object."""

    object_name: str
    catalog_number: int
    time_s: tuple[float, ...]
    doppler_hz: tuple[float, ...]
    doppler_rate_hz_s: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.object_name or self.catalog_number <= 0:
            raise ValueError("satellite prediction identity is incomplete")
        if len(self.time_s) < 2 or len(self.doppler_hz) != len(self.time_s):
            raise ValueError("satellite prediction needs equal-length sampled time and Doppler")
        if self.doppler_rate_hz_s is not None and len(self.doppler_rate_hz_s) != len(self.time_s):
            raise ValueError("sampled Doppler-rate length differs from prediction time")
        values = (*self.time_s, *self.doppler_hz)
        if self.doppler_rate_hz_s is not None:
            values += self.doppler_rate_hz_s
        if any(not math.isfinite(value) for value in values):
            raise ValueError("satellite prediction values must be finite")
        if any(
            second <= first for first, second in zip(self.time_s, self.time_s[1:], strict=False)
        ):
            raise ValueError("satellite prediction times must be strictly increasing")


@dataclass(frozen=True, slots=True)
class SatelliteAssignmentConfig:
    """Numerical controls and explicit model/support penalties."""

    tau_min_s: float = -0.30
    tau_max_s: float = 0.30
    tau_step_s: float = 0.05
    tau_prior_mean_s: float = 0.0
    tau_prior_sigma_s: float | None = None
    cfo_offset_bounds_hz: tuple[float, float] | None = None
    rate_nuisance_bounds_hz_s: tuple[float, float] = (-200.0, 200.0)
    huber_k: float = 1.345
    maximum_iterations: int = 50
    maximum_source_group_weight: float = 1.0
    minimum_span_s: float = 1.0
    minimum_distinct_source_groups: int = 10
    expected_probe_interval_s: float = 0.05
    minimum_coverage_fraction: float = 0.70
    maximum_gap_s: float = 0.20
    maximum_segment_groups: int | None = None
    satellite_activation_penalty_per_segment: float = 6.0
    segment_penalty: float = 2.0
    unassigned_cost_per_group: float = 1.0
    profile_confidence_delta: float = 1.92
    minimum_profile_cost_span: float = 1.0
    maximum_identifiable_tau_width_s: float = 0.20
    minimum_delay_information: float = 1e-6
    flat_profile_tolerance: float = 1e-8

    def __post_init__(self) -> None:
        for value, label in (
            (self.tau_min_s, "minimum delay"),
            (self.tau_max_s, "maximum delay"),
            (self.tau_prior_mean_s, "delay-prior mean"),
        ):
            _finite(value, label)
        if self.tau_min_s >= self.tau_max_s:
            raise ValueError("delay bounds must be increasing")
        for value, label in (
            (self.tau_step_s, "delay step"),
            (self.huber_k, "Huber threshold"),
            (self.maximum_source_group_weight, "source-group weight cap"),
            (self.minimum_span_s, "minimum segment span"),
            (self.expected_probe_interval_s, "expected probe interval"),
            (self.maximum_gap_s, "maximum segment gap"),
            (self.profile_confidence_delta, "profile confidence delta"),
            (self.maximum_identifiable_tau_width_s, "identifiable delay width"),
        ):
            _positive(value, label)
        if self.tau_prior_sigma_s is not None:
            _positive(self.tau_prior_sigma_s, "delay-prior sigma")
        for bounds, label in (
            (self.cfo_offset_bounds_hz, "CFO-offset"),
            (self.rate_nuisance_bounds_hz_s, "rate-nuisance"),
        ):
            if bounds is None:
                continue
            lower, upper = bounds
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                raise ValueError(f"{label} bounds must be finite and increasing")
        if self.maximum_iterations < 1:
            raise ValueError("maximum iterations must be positive")
        if self.minimum_distinct_source_groups < 2:
            raise ValueError("minimum distinct source groups must be at least two")
        if not 0.0 < self.minimum_coverage_fraction <= 1.0:
            raise ValueError("minimum coverage fraction must lie in (0, 1]")
        if self.maximum_segment_groups is not None and (
            self.maximum_segment_groups < self.minimum_distinct_source_groups
        ):
            raise ValueError("maximum segment groups is below the minimum support")
        for value, label in (
            (
                self.satellite_activation_penalty_per_segment,
                "per-segment satellite activation penalty",
            ),
            (self.segment_penalty, "segment penalty"),
            (self.unassigned_cost_per_group, "unassigned cost"),
            (self.minimum_profile_cost_span, "minimum profile span"),
            (self.minimum_delay_information, "minimum delay information"),
            (self.flat_profile_tolerance, "flat-profile tolerance"),
        ):
            _nonnegative(value, label)
        span_steps = (self.tau_max_s - self.tau_min_s) / self.tau_step_s
        if not math.isclose(span_steps, round(span_steps), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("delay range must be divisible by the delay step")

    def tau_grid(self) -> np.ndarray:
        count = round((self.tau_max_s - self.tau_min_s) / self.tau_step_s) + 1
        return np.linspace(self.tau_min_s, self.tau_max_s, count, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class IntervalSupport:
    source_group_ids: tuple[str, ...]
    start_s: float
    end_s: float
    span_s: float
    maximum_gap_s: float
    expected_group_count: int
    coverage_fraction: float
    eligible: bool
    reasons: tuple[str, ...]


class ScoreMode(StrEnum):
    FREQUENCY = "frequency"
    RATE = "rate"


@dataclass(frozen=True, slots=True)
class DelayProfilePoint:
    tau_s: float
    fitted_nuisance: float
    nuisance_at_bound: bool
    data_cost: float
    prior_cost: float
    total_cost: float
    residual_rms: float
    standardized_rms: float


@dataclass(frozen=True, slots=True)
class DelayIdentifiability:
    evaluated_tau_min_s: float
    evaluated_tau_max_s: float
    profile_complete: bool
    data_cost_span: float
    data_flat: bool
    data_profile_low_s: float
    data_profile_high_s: float
    data_profile_width_s: float
    tau_at_boundary: bool
    prior_changed_optimum: bool
    tau_nuisance_correlation: float | None
    conditional_delay_information: float
    identifiable: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntervalScore:
    mode: ScoreMode
    object_name: str
    catalog_number: int
    lane_id: str
    support: IntervalSupport
    observation_ids: tuple[str, ...]
    profile: tuple[DelayProfilePoint, ...]
    best_index: int
    fitted_tau_s: float
    fitted_cfo_offset_hz: float | None
    fitted_rate_nuisance_hz_s: float | None
    data_cost: float
    prior_cost: float
    total_cost: float
    residual_rms: float
    standardized_rms: float
    identifiability: DelayIdentifiability


@dataclass(frozen=True, slots=True)
class SharedEpisodeNuisance:
    segment_index: int
    fitted_nuisance: float
    nuisance_at_bound: bool


@dataclass(frozen=True, slots=True)
class SharedDelayProfilePoint:
    tau_s: float
    episode_nuisances: tuple[SharedEpisodeNuisance, ...]
    data_cost: float
    prior_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class SharedSatelliteRefit:
    mode: ScoreMode
    object_name: str
    catalog_number: int
    segment_indices: tuple[int, ...]
    profile: tuple[SharedDelayProfilePoint, ...]
    best_index: int
    fitted_tau_s: float
    episode_nuisances: tuple[SharedEpisodeNuisance, ...]
    identifiability: DelayIdentifiability


class AssignmentState(StrEnum):
    SATELLITE = "satellite"
    UNASSIGNED = "unassigned"


@dataclass(frozen=True, slots=True)
class AssignmentSegment:
    state: AssignmentState
    lane_id: str
    source_group_ids: tuple[str, ...]
    start_s: float
    end_s: float
    catalog_number: int | None
    object_name: str | None
    interval_score: IntervalScore | None
    runner_up_catalog_number: int | None
    runner_up_cost_margin: float | None


@dataclass(frozen=True, slots=True)
class AssignmentObjective:
    satellite_data_cost: float
    delay_prior_cost: float
    model_penalty: float
    unassigned_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class SatelliteAssignmentResult:
    lane_id: str
    mode: ScoreMode
    source_group_count: int
    segments: tuple[AssignmentSegment, ...]
    shared_satellite_refits: tuple[SharedSatelliteRefit, ...]
    objective: AssignmentObjective
    algorithm: str = "lane-duration-semimarkov-profile-v1"
    global_cross_lane_exclusivity_enforced: bool = False


@dataclass(frozen=True, slots=True)
class CrossLaneConflict:
    source_group_id: str
    owners: tuple[tuple[str, int], ...]


def _validate_probes(probes: tuple[Probe, ...]) -> tuple[str, dict[str, float]]:
    if not probes:
        raise ValueError("satellite assignment needs at least one probe")
    if len({item.observation_id for item in probes}) != len(probes):
        raise ValueError("probe observation IDs must be unique")
    lanes = {item.lane_id for item in probes}
    if len(lanes) != 1:
        raise ValueError("one assignment problem must contain exactly one frozen lane")
    source_times: dict[str, float] = {}
    for item in probes:
        previous = source_times.setdefault(item.source_group_id, item.source_time_s)
        if not math.isclose(previous, item.source_time_s, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("one source group has inconsistent source times")
    ordered = sorted(source_times.items(), key=lambda item: (item[1], item[0]))
    if any(second[1] <= first[1] for first, second in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("source-group times must be strictly increasing within one lane")
    return next(iter(lanes)), dict(ordered)


def interval_support(
    probes: tuple[Probe, ...], config: SatelliteAssignmentConfig
) -> IntervalSupport:
    """Evaluate duration, distinct-group, coverage, and gap gates."""

    _lane, source_times = _validate_probes(probes)
    ordered = tuple(source_times)
    times: np.ndarray = np.asarray(tuple(source_times.values()), dtype=np.float64)
    span = float(times[-1] - times[0])
    maximum_gap = float(np.max(np.diff(times))) if times.size > 1 else 0.0
    expected = max(1, int(round(span / config.expected_probe_interval_s)) + 1)
    coverage = min(1.0, len(ordered) / expected)
    reasons = []
    if span < config.minimum_span_s:
        reasons.append("span_below_minimum")
    if len(ordered) < config.minimum_distinct_source_groups:
        reasons.append("too_few_distinct_source_groups")
    if coverage < config.minimum_coverage_fraction:
        reasons.append("coverage_below_minimum")
    if maximum_gap > config.maximum_gap_s:
        reasons.append("gap_above_maximum")
    if config.maximum_segment_groups is not None and len(ordered) > config.maximum_segment_groups:
        reasons.append("too_many_source_groups")
    return IntervalSupport(
        source_group_ids=ordered,
        start_s=float(times[0]),
        end_s=float(times[-1]),
        span_s=span,
        maximum_gap_s=maximum_gap,
        expected_group_count=expected,
        coverage_fraction=coverage,
        eligible=not reasons,
        reasons=tuple(reasons),
    )


def _effective_weights(probes: tuple[Probe, ...], cap: float) -> np.ndarray:
    totals: dict[str, float] = {}
    for item in probes:
        totals[item.source_group_id] = totals.get(item.source_group_id, 0.0) + item.weight
    return np.asarray(
        [item.weight * min(1.0, cap / totals[item.source_group_id]) for item in probes],
        dtype=np.float64,
    )


def _fit_location(
    raw: np.ndarray,
    sigma: np.ndarray,
    weights: np.ndarray,
    *,
    bounds: tuple[float, float] | None,
    config: SatelliteAssignmentConfig,
) -> tuple[float, bool, np.ndarray, float]:
    lower, upper = (-math.inf, math.inf) if bounds is None else bounds
    base = weights / sigma**2
    location = float(np.clip(np.average(raw, weights=base), lower, upper))
    for _iteration in range(config.maximum_iterations):
        standardized = np.abs((raw - location) / sigma)
        robust: np.ndarray = np.ones(raw.size, dtype=np.float64)
        tail = standardized > config.huber_k
        robust[tail] = config.huber_k / standardized[tail]
        updated = float(np.clip(np.average(raw, weights=base * robust), lower, upper))
        if abs(updated - location) <= 1e-10 * max(1.0, abs(location)):
            location = updated
            break
        location = updated
    residual = raw - location
    cost = math.fsum(
        float(weight) * huber_loss(float(value), config.huber_k)
        for weight, value in zip(weights, residual / sigma, strict=True)
    )
    at_bound = (
        math.isfinite(lower) and math.isclose(location, lower, rel_tol=0.0, abs_tol=1e-9)
    ) or (math.isfinite(upper) and math.isclose(location, upper, rel_tol=0.0, abs_tol=1e-9))
    return location, at_bound, residual, cost


def _prediction_arrays(
    prediction: SatellitePrediction, mode: ScoreMode
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times: np.ndarray = np.asarray(prediction.time_s, dtype=np.float64)
    doppler: np.ndarray = np.asarray(prediction.doppler_hz, dtype=np.float64)
    if prediction.doppler_rate_hz_s is None:
        rate = (
            np.gradient(doppler, times, edge_order=2)
            if times.size >= 3
            else np.gradient(doppler, times, edge_order=1)
        )
    else:
        rate = np.asarray(prediction.doppler_rate_hz_s, dtype=np.float64)
    values = doppler if mode is ScoreMode.FREQUENCY else rate
    derivative = (
        np.gradient(values, times, edge_order=2)
        if times.size >= 3
        else np.gradient(values, times, edge_order=1)
    )
    return times, values, derivative


def _interpolate(
    prediction_times: np.ndarray, values: np.ndarray, query: np.ndarray
) -> np.ndarray | None:
    if float(np.min(query)) < prediction_times[0] or float(np.max(query)) > prediction_times[-1]:
        return None
    return np.interp(query, prediction_times, values)


def _prior_cost(tau_s: float, config: SatelliteAssignmentConfig) -> float:
    if config.tau_prior_sigma_s is None:
        return 0.0
    return 0.5 * ((tau_s - config.tau_prior_mean_s) / config.tau_prior_sigma_s) ** 2


def _profile_diagnostics(
    points: tuple[DelayProfilePoint, ...],
    best_index: int,
    *,
    information: float,
    expected_count: int,
    config: SatelliteAssignmentConfig,
) -> DelayIdentifiability:
    data_minimum = min(item.data_cost for item in points)
    eligible = tuple(
        item for item in points if item.data_cost <= data_minimum + config.profile_confidence_delta
    )
    low = min(item.tau_s for item in eligible)
    high = max(item.tau_s for item in eligible)
    span = max(item.data_cost for item in points) - data_minimum
    best = points[best_index]
    boundary = (
        best_index in {0, len(points) - 1}
        or math.isclose(best.tau_s, config.tau_min_s, abs_tol=1e-12)
        or math.isclose(best.tau_s, config.tau_max_s, abs_tol=1e-12)
    )
    nuisances: np.ndarray = np.asarray([item.fitted_nuisance for item in points], dtype=np.float64)
    taus: np.ndarray = np.asarray([item.tau_s for item in points], dtype=np.float64)
    correlation = None
    if len(points) >= 2 and float(np.std(nuisances)) > 0.0:
        correlation = float(np.corrcoef(taus, nuisances)[0, 1])
    data_best = min(
        range(len(points)),
        key=lambda index: (points[index].data_cost, abs(points[index].tau_s), points[index].tau_s),
    )
    reasons = []
    if len(points) != expected_count:
        reasons.append("prediction_does_not_cover_full_tau_grid")
    if boundary:
        reasons.append("tau_optimum_at_boundary")
    if span < config.minimum_profile_cost_span:
        reasons.append("delay_profile_too_flat")
    if high - low > config.maximum_identifiable_tau_width_s:
        reasons.append("delay_profile_interval_too_wide")
    if information < config.minimum_delay_information:
        reasons.append("insufficient_conditional_delay_information")
    return DelayIdentifiability(
        evaluated_tau_min_s=points[0].tau_s,
        evaluated_tau_max_s=points[-1].tau_s,
        profile_complete=len(points) == expected_count,
        data_cost_span=span,
        data_flat=span <= config.flat_profile_tolerance,
        data_profile_low_s=low,
        data_profile_high_s=high,
        data_profile_width_s=high - low,
        tau_at_boundary=boundary,
        prior_changed_optimum=data_best != best_index,
        tau_nuisance_correlation=correlation,
        conditional_delay_information=information,
        identifiable=not reasons,
        reasons=tuple(reasons),
    )


def _score_interval(
    probes: tuple[Probe, ...],
    prediction: SatellitePrediction,
    config: SatelliteAssignmentConfig,
    mode: ScoreMode,
) -> IntervalScore:
    lane_id, _times = _validate_probes(probes)
    if mode is ScoreMode.FREQUENCY and any(not isinstance(item, FrequencyProbe) for item in probes):
        raise TypeError("frequency interval scoring requires only FrequencyProbe values")
    if mode is ScoreMode.RATE and any(not isinstance(item, RateProbe) for item in probes):
        raise TypeError("rate interval scoring requires only RateProbe values")
    support = interval_support(probes, config)
    if not support.eligible:
        raise ValueError("interval is ineligible: " + ", ".join(support.reasons))
    ordered = tuple(sorted(probes, key=lambda item: (item.time_s, item.observation_id)))
    observation_times: np.ndarray = np.asarray([item.time_s for item in ordered], dtype=np.float64)
    if mode is ScoreMode.FREQUENCY:
        frequency_ordered = cast(tuple[FrequencyProbe, ...], ordered)
        observed: np.ndarray = np.asarray(
            [item.cfo_hz for item in frequency_ordered], dtype=np.float64
        )
        sigma: np.ndarray = np.asarray(
            [item.sigma_hz for item in frequency_ordered], dtype=np.float64
        )
        bounds = config.cfo_offset_bounds_hz
    else:
        rate_ordered = cast(tuple[RateProbe, ...], ordered)
        observed = np.asarray([item.rate_hz_s for item in rate_ordered], dtype=np.float64)
        sigma = np.asarray([item.sigma_hz_s for item in rate_ordered], dtype=np.float64)
        bounds = config.rate_nuisance_bounds_hz_s
    weights = _effective_weights(ordered, config.maximum_source_group_weight)
    prediction_times, predicted_values, predicted_derivative = _prediction_arrays(prediction, mode)
    tau_grid = config.tau_grid()
    points = []
    derivative_at_tau: dict[float, np.ndarray] = {}
    for tau in tau_grid:
        query = observation_times + float(tau)
        predicted = _interpolate(prediction_times, predicted_values, query)
        derivative = _interpolate(prediction_times, predicted_derivative, query)
        if predicted is None or derivative is None:
            continue
        nuisance, at_bound, residual, data_cost = _fit_location(
            observed - predicted,
            sigma,
            weights,
            bounds=bounds,
            config=config,
        )
        prior = _prior_cost(float(tau), config)
        points.append(
            DelayProfilePoint(
                tau_s=float(tau),
                fitted_nuisance=nuisance,
                nuisance_at_bound=at_bound,
                data_cost=data_cost,
                prior_cost=prior,
                total_cost=data_cost + prior,
                residual_rms=float(np.sqrt(np.average(residual**2, weights=weights))),
                standardized_rms=float(
                    np.sqrt(np.average((residual / sigma) ** 2, weights=weights))
                ),
            )
        )
        derivative_at_tau[float(tau)] = derivative
    if not points:
        raise ValueError("prediction does not cover any configured delay for this interval")
    profile = tuple(points)
    best_index = min(
        range(len(profile)),
        key=lambda index: (
            profile[index].total_cost,
            abs(profile[index].tau_s - config.tau_prior_mean_s),
            profile[index].tau_s,
        ),
    )
    best = profile[best_index]
    derivative = derivative_at_tau[best.tau_s]
    base = weights / sigma**2
    centered = derivative - float(np.average(derivative, weights=base))
    information = float(np.sum(base * centered**2))
    diagnostics = _profile_diagnostics(
        profile,
        best_index,
        information=information,
        expected_count=len(tau_grid),
        config=config,
    )
    return IntervalScore(
        mode=mode,
        object_name=prediction.object_name,
        catalog_number=prediction.catalog_number,
        lane_id=lane_id,
        support=support,
        observation_ids=tuple(item.observation_id for item in ordered),
        profile=profile,
        best_index=best_index,
        fitted_tau_s=best.tau_s,
        fitted_cfo_offset_hz=best.fitted_nuisance if mode is ScoreMode.FREQUENCY else None,
        fitted_rate_nuisance_hz_s=best.fitted_nuisance if mode is ScoreMode.RATE else None,
        data_cost=best.data_cost,
        prior_cost=best.prior_cost,
        total_cost=best.total_cost,
        residual_rms=best.residual_rms,
        standardized_rms=best.standardized_rms,
        identifiability=diagnostics,
    )


def score_frequency_interval(
    probes: tuple[FrequencyProbe, ...],
    prediction: SatellitePrediction,
    config: SatelliteAssignmentConfig | None = None,
) -> IntervalScore:
    """Robustly profile one CFO offset and orbital delay over an eligible interval."""

    return _score_interval(
        probes,
        prediction,
        config or SatelliteAssignmentConfig(),
        ScoreMode.FREQUENCY,
    )


def score_rate_interval(
    probes: tuple[RateProbe, ...],
    prediction: SatellitePrediction,
    config: SatelliteAssignmentConfig | None = None,
) -> IntervalScore:
    """Profile delay and one bounded constant apparent-rate nuisance."""

    return _score_interval(
        probes,
        prediction,
        config or SatelliteAssignmentConfig(),
        ScoreMode.RATE,
    )


@dataclass(frozen=True, slots=True)
class _Choice:
    start: int
    stop: int
    catalog_number: int | None
    score: IntervalScore | None


@dataclass(frozen=True, slots=True)
class _State:
    cost: float
    satellite_segments: int
    assigned_groups: int
    signature: tuple[tuple[int, int, int], ...]
    choices: tuple[_Choice, ...]


def _state_key(state: _State) -> tuple[object, ...]:
    return state.cost, state.satellite_segments, state.assigned_groups, state.signature


def _probes_for_group_range(
    probes: tuple[Probe, ...], group_ids: tuple[str, ...], start: int, stop: int
) -> tuple[Probe, ...]:
    selected = set(group_ids[start:stop])
    return tuple(item for item in probes if item.source_group_id in selected)


def assign_duration_constrained(
    probes: tuple[Probe, ...],
    predictions: tuple[SatellitePrediction, ...],
    config: SatelliteAssignmentConfig | None = None,
) -> SatelliteAssignmentResult:
    """Assign one frozen radio-only lane using an exact segmental dynamic program.

    This is not a cross-lane global multi-target solution.  Candidate-rank
    exclusivity must be resolved by the upstream radio path cover or audited
    afterward with :func:`find_cross_lane_conflicts`.
    """

    selected_config = config or SatelliteAssignmentConfig()
    lane_id, source_times = _validate_probes(probes)
    if all(isinstance(item, FrequencyProbe) for item in probes):
        mode = ScoreMode.FREQUENCY
    elif all(isinstance(item, RateProbe) for item in probes):
        mode = ScoreMode.RATE
    else:
        raise TypeError("one assignment problem cannot mix frequency and rate probes")
    if len({item.catalog_number for item in predictions}) != len(predictions):
        raise ValueError("satellite prediction catalog numbers must be unique")
    ordered_predictions = tuple(
        sorted(predictions, key=lambda item: (item.catalog_number, item.object_name))
    )
    group_ids = tuple(source_times)
    count = len(group_ids)
    scores: dict[tuple[int, int, int], IntervalScore] = {}
    states = [_State(0.0, 0, 0, (), ())]
    for stop in range(1, count + 1):
        previous = states[stop - 1]
        candidates = [
            _State(
                cost=previous.cost + selected_config.unassigned_cost_per_group,
                satellite_segments=previous.satellite_segments,
                assigned_groups=previous.assigned_groups,
                signature=previous.signature + ((0, stop - 1, stop),),
                choices=previous.choices + (_Choice(stop - 1, stop, None, None),),
            )
        ]
        for start in range(stop):
            if (
                selected_config.maximum_segment_groups is not None
                and stop - start > selected_config.maximum_segment_groups
            ):
                continue
            interval = _probes_for_group_range(probes, group_ids, start, stop)
            support = interval_support(interval, selected_config)
            if not support.eligible:
                continue
            for prediction in ordered_predictions:
                try:
                    score = _score_interval(interval, prediction, selected_config, mode)
                except ValueError as error:
                    if "prediction does not cover" in str(error):
                        continue
                    raise
                scores[start, stop, prediction.catalog_number] = score
                prefix = states[start]
                cost = (
                    prefix.cost
                    + score.total_cost
                    + selected_config.satellite_activation_penalty_per_segment
                    + selected_config.segment_penalty
                )
                candidates.append(
                    _State(
                        cost=cost,
                        satellite_segments=prefix.satellite_segments + 1,
                        assigned_groups=prefix.assigned_groups + stop - start,
                        signature=prefix.signature + ((prediction.catalog_number, start, stop),),
                        choices=prefix.choices
                        + (_Choice(start, stop, prediction.catalog_number, score),),
                    )
                )
        states.append(min(candidates, key=_state_key))
    best = states[-1]

    collapsed: list[_Choice] = []
    for choice in best.choices:
        if (
            choice.catalog_number is None
            and collapsed
            and collapsed[-1].catalog_number is None
            and collapsed[-1].stop == choice.start
        ):
            prior = collapsed[-1]
            collapsed[-1] = _Choice(prior.start, choice.stop, None, None)
        else:
            collapsed.append(choice)
    segments = []
    for choice in collapsed:
        selected_groups = group_ids[choice.start : choice.stop]
        if choice.catalog_number is None:
            segments.append(
                AssignmentSegment(
                    state=AssignmentState.UNASSIGNED,
                    lane_id=lane_id,
                    source_group_ids=selected_groups,
                    start_s=source_times[selected_groups[0]],
                    end_s=source_times[selected_groups[-1]],
                    catalog_number=None,
                    object_name=None,
                    interval_score=None,
                    runner_up_catalog_number=None,
                    runner_up_cost_margin=None,
                )
            )
            continue
        choice_score = choice.score
        if choice_score is None:
            raise RuntimeError("satellite choice is missing its interval score")
        alternatives = sorted(
            (
                item
                for (start, stop, catalog), item in scores.items()
                if start == choice.start
                and stop == choice.stop
                and catalog != choice.catalog_number
            ),
            key=lambda item: (item.total_cost, item.catalog_number),
        )
        runner = alternatives[0] if alternatives else None
        segments.append(
            AssignmentSegment(
                state=AssignmentState.SATELLITE,
                lane_id=lane_id,
                source_group_ids=selected_groups,
                start_s=source_times[selected_groups[0]],
                end_s=source_times[selected_groups[-1]],
                catalog_number=choice.catalog_number,
                object_name=choice_score.object_name,
                interval_score=choice_score,
                runner_up_catalog_number=None if runner is None else runner.catalog_number,
                runner_up_cost_margin=(
                    None if runner is None else runner.total_cost - choice_score.total_cost
                ),
            )
        )
    segment_tuple = tuple(segments)
    shared = []
    by_catalog = {item.catalog_number: item for item in ordered_predictions}
    for catalog_number in sorted(
        {item.catalog_number for item in segment_tuple if item.catalog_number is not None}
    ):
        shared.append(
            refit_shared_satellite_delay(
                segment_tuple,
                probes,
                by_catalog[catalog_number],
                selected_config,
            )
        )
    satellite_scores = tuple(
        item.interval_score for item in segment_tuple if item.interval_score is not None
    )
    data_cost = math.fsum(item.data_cost for item in satellite_scores)
    prior_cost = math.fsum(item.prior_cost for item in satellite_scores)
    model_cost = len(satellite_scores) * (
        selected_config.satellite_activation_penalty_per_segment + selected_config.segment_penalty
    )
    unassigned_groups = sum(
        len(item.source_group_ids)
        for item in segment_tuple
        if item.state is AssignmentState.UNASSIGNED
    )
    unassigned_cost = unassigned_groups * selected_config.unassigned_cost_per_group
    objective = AssignmentObjective(
        satellite_data_cost=data_cost,
        delay_prior_cost=prior_cost,
        model_penalty=model_cost,
        unassigned_cost=unassigned_cost,
        total_cost=data_cost + prior_cost + model_cost + unassigned_cost,
    )
    if not math.isclose(objective.total_cost, best.cost, rel_tol=1e-12, abs_tol=1e-9):
        raise RuntimeError("assignment objective disagrees with dynamic-program cost")
    return SatelliteAssignmentResult(
        lane_id=lane_id,
        mode=mode,
        source_group_count=count,
        segments=segment_tuple,
        shared_satellite_refits=tuple(shared),
        objective=objective,
    )


def refit_shared_satellite_delay(
    segments: tuple[AssignmentSegment, ...],
    probes: tuple[Probe, ...],
    prediction: SatellitePrediction,
    config: SatelliteAssignmentConfig,
) -> SharedSatelliteRefit:
    """Profile one shared delay across this object's selected lane episodes.

    Every episode retains its own CFO offset or rate nuisance.  The result is a
    diagnostic refit and does not silently rewrite the dynamic-program objective.
    """

    chosen = tuple(
        (index, segment)
        for index, segment in enumerate(segments)
        if segment.catalog_number == prediction.catalog_number
        and segment.state is AssignmentState.SATELLITE
    )
    if not chosen:
        raise ValueError("shared-delay refit has no selected episode for this satellite")
    lane_id, _source_times = _validate_probes(probes)
    if any(segment.lane_id != lane_id for _index, segment in chosen):
        raise ValueError("shared-delay refit segments and probes disagree on lane")
    mode = chosen[0][1].interval_score.mode  # type: ignore[union-attr]
    prediction_times, predicted_values, predicted_derivative = _prediction_arrays(prediction, mode)
    tau_grid = config.tau_grid()
    profile = []
    information_at_tau: dict[float, float] = {}
    for tau in tau_grid:
        nuisances = []
        total_data = 0.0
        total_information = 0.0
        valid = True
        for segment_index, segment in chosen:
            selected = set(segment.source_group_ids)
            episode = tuple(item for item in probes if item.source_group_id in selected)
            ordered = tuple(sorted(episode, key=lambda item: (item.time_s, item.observation_id)))
            times: np.ndarray = np.asarray([item.time_s for item in ordered], dtype=np.float64)
            query = times + float(tau)
            predicted = _interpolate(prediction_times, predicted_values, query)
            derivative = _interpolate(prediction_times, predicted_derivative, query)
            if predicted is None or derivative is None:
                valid = False
                break
            if mode is ScoreMode.FREQUENCY:
                frequency_ordered = cast(tuple[FrequencyProbe, ...], ordered)
                observed: np.ndarray = np.asarray(
                    [item.cfo_hz for item in frequency_ordered], dtype=np.float64
                )
                sigma: np.ndarray = np.asarray(
                    [item.sigma_hz for item in frequency_ordered], dtype=np.float64
                )
                bounds = config.cfo_offset_bounds_hz
            else:
                rate_ordered = cast(tuple[RateProbe, ...], ordered)
                observed = np.asarray([item.rate_hz_s for item in rate_ordered], dtype=np.float64)
                sigma = np.asarray([item.sigma_hz_s for item in rate_ordered], dtype=np.float64)
                bounds = config.rate_nuisance_bounds_hz_s
            weights = _effective_weights(ordered, config.maximum_source_group_weight)
            nuisance, at_bound, _residual, cost = _fit_location(
                observed - predicted,
                sigma,
                weights,
                bounds=bounds,
                config=config,
            )
            nuisances.append(SharedEpisodeNuisance(segment_index, nuisance, at_bound))
            total_data += cost
            base = weights / sigma**2
            centered = derivative - float(np.average(derivative, weights=base))
            total_information += float(np.sum(base * centered**2))
        if valid:
            prior = _prior_cost(float(tau), config)
            profile.append(
                SharedDelayProfilePoint(
                    tau_s=float(tau),
                    episode_nuisances=tuple(nuisances),
                    data_cost=total_data,
                    prior_cost=prior,
                    total_cost=total_data + prior,
                )
            )
            information_at_tau[float(tau)] = total_information
    if not profile:
        raise ValueError("prediction does not cover any shared-delay profile point")
    result = tuple(profile)
    best_index = min(
        range(len(result)),
        key=lambda index: (
            result[index].total_cost,
            abs(result[index].tau_s - config.tau_prior_mean_s),
            result[index].tau_s,
        ),
    )
    # Reuse the common diagnostics through nuisance summaries.  Residual-only
    # fields are immaterial here; costs and nuisance-vs-delay are exact.
    diagnostic_points = tuple(
        DelayProfilePoint(
            tau_s=item.tau_s,
            fitted_nuisance=float(
                np.mean([nuisance.fitted_nuisance for nuisance in item.episode_nuisances])
            ),
            nuisance_at_bound=any(
                nuisance.nuisance_at_bound for nuisance in item.episode_nuisances
            ),
            data_cost=item.data_cost,
            prior_cost=item.prior_cost,
            total_cost=item.total_cost,
            residual_rms=math.nan,
            standardized_rms=math.nan,
        )
        for item in result
    )
    best = result[best_index]
    diagnostics = _profile_diagnostics(
        diagnostic_points,
        best_index,
        information=information_at_tau[best.tau_s],
        expected_count=len(tau_grid),
        config=config,
    )
    return SharedSatelliteRefit(
        mode=mode,
        object_name=prediction.object_name,
        catalog_number=prediction.catalog_number,
        segment_indices=tuple(index for index, _segment in chosen),
        profile=result,
        best_index=best_index,
        fitted_tau_s=best.tau_s,
        episode_nuisances=best.episode_nuisances,
        identifiability=diagnostics,
    )


def find_cross_lane_conflicts(
    results: tuple[SatelliteAssignmentResult, ...],
) -> tuple[CrossLaneConflict, ...]:
    """Audit, but do not resolve, duplicate source-group assignments across lanes.

    Callers must use capture-global source-group identities for this audit to be
    meaningful.  Returning no conflicts does not turn lane-local optimization
    into a globally exclusive multi-target solution.
    """

    ownership: dict[str, set[tuple[str, int]]] = {}
    for result in results:
        for segment in result.segments:
            if segment.catalog_number is None:
                continue
            for source_group_id in segment.source_group_ids:
                ownership.setdefault(source_group_id, set()).add(
                    (result.lane_id, segment.catalog_number)
                )
    return tuple(
        CrossLaneConflict(source_group_id, tuple(sorted(owners)))
        for source_group_id, owners in sorted(ownership.items())
        if len(owners) > 1
    )
