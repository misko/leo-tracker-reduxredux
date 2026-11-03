import numpy as np
import pytest

from leo.analysis.localization_uncertainty import profiled_position_covariance


def test_profiled_covariance_matches_full_inverse_and_coordinate_rescaling():
    rng = np.random.default_rng(812)
    design = rng.normal(size=(40, 7))
    info = design.T@design+np.eye(7)
    actual = profiled_position_covariance(info)
    np.testing.assert_allclose(actual, np.linalg.inv(info)[:2, :2])
    scaling = np.diag([1., 1., .001, 100., 5., 1., 20.])
    np.testing.assert_allclose(profiled_position_covariance(scaling@info@scaling), actual)


def test_shared_nuisance_coupling_increases_uncertainty():
    info = np.array([[2., 0., 1.], [0., 1., 0.], [1., 0., 1.]])
    actual = profiled_position_covariance(info)
    np.testing.assert_allclose(actual, np.eye(2))
    assert actual[0, 0] > np.linalg.inv(info[:2, :2])[0, 0]


def test_invalid_and_unidentifiable_geometry_fail_explicitly():
    with pytest.raises(ValueError):
        profiled_position_covariance(np.ones((2, 3)))
    with pytest.raises(np.linalg.LinAlgError):
        profiled_position_covariance(np.ones((3, 3)))
