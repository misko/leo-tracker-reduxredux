"""Bounded multi-method polynomial CFO trajectory fitting and correction."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.contracts.digests import canonical_digest


@dataclass(frozen=True, slots=True)
class TrajectoryObservation:
    observation_id: str
    method: PilotMethod
    sample_start: int
    time_s: float
    tracking_cfo_hz: float
    score: float
    control_score: float | None
    margin: float

    def __post_init__(self) -> None:
        if not self.observation_id or self.sample_start < 0:
            raise ValueError("trajectory observation identity is invalid")
        values = (self.time_s, self.tracking_cfo_hz, self.score, self.margin)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("trajectory observation values must be finite")
        if self.control_score is not None and not math.isfinite(self.control_score):
            raise ValueError("trajectory control score must be finite")


@dataclass(frozen=True, slots=True)
class TrajectoryMethodConfig:
    method: PilotMethod
    high_gate: float | None = None
    low_gate: float = 0.0
    negative_tail_sigma_multiplier: float = 5.0
    local_residual_gate_hz: float = 8_000.0
    final_residual_gate_hz: float = 8_000.0
    minimum_local_points: int = 6
    minimum_high_points: int = 2
    maximum_merge_gap_s: float = 1.0
    endpoint_gate_hz: float = 12_000.0
    endpoint_growth_hz_per_s: float = 5_000.0
    maximum_slope_difference_hz_per_s: float = 30_000.0

    def __post_init__(self) -> None:
        finite = (
            self.low_gate,
            self.negative_tail_sigma_multiplier,
            self.local_residual_gate_hz,
            self.final_residual_gate_hz,
            self.maximum_merge_gap_s,
            self.endpoint_gate_hz,
            self.endpoint_growth_hz_per_s,
            self.maximum_slope_difference_hz_per_s,
        )
        if any(not math.isfinite(value) for value in finite):
            raise ValueError("trajectory method configuration must be finite")
        if self.high_gate is not None and not math.isfinite(self.high_gate):
            raise ValueError("trajectory high gate must be finite")
        positive = finite[1:]
        if any(value <= 0 for value in positive):
            raise ValueError("trajectory method bounds must be positive")
        if self.minimum_local_points < 2 or self.minimum_high_points < 1:
            raise ValueError("trajectory support counts are invalid")
        if self.minimum_high_points > self.minimum_local_points:
            raise ValueError("high-point requirement exceeds local support")


@dataclass(frozen=True, slots=True)
class TrajectoryBankConfig:
    methods: tuple[TrajectoryMethodConfig, ...]
    polynomial_degrees: tuple[int, ...] = (1, 2, 3)
    local_window_s: float = 1.0
    minimum_final_duration_s: float = 1.5
    em_extension_s: float = 0.35
    maximum_em_iterations: int = 12
    maximum_trajectories: int = 256
    deduplication_overlap_fraction: float = 0.70
    deduplication_frequency_gate_hz: float = 5_000.0

    def __post_init__(self) -> None:
        if not self.methods or len({item.method for item in self.methods}) != len(self.methods):
            raise ValueError("trajectory method configurations must be nonempty and unique")
        if not self.polynomial_degrees or any(
            degree not in (1, 2, 3) for degree in self.polynomial_degrees
        ):
            raise ValueError("trajectory polynomial degrees must lie in 1..3")
        if len(set(self.polynomial_degrees)) != len(self.polynomial_degrees):
            raise ValueError("trajectory polynomial degrees must be unique")
        positive = (
            self.local_window_s,
            self.minimum_final_duration_s,
            self.em_extension_s,
            self.deduplication_frequency_gate_hz,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("trajectory bank bounds must be finite and positive")
        if not 0 < self.deduplication_overlap_fraction <= 1:
            raise ValueError("trajectory deduplication overlap must lie in (0,1]")
        if self.maximum_em_iterations < 1 or self.maximum_trajectories < 1:
            raise ValueError("trajectory iteration and count budgets must be positive")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class PolynomialTrajectory:
    trajectory_id: str
    method: PilotMethod
    polynomial_degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    start_s: float
    end_s: float
    observation_ids: tuple[str, ...]
    point_count: int
    residual_rms_hz: float
    bic: float
    high_gate: float
    em_iterations: int
    candidate_only: bool = True

    def __post_init__(self) -> None:
        if self.polynomial_degree not in (1, 2, 3):
            raise ValueError("trajectory degree must lie in 1..3")
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("trajectory coefficient count differs from its degree")
        if self.start_s > self.end_s or self.point_count != len(self.observation_ids):
            raise ValueError("trajectory support geometry is invalid")
        values = (
            self.reference_time_s,
            self.start_s,
            self.end_s,
            self.residual_rms_hz,
            self.bic,
            self.high_gate,
            *self.coefficients_hz,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("trajectory model values must be finite")

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )

    def phase_cycles(self, time_s: np.ndarray | float) -> np.ndarray:
        delta = np.asarray(time_s, dtype=float) - self.reference_time_s
        integral = np.polyint(np.asarray(self.coefficients_hz, dtype=float))
        return np.polyval(integral, delta) - np.polyval(integral, 0.0)


@dataclass(frozen=True, slots=True)
class TrajectoryFamily:
    family_id: str
    representative_trajectory_id: str
    member_trajectory_ids: tuple[str, ...]
    start_s: float
    end_s: float


@dataclass(frozen=True, slots=True)
class TrajectoryBankResult:
    config_digest: str
    trajectories: tuple[PolynomialTrajectory, ...]
    families: tuple[TrajectoryFamily, ...]
    observation_count: int
    truncated_trajectory_count: int
    candidate_only: bool = True


def default_trajectory_bank_config() -> TrajectoryBankConfig:
    residual_methods = {
        PilotMethod.DIFFERENTIAL16,
        PilotMethod.DIFFERENTIAL32,
        PilotMethod.GLRT32,
        PilotMethod.GLRT64,
    }
    methods = []
    for method in PilotMethod:
        residual = method in residual_methods
        methods.append(
            TrajectoryMethodConfig(
                method=method,
                high_gate=0.60 if method is PilotMethod.QAM_ACCURACY else None,
                low_gate=0.45 if method is PilotMethod.QAM_ACCURACY else 0.0,
                local_residual_gate_hz=2_500.0 if residual else 8_000.0,
                final_residual_gate_hz=2_500.0 if residual else 8_000.0,
                minimum_local_points=5 if residual else 6,
                minimum_high_points=2,
                maximum_merge_gap_s=1.10 if residual else 1.0,
                endpoint_gate_hz=4_000.0 if residual else 12_000.0,
                endpoint_growth_hz_per_s=3_000.0 if residual else 5_000.0,
                maximum_slope_difference_hz_per_s=20_000.0 if residual else 30_000.0,
            )
        )
    return TrajectoryBankConfig(tuple(methods))


def fit_trajectory_bank(
    observations: tuple[TrajectoryObservation, ...],
    config: TrajectoryBankConfig,
) -> TrajectoryBankResult:
    """Run local seeding, iterative merging, and hard EM for all methods/degrees."""

    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("trajectory observation IDs must be unique")
    by_method = {
        method_config.method: tuple(
            sorted(
                (item for item in observations if item.method is method_config.method),
                key=lambda item: (item.time_s, item.observation_id),
            )
        )
        for method_config in config.methods
    }
    trajectories: list[PolynomialTrajectory] = []
    for method_config in config.methods:
        method_observations = by_method[method_config.method]
        if not method_observations:
            continue
        high_gate = _high_gate(method_observations, method_config)
        for degree in config.polynomial_degrees:
            trajectories.extend(
                _fit_method_degree(
                    method_observations,
                    method_config,
                    config,
                    high_gate,
                    degree,
                )
            )
    trajectories.sort(
        key=lambda item: (
            item.start_s,
            item.end_s,
            item.method.value,
            item.polynomial_degree,
            item.trajectory_id,
        )
    )
    truncated = max(0, len(trajectories) - config.maximum_trajectories)
    retained = tuple(trajectories[: config.maximum_trajectories])
    return TrajectoryBankResult(
        config.digest,
        retained,
        _trajectory_families(retained, config),
        len(observations),
        truncated,
    )


def correct_polynomial_cfo(
    samples: np.ndarray,
    sample_rate_hz: float,
    absolute_sample_start: int,
    trajectory: PolynomialTrajectory,
    *,
    frequency_offset_hz: float = 0.0,
) -> np.ndarray:
    """Return a phase-continuous trajectory-dechirped copy of one IQ block.

    ``frequency_offset_hz`` resolves a constant integer alias lift without
    mutating the canonical modulo-alias trajectory or its persisted identity.
    """

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1:
        raise ValueError("trajectory correction requires one-dimensional IQ")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if absolute_sample_start < 0:
        raise ValueError("absolute sample start must be nonnegative")
    if not math.isfinite(frequency_offset_hz):
        raise ValueError("trajectory frequency offset must be finite")
    times = (absolute_sample_start + np.arange(len(values), dtype=float)) / sample_rate_hz
    lifted_phase_cycles = trajectory.phase_cycles(times) + frequency_offset_hz * (
        times - trajectory.reference_time_s
    )
    corrected = values * np.exp(-2j * np.pi * lifted_phase_cycles)
    return np.ascontiguousarray(corrected)


def _high_gate(
    observations: tuple[TrajectoryObservation, ...], config: TrajectoryMethodConfig
) -> float:
    if config.high_gate is not None:
        return config.high_gate
    negative = np.abs(np.asarray([item.margin for item in observations if item.margin < 0]))
    if not len(negative):
        return math.inf
    sigma = float(np.median(negative) / 0.6744897501960817)
    return config.negative_tail_sigma_multiplier * sigma


def _fit_method_degree(
    observations: tuple[TrajectoryObservation, ...],
    method_config: TrajectoryMethodConfig,
    bank_config: TrajectoryBankConfig,
    high_gate: float,
    degree: int,
) -> tuple[PolynomialTrajectory, ...]:
    times = np.asarray([item.time_s for item in observations])
    frequency = np.asarray([item.tracking_cfo_hz for item in observations])
    margins = np.asarray([item.margin for item in observations])
    low = margins >= method_config.low_gate
    high = margins >= high_gate
    seeds = []
    first_window = math.floor(float(times.min()) / bank_config.local_window_s)
    final_window = math.ceil(float(times.max()) / bank_config.local_window_s)
    for window in range(first_window, final_window + 1):
        start = window * bank_config.local_window_s
        indexes = np.flatnonzero(
            (times >= start) & (times < start + bank_config.local_window_s) & low
        )
        seed = _local_seed(
            indexes,
            times,
            frequency,
            high,
            method_config,
        )
        if seed is not None:
            seeds.append(seed)
    merged = _merge_groups(seeds, times, frequency, method_config, degree)
    merged = [
        group
        for group in merged
        if float(times[group].max() - times[group].min()) >= bank_config.minimum_final_duration_s
    ]
    refined, iterations = _hard_em(
        merged,
        times,
        frequency,
        low,
        method_config,
        bank_config,
        degree,
    )
    result = []
    for group in refined:
        reference, coefficients, rms = _fit(group, times, frequency, degree)
        bic = _bic(group, times, frequency, degree)
        document = {
            "method": method_config.method.value,
            "degree": degree,
            "reference_time_s": round(reference, 12),
            "coefficients_hz": [round(float(value), 12) for value in coefficients],
            "observation_ids": [observations[int(index)].observation_id for index in group],
        }
        result.append(
            PolynomialTrajectory(
                canonical_digest(document),
                method_config.method,
                degree,
                reference,
                tuple(float(value) for value in coefficients),
                float(times[group].min()),
                float(times[group].max()),
                tuple(observations[int(index)].observation_id for index in group),
                len(group),
                rms,
                bic,
                high_gate,
                iterations,
            )
        )
    return tuple(result)


def _local_seed(indexes, times, frequency, high, config):
    if len(indexes) < config.minimum_local_points:
        return None
    best = None
    for left_position in range(len(indexes)):
        for right_position in range(left_position + 1, len(indexes)):
            left, right = int(indexes[left_position]), int(indexes[right_position])
            if times[right] - times[left] < 0.15:
                continue
            slope = (frequency[right] - frequency[left]) / (times[right] - times[left])
            prediction = frequency[left] + slope * (times[indexes] - times[left])
            inliers = indexes[
                np.abs(frequency[indexes] - prediction) <= config.local_residual_gate_hz
            ]
            high_count = int(np.count_nonzero(high[inliers]))
            if (
                len(inliers) < config.minimum_local_points
                or high_count < config.minimum_high_points
            ):
                continue
            rms = _fit(inliers, times, frequency, 1)[2]
            key = (len(inliers), high_count, -rms)
            if best is None or key > best[0]:
                best = key, inliers
    if best is None:
        return None
    return np.asarray(sorted(int(index) for index in best[1]), dtype=int)


def _fit(indexes, times, frequency, degree):
    selected_times = times[indexes]
    reference = float(np.mean(selected_times))
    coefficients = np.polyfit(
        selected_times - reference,
        frequency[indexes],
        min(degree, len(indexes) - 1),
    )
    residual = frequency[indexes] - np.polyval(coefficients, selected_times - reference)
    return reference, coefficients, float(np.sqrt(np.mean(residual**2)))


def _bic(indexes, times, frequency, degree):
    _, _, rms = _fit(indexes, times, frequency, degree)
    count = len(indexes)
    parameters = min(degree, count - 1) + 1
    variance = max(rms**2, np.finfo(float).tiny)
    return float(count * math.log(variance) + parameters * math.log(count))


def _predict(model, values):
    reference, coefficients, _ = model
    return np.polyval(coefficients, np.asarray(values) - reference)


def _merge_groups(groups, times, frequency, config, degree):
    groups = list(groups)
    while True:
        best = None
        for left_index, left in enumerate(groups):
            left_model = _fit(left, times, frequency, 1)
            left_slope = float(left_model[1][0])
            for right_index, right in enumerate(groups):
                if times[right].min() <= times[left].max():
                    continue
                gap = float(times[right].min() - times[left].max())
                if gap > config.maximum_merge_gap_s:
                    continue
                right_model = _fit(right, times, frequency, 1)
                right_slope = float(right_model[1][0])
                if abs(left_slope - right_slope) > config.maximum_slope_difference_hz_per_s:
                    continue
                right_start = float(times[right].min())
                endpoint_residual = abs(
                    float(_predict(left_model, right_start) - _predict(right_model, right_start))
                )
                endpoint_gate = config.endpoint_gate_hz + config.endpoint_growth_hz_per_s * gap
                if endpoint_residual > endpoint_gate:
                    continue
                combined = np.unique(np.concatenate((left, right)))
                combined_rms = _fit(combined, times, frequency, degree)[2]
                if combined_rms > config.final_residual_gate_hz:
                    continue
                cost = (
                    endpoint_residual / endpoint_gate
                    + combined_rms / config.final_residual_gate_hz
                    + gap / config.maximum_merge_gap_s
                )
                if best is None or cost < best[0]:
                    best = cost, left_index, right_index, combined
        if best is None:
            return groups
        _, left_index, right_index, combined = best
        groups[left_index] = combined
        del groups[right_index]


def _hard_em(groups, times, frequency, low, method_config, bank_config, degree):
    previous = None
    for iteration in range(1, bank_config.maximum_em_iterations + 1):
        models = [_fit(group, times, frequency, degree) for group in groups]
        assignments: list[list[int]] = [[] for _ in groups]
        for index in np.flatnonzero(low):
            options = []
            for track_index, (group, model) in enumerate(zip(groups, models, strict=True)):
                if (
                    times[index] < times[group].min() - bank_config.em_extension_s
                    or times[index] > times[group].max() + bank_config.em_extension_s
                ):
                    continue
                residual = abs(float(frequency[index] - _predict(model, times[index])))
                if residual <= method_config.final_residual_gate_hz:
                    options.append((residual, track_index))
            if options:
                assignments[min(options)[1]].append(int(index))
        updated = [
            np.asarray(indexes, dtype=int)
            for indexes in assignments
            if len(indexes) >= method_config.minimum_local_points
        ]
        state = tuple(tuple(int(index) for index in group) for group in updated)
        groups = updated
        if state == previous:
            return groups, iteration
        previous = state
    return groups, bank_config.maximum_em_iterations


def _trajectory_families(
    trajectories: tuple[PolynomialTrajectory, ...], config: TrajectoryBankConfig
) -> tuple[TrajectoryFamily, ...]:
    groups: list[list[PolynomialTrajectory]] = []
    for trajectory in trajectories:
        matches = [
            group
            for group in groups
            if any(_same_family(trajectory, member, config) for member in group)
        ]
        if not matches:
            groups.append([trajectory])
            continue
        target = matches[0]
        target.append(trajectory)
        for extra in matches[1:]:
            target.extend(extra)
            groups.remove(extra)
    result = []
    for group in groups:
        group.sort(
            key=lambda item: (
                -(item.end_s - item.start_s),
                -item.point_count,
                item.bic / item.point_count,
                item.polynomial_degree,
                item.trajectory_id,
            )
        )
        members = tuple(item.trajectory_id for item in group)
        result.append(
            TrajectoryFamily(
                canonical_digest({"members": members}),
                group[0].trajectory_id,
                members,
                min(item.start_s for item in group),
                max(item.end_s for item in group),
            )
        )
    result.sort(key=lambda item: (item.start_s, item.end_s, item.family_id))
    return tuple(result)


def _same_family(
    left: PolynomialTrajectory,
    right: PolynomialTrajectory,
    config: TrajectoryBankConfig,
) -> bool:
    overlap_start = max(left.start_s, right.start_s)
    overlap_end = min(left.end_s, right.end_s)
    if overlap_end <= overlap_start:
        return False
    overlap = overlap_end - overlap_start
    shorter = min(left.end_s - left.start_s, right.end_s - right.start_s)
    if overlap / max(shorter, np.finfo(float).eps) < config.deduplication_overlap_fraction:
        return False
    grid = np.linspace(overlap_start, overlap_end, 17)
    difference = np.median(np.abs(left.frequency_hz(grid) - right.frequency_hz(grid)))
    return bool(difference <= config.deduplication_frequency_gate_hz)
