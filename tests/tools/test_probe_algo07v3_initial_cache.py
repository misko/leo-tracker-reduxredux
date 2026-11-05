import ast
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_initial_cache import fixed_calculations, functions

from tests.analysis.test_localization_v3_position import prepared


def test_scopes_only_wrap_original_statements():
    _, _, sources = functions()
    class Unwrap(ast.NodeTransformer):
        def visit_With(self, node):
            assert ast.unparse(node.items[0].context_expr).startswith('fixed_calculations(')
            return node.body

    for source in sources.values():
        assert ast.dump(ast.parse(source['original'])) == ast.dump(
            Unwrap().visit(ast.parse(source['candidate'])))


@pytest.mark.parametrize('budget', [1, 3])
def test_complete_initial_search_both_arms_and_zero_controls_exact(budget):
    baseline, candidate, _ = functions()
    a, _ = prepared()
    b, _ = prepared()
    before = baseline(a, 150., branch_budget=budget)
    after = candidate(b, 150., branch_budget=budget)
    assert fingerprint(before) == fingerprint(after)


def test_one_entry_copies_results_and_position_bytes_distinguish_signed_zero():
    calls = []
    def original(x):
        calls.append(np.asarray(x).copy())
        return dict(value=np.asarray(x).copy(), nested=[dict(a=np.ones(2))])

    p = SimpleNamespace(calculate=original)
    with fixed_calculations(p):
        first = p.calculate([0.])
        first['value'][0] = 999
        first['nested'][0]['a'][0] = 999
        second = p.calculate([0.])
        assert second['value'][0] == 0 and second['nested'][0]['a'][0] == 1
        second['nested'][0]['a'][0] = 888
        assert p.calculate([0.])['nested'][0]['a'][0] == 1
        p.calculate([-0.])
        p.calculate([0.])
        p.calculate(np.array([0.], dtype=np.float32))
    assert len(calls) == 4 and p.calculate is original


def test_model_changes_between_scopes_are_observed_and_failure_restores_descriptor():
    class Problem:
        value = 1
        def calculate(self, x):
            return [self.value]

    p = Problem()
    with fixed_calculations(p):
        assert p.calculate([0.]) == [1]
    assert 'calculate' not in vars(p)
    p.value = 2
    with pytest.raises(RuntimeError), fixed_calculations(p):
        assert p.calculate([0.]) == [2]
        raise RuntimeError('abort')
    assert 'calculate' not in vars(p) and p.calculate([0.]) == [2]
