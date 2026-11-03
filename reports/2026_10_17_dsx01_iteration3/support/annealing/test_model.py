import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'reports/2026_10_16_dsx01_iteration2'))
import test_bank_expansion as fixture  # noqa: E402

spec = importlib.util.spec_from_file_location('annealing_model',
                                             Path(__file__).with_name('model.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
case = fixture.case


def test_125_exact_closure_and_500_full_gradient(case):
    ctx, _ = case
    original = ctx.model.evaluate_joint(ctx.vector, ctx.nuisance)
    same = core.WidthModel(ctx.model, 125).evaluate_joint(ctx.vector, ctx.nuisance)
    for a, b in zip(original[:3], same[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(original[3].responsibilities, same[3].responsibilities)
    model = core.WidthModel(ctx.model, 500)
    base = np.r_[ctx.vector, ctx.nuisance]
    result = model.evaluate_joint(ctx.vector, ctx.nuisance)
    grad = np.r_[result[1], result[2]]
    size = len(ctx.vector)
    for i in range(len(base)):
        h = 1e-4 if i in (2, 4, 6) or i >= size else 1e-5
        plus, minus = base.copy(), base.copy()
        plus[i] += h
        minus[i] -= h
        finite = (model.evaluate_joint(plus[:size], plus[size:])[0]
                  -model.evaluate_joint(minus[:size], minus[size:])[0])/(2*h)
        np.testing.assert_allclose(finite, grad[i], atol=2e-4, rtol=2e-5)
    assert ctx.model.score.sigma_hz == model.score.sigma_hz == 125
    assert np.all(model.hyperparameters(ctx.nuisance[model.base_nuisance_count:])[0] == 500)


def test_mask_invariance_for_each_declared_width(case):
    from dataclasses import replace
    ctx, _ = case
    changed_raw = object.__new__(type(ctx.model.original))
    changed_raw.__dict__.update(ctx.model.original.__dict__)
    changed_raw.observations = replace(ctx.observations, measured_hz=
        ctx.observations.measured_hz+np.where(ctx.train_mask, 0., 12345678.))
    source = fixture.SharedScanObjective(changed_raw, fixture.core.fixed_shift(ctx.model),
                                         mask=ctx.train_mask)
    for width in (125, 250, 500, 1000):
        a = core.WidthModel(ctx.model, width).evaluate_joint(ctx.vector, ctx.nuisance)
        b = core.WidthModel(source, width).evaluate_joint(ctx.vector, ctx.nuisance)
        for x, y in zip(a[:3], b[:3], strict=True):
            np.testing.assert_array_equal(x, y)


def test_total_schedule_budget_and_only_125_scores_select(case):
    ctx, _ = case
    calls = []
    def audit(ctx, v, n):
        return dict(feasible=True, accepted=True, training_objective=1.)
    def refit(ctx, v, n, **options):
        width = ctx.model.fixed_width_hz
        for _ in range(options['max_evaluations']):
            ctx.model.evaluate_joint(v, n)
        calls.append((width, options['max_evaluations']))
        return dict(vector=v, nuisance=n, diagnostics=dict(
            objective=-1000. if width != 125 else 2., accepted=True,
            evaluations=options['max_evaluations']))
    seed = dict(vector=ctx.vector, nuisance=ctx.nuisance)
    result = core.fit(ctx, seed, seed, refitter=refit, auditor=audit)
    assert result['diagnostics']['evaluations'] == 1000
    assert calls == [(1000, 149), (500, 150), (250, 150), (125, 550)]
    assert result['diagnostics']['selected_origin'] == 'raw-own-arm125-incumbent'
    with pytest.raises(ValueError):
        core.WidthModel(ctx.model, 2000)
