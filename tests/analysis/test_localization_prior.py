import numpy as np
import pytest

from leo.analysis.localization_prior import ScalarStudentPriorPort


def test_normalization_variance_and_heavy_tail():
    port = ScalarStudentPriorPort(1, 2, .25, 'prior:epoch')
    # Independent closed t4 formula; integration checks the declared variance.
    x = np.linspace(-100., 100., 200001)
    scale = np.sqrt(.125)
    density = .375/scale*(1+x*x/(4*scale*scale))**-2.5
    np.testing.assert_allclose(np.trapezoid(density, x), 1., atol=1e-8)
    np.testing.assert_allclose(np.trapezoid(x*x*density, x), .25, atol=2e-5)
    for value in [0., .3, 2.]:
        expected = np.log(.375/scale)-2.5*np.log1p(value*value/(4*scale*scale))
        assert port.score_selected(np.array([0., value]), 0) == pytest.approx(expected)
    gaussian_log = -.5*np.log(2*np.pi*.25)-.5*2.**2/.25
    assert port.score_selected(np.array([0., 2.]), 0) > gaussian_log


def test_irls_gradient_and_isolated_coordinate():
    port = ScalarStudentPriorPort(2, 4, .25, 'prior:epoch')
    state = np.array([1., -2., .7, .2])
    prediction = port.predict_selected(state, 0)
    for column in range(4):
        shift = np.eye(4)[column]*1e-6
        derivative = (port.score_selected(state+shift, 0)
                      -port.score_selected(state-shift, 0))/2e-6
        expected = -5*state[2]/(.5+state[2]**2) if column == 2 else 0.
        assert derivative == pytest.approx(expected, abs=1e-8)
    np.testing.assert_equal(prediction.jacobian, [[0., 0., 1., 0.]])
    assert np.isneginf(port.score_all(state)[1])
    with pytest.raises(ValueError):
        ScalarStudentPriorPort(4, 4, .25, 'invalid')
    with pytest.raises(ValueError):
        port.predict_selected(np.zeros(3), 0)
