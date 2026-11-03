import importlib.util
from pathlib import Path

import numpy as np
import pytest
import test_bank_expansion as fixture

spec = importlib.util.spec_from_file_location('candidate_screen', Path(__file__).with_name(
    'candidate_screen.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
case = fixture.case


def test_novelty_ranking_avoids_redundant_curve_and_deduplicates():
    rows = [dict(number=i, gain=g, timing_prior_delta=0.) for i, g in
            ((10, 10.), (11, 9.), (12, 8.))]
    chosen = core.greedy_select(rows, np.array([[10., 0.], [9., 0.], [0., 8.]]),
                                max_additions=8)
    assert [r['number'] for r in chosen] == [10, 12]
    assert len({r['number'] for r in chosen}) == len(chosen)


def test_exact_single_addition_density_timing_and_predictor_inventory(case):
    ctx, regional = case
    ctx.source_id = 'synthetic'
    additions, result = core.screen(ctx, regional, max_additions=2, max_seconds=10)
    assert result['state'] == 'complete'
    assert len(additions) <= 2 and len(set(additions)) == len(additions)
    assert not set(additions) & set(ctx.bank.numbers)
    assert result['predictor_calls'] == 83 and result['candidate_timing_evaluations'] == 3*82
    assert len(result['candidates']) == 3
    row = result['candidates'][0]
    expanded, _ = fixture.core.expandable_context(ctx, [row['number']], regional=regional)
    tau = ctx.vector[7]+ctx.model.basis@ctx.vector[8:]
    added_tau = np.r_[tau, row['best_timing_s']]
    expanded.vector[7] = added_tau.mean()
    expanded.vector[8:] = expanded.model.basis.T@(added_tau-added_tau.mean())
    old = ctx.model.evaluate_joint(ctx.vector, ctx.nuisance)
    new = expanded.model.evaluate_joint(expanded.vector, expanded.nuisance)
    data_gain = old[3].nll-new[3].nll
    penalty = (core.timing_penalty(added_tau, ctx.model.score)
               -core.timing_penalty(tau, ctx.model.score))
    assert row['data_gain'] == pytest.approx(data_gain, abs=1e-10)
    assert row['timing_prior_delta'] == pytest.approx(penalty, abs=1e-10)
    assert row['gain'] == pytest.approx(data_gain-penalty, abs=1e-10)


def test_no_held_cfo_influence_and_uniform_row_cap(case, monkeypatch):
    from dataclasses import replace
    ctx, regional = case
    ctx.source_id = 'synthetic'
    monkeypatch.setattr(core, 'MAX_ROWS', 4)
    a, da = core.screen(ctx, regional, max_additions=2, max_seconds=10)
    modified = replace(ctx.observations, measured_hz=ctx.observations.measured_hz+
                       np.where(ctx.train_mask, 0., 12345678.))
    changed = replace(ctx, observations=modified)
    changed.source_id = ctx.source_id
    b, db = core.screen(changed, regional,
                        max_additions=2, max_seconds=10)
    assert a == b and da['candidates'] == db['candidates']
    assert da['selected'] == db['selected'] and da['scored_rows'] == 4
    assert da['row_indices'] == [0, 4, 8, 14]
    assert da['row_scale'] == 2


def test_soft_horizon_matches_original_equations(case):
    from leo.analysis.shared_scan_model import elevation_geometry, horizon_weight
    ctx, regional = case
    tau = np.linspace(-5, 5, len(regional.numbers))
    _, actual = core.prediction_weight(regional, ctx.observations, ctx.prior,
                                       ctx.vector[:2], tau, ctx.model.visibility_width)
    sine = elevation_geometry(regional, ctx.observations, ctx.prior, ctx.vector[:2], tau)[0]
    np.testing.assert_allclose(actual, horizon_weight(sine, ctx.model.visibility_width)[0],
                               atol=1e-14, rtol=0)


def test_expired_budget_and_invalid_options_never_predict(case, monkeypatch):
    ctx, regional = case
    ctx.source_id, ctx.deadline = 'synthetic', 0.
    monkeypatch.setattr(core, 'prediction_weight', lambda *a: pytest.fail('expired'))
    numbers, result = core.screen(ctx, regional)
    assert numbers == [] and result['predictor_calls'] == 0
    for options in (dict(max_additions=9), dict(max_seconds=61), dict(max_seconds=float('nan'))):
        with pytest.raises(ValueError):
            core.screen(ctx, regional, **options)
