"""Private inverse workspace preserves the owned likelihood and LAPACK failures."""

import ast
import inspect

import algo07v3_preworkspace_hierarchical_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_lapack_workspace import candidate

from leo.analysis.localization_v3 import hierarchical


def test_owned_body_matches_the_measured_complete_fit_prototype():
    _, _, source = candidate('inverse')
    assert ast.dump(ast.parse(inspect.getsource(hierarchical.hierarchical_bound))) == (
        ast.dump(ast.parse(source)))


@pytest.mark.parametrize('width', [0, 1, 16, 175])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('learned', [False, True])
def test_owned_full_bound_keeps_every_value_and_input_bit(width, layout, learned):
    rng = np.random.default_rng(1106 + width)
    u = rng.normal(size=(80, width))
    u[rng.random(u.shape) < .6] = 0
    u = np.array(u, order=layout)
    y, s, g = rng.normal(size=80)*150, rng.uniform(60, 200, 80), np.arange(80) % 4
    prior = np.arange(width) % 3 - 1 if learned else None
    kwargs = dict(prior_groups=prior, iterations=16, powers=[.3, .8, .9, 1.])
    before = fingerprint((y, u, s, g, kwargs))
    assert fingerprint(hierarchical.hierarchical_bound(y, u, s, g, **kwargs)) == fingerprint(
        oracle.hierarchical_bound(y, u, s, g, **kwargs))
    assert before == fingerprint((y, u, s, g, kwargs))


def test_private_workspace_is_reused_and_result_does_not_alias_it(monkeypatch):
    original, pointers = hierarchical.dgetrs, []
    workspace = []
    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('overwrite_b') == 1:
            assert args[2].flags.f_contiguous and np.shares_memory(args[2], result[0])
            pointers.append(args[2].ctypes.data)
            workspace.append(args[2])
        return result
    monkeypatch.setattr(hierarchical, 'dgetrs', observed)
    result = hierarchical.hierarchical_bound(
        np.arange(30.), np.ones((30, 5)), 1., np.arange(30) % 3, iterations=4)
    assert len(pointers) == 4 and len(set(pointers)) == 1
    for value in result.values():
        if isinstance(value, np.ndarray):
            assert not np.shares_memory(value, workspace[0])


def test_buffered_solve_failure_propagates(monkeypatch):
    original = hierarchical.dgetrs
    def fail(*args, **kwargs):
        return (None, -1) if kwargs.get('overwrite_b') else original(*args, **kwargs)
    monkeypatch.setattr(hierarchical, 'dgetrs', fail)
    with pytest.raises(np.linalg.LinAlgError, match='DGETRS failed: -1'):
        hierarchical.hierarchical_bound(np.ones(4), np.ones((4, 1)), 1., np.zeros(4, int))
