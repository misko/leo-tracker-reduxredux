from unittest.mock import patch

import numpy as np
import pytest

from timing_penalty_variants import MODES, PenaltyTimingObjective, Objective, relative_terms
from timing_model import zero_sum_basis, TimingObjective
from rf_calibration_diagnostic import CalibrationObjective


def make_base(mode):
    obj = object.__new__(PenaltyTimingObjective)
    obj.basis = zero_sum_basis(4); obj.common_prior = True
    for k, v in MODES[mode].items(): setattr(obj, k, v)
    return obj


@pytest.mark.parametrize('mode', MODES)
def test_prior_gradient_and_exact_curvature_in_zero_sum_coordinates(mode):
    obj = make_base(mode)
    vector = np.array([1., 2., 30., 2., 10., -1., .7, -.2, 2., -5.])
    value, gradient = obj.penalty(vector)
    hessian = obj.penalty_curvature(vector)
    assert value >= 0
    np.testing.assert_array_equal(gradient[:6], np.zeros(6))
    assert np.linalg.eigvalsh(hessian).min() > -1e-12
    for j in range(len(vector)):
        eps = np.eye(len(vector))[j]*1e-5
        fd = (obj.penalty(vector+eps)[0]-obj.penalty(vector-eps)[0])/2e-5
        np.testing.assert_allclose(fd, gradient[j], atol=1e-7, rtol=1e-7)
        hfd = (obj.penalty(vector+eps)[1]-obj.penalty(vector-eps)[1])/2e-5
        np.testing.assert_allclose(hfd, hessian[:, j], atol=1e-7, rtol=1e-7)


@pytest.mark.parametrize('mode', MODES)
def test_fisher_replaces_legacy_prior_without_changing_data_terms(mode):
    obj = object.__new__(Objective); obj.base = make_base(mode); obj.size = 10
    vector = np.array([1., 2., 30., 2., 10., -1., .7, -.2, 2., -5., 300.])
    data_h = np.eye(11)*4.
    legacy_h = data_h.copy(); legacy_h[6, 6] += .01
    indices = np.arange(7, 10); legacy_h[indices, indices] += 1.
    with patch.object(CalibrationObjective, 'curvature', return_value=legacy_h):
        actual = obj.curvature(vector)
    expected = data_h.copy(); expected[:10, :10] += obj.base.penalty_curvature(vector[:10])
    np.testing.assert_allclose(actual, expected, atol=1e-12)


def test_gaussian_controls_exactly_reproduce_previous_priors():
    vector = np.arange(10, dtype=float)/3.
    for mode, scale in [('baseline', 1.), ('both-tight', 9.)]:
        obj = make_base(mode)
        old_value, old_gradient = TimingObjective.penalty(obj, vector)
        value, gradient = obj.penalty(vector)
        np.testing.assert_allclose(value, scale*old_value)
        np.testing.assert_allclose(gradient, scale*old_gradient)


def test_robust_prior_is_tight_near_zero_but_linear_in_far_tails():
    d = np.array([0., 1e-7, 1., 1000.])
    p, g, h = relative_terms(d, 1./3., 1.)
    assert p[0] == g[0] == 0. and h[0] == 9.
    assert abs(p[1]/(.5*9*d[1]**2)-1) < 1e-10
    assert g[-1] < 9. and abs(g[-1]-9.) < 1e-5
    assert h[-1] > 0. and h[-1] < 1e-7
    np.testing.assert_allclose(relative_terms(-d, 1./3., 1.)[0], p)
    np.testing.assert_allclose(relative_terms(-d, 1./3., 1.)[1], -g)


@pytest.mark.parametrize('sigma,transition', [(0., None), (float('nan'), None), (1., 0.), (1., -1.)])
def test_invalid_width_rejected(sigma, transition):
    with pytest.raises(ValueError): relative_terms(np.ones(2), sigma, transition)
