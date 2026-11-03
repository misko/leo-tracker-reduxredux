from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_spatial_score_integration import local_covariance, score_integral


def test_gaussian_recovers_covariance_and_mean_without_target_coordinate():
    covariance=np.array([[.8, .2], [.2, .5]]); mean=np.array([2., -3.])
    score=lambda x: float((x-mean)@np.linalg.solve(covariance, x-mean)+1234.)
    np.testing.assert_allclose(local_covariance(score, mean), covariance, atol=1e-9)
    result=score_integral(score, mean, covariance, 9)
    np.testing.assert_allclose(result['mean'], mean, atol=1e-12)
    np.testing.assert_allclose(result['covariance'], covariance, atol=1e-12)
    assert abs(result['log_relative_mass'])<1e-12


def test_proposal_centre_does_not_force_integrated_mean():
    target=np.array([.3, -.2]); score=lambda x: float(np.sum((x-target)**2))
    result=score_integral(score, np.zeros(2), np.eye(2), 13)
    np.testing.assert_allclose(result['mean'], target, atol=1e-11)


def test_indefinite_curvature_is_rejected_instead_of_regularized_silently():
    with pytest.raises(ValueError, match='positive definite'):
        local_covariance(lambda x: float(x[0]**2-x[1]**2), np.zeros(2))
