import numpy as np
import pytest

from leo.analysis.research.tle_shape_comparison import profile_shapes, unwrap_cfo


def test_late_measurements_do_not_change_fitted_nuisance_or_training_rank():
    t = np.linspace(0, 2.25, 101)
    p = np.array([3 * t**2, 5 * t**2])
    y = p[0] + 20 - 7 * t
    a = profile_shapes(t, y, p, nuisance_degree=1, split_s=1.35)
    y[t >= 1.35] += 1000
    b = profile_shapes(t, y, p, nuisance_degree=1, split_s=1.35)
    np.testing.assert_allclose(a["coefficients"], b["coefficients"])
    np.testing.assert_array_equal(a["order"], b["order"])
    assert a["order"][0] == 0
    assert a["late_rms"][0] < 1e-12
    assert b["late_rms"][0] > 999


def test_free_clock_drift_erases_quadratic_timing_discrimination():
    t = np.linspace(0, 2.25, 101)
    p = np.array([t**2, 4 * t**2])
    a = profile_shapes(t, p[0], p, nuisance_degree=1, split_s=1.35)
    b = profile_shapes(t, p[0], p, nuisance_degree=2, split_s=1.35)
    assert a["late_rms"][1] > 1
    assert max(b["late_rms"]) < 1e-12


def test_frequency_alias_unwrap_preserves_slope_and_nonalias_outlier():
    t = np.arange(10) * 0.01
    y = -3000 * t + 100
    aliases = np.array([0, 0, 1, -2, 2, 3, 1, 0, 0, -1])
    raw = y + aliases * (2_500_000 / 11)
    raw[5] += 20
    result = unwrap_cfo(raw)
    np.testing.assert_allclose(result - y, [0, 0, 0, 0, 0, 20, 0, 0, 0, 0], atol=1e-9)


def test_profile_rejects_empty_candidates_and_unordered_observations():
    with pytest.raises(ValueError):
        profile_shapes([0, 1, 2], [1, 2, 3], np.empty((0, 3)), nuisance_degree=0, split_s=1)
    with pytest.raises(ValueError):
        profile_shapes([0, 2, 1], [1, 2, 3], [[1, 2, 3]], nuisance_degree=0, split_s=1)
