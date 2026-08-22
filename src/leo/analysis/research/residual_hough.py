"""Bounded residual-Hough proposal grouping for offline research reports.

The weighted Hough detector remains the proposal generator.  This module fits
the proposal supports on the parent-line residual coordinate, searches every
admissible proposal partition, and charges an explicit additional cost for each
returned line.  It deliberately does not alter the persisted Standard V1
alternate-track contract.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass, replace

import numpy as np

from leo.analysis.cfo_lines import (
    CfoPoint,
    HoughConfig,
    LineSegment,
    circular_residual_hz,
    weighted_hough_lines,
)


@dataclass(frozen=True, slots=True)
class ResidualHoughSelectionConfig:
    """Explicit bounds and policy for grouping residual-Hough proposals."""

    minimum_split_gain: float = 200.0
    maximum_proposals: int = 8
    maximum_parent_support: int = 2_000

    def __post_init__(self) -> None:
        if not math.isfinite(self.minimum_split_gain) or self.minimum_split_gain < 0.0:
            raise ValueError("minimum split gain must be finite and non-negative")
        if not 1 <= self.maximum_proposals <= 8:
            raise ValueError("maximum residual-Hough proposals must be between one and eight")
        if not 2 <= self.maximum_parent_support <= 5_000:
            raise ValueError("maximum parent support must be between two and 5,000")


_DEFAULT_SELECTION_CONFIG = ResidualHoughSelectionConfig()


@dataclass(frozen=True, slots=True)
class ResidualHoughLine:
    """One grouped, robustly refitted residual-Hough line."""

    line_id: str
    source_proposal_numbers: tuple[int, ...]
    point_ids: tuple[str, ...]
    start_s: float
    end_s: float
    support: int
    residual_slope_hz_per_s: float
    residual_intercept_hz: float
    mapped_slope_hz_per_s: float
    mapped_intercept_hz: float
    median_absolute_residual_hz: float


@dataclass(frozen=True, slots=True)
class ResidualHoughSelection:
    """Deterministic result of the bounded exact partition search."""

    parent_segment_id: str
    residual_gate_hz: float
    minimum_split_gain: float
    detected_proposal_count: int
    considered_proposal_count: int
    shared_point_count: int
    assigned_point_count: int
    unassigned_point_count: int
    admissible_partition_count: int
    selected_line_count: int
    robust_mdl: float
    adjusted_robust_mdl: float
    gaussian_bic: float
    adjusted_gaussian_bic: float
    gaussian_selected_line_count: int
    lines: tuple[ResidualHoughLine, ...]


@dataclass(frozen=True, slots=True)
class _BlockFit:
    proposal_indexes: tuple[int, ...]
    point_ids: tuple[str, ...]
    start_s: float
    end_s: float
    robust_slope_hz_per_s: float
    robust_intercept_hz: float
    robust_sad_hz: float
    robust_median_absolute_residual_hz: float
    ols_sse_hz2: float


@dataclass(frozen=True, slots=True)
class _PartitionScore:
    partition: tuple[tuple[int, ...], ...]
    fits: tuple[_BlockFit, ...]
    robust_mdl: float
    adjusted_robust_mdl: float
    gaussian_bic: float
    adjusted_gaussian_bic: float


def _partitions(items: tuple[int, ...]) -> Iterator[tuple[tuple[int, ...], ...]]:
    if not items:
        yield ()
        return
    first = items[0]
    for partition in _partitions(items[1:]):
        yield ((first,),) + partition
        for index, block in enumerate(partition):
            yield partition[:index] + ((first,) + block,) + partition[index + 1 :]


def _connected_spans(
    block: tuple[int, ...], proposals: tuple[LineSegment, ...], maximum_gap_s: float
) -> bool:
    spans = sorted((proposals[index].start_s, proposals[index].end_s) for index in block)
    end_s = spans[0][1]
    for start_s, next_end_s in spans[1:]:
        if start_s - end_s > maximum_gap_s:
            return False
        end_s = max(end_s, next_end_s)
    return True


def _theil_sen_line(times: np.ndarray, values: np.ndarray) -> tuple[float, float, np.ndarray]:
    left, right = np.triu_indices(times.size, 1)
    delta_time = times[right] - times[left]
    usable = delta_time != 0.0
    if not np.any(usable):
        raise ValueError("residual-Hough support must span at least two distinct times")
    slopes = (values[right[usable]] - values[left[usable]]) / delta_time[usable]
    slope = float(np.median(slopes))
    intercept = float(np.median(values - slope * times))
    return slope, intercept, values - (slope * times + intercept)


def _least_squares_line(times: np.ndarray, values: np.ndarray) -> tuple[float, float, np.ndarray]:
    centre = float(np.mean(times))
    design = np.column_stack((times - centre, np.ones(times.size)))
    slope, intercept_at_centre = np.linalg.lstsq(design, values, rcond=None)[0]
    intercept = float(intercept_at_centre - slope * centre)
    slope = float(slope)
    return slope, intercept, values - (slope * times + intercept)


def _canonical_partition(partition: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted((tuple(sorted(block)) for block in partition), key=lambda block: block))


def select_residual_hough_partition(
    *,
    parent: LineSegment,
    residual_points: tuple[CfoPoint, ...],
    proposals: tuple[LineSegment, ...],
    maximum_gap_s: float,
    config: ResidualHoughSelectionConfig = _DEFAULT_SELECTION_CONFIG,
    residual_gate_hz: float,
) -> ResidualHoughSelection:
    """Group residual-Hough proposals with an exact, split-penalized search."""

    if not math.isfinite(maximum_gap_s) or maximum_gap_s <= 0.0:
        raise ValueError("maximum gap must be finite and positive")
    if not math.isfinite(residual_gate_hz) or residual_gate_hz <= 0.0:
        raise ValueError("residual gate must be finite and positive")
    if len(residual_points) > config.maximum_parent_support:
        raise ValueError("parent support exceeds the residual-Hough research bound")
    by_id = {point.point_id: point for point in residual_points}
    if len(by_id) != len(residual_points):
        raise ValueError("residual-Hough point identifiers must be unique")
    considered = proposals[: config.maximum_proposals]
    if not considered:
        return ResidualHoughSelection(
            parent_segment_id=parent.segment_id,
            residual_gate_hz=residual_gate_hz,
            minimum_split_gain=config.minimum_split_gain,
            detected_proposal_count=len(proposals),
            considered_proposal_count=0,
            shared_point_count=0,
            assigned_point_count=0,
            unassigned_point_count=len(residual_points),
            admissible_partition_count=0,
            selected_line_count=0,
            robust_mdl=0.0,
            adjusted_robust_mdl=0.0,
            gaussian_bic=0.0,
            adjusted_gaussian_bic=0.0,
            gaussian_selected_line_count=0,
            lines=(),
        )

    exclusive_point_ids: list[set[str]] = []
    seen: set[str] = set()
    shared: set[str] = set()
    for proposal in considered:
        proposal_ids = set(proposal.point_ids)
        unknown = proposal_ids.difference(by_id)
        if unknown:
            raise ValueError("residual-Hough proposal references an unknown point")
        shared.update(seen.intersection(proposal_ids))
        exclusive = proposal_ids.difference(seen)
        if len(exclusive) < 2:
            raise ValueError("exclusive residual-Hough proposal has fewer than two points")
        exclusive_point_ids.append(exclusive)
        seen.update(exclusive)

    fit_cache: dict[tuple[int, ...], _BlockFit] = {}

    def fit_block(block: tuple[int, ...]) -> _BlockFit:
        key = tuple(sorted(block))
        cached = fit_cache.get(key)
        if cached is not None:
            return cached
        point_ids = tuple(
            sorted(
                set().union(*(exclusive_point_ids[index] for index in key)),
                key=lambda point_id: (by_id[point_id].time_s, point_id),
            )
        )
        times = np.asarray([by_id[point_id].time_s for point_id in point_ids], dtype=float)
        values = np.asarray([by_id[point_id].frequency_hz for point_id in point_ids], dtype=float)
        robust_slope, robust_intercept, robust_residual = _theil_sen_line(times, values)
        _, _, ols_residual = _least_squares_line(times, values)
        fit = _BlockFit(
            proposal_indexes=key,
            point_ids=point_ids,
            start_s=float(np.min(times)),
            end_s=float(np.max(times)),
            robust_slope_hz_per_s=robust_slope,
            robust_intercept_hz=robust_intercept,
            robust_sad_hz=float(np.sum(np.abs(robust_residual))),
            robust_median_absolute_residual_hz=float(np.median(np.abs(robust_residual))),
            ols_sse_hz2=float(np.sum(ols_residual**2)),
        )
        fit_cache[key] = fit
        return fit

    scores: list[_PartitionScore] = []
    for raw_partition in _partitions(tuple(range(len(considered)))):
        partition = _canonical_partition(raw_partition)
        if not all(_connected_spans(block, considered, maximum_gap_s) for block in partition):
            continue
        fits = tuple(fit_block(block) for block in partition)
        observation_count = sum(len(fit.point_ids) for fit in fits)
        parameter_count = 2 * len(fits) + 1
        robust_sad = sum(fit.robust_sad_hz for fit in fits)
        gaussian_sse = sum(fit.ols_sse_hz2 for fit in fits)
        if robust_sad <= 0.0 or gaussian_sse <= 0.0:
            raise ValueError("residual-Hough model scale collapsed to zero")
        robust_mdl = float(
            2.0 * observation_count * np.log(robust_sad / observation_count)
            + parameter_count * np.log(observation_count)
        )
        gaussian_bic = float(
            observation_count * np.log(gaussian_sse / observation_count)
            + parameter_count * np.log(observation_count)
        )
        scores.append(
            _PartitionScore(
                partition=partition,
                fits=fits,
                robust_mdl=robust_mdl,
                adjusted_robust_mdl=robust_mdl + config.minimum_split_gain * len(fits),
                gaussian_bic=gaussian_bic,
                adjusted_gaussian_bic=(gaussian_bic + config.minimum_split_gain * len(fits)),
            )
        )
    if not scores:
        raise ValueError("no admissible residual-Hough proposal partitions")
    selected = min(
        scores,
        key=lambda item: (
            item.adjusted_robust_mdl,
            len(item.fits),
            item.partition,
        ),
    )
    gaussian_selected = min(
        scores,
        key=lambda item: (
            item.adjusted_gaussian_bic,
            len(item.fits),
            item.partition,
        ),
    )
    lines: list[ResidualHoughLine] = []
    for fit in selected.fits:
        identity_material = "\0".join(
            (parent.segment_id, *(considered[index].segment_id for index in fit.proposal_indexes))
        )
        identity = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()
        lines.append(
            ResidualHoughLine(
                line_id=f"sha256:{identity}",
                source_proposal_numbers=tuple(index + 1 for index in fit.proposal_indexes),
                point_ids=fit.point_ids,
                start_s=fit.start_s,
                end_s=fit.end_s,
                support=len(fit.point_ids),
                residual_slope_hz_per_s=fit.robust_slope_hz_per_s,
                residual_intercept_hz=fit.robust_intercept_hz,
                mapped_slope_hz_per_s=(parent.slope_hz_per_s + fit.robust_slope_hz_per_s),
                mapped_intercept_hz=parent.intercept_hz + fit.robust_intercept_hz,
                median_absolute_residual_hz=fit.robust_median_absolute_residual_hz,
            )
        )
    lines.sort(key=lambda line: (line.start_s, line.end_s, line.line_id))
    assigned = len(seen)
    return ResidualHoughSelection(
        parent_segment_id=parent.segment_id,
        residual_gate_hz=residual_gate_hz,
        minimum_split_gain=config.minimum_split_gain,
        detected_proposal_count=len(proposals),
        considered_proposal_count=len(considered),
        shared_point_count=len(shared),
        assigned_point_count=assigned,
        unassigned_point_count=len(residual_points) - assigned,
        admissible_partition_count=len(scores),
        selected_line_count=len(lines),
        robust_mdl=selected.robust_mdl,
        adjusted_robust_mdl=selected.adjusted_robust_mdl,
        gaussian_bic=selected.gaussian_bic,
        adjusted_gaussian_bic=selected.adjusted_gaussian_bic,
        gaussian_selected_line_count=len(gaussian_selected.fits),
        lines=tuple(lines),
    )


def detect_residual_hough_lines(
    *,
    points: tuple[CfoPoint, ...],
    parent: LineSegment,
    hough_config: HoughConfig,
    selection_config: ResidualHoughSelectionConfig = _DEFAULT_SELECTION_CONFIG,
) -> ResidualHoughSelection:
    """Detect residual proposals with a half-intercept-bin gate, then group them."""

    by_id = {point.point_id: point for point in points}
    try:
        parent_points = tuple(by_id[point_id] for point_id in parent.point_ids)
    except KeyError as error:
        raise ValueError("parent segment references an unknown point") from error
    if len(parent_points) > selection_config.maximum_parent_support:
        raise ValueError("parent support exceeds the residual-Hough research bound")
    times = np.asarray([point.time_s for point in parent_points], dtype=float)
    frequencies = np.asarray([point.frequency_hz for point in parent_points], dtype=float)
    residual = circular_residual_hz(
        frequencies,
        parent.slope_hz_per_s * times + parent.intercept_hz,
        hough_config.common.alias_spacing_hz,
    )
    residual_points = tuple(
        CfoPoint(
            point_id=point.point_id,
            time_s=point.time_s,
            frequency_hz=float(point_residual),
            exact_score=point.exact_score,
            control_score=point.control_score,
            margin=point.margin,
        )
        for point, point_residual in zip(parent_points, residual, strict=True)
    )
    residual_gate_hz = hough_config.common.alias_spacing_hz / (2.0 * hough_config.intercept_bins)
    residual_common = replace(hough_config.common, residual_gate_hz=residual_gate_hz)
    residual_proposals = weighted_hough_lines(
        residual_points,
        replace(hough_config, common=residual_common),
    )
    return select_residual_hough_partition(
        parent=parent,
        residual_points=residual_points,
        proposals=residual_proposals,
        maximum_gap_s=residual_common.maximum_gap_s,
        config=selection_config,
        residual_gate_hz=residual_gate_hz,
    )
