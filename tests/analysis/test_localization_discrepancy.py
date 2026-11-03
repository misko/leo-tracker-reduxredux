import numpy as np
import pytest

from leo.analysis.localization_discrepancy import slope_discrepancy_scale


def test_random_slope_covariance_and_trace_matched_control():
    c = np.diag([2., 3., 4.])
    v = np.array([-2., 0., 2.])
    actual = slope_discrepancy_scale(c, v, .5)
    np.testing.assert_allclose(actual-c, [[1, 0, -1], [0, 0, 0], [-1, 0, 1]])
    control = slope_discrepancy_scale(c, v, .5, isotropic_control=True)
    assert np.isclose(np.trace(actual), np.trace(control))
    assert np.linalg.eigvalsh(actual).min() > 0
    np.testing.assert_array_equal(slope_discrepancy_scale(c, v, 0), c)


def test_invalid_scale_is_rejected():
    with pytest.raises(ValueError):
        slope_discrepancy_scale(np.eye(2), np.ones(2), -1)
    with pytest.raises(ValueError):
        slope_discrepancy_scale(np.eye(2), np.ones(3), 1)
    with pytest.raises(np.linalg.LinAlgError):
        slope_discrepancy_scale(-np.eye(2), np.ones(2), 1)
