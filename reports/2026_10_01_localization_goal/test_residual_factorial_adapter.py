import numpy as np
import pytest
from residual_factorial_adapter import FixedResidualPort
from test_nonlinear_gaussian_adapter import Port

from leo.analysis.robust_likelihood import student_t_weight


@pytest.mark.parametrize('family', ['gaussian', 'student'])
@pytest.mark.parametrize('scale', [1., 2.])
def test_family_scale_gradient_and_original_covariance(family, scale):
    port = FixedResidualPort(Port(), 0, family=family, scale=scale)
    state = np.arange(7)*.1
    prediction = port.predict_selected(state, 0)
    np.testing.assert_equal(prediction.covariance, scale*np.eye(2))
    residual = port.observation-prediction.mean
    weight = 1. if family == 'gaussian' else student_t_weight(
        float(residual@residual/scale), 2, 4.)
    for column in range(7):
        delta = np.eye(7)[column]*1e-5
        finite = (port.score_selected(state+delta, 0)
                  -port.score_selected(state-delta, 0))/2e-5
        np.testing.assert_allclose(
            finite, weight*prediction.jacobian[:, column]@residual/scale, atol=1e-9)
    np.testing.assert_equal(port.base.predict_selected(state, 0).covariance, np.eye(2))
