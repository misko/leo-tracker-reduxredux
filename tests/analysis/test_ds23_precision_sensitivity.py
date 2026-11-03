from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_precision_sensitivity import precision_sweep


def test_noise_scaling_matches_dense_marginal_covariance_and_is_monotone():
    rng = np.random.default_rng(20261021)
    j, u = rng.normal(size=(40, 2)), rng.normal(size=(40, 6))
    w, prior = rng.uniform(.2, 2., 40), rng.uniform(.5, 3., 6)
    result = precision_sweep(j[:25], u[:25], w[:25], j[25:], u[25:], w[25:], prior, [1., .1, .01])
    previous = result['before_information']
    for row in result['rows']:
        weights = np.r_[w[:25], w[25:]/row['sigma_factor']**2]
        cov = np.diag(1/weights)+(u/prior)@u.T
        np.testing.assert_allclose(row['information'], j.T@np.linalg.solve(cov, j), rtol=2e-10, atol=1e-8)
        assert np.linalg.eigvalsh(row['information']-previous).min() > 0
        previous = row['information']


def test_precision_does_not_remove_an_exact_position_phase_degeneracy():
    j = np.column_stack((np.ones(20), np.linspace(-1, 1, 20)))
    u, w, prior = np.ones((20, 1)), np.ones(20), np.array([.25])
    result = precision_sweep(j[:10], u[:10], w[:10], j[10:], u[10:], w[10:], prior, [1., .01])
    assert result['rows'][-1]['information'][0, 0] < .251


@pytest.mark.parametrize('factors', [[0.], [-1.], [np.nan], [], [[1.]]])
def test_invalid_frequency_precision_factors_rejected(factors):
    with pytest.raises(ValueError):
        precision_sweep(np.eye(2), np.ones((2, 1)), np.ones(2), np.eye(2), np.ones((2, 1)), np.ones(2), np.ones(1), factors)
