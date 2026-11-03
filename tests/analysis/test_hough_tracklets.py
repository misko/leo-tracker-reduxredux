import numpy as np

from leo.analysis.hough_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig

PERIOD = 1 / 4.4e-6


def wrap(y):
    return (y + PERIOD / 2) % PERIOD - PERIOD / 2


def test_wrapped_quadratic_is_recovered_and_alias_lifts_are_consistent():
    rng = np.random.default_rng(812)
    t = np.linspace(0, 48, 145)
    y = wrap(125_000 - 1400 * t - 10 * t**2 + rng.normal(0, 35, len(t)))
    result = fit_lane(t, y)
    assert np.mean(result["assignment"] >= 0) > 0.9
    assert any(p["degree"] >= 2 for tr in result["tracks"] for p in tr["pieces"])
    for track in result["tracks"]:
        for p in track["pieces"]:
            ix = p["indices"]
            pred = np.polynomial.legendre.legval(
                (t[ix] - p["reference_time_s"]) / p["time_scale_s"], p["coefficients_hz"]
            )
            residual = y[ix] + result["alias_lifts"][ix] * PERIOD - pred
            assert np.max(abs(residual)) < 450


def test_crossing_tracks_retain_identity_and_reject_clutter():
    rng = np.random.default_rng(813)
    base = np.linspace(0, 48, 100)
    t = np.r_[base, base + 0.01, rng.uniform(0, 48, 70)]
    y = wrap(
        np.r_[90_000 - 1400 * base, 22_800 + 1400 * base, rng.uniform(-PERIOD / 2, PERIOD / 2, 70)]
        + rng.normal(0, 35, len(t))
    )
    result = fit_lane(t, y)
    assert np.mean(result["assignment"][:200] >= 0) > 0.85
    assert np.mean(result["assignment"][200:] >= 0) < 0.2
    for track in result["tracks"]:
        ix = np.array(track["indices"])
        labels = ix[ix < 200] // 100
        assert not len(labels) or np.bincount(labels).max() / len(labels) > 0.9


def test_frequency_step_and_large_gap_are_not_bridged():
    t = np.r_[np.linspace(0, 20, 61), np.linspace(80, 100, 61)]
    y = wrap(110_000 - 1600 * t + 20_000 * (t > 50))
    result = fit_lane(t, y)
    assert np.mean(result["assignment"] >= 0) > 0.9
    for track in result["tracks"]:
        assert np.max(np.diff(np.sort(t[track["indices"]]))) <= 10


def test_noise_does_not_create_tracks_and_input_permutation_preserves_membership():
    rng = np.random.default_rng(814)
    t = np.linspace(0, 60, 100)
    assert fit_lane(t, rng.uniform(-PERIOD / 2, PERIOD / 2, len(t)))["tracks"] == []
    y = wrap(125_000 - 1400 * t + rng.normal(0, 35, len(t)))
    permutation = rng.permutation(len(t))
    a = fit_lane(t, y, TrackConfig())
    b = fit_lane(t[permutation], y[permutation] + 3 * PERIOD, TrackConfig())
    np.testing.assert_array_equal(
        a["assignment"] >= 0, b["assignment"][np.argsort(permutation)] >= 0
    )
