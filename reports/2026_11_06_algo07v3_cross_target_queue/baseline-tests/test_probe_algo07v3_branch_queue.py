import ast

import probe_algo07v3_branch_queue as probe
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from tests.analysis.test_localization_v3_position import prepared


def test_queue_extraction_preserves_branch_result_and_original_fit_expression():
    _, before, after = probe.transform()
    trees = [ast.parse(v) for v in (before, after)]
    loops = [next(n for n in t.body[0].body if isinstance(n, ast.For)
                  and ast.unparse(n.target) == '(index, (score, node))') for t in trees]
    helper = next(n for n in trees[1].body[0].body if isinstance(n, ast.FunctionDef))
    assert ast.dump(helper.body[-1].value) == ast.dump(loops[0].body[1].value.args[0].body)
    for loop in loops:
        loop.body[1].value = ast.Constant(None)
    assert ast.dump(loops[0]) == ast.dump(loops[1])


@pytest.mark.parametrize('budget', [1, 3])
def test_real_full_search_and_zero_phase_controls_are_exact(budget):
    a, _ = prepared()
    b, _ = prepared()
    expected = probe.initial_search.initial_search(a, 150., branch_budget=budget,
                                                  map_arms=probe.map_initial_arms)
    candidate, _, _ = probe.transform()
    actual = candidate(b, 150., branch_budget=budget, map_arms=probe.map_initial_arms)
    assert fingerprint(actual) == fingerprint(expected)


def test_external_probe_refuses_callbacks_or_larger_worker_scope():
    candidate, _, _ = probe.transform()
    for kwargs in (dict(on_branch=lambda row: None), dict(branch_budget=4)):
        with pytest.raises(ValueError, match='External queue probe'):
            candidate(None, 150., **kwargs)


def test_alternating_trials_require_full_saved_search_equality(monkeypatch):
    monkeypatch.setattr(probe, 'cpu_policy', lambda: {'fixture': 'not hardware evidence'})
    calls = []
    expected = dict(fully_fitted_hypotheses=3, zero_phase_control={'c0': 1})

    def fresh(side):
        calls.append(side)
        return lambda: expected

    functions = {side: lambda side=side: fresh(side) for side in ('baseline', 'candidate')}
    assert len(probe.trials(functions, expected, 3)) == 6
    assert calls == ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    failures = []
    with pytest.raises(ValueError, match='Full initial search changed'):
        probe.trials(functions, dict(expected, zero_phase_control={'c0': 2}), 1,
                     on_failure=lambda *args: failures.append(args))
    assert len(failures) == 1 and failures[0][2:] == ('baseline', 0)
    assert failures[0][0] != failures[0][1]
