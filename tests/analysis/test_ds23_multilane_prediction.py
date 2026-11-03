from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_multilane_prediction import condition_multiple


def test_per_probe_conditionals_equal_full_Gaussian_precision_for_different_covariances():
    y = np.array([12., 20., 16., 32.]); u = np.array([[1., 2.], [3., 4.], [2., 7.], [5., 9.]])
    mean = np.array([2., -1., 4., 3.]); v = np.array([100., 225.]); k = np.array([.9, .8])
    covariance = np.diag(np.r_[v, v]); covariance[0, 2] = covariance[2, 0] = v[0]*k[0]
    covariance[1, 3] = covariance[3, 1] = v[1]*k[1]
    yy, uu, mm = condition_multiple(y[2:], u[2:], mean[2:], y[:2], u[:2], mean[:2], [0, 1], [0, 1], k)
    design = np.vstack((u[:2]/np.sqrt(v[:, None]), uu/np.sqrt((v*(1-k*k))[:, None])))
    response = np.r_[(y[:2]-mean[:2])/np.sqrt(v), (yy-mm)/np.sqrt(v*(1-k*k))]
    np.testing.assert_allclose(design.T@design, u.T@np.linalg.solve(covariance, u), atol=1e-14)
    np.testing.assert_allclose(design.T@response, u.T@np.linalg.solve(covariance, y-mean), atol=1e-14)


def test_reusing_primary_probe_requires_joint_secondary_covariance_and_is_rejected():
    with pytest.raises(ValueError, match='distinct'):
        condition_multiple([1., 2.], [[1.], [1.]], [0., 0.], [3.], [[1.]], [0.], [0, 1], [0, 0], [.9, .9])
