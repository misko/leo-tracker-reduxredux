"""Component tests for memory-bounded adaptive TLE prediction banks."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import leo.analysis.adaptive_tle_prediction as prediction_module
from leo.analysis.adaptive_tle_position import score_point
from leo.analysis.adaptive_tle_prediction import (
    AdaptiveTrackInput,
    AdaptiveTrackStateBank,
    ReceiverPoint,
    RegionalTrackPredictionEvaluator,
    build_prediction_banks,
    required_geometry_nodes,
)


def bank(*, coarse_z=7000.0):
    times = np.asarray([0.0, 0.7, 1.5, 2.2, 3.1, 3.8])
    source = AdaptiveTrackInput(
        "track",
        tuple(f"obs-{index}" for index in range(6)),
        times,
        np.linspace(1.0, 6.0, 6),
        np.asarray([True, True, True, False, False, False]),
    )
    taus = np.arange(-5.0, 6.0)
    nodes = required_geometry_nodes((times,), taus)
    position = np.zeros((2, len(taus), 6, 3))
    position[..., 2] = coarse_z
    velocity = np.zeros_like(position)
    coarse = np.zeros((2, len(nodes), 3))
    coarse[..., 2] = coarse_z
    return AdaptiveTrackStateBank(
        source,
        np.asarray([10, 20]),
        position,
        velocity,
        coarse,
        nodes,
        np.asarray([0, 1]),
    )


def test_required_nodes_include_both_interpolation_endpoints():
    nodes = required_geometry_nodes((np.asarray([0.0, 0.25, 3.8]),), np.asarray([-5.0, 5.0]))

    assert 502 in nodes and 503 in nodes
    assert 515 in nodes and 516 in nodes


def test_regional_evaluator_streams_candidate_blocks_and_scores_once_per_track():
    evaluator = RegionalTrackPredictionEvaluator(
        (bank(),),
        lambda _east, _north: ReceiverPoint(np.zeros(3), np.asarray([0, 0, 1])),
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
        (varied,),
        lambda _east, _north: ReceiverPoint(np.zeros(3), np.asarray([0, 0, 1])),
        candidate_block=1,
    )

    blocks = tuple(evaluator(0.0, 0.0))

    assert [block.candidate_ids.tolist() for block in blocks] == [[20]]


@pytest.mark.parametrize("all_invalid", [False, True])
@pytest.mark.parametrize("direct_allocation", [False, True])
def test_bank_chunks_preserve_candidate_order_and_validity(
    monkeypatch, all_invalid, direct_allocation
):
    calls = []

    def propagate(catalogue, indices, epoch, times, taus):
        calls.append(len(indices))
        indices = np.asarray(indices)
        valid = indices[(indices % (3 if len(times) == 1316 else 5)) != 0]
        if all_invalid:
            valid = valid[:0]
        values = np.broadcast_to(
            valid[:, None, None, None] * 10000
            + taus[None, :, None, None]
            + times[None, None, :, None],
            (len(valid), len(taus), len(times), 3),
        ).copy()
        return values, values / 100, valid

    monkeypatch.setattr(prediction_module, "propagate_candidate_states", propagate)
    source = bank().source
    indices = list(reversed(range(17)))
    catalogue = SimpleNamespace(satellite_numbers=np.arange(100, 117))
    allocations = []
    finalized = []

    def allocate(shape):
        values = np.empty(shape)
        allocations.append(values)
        return values

    def finalize(values, used):
        assert any(values is allocated for allocated in allocations)
        finalized.append(values)
        result = values[:used]
        result.flags.writeable = False
        return result

    ports = dict(allocate_array=allocate, finalize_array=finalize) if direct_allocation else {}
    banks, receipt = build_prediction_banks(
        catalogue, indices, 0, (source,), candidate_block=4, **ports
    )
    actual = banks[0]
    assert max(calls) <= 4
    if direct_allocation:
        assert len(allocations) == len(finalized) == 3
        assert not actual.position_km.flags.writeable
    coarse_ids = [i for i in indices if i % 3] if not all_invalid else []
    track_ids = [i for i in coarse_ids if i % 5]
    np.testing.assert_array_equal(actual.candidate_ids, np.asarray(track_ids) + 100)
    np.testing.assert_array_equal(
        actual.coarse_candidate_rows, [coarse_ids.index(i) for i in track_ids]
    )
    expected_position, expected_velocity, _ = propagate(
        catalogue, track_ids, 0, source.times_s, np.arange(-5.0, 6.0)
    )
    np.testing.assert_array_equal(actual.position_km, expected_position)
    np.testing.assert_array_equal(actual.velocity_km_s, expected_velocity)
    expected_coarse, _, _ = propagate(
        catalogue, coarse_ids, 0, np.arange(-507.0, 809.0), np.array([0.0])
    )
    np.testing.assert_array_equal(
        actual.coarse_position_km, expected_coarse[:, 0, actual.coarse_node_indices]
    )
    assert receipt.candidate_count == len(coarse_ids)
    assert (
        receipt.propagated_candidate_time_values == 1316 * len(coarse_ids) + len(track_ids) * 11 * 6
    )


def test_bank_allocation_ports_require_a_pair():
    with pytest.raises(ValueError, match="paired"):
        build_prediction_banks(None, [], 0, (bank().source,), allocate_array=np.empty)


@pytest.mark.parametrize("all_invisible", [False, True])
def test_exact_visibility_filters_velocity_reads_and_keeps_unmatched_tracks(all_invisible):
    source = bank()
    positions = source.position_km.copy()
    positions[0, ..., 2] = -7000
    if all_invisible:
        positions[1, ..., 2] = -7000
    reads = []

    class VelocityReader:
        def __getitem__(self, indexes):
            reads.extend(np.asarray(indexes).tolist())
            return source.velocity_km_s[indexes]

    evaluator = RegionalTrackPredictionEvaluator(
        (replace(source, position_km=positions, velocity_km_s=VelocityReader()),),
        lambda *_: ReceiverPoint(np.zeros(3), np.array([0, 0, 1])),
    )
    score = score_point(0, 0, evaluator(0, 0))
    assert reads == ([] if all_invisible else [1])
    assert score.matched_track_count == (0 if all_invisible else 1)
    if all_invisible:
        assert score.unmatched_track_count == 1
        assert score.residual_rmse_hz == 800.0
    else:
        assert score.tracks[0].candidate_id == "20"


def test_fixed_interpolation_metadata_is_prepared_only_once(monkeypatch):
    evaluator = RegionalTrackPredictionEvaluator(
        (bank(),), lambda *_: ReceiverPoint(np.zeros(3), np.array([0, 0, 1]))
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("point evaluation rebuilt fixed interpolation metadata")

    monkeypatch.setattr(prediction_module.np, "vectorize", unexpected)
    assert score_point(0, 0, evaluator(0, 0)).matched_track_count == 1
    assert score_point(1, 1, evaluator(1, 1)).matched_track_count == 1
