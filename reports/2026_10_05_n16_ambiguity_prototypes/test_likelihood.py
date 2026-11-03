"""Owned tests for the N-cohort extension; synthetic plus explicit cached-data checks."""
from types import SimpleNamespace
import numpy as np
import pytest

import experiment as ex
from likelihood import Likelihood, freeze
from smooth_visibility_model import finite_set_terms, gate_terms


def fixture(mode):
    data = SimpleNamespace(measured=np.array([0., 100., 200.]), times=np.arange(3), numbers=np.arange(3))
    frozen = dict(winner=np.array([0, 1, 2]), real=np.ones(3, bool), keep=np.array([1, 0, 1], bool))
    model = Likelihood(data, np.array([[.1], [.2], [-.1]]), frozen, mode)
    pred = np.array([[30., 140., 800.], [20., 80., 500.], [1000., 450., 280.]])
    sine = np.array([[.005, .007, -.1], [.1, .01, .015], [.009, .011, .1]])
    model.geometry = (sine, np.zeros_like(sine))
    return model, pred, sine


def test_threshold_and_clutter():
    p = np.array([[.8, .05, .01], [.6, .050001, .01], [.03, .02, .01]])
    f = freeze(p, 1-p.sum(axis=1))
    np.testing.assert_array_equal(f['keep'], [True, False, False])


@pytest.mark.parametrize('mode', list(ex.MODES))
def test_prediction_and_smooth_geometry_gradients(mode):
    model, pred, sine = fixture(mode)
    vis = sine >= 0
    r = model.evaluate(pred, vis, sigma_hz=200.)
    for i in range(3):
        for j in range(3):
            df = np.zeros_like(pred); df[i, j] = .001
            numerical = (model.evaluate(pred+df, vis, sigma_hz=200.)['total_log_likelihood']
                -model.evaluate(pred-df, vis, sigma_hz=200.)['total_log_likelihood'])/.002
            assert numerical == pytest.approx(r['prediction_gradient'][i, j], abs=2e-8)
            ds = np.zeros_like(sine); ds[i, j] = 1e-7
            model.geometry = (sine+ds, np.zeros_like(sine))
            plus = model.evaluate(pred, vis, sigma_hz=200.)['total_log_likelihood']
            model.geometry = (sine-ds, np.zeros_like(sine))
            minus = model.evaluate(pred, vis, sigma_hz=200.)['total_log_likelihood']
            model.geometry = (sine, np.zeros_like(sine))
            assert (plus-minus)/2e-7 == pytest.approx(-r['sine_loss_gradient'][i, j], abs=1e-5)
    np.testing.assert_allclose(r['row_association_probability'].sum(axis=1)+r['row_clutter_probability'], 1.)


def test_baseline_parity_variable_q():
    model, pred, sine = fixture('baseline')
    r = model.evaluate(pred, sine >= 0, sigma_hz=200.)
    q = (.8/3)*gate_terms(sine, 'Q1')[0]
    original = finite_set_terms(model.measured, pred, q, np.ones(3))
    for k in ['total_log_likelihood', 'prediction_gradient', 'row_association_probability', 'irls_weights']:
        np.testing.assert_allclose(r[k], original[k], atol=1e-12)


def test_no_visible_satellite_and_hard_guard():
    model, pred, sine = fixture('penalty_2')
    model.geometry = (-np.ones_like(sine), np.zeros_like(sine))
    r = model.evaluate(pred, sine < 0, sigma_hz=200.)
    assert r['ambiguity_penalty'] == 0
    assert np.isfinite(r['total_log_likelihood'])
    model.hard = True; model.eta = 0
    r = model.evaluate(pred, sine < 0, sigma_hz=200.)
    assert r['hard_invisible_windows'] == 3
    assert r['total_log_likelihood'] < -1e24


def test_cached_n01_objective_parity_and_full_gradient():
    data, receipt, saved = ex.load('N01')
    center = receipt['rf_center_hz']
    old = ex.ConeObjective(data, center, 'fitted-c', 0., None, None, None)
    v = np.array(saved['fitted-c']['best']['vector'])
    original, original_g = old.evaluate(v)
    soft = old.likelihood.last_result
    frozen = freeze(soft['row_association_probability'], soft['row_clutter_probability'])
    control = ex.Objective(data, center, 'fitted-c', frozen, 'baseline')
    actual, grad = control.evaluate(v)
    np.testing.assert_allclose(actual, original, atol=1e-8, rtol=0)
    np.testing.assert_allclose(grad, original_g, atol=1e-8, rtol=0)
    for mode in ['drop_hard', 'penalty_2']:
        obj = ex.Objective(data, center, 'fitted-c', frozen, mode)
        _, g = obj.evaluate(v)
        for axis, step in [(0, 1e-4), (1, 1e-4), (3, 1e-4), (6, 1e-5), (7, 1e-5), (len(v)-1, .001)]:
            dv = np.zeros_like(v); dv[axis] = step
            numerical = (obj.evaluate(v+dv)[0]-obj.evaluate(v-dv)[0])/(2*step)
            assert numerical == pytest.approx(g[axis], abs=.005, rel=3e-5)
