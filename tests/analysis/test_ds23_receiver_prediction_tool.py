import numpy as np
import pytest
from probe_ds23_receiver_prediction import gaussian_score


def test_shared_error_covariance_scores_common_and_opposing_residuals_differently():
    covariance=np.eye(2)+100*np.ones((2,2))
    same=gaussian_score([10,10],covariance)
    opposite=gaussian_score([10,-10],covariance)
    assert same['quadratic']<2 and opposite['quadratic']>199
    # An independent-error model cannot make this distinction.
    assert gaussian_score([10,10],101*np.eye(2))==gaussian_score([10,-10],101*np.eye(2))


def test_predictive_score_penalizes_inflating_uncertainty_without_error():
    assert gaussian_score([0,0],np.eye(2))['negative_twice_log_density']<gaussian_score([0,0],10*np.eye(2))['negative_twice_log_density']


def test_indefinite_predictive_covariance_fails_closed():
    with pytest.raises(np.linalg.LinAlgError):gaussian_score([0,0],[[1,2],[2,1]])
