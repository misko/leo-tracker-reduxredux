"""Routing and feasibility tests for the two additional controlled passes."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import run_variants as run
from leo.contracts.regional_position import RegionalPrior, PositionScore


def test_only_one_setting_changes_per_variant():
    original = dict(sigma=1., width=60., levels=[40., 20., 10., 5.], edge='nearest')
    assert run.PHASES['sigma2_60'] == {**original, 'sigma': 2.}
    assert run.PHASES['sigma1_30'] == {**original, 'width': 30.}
    assert run.engine.HERE == run.HERE != run.OLD
    assert run.data.HERE == run.OLD


def test_sigma_changes_relative_prior_only():
    original = PositionScore(name='V16', sigma_hz=125., detection_budget=1.6,
                             clutter_rate=.5, common_sigma_s=3., relative_sigma_s=.15)
    run.engine.CONTEXT['test'] = ({}, None, None, RegionalPrior(), original)
    try:
        for phase, cfg in run.PHASES.items():
            result = run.engine.context('test', phase)[-1]
            assert result == replace(original, relative_sigma_s=cfg['sigma'])
    finally:
        del run.engine.CONTEXT['test']


def test_hard_width_audit_accepts_30_and_rejects_31():
    objective = SimpleNamespace(prior=RegionalPrior(),
        bank=SimpleNamespace(numbers=np.array([1]), nodes_s=np.array([-30., 30.])),
        observations=SimpleNamespace(times_s=np.array([0., 1.])), basis=np.empty((1, 0)))
    vector = np.zeros(8)
    vector[3] = 30.
    checked = run.engine.audit(objective, vector, np.zeros(8), 'zero-c', [0., 0.], 25., 30.)
    assert checked['feasible'] and checked['converged'] and checked['slope_active_bounds'] == [3]
    vector[3] = 31.
    assert not run.engine.audit(objective, vector, np.zeros(8), 'zero-c', [0., 0.], 25., 30.)['feasible']
    assert run.engine.audit(objective, vector, np.zeros(8), 'zero-c', [0., 0.], 25., 60.)['feasible']


def test_pairing_uses_same_scan_and_excludes_missing_acceptance():
    import compare_variants
    rows = [dict(label='N01', phase='before', arm='zero-c', accepted=True, error_km=100.),
            dict(label='N02', phase='before', arm='zero-c', accepted=True, error_km=2.),
            dict(label='N01', phase='sigma2_60', arm='zero-c', accepted=True, error_km=3.),
            dict(label='N02', phase='sigma2_60', arm='zero-c', accepted=False, error_km=None)]
    result = compare_variants.paired(rows, 'zero-c', 'sigma2_60', 'before')
    assert result['count'] == result['improved'] == 1
    assert result['worsened'] == 0 and result['median_change_km'] == -97.


def test_two_second_prior_and_native_objective_against_original():
    import json
    from leo.analysis.regional_position_score import PositionObjective
    _, obs, bank, prior, original_score = run.data.load('N01')
    region_path = next((run.OLD / 'results' / 'N01' / 'after' / 'regions').glob('*.json'))
    region = json.loads(region_path.read_text())
    bank = bank.select(region['association']['selected_indices'])
    vector = np.asarray(region['candidates'][0]['vector'])
    baseline = np.asarray(region['calibration']['receiver_baseline_hz'])
    values = []
    for sigma in (1., 2.):
        score = replace(original_score, relative_sigma_s=sigma)
        oracle = PositionObjective(obs, bank, prior, score, receiver_baseline_hz=baseline)
        native = run.engine.NativeObjective(obs, bank, prior, score, receiver_baseline_hz=baseline)
        value, gradient, terms = oracle.evaluate(vector)
        fast, fast_gradient, _ = native.evaluate(vector)
        np.testing.assert_allclose(fast, value, atol=1e-6, rtol=0)
        np.testing.assert_allclose(fast_gradient, gradient, atol=1e-6, rtol=1e-7)
        common = .5 * (vector[7] / score.common_sigma_s) ** 2
        values.append((terms.nll, value - terms.nll - common))
    np.testing.assert_allclose(values[0][0], values[1][0], atol=1e-10, rtol=0)
    np.testing.assert_allclose(values[1][1], values[0][1] / 4, atol=1e-10, rtol=0)
