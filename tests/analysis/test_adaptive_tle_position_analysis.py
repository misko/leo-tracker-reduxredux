"""Component tests for the promoted adaptive TLE position analysis."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.adaptive_tle_position import (
    AdaptiveTrackPrediction,
    adaptive_best_first_search,
    effective_one_second_bin_weight,
    fixed_randomized_training_mask,
    make_point_evaluator,
    score_point,
    score_track_prediction,
)
from leo.contracts.digests import canonical_digest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = ROOT / "tools" / "research" / "search_multiresolution_tle_coverage.py"


def prediction(
    candidate_ids=("10", "20"),
    predictions=None,
    *,
    visible=None,
    track_id="track",
):
    measured = np.asarray([10.0, 13.0, 16.0, 20.0, 24.0, 29.0])
    taus = np.asarray([-1.0, 0.0, 1.0])
    if predictions is None:
        predictions = np.zeros((len(candidate_ids), len(taus), len(measured)))
    if visible is None:
        visible = np.ones((len(candidate_ids), len(taus)), dtype=bool)
    return AdaptiveTrackPrediction(
        track_id=track_id,
        observation_ids=tuple(f"obs-{index}" for index in range(len(measured))),
        times_s=np.asarray([0.0, 0.7, 1.5, 2.2, 3.1, 3.8]),
        measured_hz=measured,
        training_mask=np.asarray([True, True, True, False, False, False]),
        candidate_ids=np.asarray(candidate_ids),
        taus_s=taus,
        predictions_hz=np.asarray(predictions, dtype=float),
        visible=np.asarray(visible, dtype=bool),
    )


def test_tau_and_offset_use_training_but_identity_preserves_evaluation_selection():
    base = prediction(candidate_ids=("10", "20"))
    values = np.empty((2, 3, 6), dtype=float)
    # Candidate 10 has the better training shape at tau 0, but poor evaluation.
    values[0] = base.measured_hz
    values[0, 0] += np.asarray([5, -5, 5, 100, -100, 100])
    values[0, 1] += np.asarray([0, 0, 0, 80, -80, 80])
    values[0, 2] += np.asarray([4, -4, 4, 60, -60, 60])
    # Candidate 20 selects tau +1 from training and wins on evaluation.
    values[1] = base.measured_hz
    values[1, 0] += np.asarray([8, -8, 8, 4, -4, 4])
    values[1, 1] += np.asarray([6, -6, 6, 3, -3, 3])
    values[1, 2] += np.asarray([2, -2, 2, 1, -1, 1])

    score = score_track_prediction(prediction(predictions=values))

    assert score.candidate_id == "20"
    assert score.tau_s == 1.0
    assert score.training_rms_hz == pytest.approx(np.std([2, -2, 2]))
    assert score.heldout_rms_hz == pytest.approx(1.0)
    assert score.frequency_offset_hz == pytest.approx(-2 / 3)


def test_candidate_blocks_reduce_to_same_full_catalogue_winner():
    full = prediction()
    full_score = score_point(1.0, 2.0, (full,))
    blocks = (
        prediction(("10",), full.predictions_hz[:1]),
        prediction(("20",), full.predictions_hz[1:]),
    )
    block_score = score_point(1.0, 2.0, iter(blocks))

    assert block_score == full_score


def test_score_matches_qualified_research_kernel_on_frozen_arrays():
    spec = importlib.util.spec_from_file_location("qualified_search_reference", REFERENCE_PATH)
    assert spec and spec.loader
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    track = prediction()
    rows = reference.score_prediction_bank(
        track.measured_hz,
        track.predictions_hz,
        track.training_mask,
        track.taus_s,
        np.ones(len(track.candidate_ids), dtype=bool),
        (200.0,),
    )
    expected = min(
        rows,
        key=lambda row: (
            row["heldout_rms_hz"],
            row["training_rms_hz"],
            int(track.candidate_ids[row["candidate_index"]]),
        ),
    )
    actual = score_track_prediction(track)

    assert int(actual.candidate_id) == int(track.candidate_ids[expected["candidate_index"]])
    assert actual.tau_s == expected["tau_s"]
    assert actual.training_rms_hz == pytest.approx(expected["training_rms_hz"])
    assert actual.heldout_rms_hz == pytest.approx(expected["heldout_rms_hz"])


def test_effective_weight_uses_session_relative_bins_without_rebasing_track():
    assert effective_one_second_bin_weight([10.9, 11.1, 11.9, 13.0]) == 3


def test_fixed_partition_is_order_stable_and_position_independent():
    ids = tuple(canonical_digest({"observation": index}) for index in range(10))
    seed = canonical_digest({"session": "track"})
    first = fixed_randomized_training_mask(ids, seed=seed)
    second = fixed_randomized_training_mask(ids, seed=seed)

    assert np.array_equal(first, second)
    assert np.sum(first) == 6
    assert np.any(~first)


def test_search_preserves_global_and_finest_incumbents_with_bounded_frontier():
    base = prediction(candidate_ids=("10",))

    def tracks(east, north):
        values = np.broadcast_to(
            base.measured_hz + np.hypot(east + 50, north + 50),
            base.predictions_hz.shape,
        ).copy()
        return (prediction(("10",), values),)

    result = adaptive_best_first_search(
        make_point_evaluator(tracks),
        radius_km=100,
        region_size_km=200,
        levels_km=(100, 50),
        budget_points=8,
    )

    assert result.global_incumbent is not None
    assert result.finest_incumbent is not None
    assert result.stop_reason == "point-budget-reached"
    assert not result.complete
    assert result.deferred_cells


def test_track_eligibility_and_search_policy_fail_closed():
    with pytest.raises(ValueError, match="incomplete"):
        AdaptiveTrackPrediction(
            "short",
            ("1", "2"),
            np.asarray([0.0, 3.0]),
            np.ones(2),
            np.asarray([True, False]),
            np.asarray([1]),
            np.asarray([0.0]),
            np.zeros((1, 1, 2)),
            np.ones(1, dtype=bool),
        )
    with pytest.raises(ValueError, match="bounded search policy"):
        adaptive_best_first_search(
            lambda _points: (),
            radius_km=501,
            region_size_km=1000,
        )
