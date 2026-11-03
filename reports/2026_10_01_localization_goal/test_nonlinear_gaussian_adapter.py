from types import SimpleNamespace

import numpy as np
from nonlinear_gaussian_adapter import FixedGaussianPort

from leo.analysis.gaussian_sum_location import Prediction


class Port:
    candidate_count = 2
    observation = np.array([3., -2.])
    observation_ids = ('a', 'b')
    config = SimpleNamespace(signal_prior=.8)

    def predict_selected(self, state, index):
        jacobian = np.array([[1., 0., 2., 0., 0., .2, 0.],
                             [0., 1., .4, 0., 1., .3, 0.]])
        return Prediction(jacobian@state, jacobian, np.eye(2), True)

    def score_selected(self, state, index):
        assert index == 2 and np.all(state[2:] == 0)
        return -7.


def test_normalized_gaussian_score_covariance_and_gradient():
    port = FixedGaussianPort(Port(), 0)
    state = np.arange(7)*.1
    prediction = port.predict_selected(state, 0)
    residual = port.observation-prediction.mean
    expected = np.log(.4)-.5*(2*np.log(2*np.pi)+2*np.log(2)+residual@residual/2)
    np.testing.assert_allclose(port.score_selected(state, 0), expected)
    assert np.all(np.isneginf(port.score_all(state)[1:]))
    np.testing.assert_equal(prediction.covariance, 2*np.eye(2))
    for column in range(7):
        delta = np.eye(7)[column]*1e-5
        finite = (port.score_selected(state+delta, 0)
                  -port.score_selected(state-delta, 0))/2e-5
        np.testing.assert_allclose(finite, prediction.jacobian[:, column]@residual/2, atol=1e-9)


def test_background_keeps_original_model_at_nominal_nuisance():
    port = FixedGaussianPort(Port(), 2)
    np.testing.assert_equal(port.score_all(np.ones(7)), [-np.inf, -np.inf, -7.])
