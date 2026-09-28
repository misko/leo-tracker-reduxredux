import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import ds7_beam_crossing as crossing  # noqa: E402


def features(contrast):
    values = np.asarray(contrast, dtype=float)
    los = np.zeros((len(values), values.shape[1], 3))
    los[:, :, 0] = values / 2
    los[:, :, 2] = np.sqrt(1 - los[:, :, 0] ** 2)
    return crossing.trajectory_features(
        np.arange(values.shape[1], dtype=float), los, [-1, 0, 0], [1, 0, 0]
    )


def track(observed=None, mask=None):
    observed = np.asarray(observed or [-0.8, -0.4, 0.1, 0.5, 0.9, 1.2])
    mask = np.asarray(mask or [True, True, True, False, False, False])
    return crossing.ConditionalTrack(
        "track-a",
        np.log([0.5, 0.5]),
        np.arange(6, dtype=float),
        observed,
        mask,
        features([[-0.8, -0.4, 0.1, 0.5, 0.9, 1.0], [0.8, 0.4, -0.1, -0.5, -0.9, -1.0]]),
    )


def test_crossing_is_interpolated_only_inside_window_and_ambiguous_is_missing():
    result = features(
        [
            [-0.5, 0.5, 0.8],
            [0.2, 0.3, 0.4],
            [-0.5, 0.5, -0.5],
        ]
    )
    assert result.crossing_time[0] == 0.5
    assert math.isnan(result.crossing_time[1])
    assert math.isnan(result.crossing_time[2])
    assert np.isnan(result.crossing_coordinate[1:]).all()


def test_held_values_cannot_change_training_component_scores():
    first = track()
    changed = track(observed=[-0.8, -0.4, 0.1, 1000, -2000, 3000])
    first_train, _ = crossing.component_scores(first, [0, 1, 0, 1, 0], temporal=True)
    changed_train, _ = crossing.component_scores(changed, [0, 1, 0, 1, 0], temporal=True)
    np.testing.assert_array_equal(first_train, changed_train)


def test_temporal_pairs_do_not_cross_partition_boundary():
    interleaved = track(mask=[True, False, True, False, True, False])
    train, held = crossing.component_scores(interleaved, [0, 1, 0, 0, 0], temporal=True)
    # Every row is a sequence start; no transition can bridge train and held.
    expected_train, expected_held = crossing.component_scores(
        interleaved, [0, 1, 0], temporal=False
    )
    np.testing.assert_allclose(train, expected_train)
    np.testing.assert_allclose(held, expected_held)


def test_candidate_identity_is_fixed_by_training_for_held_prediction():
    weights = np.log([0.5, 0.5])
    training = np.log([0.9, 0.1])
    held = np.log([0.2, 0.8])
    expected = np.log((0.9 * 0.2 + 0.1 * 0.8) / (0.9 + 0.1))
    np.testing.assert_allclose(
        crossing.held_predictive_log_density(weights, training, held), expected
    )


def test_controls_are_deterministic_and_preserve_masks_and_counts():
    source = track()
    first = crossing.deterministic_time_shuffle(source, 20260928)
    second = crossing.deterministic_time_shuffle(source, 20260928)
    np.testing.assert_array_equal(first.log_rx1_over_rx0, second.log_rx1_over_rx0)
    np.testing.assert_array_equal(first.training_mask, source.training_mask)
    np.testing.assert_array_equal(
        np.sort(first.log_rx1_over_rx0[source.training_mask]),
        np.sort(source.log_rx1_over_rx0[source.training_mask]),
    )
    np.testing.assert_array_equal(
        crossing.receiver_swap(source).features.contrast,
        -source.features.contrast,
    )
    np.testing.assert_array_equal(
        crossing.receiver_swap(source).log_rx1_over_rx0,
        source.log_rx1_over_rx0,
    )
    reversed_track = crossing.reverse_candidate_trajectory(source)
    np.testing.assert_array_equal(
        reversed_track.features.contrast, source.features.contrast[:, ::-1]
    )
    np.testing.assert_allclose(
        reversed_track.features.change,
        np.gradient(reversed_track.features.contrast, source.times, axis=1),
    )


def test_strict_validation_rejects_nonboolean_mask_and_nonunit_directions():
    source = track()
    invalid = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0,
        source.training_mask.astype(int),
        source.features,
    )
    with pytest.raises(ValueError, match="boolean mask"):
        crossing.validate_track(invalid)
    with pytest.raises(ValueError, match="unit length"):
        crossing.trajectory_features([0, 1], np.ones((1, 2, 3)), [-1, 0, 0], [1, 0, 0])


