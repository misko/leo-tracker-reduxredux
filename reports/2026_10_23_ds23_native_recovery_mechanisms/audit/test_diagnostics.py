import numpy as np
from diagnostics import dense_prediction
import diagnostics


def test_shared_calibration_is_integrated_once_across_entries():
    # Shared unknown constant: joint covariance has a nonzero off-diagonal.
    result = dense_prediction([1., 2.], [[1.], [1.]], [[4.]], [1., 1.], [0, 1], bias_sigma=0.)
    np.testing.assert_allclose(result['covariance_hz2'], [[5., 4.], [4., 5.]])
    np.testing.assert_allclose(result['predictive_quadratic'], 1.)
    np.testing.assert_allclose(result['predictive_logdet'], np.log(9.))
    # Independent per-path scoring happens to give the same quadratic here,
    # but incorrectly gives logdet log25.
    assert not np.isclose(result['predictive_logdet'], np.log(25.))


def test_independent_path_bias_and_shared_within_path_bias():
    result = dense_prediction(np.zeros(3), np.zeros((3, 1)), [[1.]], np.ones(3), [0, 0, 1], bias_sigma=2.)
    np.testing.assert_allclose(result['covariance_hz2'], [[5., 4., 0.], [4., 5., 0.], [0., 0., 5.]])
    np.testing.assert_allclose(result['predictive_objective'], np.log(45.)+3*np.log(2*np.pi))


def test_conditional_gradient_components_add_without_phase_refresh(monkeypatch):
    reference = np.array([3.])
    p = type('Problem', (), {'reference': reference})()
    def fake_decompose(problem, x, powers):
        assert problem.reference is reference
        curved = x[0]**2+2*x[1]
        quadratic = 3*x[0]-x[1]**2
        logdet = x[0]+x[1]
        return dict(curved_objective=curved, predictive_quadratic=quadratic,
                    predictive_logdet=logdet, predictive_normalization=7.,
                    predictive_objective=quadratic+logdet+7.,
                    total_objective=curved+quadratic+logdet+7.)
    monkeypatch.setattr(diagnostics, 'decompose', fake_decompose)
    g = diagnostics.conditional_gradients(p, [2., 3.], [])['gradients']
    np.testing.assert_allclose(g['curved_objective'], [4., 2.])
    np.testing.assert_allclose(g['predictive_quadratic'], [3., -6.])
    np.testing.assert_allclose(g['predictive_logdet'], [1., 1.])
    np.testing.assert_allclose(g['total_objective'], [8., -3.])
