from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.cfo_lines import CfoPoint, LineSegment
from leo.analysis.research.residual_hough import (
    ResidualHoughSelectionConfig,
    select_residual_hough_partition,
)


def _segment(
    number: int,
    point_ids: tuple[str, ...],
    start_s: float,
    end_s: float,
    slope_hz_per_s: float,
) -> LineSegment:
    return LineSegment(
        algorithm="weighted_hough",
        segment_id=f"sha256:{number:064x}",
        point_ids=point_ids,
        start_s=start_s,
        end_s=end_s,
        support=len(point_ids),
        weighted_support=float(len(point_ids)),
        slope_hz_per_s=slope_hz_per_s,
        intercept_hz=0.0,
        intercept_mod_alias_hz=0.0,
        residual_rms_hz=1.0,
        residual_max_hz=2.0,
        maximum_gap_s=0.1,
    )


def _fixture() -> tuple[LineSegment, tuple[CfoPoint, ...], tuple[LineSegment, ...]]:
    points: list[CfoPoint] = []
    proposals: list[LineSegment] = []
    definitions = (
        (0.0, 0.0, 0.0),
        (2.0, 80.0, -160.0),
        (4.0, 1_000.0, -4_000.0),
    )
    for group, (start_s, slope, intercept) in enumerate(definitions, start=1):
        point_ids: list[str] = []
        for index in range(20):
            time_s = start_s + index * 0.1
            point_id = f"proposal-{group}-point-{index}"
            point_ids.append(point_id)
            points.append(
                CfoPoint(
                    point_id=point_id,
                    time_s=time_s,
                    frequency_hz=slope * time_s + intercept + 5.0 * math.sin(index),
                    exact_score=1.0,
                    control_score=0.1,
                    margin=1.0,
                )
            )
        proposals.append(_segment(group, tuple(point_ids), start_s, start_s + 1.9, slope))
    parent = _segment(
        99,
        tuple(point.point_id for point in points),
        0.0,
        5.9,
        0.0,
    )
    return parent, tuple(points), tuple(proposals)


def _select(minimum_split_gain: float, points: tuple[CfoPoint, ...] | None = None):
    parent, fixture_points, proposals = _fixture()
    return select_residual_hough_partition(
        parent=parent,
        residual_points=fixture_points if points is None else points,
        proposals=proposals,
        maximum_gap_s=0.2,
        residual_gate_hz=100.0,
        config=ResidualHoughSelectionConfig(minimum_split_gain=minimum_split_gain),
    )


def test_explicit_split_gain_merges_weak_fragment_but_preserves_strong_line() -> None:
    unpenalized = _select(0.0)
    penalized = _select(200.0)

    assert unpenalized.selected_line_count == 3
    assert [line.source_proposal_numbers for line in unpenalized.lines] == [(1,), (2,), (3,)]
    assert penalized.selected_line_count == 2
    assert [line.source_proposal_numbers for line in penalized.lines] == [(1, 2), (3,)]
    assert penalized.minimum_split_gain == 200.0
    assert penalized.adjusted_robust_mdl < (
        unpenalized.robust_mdl + 200.0 * unpenalized.selected_line_count
    )


def test_partition_selection_is_point_permutation_deterministic() -> None:
    _, points, _ = _fixture()
    shuffled = tuple(points[index] for index in np.random.default_rng(41).permutation(len(points)))
    assert _select(200.0, shuffled) == _select(200.0, points)


def test_redundant_proposal_with_fewer_than_two_new_points_is_ignored() -> None:
    points = tuple(
        CfoPoint(
            point_id=f"point-{index}",
            time_s=time_s,
            frequency_hz=frequency_hz,
            exact_score=1.0,
            control_score=0.1,
            margin=0.9,
        )
        for index, (time_s, frequency_hz) in enumerate(
            ((0.0, 0.0), (0.1, 1.0), (1.0, 10.0), (1.1, 11.0))
        )
    )
    proposals = (
        _segment(1, ("point-0", "point-1"), 0.0, 0.1, 10.0),
        _segment(2, ("point-0", "point-1"), 0.0, 0.1, 10.0),
        _segment(3, ("point-2", "point-3"), 1.0, 1.1, 10.0),
    )
    parent = _segment(99, tuple(point.point_id for point in points), 0.0, 1.1, 10.0)

    selected = select_residual_hough_partition(
        parent=parent,
        residual_points=points,
        proposals=proposals,
        maximum_gap_s=0.2,
        residual_gate_hz=100.0,
        config=ResidualHoughSelectionConfig(minimum_split_gain=0.0),
    )

    assert selected.detected_proposal_count == 3
    assert selected.considered_proposal_count == 3
    assert selected.assigned_point_count == 4
    assert selected.unassigned_point_count == 0
    assert selected.selected_line_count == 2
    assert [line.source_proposal_numbers for line in selected.lines] == [(1,), (3,)]


@pytest.mark.parametrize("value", (-1.0, float("nan"), float("inf")))
def test_invalid_minimum_split_gain_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="minimum split gain"):
        ResidualHoughSelectionConfig(minimum_split_gain=value)
