"""Independent controls for sequential state-space tracklet discovery."""

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.mht_tracklets import _transition, fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig, _predict, _wrap


def config():
    return TrackConfig(max_slope_hz_s=8000, max_proposals=48)


def assert_ownership_and_gate(result, times, values, cfg):
    owned = []
    for number, track in enumerate(result["tracks"]):
        for piece in track["pieces"]:
            indices = piece["indices"]
            assert np.all(result["assignment"][indices] == number)
            lifted = values[indices] + result["alias_lifts"][indices] * cfg.alias_spacing_hz
            assert np.max(np.abs(lifted - _predict(piece, times[indices]))) < 450 + 1e-6
            owned.extend(indices)
    assert len(owned) == len(set(owned))


def test_wrapped_curved_track_and_alias_lifts():
    rng = np.random.default_rng(91)
    t = np.linspace(0, 60, 81)
    cfg = config()
    y = _wrap(100_000 - 2200 * t + 4 * t**2 + rng.normal(0, 40, len(t)), cfg.alias_spacing_hz)
    result = fit_lane(t, y, cfg)
    assert np.count_nonzero(result["assignment"] >= 0) >= 70
    assert result["diagnostics"]["measurement_branches"] > 0
    assert any(p["degree"] >= 2 for tr in result["tracks"] for p in tr["pieces"])
    assert_ownership_and_gate(result, t, y, cfg)


def test_crossing_tracks_with_clutter():
    rng = np.random.default_rng(12)
    t = np.linspace(0, 60, 65)
    times = np.r_[t, t + 0.02, rng.uniform(0, 60, 25)]
    values = np.r_[
        40_000 - 1100 * t + rng.normal(0, 45, len(t)),
        -40_000 + 1100 * t + rng.normal(0, 45, len(t)),
        rng.uniform(-100_000, 100_000, 25),
    ]
    cfg = config()
    result = fit_lane(times, values, cfg)
    assert np.count_nonzero(result["assignment"][:130] >= 0) >= 110
    assert np.count_nonzero(result["assignment"][130:] < 0) >= 18
    assert len(result["tracks"]) >= 2
    assert_ownership_and_gate(result, times, values, cfg)


def test_true_step_and_gap_are_separate_tracks():
    t = np.r_[np.arange(0, 25, 0.75), np.arange(40, 65, 0.75)]
    y = 10_000 - 500 * t + np.where(t >= 40, 18_000, 0)
    result = fit_lane(t, y, config())
    assert np.count_nonzero(result["assignment"] >= 0) >= 60
    assert len(result["tracks"]) >= 2
    for track in result["tracks"]:
        assert not (track["start_s"] < 25 and track["end_s"] > 40)


def test_true_frequency_step_without_observation_gap_splits():
    t = np.arange(0, 50, 0.75)
    y = 10_000 - 500 * t + np.where(t >= 25, 18_000, 0)
    result = fit_lane(t, y, config())
    assert np.count_nonzero(result["assignment"] >= 0) >= 60
    assert len(result["tracks"]) >= 2
    for track in result["tracks"]:
        assert not (track["start_s"] < 24 and track["end_s"] > 26)


def test_shuffle_nonfinite_and_simultaneous_times_preserve_indices():
    t = np.repeat(np.arange(0, 25, 1.0), 2)
    y = 30_000 - 900 * t + np.tile([-10, 10], len(t) // 2)
    permutation = np.random.default_rng(2).permutation(len(t))
    t = np.r_[t[permutation], np.nan]
    y = np.r_[y[permutation], 0.0]
    cfg = config()
    result = fit_lane(t, y, cfg)
    assert result["assignment"][-1] == -1
    assert np.count_nonzero(result["assignment"] >= 0) >= 40
    assert_ownership_and_gate(result, t, y, cfg)


def test_elapsed_time_transition_and_track_budget():
    state, covariance = _transition(np.array([1.0, 2.0, 3.0]), np.eye(3), 2.0, 150.0)
    np.testing.assert_allclose(state, [11, 8, 3])
    assert np.all(np.linalg.eigvalsh(covariance) > 0)
    first, first_cov = _transition(np.array([1.0, 2.0, 3.0]), np.eye(3), 1.0, 150.0)
    second, second_cov = _transition(first, first_cov, 1.0, 150.0)
    np.testing.assert_allclose(second, state)
    np.testing.assert_allclose(second_cov, covariance)
    t = np.r_[np.arange(0, 30.0), np.arange(0, 30.0) + 0.05]
    y = np.r_[1000 - 100 * np.arange(0, 30.0), 80_000 - 100 * np.arange(0, 30.0)]
    result = fit_lane(t, y, replace(config(), max_tracks=1))
    assert len(result["tracks"]) <= 1


def test_invalid_dimensions_raise():
    with pytest.raises(ValueError, match="matching one-dimensional"):
        fit_lane(np.arange(3), np.zeros((3, 1)))
