"""Causal correlation selection and unchanged independent marginal controls."""

import numpy as np
import pytest
from ds23_joint_orbit_prior import correlation_fit, nll, qualify, standardized, wrap_angle
from learn_ds23_causal_phase_forecast import distribution_cost


def test_identity_correlation_exactly_reproduces_independent_phase_and_shape_density():
    rng = np.random.default_rng(11)
    z = rng.normal(size=(30,4))
    for nu in (None, 3., 8.):
        expected = distribution_cost(z[:,0], np.ones(30), 1., nu)+np.sum(z[:,1:]**2, axis=1)+3*np.log(2*np.pi)
        np.testing.assert_allclose(nll(z, np.eye(4), nu), expected, atol=1e-13)


def test_robust_correlation_preserves_marginal_scales_and_is_positive_definite():
    rng = np.random.default_rng(7)
    z = rng.normal(size=(300,4))
    z[:,1] += 2*z[:,0]
    covariance = correlation_fit(z)
    np.testing.assert_allclose(np.diag(covariance), 1.)
    assert np.linalg.eigvalsh(covariance).min() > 0
    assert covariance[0,1] > .75


def test_insufficient_history_keeps_exact_independence():
    p = dict(shrinkage=0., multiplier=1., nu=None)
    result = qualify([], 1, p, p)
    assert not result["qualified"]
    np.testing.assert_array_equal(result["correlation"], np.eye(4))


def test_standardization_uses_declared_phase_model_and_angular_wrap():
    rows=[dict(predicted_sigma_s=2., unit_phase_forecast_s=4., phase_residual_s=3., shape_z=[1.,2.,3.])]
    z=standardized(rows, dict(shrinkage=.5, multiplier=2., nu=None))
    np.testing.assert_allclose(z, [[.25,1.,2.,3.]])
    assert wrap_angle(2*np.pi+.1) == pytest.approx(.1)
