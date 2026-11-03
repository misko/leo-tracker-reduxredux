import numpy as np
from nonlinear_laplace_adapter import FixedNuisancePort, observed_information

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.robust_likelihood import student_t_logpdf


class Port:
    candidate_count = 1
    observation = np.array([1., -.5, .3])
    observation_ids = ('a', 'b', 'c')
    matrix = np.array([[1., .2, .3, 0., .1, .3], [.2, 1., .3, .1, 0., .3],
                       [.1, .4, .2, 0., .2, .2]])

    def predict_selected(self, state, index):
        return Prediction(self.matrix@state, self.matrix, np.eye(3))

    def score_selected(self, state, index):
        return student_t_logpdf(self.observation-self.matrix@state, np.eye(3), 4.)


def test_observed_student_hessian_against_closed_form():
    port = Port()
    state = np.arange(6)*.03
    r = port.observation-port.matrix@state
    w = 7/(4+r@r)
    a = port.matrix.T@r
    prior = np.diag([0., 0., 1., 4., 4., 4.])
    exact = prior+w*port.matrix.T@port.matrix-2*w/(4+r@r)*np.outer(a, a)
    actual = observed_information([port], [0], state, np.arange(6), step=1e-4)
    np.testing.assert_allclose(actual, exact, atol=1e-8)
    nuisance = observed_information([port], [0], state, np.arange(2, 6), step=1e-4)
    np.testing.assert_allclose(nuisance, exact[2:, 2:], atol=1e-8)


def test_fixed_position_score_and_jacobian():
    base = Port()
    port = FixedNuisancePort(base, 0, [.3, -.2])
    state = np.arange(6)*.1
    effective = state.copy()
    effective[:2] = [.3, -.2]
    assert port.score_selected(state, 0) == base.score_selected(effective, 0)
    prediction = port.predict_selected(state, 0)
    np.testing.assert_equal(prediction.jacobian[:, :2], 0.)
    np.testing.assert_equal(prediction.jacobian[:, 2:], base.matrix[:, 2:])
    assert np.isneginf(port.score_all(state)[1])
