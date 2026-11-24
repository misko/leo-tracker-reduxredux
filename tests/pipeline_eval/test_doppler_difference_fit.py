from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def fit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "reports/ALGO08/v3"))
    import doppler_difference_fit

    return doppler_difference_fit


def test_shape_matches_the_correlated_adjacent_difference_likelihood(fit):
    data = np.arange(30, dtype=float).reshape(10, 3)**1.3
    sigma = np.arange(1., 11.) / 4.
    groups = np.repeat([4, 7], [6, 4])
    actual = fit.TrackNoise(groups, sigma).apply(data, track_means=False)
    expected = np.zeros((3, 3))
    offset = 0
    for n in (6, 4):
        sl = slice(offset, offset + n)
        d = np.diff(np.eye(n), axis=0)
        cov = (d * sigma[sl]**2) @ d.T
        assert np.all(np.diag(cov, k=1) < 0.)
        y = d @ data[sl]
        expected += y.T @ np.linalg.solve(cov, y)
        offset += n
    np.testing.assert_allclose(actual.T @ actual, expected, atol=1e-10)


def test_mean_plus_shape_matches_correlated_random_track_intercept(fit):
    data = np.arange(24., dtype=float).reshape(8, 3)**1.7
    sigma = np.arange(1., 9.) * 30
    groups = np.repeat([0, 1, 2], [3, 3, 2])
    actual = fit.TrackNoise(groups, sigma).apply(data, track_means=True)
    cov = np.diag(sigma**2) + fit.ARC_BIAS_HZ**2 * (groups[:, None] == groups)
    np.testing.assert_allclose(actual.T @ actual, data.T @ np.linalg.solve(cov, data), atol=1e-12)


def test_profile_removes_full_shared_design_and_preserves_calibration_gauge(fit):
    groups = np.repeat([0, 1, 2], 4)
    t = np.linspace(0., 1., len(groups))
    d = np.column_stack((t, t**2, (groups-1.)*2e5, t*2.))
    noise = fit.TrackNoise(groups, np.full_like(t, 100.))
    shape = noise.apply(d, track_means=False)
    keep_c = noise.apply(d, track_means=True)
    before = np.linalg.norm(d * noise.inverse[:, None], axis=0)
    basis, active, _ = fit.profile_space(shape, before)
    assert active.tolist() == [True, True, False, True]
    assert basis.shape[1] == 2
    assert fit.profile_space(keep_c, before)[0].shape[1] == 3
    np.testing.assert_allclose(fit.project(basis, shape), 0., atol=1e-12)
