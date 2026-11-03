from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_grouped_bias_prior import bias_covariance, conditional_bias


def test_channel_and_family_sharing_preserve_all_marginal_variances():
    keys = [(1, 1, 10.), (1, 1, 10.), (1, 2, 11.), (2, 1, 10.)]
    families = [1, 2, 1, 1]
    for channel, family in [(0., 0.), (.75, 0.), (0., .75), (.375, .375)]:
        k = bias_covariance(keys, families, channel, family)
        np.testing.assert_allclose(np.diag(k), np.full(4, 300.**2), atol=1e-10)
        assert np.linalg.eigvalsh(k).min() > 0
    assert bias_covariance(keys, families, .75, 0.)[0, 1] == pytest.approx(.75*300**2)
    assert bias_covariance(keys, families, .75, 0.)[0, 3] == 0


def test_bias_conditioning_reconstructs_full_joint_prior_without_independent_reset():
    k = bias_covariance(['A', 'B', 'A', 'A'], [1, 2, 3, 4], .75, 0.)
    c = conditional_bias(k, 2)
    factor = np.block([[c['curved_root'], np.zeros((2, 2))],
                       [c['regression']@c['curved_root'], c['conditional_root']]])
    np.testing.assert_allclose(factor@factor.T, k, rtol=0, atol=2e-11)
    assert abs(c['conditional_covariance'][0, 1]) > 0
    assert c['regression'][0, 0] == pytest.approx(.75)


def test_curved_then_predictive_gaussian_equals_direct_joint_marginal():
    k = bias_covariance(['A', 'B', 'A', 'B'], [1, 2, 3, 4], .75, 0., sigma=3.)
    c = conditional_bias(k, 2)
    # Additional shared physical nuisance, independent of the correlated biases.
    u = np.array([[1.], [2.], [3.], [-1.]])
    prior_modes = np.column_stack((u[:2], c['curved_root']))
    y = np.array([2., -3., 5., 7.]); noise = np.array([1., 2., 3., 1.])
    gram = np.eye(3)+prior_modes.T@(prior_modes/noise[:2,None]**2)
    posterior_mean = np.linalg.solve(gram, prior_modes.T@(y[:2]/noise[:2]**2))
    future_modes = np.column_stack((u[2:], c['regression']@c['curved_root']))
    predictive_mean = future_modes@posterior_mean
    predictive_cov = np.diag(noise[2:]**2)+c['conditional_covariance']+future_modes@np.linalg.solve(gram, future_modes.T)
    initial_cov = np.diag(noise[:2]**2)+prior_modes@prior_modes.T
    residual = y[2:]-predictive_mean
    sequential = y[:2]@np.linalg.solve(initial_cov, y[:2])+np.linalg.slogdet(initial_cov)[1]+residual@np.linalg.solve(predictive_cov, residual)+np.linalg.slogdet(predictive_cov)[1]
    full_cov = np.diag(noise**2)+k+u@u.T
    direct = y@np.linalg.solve(full_cov,y)+np.linalg.slogdet(full_cov)[1]
    assert sequential == pytest.approx(direct, abs=1e-12)


def test_zero_correlation_is_independent_300Hz_biases():
    c = conditional_bias(bias_covariance(['A']*5, [1]*5), 3)
    np.testing.assert_array_equal(c['curved_root'], np.eye(3)*300)
    np.testing.assert_array_equal(c['regression'], np.zeros((2, 3)))
    np.testing.assert_array_equal(c['conditional_root'], np.eye(2)*300)
