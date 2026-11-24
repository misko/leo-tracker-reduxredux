from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def mixture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "reports/ALGO08/v3"))
    import small_absolute_mixture

    return small_absolute_mixture


def test_arc_likelihood_retains_cfo_mean_and_matches_direct_covariance(mixture):
    sigma = np.array([30., 41., 22., 19.])
    covariance = np.diag(sigma**2)+300.**2
    factor = mixture.ArcNoise(sigma, 300.)
    gaps = np.array([[100., 84., 98., 101.], [90., 40., 80., 20.], [300., 284., 298., 301.]])
    log_norm = len(sigma)*np.log(2*np.pi)+np.linalg.slogdet(covariance)[1]
    np.testing.assert_allclose(factor.log_density(gaps), -.5*(np.einsum("ij,ji->i", gaps,
                                                                     np.linalg.solve(covariance, gaps.T))+log_norm))
    assert factor.log_density(gaps)[0] > factor.log_density(gaps)[-1]


def test_shape_slate_ignores_common_integer_alias_but_fails_closed_below_horizon(mixture):
    data = np.array([11., 18., 20., 39., 41., 47.])
    frequency = np.vstack((data, data[::-1], data))
    tangent = np.zeros_like(frequency)
    horizon = np.ones_like(frequency)
    horizon[2, -1] = -3.1
    weights = np.ones(len(data))/4
    first, visible = mixture.nominate(data, frequency, tangent, horizon, weights, np.ones(3))
    second, _ = mixture.nominate(data + 1/4.4e-6, frequency, tangent, horizon, weights, np.ones(3))
    np.testing.assert_allclose(first, second, atol=1e-8)
    assert first[0] < first[1] and visible.tolist() == [True, True, False]