def test_projected_rank_rejects_time_collinear_temporal_features():
    source = track()
    degenerate_features = crossing.CrossingFeatures(
        np.tile(source.times, (2, 1)),
        np.ones((2, len(source.times))),
        np.array([math.nan, math.nan]),
        np.full((2, len(source.times)), math.nan),
    )
    degenerate = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0,
        source.training_mask,
        degenerate_features,
    )
    assert crossing.projected_temporal_rank(degenerate, np.ones(6, dtype=bool)) == 0


def test_continuous_time_ar_uses_actual_gap_lengths():
    source = track()
    stretched = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        np.array([0.0, 1.0, 2.0, 10.0, 20.0, 30.0]),
        source.log_rx1_over_rx0,
        source.training_mask,
        source.features,
    )
    first = crossing.component_scores(source, [0, 0, 0, 0, 0], temporal=True)
    second = crossing.component_scores(stretched, [0, 0, 0, 0, 0], temporal=True)
    assert not np.allclose(first[1], second[1])


def test_static_ar_is_temporal_ar_with_zero_change_coefficient():
    source = track()
    left = crossing.component_scores(source, [0.2, 0.7, 0.0, 1.0, -0.3], temporal=True)
    zero_change = crossing.CrossingFeatures(
        source.features.contrast,
        np.zeros_like(source.features.change),
        source.features.crossing_time,
        source.features.crossing_coordinate,
    )
    right = crossing.component_scores(
        crossing.ConditionalTrack(
            source.track_id,
            source.log_weights,
            source.times,
            source.log_rx1_over_rx0,
            source.training_mask,
            zero_change,
        ),
        [0.2, 0.7, 99.0, 1.0, -0.3],
        temporal=True,
    )
    for actual, expected in zip(left, right, strict=True):
        np.testing.assert_allclose(actual, expected)


def test_correlation_boundary_is_rejected():
    with pytest.raises(ValueError, match="frozen numerical bounds"):
        crossing.component_scores(track(), [0, 0, 0, 11, 0], temporal=True)


def test_feature_scale_uses_training_features_only():
    source = track()
    changed_features = crossing.CrossingFeatures(
        np.where(source.training_mask, source.features.contrast, 1e9),
        np.where(source.training_mask, source.features.change, -1e9),
        source.features.crossing_time,
        source.features.crossing_coordinate,
    )
    changed = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0,
        source.training_mask,
        changed_features,
    )
    assert crossing.fit_feature_scale([source]) == crossing.fit_feature_scale([changed])


def test_explicit_mask_supports_whole_recording_fit_and_evaluation():
    source = track(mask=[True] * 6)
    score = crossing.selected_component_scores(
        source, [0, 1, 0], np.ones(6, dtype=bool), temporal=False
    )
    assert score.shape == (2,)
    with pytest.raises(ValueError, match="nonempty boolean"):
        crossing.selected_component_scores(
            source, [0, 1, 0], np.zeros(6, dtype=bool), temporal=False
        )


def test_fixed_nuisance_mean_is_shared_by_static_and_temporal_scores():
    source = track()
    nuisance = np.linspace(-0.2, 0.3, len(source.times))
    adjusted = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0 + nuisance,
        source.training_mask,
        source.features,
        nuisance,
    )
    for parameters, temporal in (([0, 1, 0], False), ([0, 1, 0, 0, 0], True)):
        expected = crossing.component_scores(source, parameters, temporal=temporal)
        actual = crossing.component_scores(adjusted, parameters, temporal=temporal)
        for left, right in zip(actual, expected, strict=True):
            np.testing.assert_allclose(left, right)


def test_nuisance_mean_shape_is_strictly_validated():
    source = track()
    invalid = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0,
        source.training_mask,
        source.features,
        np.zeros(len(source.times) - 1),
    )
    with pytest.raises(ValueError, match="nuisance mean"):
        crossing.validate_track(invalid)


def test_time_shuffle_permutes_residuals_around_frozen_nuisance_mean():
    source = track()
    nuisance = np.linspace(-10, 10, len(source.times))
    adjusted = crossing.ConditionalTrack(
        source.track_id,
        source.log_weights,
        source.times,
        source.log_rx1_over_rx0 + nuisance,
        source.training_mask,
        source.features,
        nuisance,
    )
    shuffled = crossing.deterministic_time_shuffle(adjusted, 17)
    for selected in (source.training_mask, ~source.training_mask):
        np.testing.assert_allclose(
            np.sort((shuffled.log_rx1_over_rx0 - nuisance)[selected]),
            np.sort(source.log_rx1_over_rx0[selected]),
        )
