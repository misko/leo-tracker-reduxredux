"""Bounded offline line detectors for persisted GLRT64 CFO point clouds.

This module is deliberately outside the Standard analyzer registry.  Frequencies are
compared modulo the OFDM-symbol alias spacing, so one physical line may be supported
by observations on several raw CFO aliases without duplicating its probe support.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np

Algorithm = Literal["weighted_hough", "robust_ransac", "dynamic_programming"]


@dataclass(frozen=True, slots=True)
class CfoPoint:
    """One independently searched GLRT64 candidate."""

    point_id: str
    time_s: float
    frequency_hz: float
    exact_score: float
    control_score: float
    margin: float

    @property
    def weight(self) -> float:
        """Control-normalized non-negative evidence weight, bounded against outliers."""

        separation = max(self.margin, 0.0)
        return min(separation / max(self.control_score, 0.02), 16.0)


@dataclass(frozen=True, slots=True)
class LineDetectionConfig:
    """Frozen common bounds shared by all offline detectors."""

    alias_spacing_hz: float = 1.0 / 4.4e-6
    minimum_slope_hz_per_s: float = -15_000.0
    maximum_slope_hz_per_s: float = 15_000.0
    residual_gate_hz: float = 2_500.0
    maximum_gap_s: float = 0.75
    minimum_span_s: float = 0.75
    minimum_support: int = 8
    minimum_point_weight: float = 0.5
    maximum_tracks: int = 12


@dataclass(frozen=True, slots=True)
class LineSegment:
    """Deterministic, alias-aware line segment returned by an offline detector."""

    algorithm: Algorithm
    segment_id: str
    point_ids: tuple[str, ...]
    start_s: float
    end_s: float
    support: int
    weighted_support: float
    slope_hz_per_s: float
    intercept_hz: float
    intercept_mod_alias_hz: float
    residual_rms_hz: float
    residual_max_hz: float
    maximum_gap_s: float


@dataclass(frozen=True, slots=True)
class HoughConfig:
    common: LineDetectionConfig = LineDetectionConfig()
    slope_bins: int = 121
    intercept_bins: int = 512
    peak_candidates: int = 16


@dataclass(frozen=True, slots=True)
class RansacConfig:
    common: LineDetectionConfig = LineDetectionConfig()
    maximum_hypotheses: int = 2_000
    minimum_pair_separation_s: float = 0.5
    alias_delta_limit: int = 3


@dataclass(frozen=True, slots=True)
class DynamicProgrammingConfig:
    common: LineDetectionConfig = LineDetectionConfig(minimum_point_weight=0.02, maximum_tracks=6)
    slope_bins: int = 61
    maximum_candidates_per_time: int = 3
    maximum_predecessor_groups: int = 8
    transition_penalty: float = 0.35
    gap_penalty_per_s: float = 0.10
    point_cost: float = 0.015


_DEFAULT_HOUGH_CONFIG = HoughConfig()
_DEFAULT_RANSAC_CONFIG = RansacConfig()
_DEFAULT_DYNAMIC_PROGRAMMING_CONFIG = DynamicProgrammingConfig()


def canonical_points(points: tuple[CfoPoint, ...]) -> tuple[CfoPoint, ...]:
    """Validate and canonicalize input order, making permutation behavior invariant."""

    ordered = tuple(
        sorted(points, key=lambda item: (item.time_s, item.frequency_hz, item.point_id))
    )
    if len({point.point_id for point in ordered}) != len(ordered):
        raise ValueError("CFO point identifiers must be unique")
    values = np.asarray(
        [
            value
            for point in ordered
            for value in (
                point.time_s,
                point.frequency_hz,
                point.exact_score,
                point.control_score,
                point.margin,
            )
        ]
    )
    if not np.all(np.isfinite(values)):
        raise ValueError("CFO points must contain only finite values")
    return ordered


def circular_residual_hz(
    frequency_hz: np.ndarray,
    prediction_hz: np.ndarray,
    alias_spacing_hz: float,
) -> np.ndarray:
    """Signed shortest residual on the CFO alias circle."""

    return (
        frequency_hz - prediction_hz + alias_spacing_hz / 2.0
    ) % alias_spacing_hz - alias_spacing_hz / 2.0


def _arrays(
    points: tuple[CfoPoint, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.asarray([point.time_s for point in points], dtype=float),
        np.asarray([point.frequency_hz for point in points], dtype=float),
        np.asarray([point.weight for point in points], dtype=float),
    )


def _time_key(time_s: float) -> int:
    return int(round(time_s * 1_000_000_000.0))


def _one_per_time(
    indexes: np.ndarray,
    points: tuple[CfoPoint, ...],
    residual: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    best: dict[int, int] = {}
    for raw_index in indexes:
        index = int(raw_index)
        key = _time_key(points[index].time_s)
        previous = best.get(key)
        rank = (-weights[index], abs(residual[index]), points[index].point_id)
        if previous is None:
            best[key] = index
            continue
        previous_rank = (
            -weights[previous],
            abs(residual[previous]),
            points[previous].point_id,
        )
        if rank < previous_rank:
            best[key] = index
    return np.asarray(sorted(best.values(), key=lambda i: (points[i].time_s, points[i].point_id)))


def _split_contiguous(
    indexes: np.ndarray,
    times: np.ndarray,
    maximum_gap_s: float,
) -> tuple[np.ndarray, ...]:
    if not indexes.size:
        return ()
    ordered = indexes[np.argsort(times[indexes], kind="stable")]
    cuts = np.flatnonzero(np.diff(times[ordered]) > maximum_gap_s) + 1
    return tuple(part for part in np.split(ordered, cuts) if part.size)


def _fit_alias_line(
    indexes: np.ndarray,
    points: tuple[CfoPoint, ...],
    *,
    initial_slope: float,
    initial_intercept: float,
    alias_spacing_hz: float,
    algorithm: Algorithm,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> LineSegment:
    times, frequency, weights = arrays
    selected_times = times[indexes]
    selected_frequency = frequency[indexes]
    selected_weights = np.maximum(weights[indexes], np.finfo(float).eps)
    t0 = float(np.average(selected_times, weights=selected_weights))
    slope = float(initial_slope)
    intercept_at_t0 = float(initial_intercept + initial_slope * t0)
    for _ in range(4):
        prediction = intercept_at_t0 + slope * (selected_times - t0)
        lifted = (
            selected_frequency
            - np.round((selected_frequency - prediction) / alias_spacing_hz) * alias_spacing_hz
        )
        design = np.column_stack((selected_times - t0, np.ones(selected_times.size)))
        scaled = design * np.sqrt(selected_weights)[:, None]
        target = lifted * np.sqrt(selected_weights)
        coefficients, *_ = np.linalg.lstsq(scaled, target, rcond=None)
        slope, intercept_at_t0 = (float(value) for value in coefficients)
    # Hough geometry is defined modulo the pilot-alias spacing.  Canonicalize
    # the fitted global intercept before it becomes persisted trajectory
    # evidence so a round-to-nearest boundary cannot select a neighboring,
    # mathematically equivalent alias when score weights change by a few ulps.
    intercept = float((intercept_at_t0 - slope * t0) % alias_spacing_hz)
    residual = circular_residual_hz(
        selected_frequency,
        slope * selected_times + intercept,
        alias_spacing_hz,
    )
    point_ids = tuple(points[int(index)].point_id for index in indexes)
    identity = hashlib.sha256((algorithm + "\0" + "\0".join(point_ids)).encode("utf-8")).hexdigest()
    gaps = np.diff(selected_times)
    return LineSegment(
        algorithm=algorithm,
        segment_id=f"sha256:{identity}",
        point_ids=point_ids,
        start_s=float(np.min(selected_times)),
        end_s=float(np.max(selected_times)),
        support=int(indexes.size),
        weighted_support=float(np.sum(selected_weights)),
        slope_hz_per_s=slope,
        intercept_hz=intercept,
        intercept_mod_alias_hz=intercept,
        residual_rms_hz=float(np.sqrt(np.average(residual**2, weights=selected_weights))),
        residual_max_hz=float(np.max(np.abs(residual))),
        maximum_gap_s=float(np.max(gaps)) if gaps.size else 0.0,
    )


def _candidate_segments(
    points: tuple[CfoPoint, ...],
    available: np.ndarray,
    *,
    slope: float,
    intercept: float,
    common: LineDetectionConfig,
    algorithm: Algorithm,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[tuple[LineSegment, np.ndarray], ...]:
    times, frequency, weights = arrays
    residual = circular_residual_hz(
        frequency,
        slope * times + intercept,
        common.alias_spacing_hz,
    )
    raw = np.flatnonzero(
        available
        & (weights >= common.minimum_point_weight)
        & (np.abs(residual) <= common.residual_gate_hz)
    )
    unique = _one_per_time(raw, points, residual, weights)
    result: list[tuple[LineSegment, np.ndarray]] = []
    for contiguous in _split_contiguous(unique, times, common.maximum_gap_s):
        span = float(times[contiguous[-1]] - times[contiguous[0]])
        if contiguous.size < common.minimum_support or span < common.minimum_span_s:
            continue
        segment = _fit_alias_line(
            contiguous,
            points,
            initial_slope=slope,
            initial_intercept=intercept,
            alias_spacing_hz=common.alias_spacing_hz,
            algorithm=algorithm,
            arrays=arrays,
        )
        if not (
            common.minimum_slope_hz_per_s <= segment.slope_hz_per_s <= common.maximum_slope_hz_per_s
        ):
            continue
        refined_residual = circular_residual_hz(
            frequency,
            segment.slope_hz_per_s * times + segment.intercept_hz,
            common.alias_spacing_hz,
        )
        refined_raw = np.flatnonzero(
            available
            & (weights >= common.minimum_point_weight)
            & (times >= segment.start_s)
            & (times <= segment.end_s)
            & (np.abs(refined_residual) <= common.residual_gate_hz)
        )
        refined = _one_per_time(refined_raw, points, refined_residual, weights)
        for refined_contiguous in _split_contiguous(refined, times, common.maximum_gap_s):
            refined_span = float(times[refined_contiguous[-1]] - times[refined_contiguous[0]])
            if (
                refined_contiguous.size < common.minimum_support
                or refined_span < common.minimum_span_s
            ):
                continue
            refined_segment = _fit_alias_line(
                refined_contiguous,
                points,
                initial_slope=segment.slope_hz_per_s,
                initial_intercept=segment.intercept_hz,
                alias_spacing_hz=common.alias_spacing_hz,
                algorithm=algorithm,
                arrays=arrays,
            )
            result.append((refined_segment, refined_contiguous))
    return tuple(result)


def _segment_rank(item: tuple[LineSegment, np.ndarray]) -> tuple[float, float, int, float, str]:
    segment = item[0]
    return (
        segment.weighted_support,
        segment.end_s - segment.start_s,
        segment.support,
        -segment.residual_rms_hz,
        segment.segment_id,
    )


def _peel_alias_support(
    available: np.ndarray,
    points: tuple[CfoPoint, ...],
    segment: LineSegment,
    common: LineDetectionConfig,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> None:
    times, frequency, _ = arrays
    residual = circular_residual_hz(
        frequency,
        segment.slope_hz_per_s * times + segment.intercept_hz,
        common.alias_spacing_hz,
    )
    available[
        (times >= segment.start_s)
        & (times <= segment.end_s)
        & (np.abs(residual) <= common.residual_gate_hz)
    ] = False


def weighted_hough_lines(
    points: tuple[CfoPoint, ...], config: HoughConfig = _DEFAULT_HOUGH_CONFIG
) -> tuple[LineSegment, ...]:
    """Extract multiple lines using a weighted slope/intercept-mod-alias Hough map."""

    points = canonical_points(points)
    common = config.common
    arrays = _arrays(points)
    times, frequency, weights = arrays
    available = weights >= common.minimum_point_weight
    slopes = np.linspace(
        common.minimum_slope_hz_per_s,
        common.maximum_slope_hz_per_s,
        config.slope_bins,
    )
    bin_width = common.alias_spacing_hz / config.intercept_bins
    detected: list[LineSegment] = []
    for _ in range(common.maximum_tracks):
        chosen = np.flatnonzero(available)
        if chosen.size < common.minimum_support:
            break
        accumulator = np.zeros((slopes.size, config.intercept_bins), dtype=float)
        for slope_index, slope_value in enumerate(slopes):
            bins = np.floor(
                ((frequency[chosen] - slope_value * times[chosen]) % common.alias_spacing_hz)
                / bin_width
            ).astype(int)
            accumulator[slope_index] = np.bincount(
                bins,
                weights=weights[chosen],
                minlength=config.intercept_bins,
            )
        flat = np.argsort(accumulator.ravel(), kind="stable")[-config.peak_candidates :]
        hypotheses: list[tuple[LineSegment, np.ndarray]] = []
        for flat_index in flat[::-1]:
            slope_index, intercept_bin = np.unravel_index(flat_index, accumulator.shape)
            candidate_slope = float(slopes[slope_index])
            intercept = float((intercept_bin + 0.5) * bin_width)
            hypotheses.extend(
                _candidate_segments(
                    points,
                    available,
                    slope=candidate_slope,
                    intercept=intercept,
                    common=common,
                    algorithm="weighted_hough",
                    arrays=arrays,
                )
            )
        if not hypotheses:
            break
        segment, _ = max(hypotheses, key=_segment_rank)
        detected.append(segment)
        _peel_alias_support(available, points, segment, common, arrays)
    return tuple(detected)


def _ransac_hypotheses(
    points: tuple[CfoPoint, ...],
    available: np.ndarray,
    config: RansacConfig,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[tuple[float, float], ...]:
    common = config.common
    times, frequency, weights = arrays
    chosen = np.flatnonzero(available)
    if chosen.size < 2:
        return ()
    ordered = chosen[np.lexsort((chosen, -weights[chosen]))]
    pairs: list[tuple[int, int]] = []
    anchor_count = min(48, ordered.size)
    for left, right in itertools.combinations(ordered[:anchor_count], 2):
        if abs(times[right] - times[left]) >= config.minimum_pair_separation_s:
            pairs.append((int(left), int(right)))
    seed_material = "\0".join(points[int(index)].point_id for index in chosen)
    seed = int.from_bytes(hashlib.sha256(seed_material.encode()).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    attempts = 0
    maximum_attempts = config.maximum_hypotheses * 8
    while len(pairs) < config.maximum_hypotheses and attempts < maximum_attempts:
        left, right = (int(value) for value in rng.choice(chosen, size=2, replace=False))
        if times[left] > times[right]:
            left, right = right, left
        if times[right] - times[left] >= config.minimum_pair_separation_s:
            pairs.append((left, right))
        attempts += 1
    result: set[tuple[float, float]] = set()
    for left, right in pairs:
        dt = times[right] - times[left]
        for alias_delta in range(-config.alias_delta_limit, config.alias_delta_limit + 1):
            slope = (
                frequency[right] - frequency[left] - alias_delta * common.alias_spacing_hz
            ) / dt
            if common.minimum_slope_hz_per_s <= slope <= common.maximum_slope_hz_per_s:
                intercept = (frequency[left] - slope * times[left]) % common.alias_spacing_hz
                result.add((round(float(slope), 9), round(float(intercept), 9)))
                if len(result) >= config.maximum_hypotheses:
                    return tuple(sorted(result))
    return tuple(sorted(result))


def robust_ransac_lines(
    points: tuple[CfoPoint, ...], config: RansacConfig = _DEFAULT_RANSAC_CONFIG
) -> tuple[LineSegment, ...]:
    """Deterministic bounded RANSAC-style multi-line extraction."""

    points = canonical_points(points)
    arrays = _arrays(points)
    weights = arrays[2]
    available = weights >= config.common.minimum_point_weight
    detected: list[LineSegment] = []
    for _ in range(config.common.maximum_tracks):
        hypotheses = _ransac_hypotheses(points, available, config, arrays)
        candidates: list[tuple[LineSegment, np.ndarray]] = []
        for slope, intercept in hypotheses:
            candidates.extend(
                _candidate_segments(
                    points,
                    available,
                    slope=slope,
                    intercept=intercept,
                    common=config.common,
                    algorithm="robust_ransac",
                    arrays=arrays,
                )
            )
        if not candidates:
            break
        segment, _ = max(candidates, key=_segment_rank)
        detected.append(segment)
        _peel_alias_support(available, points, segment, config.common, arrays)
    return tuple(detected)


def _dp_hypothesis(
    points: tuple[CfoPoint, ...],
    available: np.ndarray,
    slope: float,
    config: DynamicProgrammingConfig,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    common = config.common
    times, frequency, weights = arrays
    by_time: dict[int, list[int]] = {}
    for raw_index in np.flatnonzero(available):
        index = int(raw_index)
        by_time.setdefault(_time_key(times[index]), []).append(index)
    groups: list[np.ndarray] = []
    for indexes in by_time.values():
        indexes.sort(key=lambda i: (-weights[i], frequency[i], points[i].point_id))
        groups.append(np.asarray(indexes[: config.maximum_candidates_per_time], dtype=int))
    groups.sort(key=lambda group: times[group[0]])
    if not groups:
        return np.asarray([], dtype=int)
    scores: dict[int, float] = {}
    lengths: dict[int, int] = {}
    predecessors: dict[int, int | None] = {}
    best_index = int(groups[0][0])
    for group_index, group in enumerate(groups):
        for raw_current in group:
            current = int(raw_current)
            emission = weights[current] - config.point_cost
            best_score = emission
            best_length = 1
            best_predecessor: int | None = None
            first_group = max(0, group_index - config.maximum_predecessor_groups)
            for previous_group in groups[first_group:group_index]:
                dt = times[current] - times[previous_group[0]]
                if dt <= 0.0 or dt > common.maximum_gap_s:
                    continue
                prediction = frequency[previous_group] + slope * dt
                residual = np.abs(
                    circular_residual_hz(
                        np.full(previous_group.size, frequency[current]),
                        prediction,
                        common.alias_spacing_hz,
                    )
                )
                valid = residual <= common.residual_gate_hz
                for previous_offset in np.flatnonzero(valid):
                    raw_previous = previous_group[previous_offset]
                    previous = int(raw_previous)
                    candidate_score = (
                        scores[previous]
                        + emission
                        - config.transition_penalty
                        * (float(residual[previous_offset]) / common.residual_gate_hz) ** 2
                        - config.gap_penalty_per_s * dt
                    )
                    candidate_length = lengths[previous] + 1
                    candidate_rank = (candidate_score, candidate_length, -previous)
                    best_rank = (best_score, best_length, -(best_predecessor or current))
                    if candidate_rank > best_rank:
                        best_score = candidate_score
                        best_length = candidate_length
                        best_predecessor = previous
            scores[current] = best_score
            lengths[current] = best_length
            predecessors[current] = best_predecessor
            if (scores[current], lengths[current], -current) > (
                scores[best_index],
                lengths[best_index],
                -best_index,
            ):
                best_index = current
    path = []
    cursor: int | None = best_index
    while cursor is not None:
        path.append(cursor)
        cursor = predecessors[cursor]
    return np.asarray(path[::-1], dtype=int)


def dynamic_programming_lines(
    points: tuple[CfoPoint, ...],
    config: DynamicProgrammingConfig = _DEFAULT_DYNAMIC_PROGRAMMING_CONFIG,
) -> tuple[LineSegment, ...]:
    """Time-ordered track-before-detect extraction over bounded slope hypotheses."""

    points = canonical_points(points)
    common = config.common
    arrays = _arrays(points)
    times, _, weights = arrays
    available = weights >= common.minimum_point_weight
    slopes = np.linspace(
        common.minimum_slope_hz_per_s,
        common.maximum_slope_hz_per_s,
        config.slope_bins,
    )
    detected: list[LineSegment] = []
    for _ in range(common.maximum_tracks):
        candidates: list[tuple[LineSegment, np.ndarray]] = []
        for slope in slopes:
            path = _dp_hypothesis(points, available, float(slope), config, arrays)
            if path.size < common.minimum_support:
                continue
            for contiguous in _split_contiguous(path, times, common.maximum_gap_s):
                if (
                    contiguous.size < common.minimum_support
                    or times[contiguous[-1]] - times[contiguous[0]] < common.minimum_span_s
                ):
                    continue
                intercept = float(
                    np.median(
                        (arrays[1][contiguous] - slope * arrays[0][contiguous])
                        % common.alias_spacing_hz
                    )
                )
                segment = _fit_alias_line(
                    contiguous,
                    points,
                    initial_slope=float(slope),
                    initial_intercept=intercept,
                    alias_spacing_hz=common.alias_spacing_hz,
                    algorithm="dynamic_programming",
                    arrays=arrays,
                )
                if segment.residual_max_hz <= common.residual_gate_hz:
                    candidates.append((segment, contiguous))
        if not candidates:
            break
        segment, _ = max(candidates, key=_segment_rank)
        detected.append(segment)
        _peel_alias_support(available, points, segment, common, arrays)
    return tuple(detected)


def with_common(
    config: HoughConfig | RansacConfig | DynamicProgrammingConfig, **changes: Any
) -> Any:
    """Return a detector configuration with validated common-bound replacements."""

    return replace(config, common=replace(config.common, **changes))
