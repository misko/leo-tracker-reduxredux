"""Component tests for memory-bounded adaptive TLE prediction banks."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from leo.analysis.adaptive_tle_position import score_point
from leo.analysis.adaptive_tle_prediction import (
    AdaptiveTrackInput,
    AdaptiveTrackStateBank,
    ReceiverPoint,
    RegionalTrackPredictionEvaluator,
    required_geometry_nodes,
)


def bank(*, coarse_z=7000.0):
    times = np.asarray([0.0, 0.7, 1.5, 2.2, 3.1, 3.8])
    source = AdaptiveTrackInput(
        "track", tuple(f"obs-{index}" for index in range(6)), times,
        np.linspace(1.0, 6.0, 6), np.asarray([True, True, True, False, False, False]),
    )
    taus = np.arange(-5.0, 6.0)
    nodes = required_geometry_nodes((times,), taus)
    position = np.zeros((2, len(taus), 6, 3))
    position[..., 2] = coarse_z
    velocity = np.zeros_like(position)
    coarse = np.zeros((2, len(nodes), 3))
    coarse[..., 2] = coarse_z
    return AdaptiveTrackStateBank(
        source, np.asarray([10, 20]), position, velocity, coarse, nodes,
        np.asarray([0, 1]),
    )


def test_required_nodes_include_both_interpolation_endpoints():
    nodes = required_geometry_nodes((np.asarray([0.0, 0.25, 3.8]),), np.asarray([-5.0, 5.0]))

    assert 502 in nodes and 503 in nodes
    assert 515 in nodes and 516 in nodes


def test_regional_evaluator_streams_candidate_blocks_and_scores_once_per_track():
    evaluator = RegionalTrackPredictionEvaluator(
        (bank(),), lambda _east, _north: ReceiverPoint(np.zeros(3), np.asarray([0, 0, 1])),
        candidate_block=1,
    )
    blocks = tuple(evaluator(0.0, 0.0))
    score = score_point(0.0, 0.0, blocks)

    assert len(blocks) == 2
    assert score.matched_track_count == 1
    assert len(score.tracks) == 1
    assert score.tracks[0].candidate_id == "10"


def test_coarse_invisible_track_is_retained_as_unmatched_penalty():
    evaluator = RegionalTrackPredictionEvaluator(
        (bank(coarse_z=-7000.0),),
        lambda _east, _north: ReceiverPoint(np.zeros(3), np.asarray([0, 0, 1])),
    )
    score = score_point(0.0, 0.0, evaluator(0.0, 0.0))

    assert score.matched_track_count == 0
    assert score.unmatched_track_count == 1
    assert score.residual_rmse_hz == 800.0


def test_endpoint_first_gather_matches_direct_union_node_interpolation():
    original = bank()
    coarse = original.coarse_position_km.copy()
    coarse[0, :, 2] = -7000.0
    varied = replace(original, coarse_position_km=coarse)
    evaluator = RegionalTrackPredictionEvaluator(
        (varied,), lambda _east, _north: ReceiverPoint(np.zeros(3), np.asarray([0, 0, 1])),
        candidate_block=1,
    )

    blocks = tuple(evaluator(0.0, 0.0))

    assert [block.candidate_ids.tolist() for block in blocks] == [[20]]
