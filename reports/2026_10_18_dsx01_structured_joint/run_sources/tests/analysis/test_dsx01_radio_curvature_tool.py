"""A curved fit must have active support beyond an isolated endpoint."""

import numpy as np
from dsx01_radio_curvature import fit_polynomial


def test_linear_signal_with_one_bad_endpoint_does_not_calibrate_curvature():
    t = np.linspace(0, 100, 61)
    rng = np.random.default_rng(81)
    y = 3000 + 50 * t + rng.normal(0, 50, len(t))
    y[-1] += 4000
    assert np.std(y - np.polyval(np.polyfit(t, y, 1), t)) > 250
    fit = fit_polynomial(t, y)
    assert fit["selected"]["degree"] == 1
    assert not fit["active_curvature"]


def test_genuine_quadratic_survives_an_isolated_wrong_endpoint():
    t = np.linspace(0, 100, 61)
    z = (t - 50) / 50
    rng = np.random.default_rng(82)
    y = 3000 + 50 * t + 2000 * z * z + rng.normal(0, 50, len(t))
    y[-1] += 4000
    fit = fit_polynomial(t, y)
    assert fit["selected"]["degree"] == 2
    assert fit["active_curvature"]
    assert fit["selected"]["signal_points"] == 60


def test_cubic_signal_is_not_forced_into_a_quadratic():
    t = np.linspace(0, 100, 91)
    z = (t - 50) / 50
    rng = np.random.default_rng(83)
    y = 3000 + 50 * t + 2500 * z * z + 1200 * z**3 + rng.normal(0, 60, len(t))
    fit = fit_polynomial(t, y)
    assert fit["selected"]["degree"] == 3
    assert fit["active_curvature"]
