import math

import numpy as np
import pytest
from scipy.stats import multivariate_normal

from ratio_random_intercept import candidate_ratio_loglik


def test_tau_zero_exact_existing_independent_expression():
    residuals = np.array([[1., -2., .5], [-.2, .3, 4.]])
    variance = .7
    expected = np.sum(-.5 * (math.log(2*math.pi*variance)
                              + residuals**2 / variance), axis=1)
    assert np.array_equal(candidate_ratio_loglik(residuals, variance, 0.), expected)


@pytest.mark.parametrize("observations", [1, 2, 7, 30])
def test_matches_dense_scipy_multivariate_normal(observations):
    rng = np.random.default_rng(123 + observations)
    residuals = rng.normal(size=(4, observations))
    variance = .37; tau = 1.4
    covariance = variance * np.eye(observations) + tau**2 * np.ones(
        (observations, observations))
    expected = np.array([multivariate_normal.logpdf(row, mean=np.zeros(observations),
                                                      cov=covariance)
                         for row in residuals])
    assert candidate_ratio_loglik(residuals, variance, tau) == pytest.approx(
        expected, abs=2e-12, rel=0)


def test_candidate_and_observation_permutation_invariance():
    residuals = np.array([[1., 2., -1.], [-2., .4, .8], [.1, -.7, 3.]])
    baseline = candidate_ratio_loglik(residuals, .6, .9)
    assert candidate_ratio_loglik(residuals[[2, 0, 1]], .6, .9) == pytest.approx(
        baseline[[2, 0, 1]])
    assert candidate_ratio_loglik(residuals[:, [2, 0, 1]], .6, .9) == pytest.approx(
        baseline)


def test_empty_matched_rows_have_zero_evidence():
    actual = candidate_ratio_loglik(np.empty((3, 0)), .4, 2.)
    assert np.array_equal(actual, np.zeros(3))


def test_shared_effect_differs_from_independent_redraw_for_repeated_residuals():
    residuals = np.full((1, 4), 2.)
    shared = candidate_ratio_loglik(residuals, 1., 1.)[0]
    independent = 4 * candidate_ratio_loglik(np.array([[2.]]), 1., 1.)[0]
    assert shared > independent


def test_small_tau_converges_to_independent_model():
    residuals = np.array([[1., -2., 3.], [.1, .2, .3]])
    zero = candidate_ratio_loglik(residuals, .8, 0.)
    tiny = candidate_ratio_loglik(residuals, .8, 1e-7)
    assert tiny == pytest.approx(zero, abs=2e-13, rel=0)


@pytest.mark.parametrize("residuals,variance,tau", [
    ([], 1., 0.),
    ([[1., float("nan")]], 1., 0.),
    ([[1.]], 0., 0.),
    ([[1.]], -1., 0.),
    ([[1.]], 1., -1.),
    ([[1.]], float("inf"), 0.),
    ([[1.]], 1., float("inf")),
])
def test_invalid_inputs_fail_closed(residuals, variance, tau):
    with pytest.raises(ValueError):
        candidate_ratio_loglik(residuals, variance, tau)
