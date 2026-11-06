import ast
import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_initial_cache import fixed_calculations, functions

from leo.analysis.localization_v3 import initial_search, position
from tests.analysis.test_localization_v3_position import prepared


def test_cache_prototype_retains_frozen_input_and_stays_out_of_runtime():
    import algo07v3_preinitial_cache_position_oracle as old_position
    import algo07v3_preinitial_cache_search_oracle as old_search

    assert hashlib.sha256(Path(old_position.__file__).read_bytes()).hexdigest() == (
        '321fd4cdff05a77f775f985fa539193597c86b02e6728b6968c6d3ab4b71c659')
    assert hashlib.sha256(Path(old_search.__file__).read_bytes()).hexdigest() == (
        'dcd98f3ea29c5be0f76a13271f74b8637b6e04f20200c5a6204f54bee4ec190a')
    _, _, sources = functions()
    # Initial scheduling was subsequently integrated and has its own exact
    # branch-queue tests. The rejected cache probe still targets frozen input.
    for function in (position.refreshed, initial_search.fit_initial_arm,
                     old_search.initial_search):
        assert ast.dump(ast.parse(inspect.getsource(function))) == ast.dump(
            ast.parse(sources[function.__name__]['original']))
    assert not hasattr(position, 'fixed_calculations')
    assert 'fixed_calculations' not in inspect.getsource(initial_search.initial_search)
    for before, after in ((old_position.fit, position.fit),
                          (old_position.NormalPosition, position.NormalPosition)):
        assert ast.dump(ast.parse(inspect.getsource(before))) == ast.dump(
            ast.parse(inspect.getsource(after)))


def test_cached_results_are_independent_and_only_one_position_is_retained():
    calls = []
    def calculate(x):
        calls.append(np.asarray(x).copy())
        return dict(array=np.asarray(x).copy(), nested=[np.ones(2)])

    p = SimpleNamespace(calculate=calculate)
    with fixed_calculations(p):
        value = p.calculate([0.])
        value['nested'][0][0] = 99
        assert p.calculate([0.])['nested'][0][0] == 1
        p.calculate([-0.])
        p.calculate([0.])
        p.calculate(np.array([0.], dtype=np.float32))
    assert len(calls) == 4 and p.calculate is calculate


def test_real_problem_noise_changes_between_scopes_are_not_stale():
    scan, node = prepared()
    p = position.NormalPosition(scan, node, 150., False)
    with fixed_calculations(p):
        before = fingerprint(p.calculate([0., 0.]))
    assert 'calculate' not in vars(p)
    p.point_noise *= 2
    expected = fingerprint(p.calculate([0., 0.]))
    assert expected != before
    with fixed_calculations(p):
        assert fingerprint(p.calculate([0., 0.])) == expected
    assert 'calculate' not in vars(p)


def test_failure_restores_descriptor_and_does_not_retain_a_failed_calculation():
    class Problem:
        calls = 0
        def calculate(self, x):
            self.calls += 1
            raise RuntimeError('failed calculation')

    p = Problem()
    with pytest.raises(RuntimeError), fixed_calculations(p):
        p.calculate([0.])
    assert 'calculate' not in vars(p)
    with pytest.raises(RuntimeError):
        p.calculate([0.])
    assert p.calls == 2


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
def test_refreshed_fit_keeps_exact_history_and_returns_uncached_problem(arm):
    import algo07v3_preinitial_cache_position_oracle as old

    def run(operation):
        scan, node = prepared()
        p, fit, history = operation(scan, 150., node, arm, rounds=2, iterations=2)
        assert 'calculate' not in vars(p)
        x = fit['parameters']
        return fingerprint(dict(fit=fit, history=history, calculated=p.calculate(x),
                                state=p.state(x)))

    _, candidate, _ = functions()
    refreshed = candidate.__globals__['fit_initial_arm'].__globals__['refreshed']
    assert run(old.refreshed) == run(refreshed)
