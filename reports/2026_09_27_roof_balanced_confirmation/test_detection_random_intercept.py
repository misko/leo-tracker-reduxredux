import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import expit

from detection_random_intercept import candidate_detection_loglik, _quadrature


def direct(logits, matched):
    values = np.asarray(logits, float)
    y = np.asarray(matched, float)
    return np.sum(y[None, :] * values - np.logaddexp(0., values), axis=1)


def oracle(logits, matched, sigma):
    values = np.asarray(logits, float)
    y = np.asarray(matched, float)
    output = []
    for row in values:
        def integrand(u):
            probability = expit(row + u)
            likelihood = np.prod(np.where(y == 1., probability, 1. - probability))
            density = math.exp(-.5 * (u / sigma) ** 2) / (sigma * math.sqrt(2*math.pi))
            return likelihood * density
        integral, error = quad(integrand, -np.inf, np.inf,
                               epsabs=1e-13, epsrel=1e-13, limit=300)
        assert error < 1e-10
        output.append(math.log(integral))
    return np.asarray(output)


def test_sigma_zero_is_exact_existing_likelihood():
    logits = np.array([[2., -1., .3], [-3., 4., 0.]])
    observed = np.array([True, False, True])
    actual = candidate_detection_loglik(logits, observed, 0.)
    assert np.array_equal(actual, direct(logits, observed))


def test_quadrature_cache_reuses_immutable_arrays():
    _quadrature.cache_clear()
    first = _quadrature(64)
    second = _quadrature(64)
    assert first[0] is second[0] and first[1] is second[1]
    assert _quadrature.cache_info().misses == 1
    assert _quadrature.cache_info().hits == 1
    with pytest.raises(ValueError):
        first[0][0] = 0.


@pytest.mark.parametrize("observed", ([1, 0, 1, 0], [1, 1, 1, 1]))
def test_quadrature_matches_independent_scipy_oracle(observed):
    logits = np.array([[-1.2, .3, 1.7, -.4], [.8, -2., .1, 2.2]])
    expected = oracle(logits, observed, .7)
    actual = candidate_detection_loglik(logits, observed, .7, 64)
    assert actual == pytest.approx(expected, abs=2e-11, rel=0)


def test_candidate_and_observation_permutation_invariance():
    logits = np.array([[1., 2., -1.], [-2., .4, .8], [.1, -.7, 3.]])
    observed = np.array([1, 0, 1])
    baseline = candidate_detection_loglik(logits, observed, 1.1)
    assert candidate_detection_loglik(logits[[2, 0, 1]], observed, 1.1) == pytest.approx(
        baseline[[2, 0, 1]])
    assert candidate_detection_loglik(logits[:, [2, 0, 1]], observed[[2, 0, 1]], 1.1) == pytest.approx(
        baseline)


def test_higher_orders_converge_to_oracle():
    logits = np.array([[-2., -1., 0., 1., 2.]])
    observed = [0, 0, 1, 1, 1]
    expected = oracle(logits, observed, 1.3)[0]
    errors = [abs(candidate_detection_loglik(logits, observed, 1.3, order)[0] - expected)
              for order in (8, 16, 32, 64)]
    assert errors[-1] < 1e-10
    assert errors[-1] < errors[0]


def test_shared_effect_is_not_independent_per_observation_evidence():
    logits = np.zeros((1, 4))
    all_hits = np.ones(4, dtype=int)
    shared = candidate_detection_loglik(logits, all_hits, 1.5)[0]
    independent = sum(candidate_detection_loglik(logits[:, index:index+1],
                                                  all_hits[index:index+1], 1.5)[0]
                      for index in range(4))
    # A positive shared effect can explain all hits together, increasing their
    # joint evidence compared with redrawing u independently for every row.
    assert shared > independent


@pytest.mark.parametrize("logits,matched,sigma,order", [
    ([[0., np.nan]], [1, 0], 1., 8),
    ([[0., 1.]], [1], 1., 8),
    ([[0., 1.]], [1, 2], 1., 8),
    ([[0., 1.]], [1, 0], -1., 8),
    ([[0., 1.]], [1, 0], 1., 1),
    ([[0., 1.]], [1, 0], 1., 3.5),
])
def test_invalid_inputs_fail_closed(logits, matched, sigma, order):
    with pytest.raises(ValueError):
        candidate_detection_loglik(logits, matched, sigma, order)
