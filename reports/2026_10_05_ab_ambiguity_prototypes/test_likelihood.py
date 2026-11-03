import numpy as np
import pytest

from likelihood import ALIAS, Likelihood, freeze


def model(hard=False, eta=0, mask=None):
    return Likelihood(np.array([0., 100., 200.]), np.array([[.1], [.2], [-.1]]), 3,
                      np.ones(3, bool) if mask is None else mask, np.array([0, 1, 2]), hard, eta)


def test_frozen_masks_threshold_ties_and_clutter():
    p = np.array([[.8, .05, .01], [.6, .05001, .01], [.03, .02, .01]])
    frozen = freeze(p, 1-p.sum(axis=1))
    np.testing.assert_array_equal(frozen['keep'], [True, False, False])
    np.testing.assert_array_equal(frozen['unambiguous'], [True, False, True])
    np.testing.assert_array_equal(frozen['real'], [True, True, False])


@pytest.mark.parametrize('hard,eta', [(False, 0), (False, 1), (False, 2), (True, 0)])
def test_analytic_prediction_and_rf_gradient(hard, eta):
    obj = model(hard, eta)
    prediction = np.array([[30., 140., 800.], [20., 80., 500.], [1000., 450., 280.]])
    visible = np.ones((3, 3), bool)
    result = obj.evaluate(prediction, visible, sigma_hz=200.)
    eps = .001
    for i in range(3):
        for s in range(3):
            delta = np.zeros_like(prediction); delta[i, s] = eps
            num = (obj.evaluate(prediction+delta, visible, sigma_hz=200.)['total_log_likelihood']
                   - obj.evaluate(prediction-delta, visible, sigma_hz=200.)['total_log_likelihood'])/(2*eps)
            assert num == pytest.approx(result['prediction_gradient'][i, s], abs=2e-8)
    obj.coefficients[0] = eps
    plus = obj.evaluate(prediction, visible, sigma_hz=200.)['total_log_likelihood']
    obj.coefficients[0] = -eps
    minus = obj.evaluate(prediction, visible, sigma_hz=200.)['total_log_likelihood']
    assert (plus-minus)/(2*eps) == pytest.approx(float(obj.features[:, 0] @ result['prediction_gradient'].sum(axis=1)), abs=2e-8)
    assert np.all(result['irls_weights'] >= 0)
    np.testing.assert_allclose(result['row_association_probability'].sum(axis=1)+result['row_clutter_probability'], 1.)


def test_ambiguity_cost_equal_candidates_and_no_visible_candidates():
    obj = model(eta=2)
    pred = np.repeat(obj.measured[:, None], 3, axis=1)
    visible = np.array([[1, 1, 1], [1, 0, 0], [0, 0, 0]], bool)
    result = obj.evaluate(pred, visible, sigma_hz=200.)
    assert result['ambiguity_penalty'] == pytest.approx(2*np.log(3))
    assert np.all(np.isfinite(result['prediction_gradient']))
    assert result['row_clutter_probability'][2] == pytest.approx(1.)


def test_hard_identity_never_switches_and_dropped_rows_have_zero_gradient():
    obj = model(hard=True, mask=np.array([1, 0, 1], bool))
    pred = np.array([[700., 0., 100.], [20., 80., 500.], [200., 250., 280.]])
    result = obj.evaluate(pred, np.ones((3, 3), bool), sigma_hz=200.)
    assert result['prediction_gradient'][0, 0] != 0
    np.testing.assert_array_equal(result['prediction_gradient'][0, 1:], 0.)
    np.testing.assert_array_equal(result['prediction_gradient'][1], 0.)
    np.testing.assert_array_equal(result['irls_weights'][1], 0.)
    obj.owners[0] = 1
    assert obj.evaluate(pred, np.ones((3, 3), bool), sigma_hz=200.)['total_log_likelihood'] > result['total_log_likelihood']


def test_alias_periodicity():
    obj = model(eta=1)
    pred = np.array([[30., 140., 800.], [20., 80., 500.], [1000., 450., 280.]])
    a = obj.evaluate(pred, np.ones((3, 3), bool), sigma_hz=200.)
    b = obj.evaluate(pred+ALIAS, np.ones((3, 3), bool), sigma_hz=200.)
    assert a['total_log_likelihood'] == pytest.approx(b['total_log_likelihood'], abs=1e-10)
