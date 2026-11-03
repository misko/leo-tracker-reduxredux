"""Analytic and original-likelihood tests for the slope-prior experiment."""
from dataclasses import replace
import json
from types import SimpleNamespace
import numpy as np
import pytest
import run_soft as run
from slope_penalty import penalty, PenalizedObjective, annotate_region


def test_matched_configuration_and_equal_cost_at_outer_limits():
    for phase, cfg in run.PHASES.items():
        assert cfg['sigma'] == 2. and cfg['levels'] == [40., 20., 10., 5.] and cfg['edge'] == 'nearest'
        if phase == 'hard30':
            continue
        for sign in (-1., 1.):
            np.testing.assert_allclose(penalty([sign * cfg['width'], 0.], cfg['slope_prior'])[0], 4.5)


def test_analytic_gradients_and_smooth_onset():
    for cfg in run.PHASES.values():
        spec = cfg['slope_prior']
        for b in (-61., -30., -15., -1., 0., 1., 15., 30., 61.):
            vector = np.array([b, -.7 * b])
            _, gradient = penalty(vector, spec)
            numeric = []
            for i in range(2):
                d = np.eye(2)[i] * 1e-5
                numeric.append((penalty(vector + d, spec)[0] - penalty(vector - d, spec)[0]) / 2e-5)
            np.testing.assert_allclose(gradient, numeric, atol=1e-7, rtol=1e-6)
    for onset in (15., 30.):
        spec = dict(kind='smooth', onset=onset, scale=5.)
        value, grad = penalty([-onset, onset], spec)
        assert value == 0 and not grad.any()


class Quadratic:
    size = 9
    def __init__(self, target):
        self.target = np.asarray(target)
        self.prior = SimpleNamespace(radius_km=250.)
        self.bank = SimpleNamespace(numbers=np.array([1, 2]), nodes_s=np.array([-100., 100.]))
        self.observations = SimpleNamespace(times_s=np.array([-1., 1.]))
        self.basis = np.array([[1.], [-1.]]) / np.sqrt(2.)
        self.scales = np.array([1., 1., 200., 2., 200., 2., 200., 1., 1.])
    def evaluate(self, vector):
        gradient = (vector - self.target) / self.scales ** 2
        return .5 * float((vector - self.target) @ gradient), gradient, SimpleNamespace(
            responsibilities=np.ones((2, 2)), residual_hz=np.zeros((2, 2)))


@pytest.mark.parametrize('phase', list(run.PHASES))
def test_solver_matches_known_penalized_optimum_and_preserves_zero_c(phase):
    cfg = run.PHASES[phase]
    for target_slope in (20., 100.):
        target = np.zeros(9)
        target[[3, 5]] = [target_slope, -target_slope]
        target[6] = 100.
        objective = PenalizedObjective(Quadratic(target), cfg['slope_prior'])
        fit = run.engine.fit_position(objective, np.zeros(9), rf_arm='zero-c',
                                     slope_half_width_hz_s=cfg['width'], maximum_iterations=200)
        spec = cfg['slope_prior']
        if spec['kind'] == 'gaussian':
            expected = target_slope / (1 + 4 / spec['scale'] ** 2)
        elif spec['kind'] == 'smooth' and target_slope > spec['onset']:
            expected = (target_slope / 4 + spec['onset'] / spec['scale'] ** 2) / (.25 + 1 / spec['scale'] ** 2)
        else:
            expected = target_slope
        expected = min(expected, cfg['width'])
        np.testing.assert_allclose(fit.vector[[3, 5]], [expected, -expected], atol=1e-5)
        assert fit.converged and fit.vector[6] == 0.


def test_frozen_prior_is_counted_once_and_timing_is_separate():
    spec = dict(kind='gaussian', scale=10.)
    final = np.zeros(9); final[3] = 20.
    post = np.zeros(9); post[5] = 10.
    row = dict(vector=final.tolist(), objective=105., timing_penalty=5., selection_score=112.)
    region = dict(candidates=[row], runs=[row], calibration=dict(postfit=dict(vector=post.tolist())))
    result = annotate_region(region, spec)
    assert result['candidates'][0]['slope_penalty'] == 2.
    assert result['candidates'][0]['timing_penalty'] == 3.
    assert result['candidates'][0]['selection_score'] == 112.5
    assert result['runs'][0] == result['candidates'][0]
    assert annotate_region(result, spec) is result
    assert row['selection_score'] == 112.


def test_native_and_original_objectives_match_with_each_prior():
    _, obs, bank, prior, score = run.data.load('N01')
    score = replace(score, relative_sigma_s=2.)
    path = next((run.PREVIOUS / 'results' / 'N01' / 'sigma2_60' / 'regions').glob('*.json'))
    region = json.loads(path.read_text())
    bank = bank.select(region['association']['selected_indices'])
    vector = np.asarray(region['candidates'][0]['vector'])
    baseline = np.asarray(region['calibration']['receiver_baseline_hz'])
    for phase, cfg in run.PHASES.items():
        run.ACTIVE_PHASE = phase
        native = run.native_objective(obs, bank, prior, score, receiver_baseline_hz=baseline)
        oracle = run.original_objective(obs, bank, prior, score, receiver_baseline_hz=baseline)
        # Force the smooth penalty to be active in this fixed-state parity test.
        vector[[3, 5]] = [.9 * cfg['width'], -.8 * cfg['width']]
        nv, ng, nt = native.evaluate(vector)
        ov, og, ot = oracle.evaluate(vector)
        np.testing.assert_allclose(nv, ov, atol=1e-6, rtol=0)
        np.testing.assert_allclose(ng, og, atol=1e-6, rtol=1e-7)
        raw, gradient, terms = oracle.base.evaluate(vector)
        cost, derivative = penalty(vector[[3, 5]], cfg['slope_prior'])
        np.testing.assert_allclose(ov, raw + cost, atol=1e-10, rtol=0)
        np.testing.assert_allclose(og[[3, 5]], gradient[[3, 5]] + derivative, atol=1e-10, rtol=0)
        assert ot.nll == terms.nll
        if phase == 'hard30':
            assert ov == raw
            np.testing.assert_array_equal(og, gradient)


def test_summary_pairing_retains_failures_without_matching_other_scans():
    from analyze_soft import paired
    rows = [dict(label='N01', phase='hard30', arm='zero-c', accepted=True, error_km=2.),
            dict(label='N02', phase='hard30', arm='zero-c', accepted=True, error_km=3.),
            dict(label='N01', phase='gaussian30', arm='zero-c', accepted=True, error_km=1.),
            dict(label='N02', phase='gaussian30', arm='zero-c', accepted=False, error_km=None)]
    result = paired(rows, 'zero-c', 'gaussian30', 'hard30')
    assert result['count'] == result['improved'] == 1
    assert result['worsened'] == result['unchanged'] == 0
    assert result['median_change_km'] == -1.
