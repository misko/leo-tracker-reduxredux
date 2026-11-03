import numpy as np
from leo.analysis.hard60_score import likelihood
from leo.analysis.shared_scan_model import density
from leo.contracts.regional_position import POSITION_SCORES
from audit import band_gradient


def test_uniform_q_conditional_and_legacy_frequency_gradients_agree():
    score = POSITION_SCORES['V16']
    measured = np.array([30., 90., -40., 150.])
    predicted = np.array([[0., 100., 200.], [0., 100., 200.], [0., -100., -200.], [0., 100., 200.]])
    visible = np.array([[True, True, False], [True, False, True], [True, True, True], [False, True, True]])
    legacy = likelihood(measured, predicted, visible, score)
    conditional, _ = density(measured, predicted, visible.astype(float), np.full(4, 125.),
        np.full(3, score.detection_budget/3), score)
    np.testing.assert_allclose(legacy.prediction_gradient, conditional.prediction_gradient, atol=1e-16, rtol=1e-14)
    np.testing.assert_allclose(legacy.responsibilities, conditional.responsibilities, atol=1e-16, rtol=1e-14)


def test_changed_q_can_change_band_gradient_without_changing_prediction():
    score = POSITION_SCORES['V16']
    measured = np.array([30., 90., -40., 150.])
    predicted = np.tile([0., 100., 200.], (4, 1))
    receiver, channel = np.array([0, 0, 1, 1]), np.full(4, 5)
    def gradient(q):
        terms, _ = density(measured, predicted, np.ones((4, 3)), np.full(4, 125.), np.array(q), score)
        return band_gradient(terms, receiver, channel, [0., 0.])
    assert np.linalg.norm(gradient([.8, .6, .2])-gradient([1.6/3]*3)) > 1e-5
