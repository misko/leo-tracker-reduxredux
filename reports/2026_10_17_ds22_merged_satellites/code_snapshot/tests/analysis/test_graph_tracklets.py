"""Known-identity controls for graph discovery, separate from training RMS."""

import numpy as np
from numpy.polynomial.legendre import legval

from leo.analysis.graph_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig

PERIOD = 1 / 4.4e-6
CONFIG = TrackConfig(max_slope_hz_s=8000)


def wrap(y):
    return (y + PERIOD / 2) % PERIOD - PERIOD / 2


def check(result, t, y):
    assignment = np.asarray(result["assignment"])
    assert assignment.shape == t.shape
    all_indices = []
    for number, track in enumerate(result["tracks"]):
        indices = np.asarray(track["indices"], int)
        np.testing.assert_array_equal(assignment[indices], number)
        assert len(indices) == len(np.unique(indices))
        assert np.max(np.diff(np.sort(t[indices]))) <= CONFIG.max_gap_s
        all_indices.extend(indices.tolist())
        piece_members = []
        for piece in track["pieces"]:
            ix = np.asarray(piece["indices"], int)
            piece_members.extend(ix.tolist())
            assert len(ix) >= max(CONFIG.min_points, 4 * (piece["degree"] + 1))
            assert piece["degree"] <= 4
            x = (t[ix] - piece["reference_time_s"]) / piece["time_scale_s"]
            predicted = legval(x, piece["coefficients_hz"])
            residual = y[ix] + PERIOD * result["alias_lifts"][ix] - predicted
            assert np.max(np.abs(residual)) < 450
        assert sorted(piece_members) == sorted(indices.tolist())
    assert len(all_indices) == len(set(all_indices))
    assert sorted(all_indices) == np.flatnonzero(assignment >= 0).tolist()


def test_wrap_crossing_line_and_original_index_permutation():
    rng = np.random.default_rng(51)
    t = np.linspace(0, 60, 181)
    y = wrap(125000 - 1500 * t + rng.normal(0, 50, len(t)))
    original = fit_lane(t, y, CONFIG)
    permutation = rng.permutation(len(t))
    permuted = fit_lane(t[permutation], y[permutation] + 2 * PERIOD, CONFIG)
    check(original, t, y)
    check(permuted, t[permutation], y[permutation] + 2 * PERIOD)
    assert np.mean(original["assignment"] >= 0) > 0.95
    assert max(len(track["indices"]) for track in original["tracks"]) > 0.9 * len(t)
    np.testing.assert_array_equal(
        original["assignment"], permuted["assignment"][np.argsort(permutation)]
    )


def test_crossing_paths_recover_both_identities_without_forcing_clutter():
    rng = np.random.default_rng(52)
    base = np.linspace(0, 60, 121)
    t = np.r_[base, base + 0.01, rng.uniform(0, 60, 60)]
    y = wrap(np.r_[90000 - 1200 * base, 18000 + 1200 * base,
                   rng.uniform(-PERIOD / 2, PERIOD / 2, 60)] + rng.normal(0, 50, len(t)))
    truth = np.r_[np.zeros(121, int), np.ones(121, int), np.full(60, -1)]
    result = fit_lane(t, y, CONFIG)
    check(result, t, y)
    assert np.mean(result["assignment"][:242] >= 0) > 0.9
    assert np.mean(result["assignment"][242:] >= 0) < 0.15
    for track in result["tracks"]:
        labels = truth[track["indices"]]
        counts = np.bincount(labels[labels >= 0], minlength=2)
        if counts.sum():
            assert counts.max() / counts.sum() > 0.9


def test_quartic_curvature_requires_higher_order_without_excessive_fragmentation():
    rng = np.random.default_rng(53)
    t = np.linspace(0, 60, 181)
    x = (t - 30) / 30
    y = wrap(50000 + 20000 * x - 10000 * x**2 + 4000 * x**3 + 8000 * x**4
             + rng.normal(0, 50, len(t)))
    result = fit_lane(t, y, CONFIG)
    check(result, t, y)
    assert np.mean(result["assignment"] >= 0) > 0.9
    assert len(result["tracks"]) <= 3
    assert any(p["degree"] >= 3 for tr in result["tracks"] for p in tr["pieces"])


def test_real_step_and_unobserved_gap_are_not_smoothed_over():
    rng = np.random.default_rng(54)
    t = np.linspace(0, 60, 181)
    y = wrap(50000 - 700 * t + 20000 * (t >= 30) + rng.normal(0, 40, len(t)))
    result = fit_lane(t, y, CONFIG)
    check(result, t, y)
    assert np.mean(result["assignment"] >= 0) > 0.9
    for tr in result["tracks"]:
        for piece in tr["pieces"]:
            support = t[piece["indices"]]
            assert not (np.any(support < 27) and np.any(support > 33))
    t = np.r_[np.linspace(0, 20, 61), np.linspace(80, 100, 61)]
    y = wrap(110000 - 1600 * t + rng.normal(0, 40, len(t)))
    result = fit_lane(t, y, CONFIG)
    check(result, t, y)
    assert np.mean(result["assignment"] >= 0) > 0.9


def test_uniform_clutter_and_insufficient_support_remain_unresolved():
    rng = np.random.default_rng(55)
    t = np.sort(rng.uniform(0, 90, 200))
    y = rng.uniform(-PERIOD / 2, PERIOD / 2, len(t))
    result = fit_lane(t, y, CONFIG)
    check(result, t, y)
    assert np.mean(result["assignment"] >= 0) < 0.1
    assert fit_lane(t[:4], y[:4], CONFIG)["tracks"] == []
    assert fit_lane([], [], CONFIG)["tracks"] == []
