from dataclasses import replace

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig, _predict, _wrap
from leo.analysis.residual_tracklets import fit_lane


def curve(n):
    t = np.linspace(0, 25, n)
    truth = 170000 - 4000 * t + 30 * t * t
    noise = np.random.default_rng(81).normal(0, 35, n)
    return t, _wrap(truth + noise, TrackConfig().alias_spacing_hz)


def test_sparse_curved_fragment_is_explicitly_blocked_by_original_support_floor():
    t, y = curve(10)
    result = fit_lane(t, y, TrackConfig())
    assert not result["tracks"]
    relaxed = fit_lane(t, y, replace(TrackConfig(), points_per_coefficient=2))
    assert len(relaxed["tracks"]) == 1
    assert np.all(relaxed["assignment"] == 0)
    assert relaxed["tracks"][0]["pieces"][0]["degree"] == 2


def test_quadratic_seed_recovers_supported_alias_crossing_with_exclusive_ownership():
    t, y = curve(20)
    result = fit_lane(t, y)
    assert len(result["tracks"]) == 1
    members = result["tracks"][0]["indices"]
    assert len(set(members)) == len(t)
    assert len(set(result["alias_lifts"])) > 1
    for piece in result["tracks"][0]["pieces"]:
        ix = piece["indices"]
        residual = y[ix] + result["alias_lifts"][ix] * TrackConfig().alias_spacing_hz
        residual -= _predict(piece, t[ix])
        assert np.max(np.abs(residual)) < 450
        assert np.sqrt(np.mean(residual**2)) < 50


def test_order_and_nonfinite_mapping_preserve_original_observations():
    t, y = curve(20)
    order = np.random.default_rng(8).permutation(len(t))
    result = fit_lane(np.r_[t[order], np.nan], np.r_[y[order], 0])
    assert np.all(result["assignment"][:-1] == 0)
    assert result["assignment"][-1] == -1
    assert set(result["tracks"][0]["indices"]) == set(range(len(t)))


def test_uniform_clutter_is_unresolved_even_with_lower_support_ratio():
    t = np.linspace(0, 60, 181)
    y = np.random.default_rng(126).uniform(-110000, 110000, len(t))
    result = fit_lane(t, y, replace(TrackConfig(), points_per_coefficient=2))
    assert not result["tracks"]
    assert np.all(result["assignment"] == -1)
