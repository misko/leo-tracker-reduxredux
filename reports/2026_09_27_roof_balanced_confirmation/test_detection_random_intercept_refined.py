import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import minimize_scalar

from detection_random_intercept_refined import (
    _mode_curvature, _quadrature, candidate_detection_loglik)


def oracle(row, observed, sigma):
    row = np.asarray(row, float); y = np.asarray(observed, float)
    def log_integrand(u):
        return (float(np.sum(y * (row + u) - np.logaddexp(0., row + u)))
                - .5 * (u / sigma)**2 - math.log(sigma * math.sqrt(2*math.pi)))
    fit = minimize_scalar(lambda u: -log_integrand(u), bracket=(-2., 2.),
                          method="brent", options={"xtol": 1e-13})
    peak = log_integrand(fit.x)
    value, error = quad(lambda u: math.exp(log_integrand(u) - peak),
                        -np.inf, np.inf, epsabs=2e-13, epsrel=2e-13, limit=500)
    assert error < 1e-9
    return math.log(value) + peak


def test_sigma_zero_exact_and_permutations():
    logits = np.array([[2., -1., .3], [-3., 4., 0.]])
    y = np.array([1, 0, 1])
    direct = np.sum(y[None, :] * logits - np.logaddexp(0., logits), axis=1)
    assert np.array_equal(candidate_detection_loglik(logits, y, 0.), direct)
    baseline = candidate_detection_loglik(logits, y, 2.)
    assert candidate_detection_loglik(logits[::-1], y, 2.) == pytest.approx(baseline[::-1])
    assert candidate_detection_loglik(logits[:, ::-1], y[::-1], 2.) == pytest.approx(baseline)


@pytest.mark.parametrize("sigma", [.1, 1., 4., 8.])
@pytest.mark.parametrize("case", ["mixed", "all_hit"])
def test_long_track_matches_independent_quad(sigma, case):
    row = np.linspace(-2., 2., 120)
    y = (np.arange(120) % 2 == 0).astype(int) if case == "mixed" else np.ones(120, int)
    expected = oracle(row, y, sigma)
    actual32 = candidate_detection_loglik(row[None, :], y, sigma, 32)[0]
    actual64 = candidate_detection_loglik(row[None, :], y, sigma, 64)[0]
    actual256 = candidate_detection_loglik(row[None, :], y, sigma, 256)[0]
    assert actual256 == pytest.approx(expected, abs=2e-9, rel=0)
    # The explicit 32/64 comparison is diagnostic rather than an acceptance
    # shortcut: extreme all-hit tracks remain skewed and need the runner's
    # independently declared high-order convergence gate.
    assert abs(actual64 - actual256) < abs(actual32 - actual256) + 1e-13


def test_mode_residual_and_positive_curvature_extremes():
    logits = np.array([np.full(120, -8.), np.full(120, 8.)])
    for y in (np.zeros(120), np.ones(120), np.arange(120) % 2):
        mode, curvature = _mode_curvature(logits, np.asarray(y, float), 8.)
        assert np.all(np.isfinite(mode))
        assert np.all(curvature > 0)


def test_actual_frozen_all_miss_track_mode_regression():
    # Full-six mixture arm, track index 78: this terminated the first refined
    # run at sigma=1 before any artifact was written.
    logits = np.array([
        [-1.1522771271, -1.3075063631, -1.1700869550, -1.5514762784,
         -1.4293420270, -.8041777662, -.8660898714, -.6581356275,
         -.7661279611, -.2993330144, -.2286646826, .0964091219,
         .1572677378, -.2156699401, -.1941621042, .1774916077],
        [.3206476580, .1662382403, .3105407409, -.0635615663, .0591429723,
         .6919561150, .6303828602, .8421491944, .7342425346, 1.2010622470,
         1.2626098141, 1.5782646343, 1.6365488086, 1.2299763714,
         1.2470851517, 1.5976372900],
        [3.3480961405, 3.1921632979, 3.3227068220, 2.9313053950,
         3.0524771268, 3.6596732094, 3.5965836889, 3.7813290157,
         3.6719139079, 4.1221379432, 4.1377109079, 4.4313329922,
         4.4846853835, 4.0307873583, 4.0430204524, 4.3724423616]])
    y = np.zeros(16, dtype=int)
    value = candidate_detection_loglik(logits, y, 1., 64)
    assert np.all(np.isfinite(value))
    assert value == pytest.approx([oracle(row, y, 1.) for row in logits],
                                  abs=2e-10, rel=0)


def test_cached_quadrature_is_immutable():
    _quadrature.cache_clear(); first = _quadrature(32); second = _quadrature(32)
    assert first[0] is second[0] and _quadrature.cache_info().hits == 1
    with pytest.raises(ValueError):
        first[1][0] = 0.


def test_shared_effect_differs_from_independent_redraw():
    logits = np.zeros((1, 4)); y = np.ones(4, int)
    shared = candidate_detection_loglik(logits, y, 4.)[0]
    redrawn = sum(candidate_detection_loglik(logits[:, i:i+1], y[i:i+1], 4.)[0]
                  for i in range(4))
    assert shared > redrawn


@pytest.mark.parametrize("logits,y,sigma,order", [
    ([[0., np.nan]], [1, 0], 1., 32), ([[0., 1.]], [1], 1., 32),
    ([[0., 1.]], [1, 2], 1., 32), ([[0., 1.]], [1, 0], -1., 32),
    ([[0., 1.]], [1, 0], 1., 1), ([[0., 1.]], [1, 0], 1., 2.5)])
def test_invalid_inputs(logits, y, sigma, order):
    with pytest.raises(ValueError):
        candidate_detection_loglik(logits, y, sigma, order)
