import numpy as np
import pytest

from diagnose_ds23_predictive_covariance import contributions, gaussian_cost


def test_mean_covariance_contributions_sum_to_total_and_recover_mean_only_case():
    old, new = np.array([2., -1.]), np.array([.5, -.3])
    cov = np.array([[2., .3], [.3, 1.]])
    result = contributions(old, cov, new, cov)
    assert result['covariance_Shapley_change'] == pytest.approx(0.)
    assert result['mean_Shapley_change'] == pytest.approx(result['total_change'])
    assert result['total_change'] < 0
    altered = contributions(old, cov, new, 2*cov)
    assert altered['mean_Shapley_change'] + altered['covariance_Shapley_change'] == pytest.approx(altered['total_change'])


def test_unchanged_mean_has_zero_mean_contribution_even_when_covariance_rotates():
    raw = np.array([3., .2])
    old, new = np.diag([1., 9.]), np.diag([9., 1.])
    result = contributions(raw, old, raw, new)
    assert result['mean_Shapley_change'] == pytest.approx(0.)
    assert result['covariance_Shapley_change'] == pytest.approx(result['total_change'])
    assert result['total_change'] < 0
    with pytest.raises(ValueError):
        gaussian_cost(raw, np.eye(3))
