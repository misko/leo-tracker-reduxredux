import numpy as np
import pytest

from leo.analysis.localization_marginal import integrate_shared_gaussian


def test_shared_integration_matches_dense_covariance_and_conditional_mean():
    rng = np.random.default_rng(623)
    sigma = np.array([.001, .5, 20.])
    blocks = []
    dense_noise = np.zeros((9, 9))
    start = 0
    for n in [2, 4, 3]:
        a = rng.normal(size=(n, n))
        covariance = a@a.T+.3*np.eye(n)
        blocks.append((rng.normal(size=n), rng.normal(size=(n, 3)), covariance))
        dense_noise[start:start+n, start:start+n] = covariance
        start += n
    r = np.concatenate([b[0] for b in blocks])
    h = np.concatenate([b[1] for b in blocks])
    prior = np.diag(sigma**2)
    c = dense_noise+h@prior@h.T
    expected = -.5*(9*np.log(2*np.pi)+np.linalg.slogdet(c)[1]+r@np.linalg.solve(c, r))
    result = integrate_shared_gaussian(blocks, sigma)
    np.testing.assert_allclose(result.log_likelihood, expected, rtol=1e-11)
    np.testing.assert_allclose(result.nuisance_mean, prior@h.T@np.linalg.solve(c, r), rtol=1e-10)
    posterior = prior-prior@h.T@np.linalg.solve(c, h@prior)
    chol = result.whitened_information_cholesky
    got = np.diag(sigma)@np.linalg.solve(chol.T, np.linalg.solve(chol, np.eye(3)))@np.diag(sigma)
    np.testing.assert_allclose(got, posterior, atol=1e-10)


def test_shared_error_prefers_coherent_residuals_over_conflicting_residuals():
    h, c = np.ones((1, 1)), np.eye(1)*.01
    shared = integrate_shared_gaussian([(np.array([1.]), h, c)]*2, np.ones(1))
    opposed = integrate_shared_gaussian(
        [(np.array([1.]), h, c), (np.array([-1.]), h, c)], np.ones(1))
    assert shared.log_likelihood > opposed.log_likelihood+90
    # Independent nuisance variables would assign equal evidence to both signs.
    plus = integrate_shared_gaussian([(np.array([1.]), h, c)], np.ones(1))
    minus = integrate_shared_gaussian([(np.array([-1.]), h, c)], np.ones(1))
    assert plus.log_likelihood == minus.log_likelihood


def test_integrated_normalization_is_not_just_profiled_residual_cost():
    result = integrate_shared_gaussian(
        [(np.zeros(1), np.ones((1, 1)), np.eye(1))], np.ones(1))
    np.testing.assert_allclose(result.log_likelihood, -.5*np.log(4*np.pi))


def test_broad_prior_avoids_cancellation_of_large_quadratics():
    result = integrate_shared_gaussian(
        [(np.array([1e10]), np.ones((1, 1)), np.eye(1))], np.array([1e10]))
    variance = 1.+1e20
    expected = -.5*(np.log(2*np.pi*variance)+1e20/variance)
    np.testing.assert_allclose(result.log_likelihood, expected, atol=1e-10)


def test_invalid_blocks_fail_explicitly():
    with pytest.raises(ValueError):
        integrate_shared_gaussian([], np.ones(1))
    with pytest.raises(ValueError):
        integrate_shared_gaussian([], np.array([0.]))
    with pytest.raises(ValueError):
        integrate_shared_gaussian([(np.ones(2), np.ones((2, 1)), np.eye(1))], np.ones(1))
    with pytest.raises(np.linalg.LinAlgError):
        integrate_shared_gaussian([(np.ones(1), np.ones((1, 1)), -np.eye(1))], np.ones(1))
