import importlib.util
from dataclasses import dataclass
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location('portfolio', Path(__file__).with_name('portfolio.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


@dataclass
class Context:
    model: object
    fixed_c: bool = False
    deadline: float = float('inf')


def fixture():
    class Model:
        clock_count = base_nuisance_count = 2
        def evaluate_joint(self, v, n):
            value = float((v[0]-2)**2+n@n)
            return value, np.zeros_like(v), np.zeros_like(n), None
    ctx = Context(Model())
    fixed = dict(vector=np.arange(10, dtype=float), nuisance=np.array([1., 2., 3.]))
    expanded = dict(vector=np.arange(10, dtype=float)+10, nuisance=np.array([4., 5., 6.]))
    return ctx, fixed, expanded


def test_complete_crosses_and_paired_c0_no_truth_input():
    ctx, f, e = fixture()
    rows = core.starts(ctx, f, e)
    assert len(rows) == 5
    np.testing.assert_array_equal(rows[2][1][:7], f['vector'][:7])
    np.testing.assert_array_equal(rows[2][1][7:], e['vector'][7:])
    np.testing.assert_array_equal(rows[2][2], [1, 2, 6])
    np.testing.assert_array_equal(rows[3][2], [4, 5, 3])
    np.testing.assert_array_equal(rows[4][1][:2], [0, 0])
    ctx.fixed_c = True
    for (_, v, n), (_, z, nn) in zip(rows, core.starts(ctx, f, e), strict=True):
        keep = np.arange(len(v)) != 6
        np.testing.assert_array_equal(v[keep], z[keep])
        np.testing.assert_array_equal(n, nn)
        assert z[6] == 0


def test_total_budget_training_selection_and_incumbent_retention():
    ctx, f, e = fixture()
    def auditor(ctx, v, n):
        return dict(feasible=True, accepted=True, training_objective=1.)
    def refit(ctx, v, n, **options):
        for _ in range(options['max_evaluations']):
            ctx.model.evaluate_joint(v, n)
        return dict(vector=v, nuisance=n, diagnostics=dict(evaluations=options['max_evaluations'],
            objective=2., accepted=False))
    result = core.fit(ctx, f, e, e, max_evaluations=26, refitter=refit, auditor=auditor)
    assert result['diagnostics']['evaluations'] == 26
    assert result['diagnostics']['selected_origin'] == 'retained-own-arm-expanded-incumbent'
    assert all(r['initial_seed_objective'] is not None for r in result['diagnostics']['records'])
    np.testing.assert_array_equal(result['vector'], e['vector'])


def test_failed_start_accounted_and_later_starts_continue():
    ctx, f, e = fixture()
    calls = []
    def auditor(ctx, v, n):
        return dict(feasible=True, accepted=False, training_objective=100.)
    def refit(ctx, v, n, **options):
        calls.append(1)
        ctx.model.evaluate_joint(v, n)
        if len(calls) == 1:
            raise TimeoutError('bounded failure')
        return dict(vector=v, nuisance=n,
                    diagnostics=dict(evaluations=1, objective=float(10-len(calls)), accepted=True))
    result = core.fit(ctx, f, e, e, max_evaluations=26, refitter=refit, auditor=auditor)
    assert result['diagnostics']['evaluations'] == 6
    assert result['diagnostics']['selected_origin'] == 'prior-center'
    assert len(result['diagnostics']['records']) == 5
