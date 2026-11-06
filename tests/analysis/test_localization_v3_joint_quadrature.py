"""Ordered audit batches keep every real phase-density value and policy receipt."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import joint_recovery as joint
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_grid_batches


def setup(monkeypatch, numerical=False):
    rng = np.random.default_rng(1106)
    y = [rng.normal(size=3), rng.normal(size=2)]
    receiver = rng.normal(size=(5, 2))
    base = np.eye(5) + receiver @ receiver.T
    def evidence(grid, problem, position, context, method):
        t = np.linspace(-1, 1, grid)
        means = [t[:, None] * np.arange(1, n + 1)[None, :] + position[k]
                 for k, n in enumerate((3, 2))]
        modes = [np.ones((grid, n, 2)) * .2 for n in (3, 2)]
        result = joint.joint_density(context, y, means, base, modes,
                                     [np.zeros(grid)] * 2, [np.ones(grid, bool)] * 2)
        return result['negative_twice_log_density']
    monkeypatch.setattr(joint, 'evidence', evidence)
    context = dict(numerical_policy=NumericalPolicy()) if numerical else {}
    offsets = np.array([[0, 0], [.025, 0], [-.025, 0], [0, .025], [0, -.025]])
    return [3, 7, 13], object(), np.array([1.2, -2.5]), context, 'joint', offsets


@pytest.mark.parametrize('numerical', [False, True])
@pytest.mark.parametrize('mapper', [None, map, map_grid_batches])
def test_real_kernel_grid_matches_original_scalar_order(monkeypatch, numerical, mapper):
    families, p, x, context, method, offsets = args = setup(monkeypatch, numerical)
    before = deepcopy(context.get('numerical_policy').receipt) if numerical else None
    expected = np.array([[joint.evidence(f, p, x + offset, context, method)
                          for f in families] for offset in offsets])
    actual = joint._quadrature_scores(*args, mapper)
    assert fingerprint(actual) == fingerprint(expected)
    if numerical:
        assert context['numerical_policy'].receipt == before


def test_every_offset_and_grid_is_kept_in_three_contiguous_batches(monkeypatch):
    args = setup(monkeypatch)
    seen = []
    def mapper(operation, batches):
        seen.extend(batches)
        return list(map(operation, batches))
    joint._quadrature_scores(*args, mapper)
    assert seen == [(0, 1), (2, 3), (4,)]


@pytest.mark.parametrize('case', ['factorized', 'custom_policy', 'custom_factory'])
def test_cheap_or_unknown_routes_remain_serial(monkeypatch, case):
    args = list(setup(monkeypatch))
    if case == 'factorized':
        args[4] = 'factorized'
    elif case == 'custom_policy':
        args[3]['numerical_policy'] = SimpleNamespace(joint_contraction_optimized=True)
    else:
        args[3]['problem_factory'] = object()
    def forbidden(*a):
        raise AssertionError('unsupported route must stay serial')
    expected = joint._quadrature_scores(*args)
    assert fingerprint(joint._quadrature_scores(*args, forbidden)) == fingerprint(expected)


@pytest.mark.parametrize('fault', ['missing', 'reverse', 'extra', 'malformed', 'shape'])
def test_invalid_transport_cannot_become_a_scientific_rejection(monkeypatch, fault):
    args = setup(monkeypatch)
    def mapper(operation, batches):
        result = list(map(operation, batches))
        if fault == 'missing':
            return result[:-1]
        if fault == 'reverse':
            return result[::-1]
        if fault == 'extra':
            return result + result[:1]
        if fault == 'malformed':
            return [None] + result[1:]
        indices, values, receipt = result[0]
        return [(indices, [values[0]], receipt)] + result[1:]
    assert not issubclass(joint.QuadratureExecutionFailure, Exception)
    with pytest.raises(joint.QuadratureExecutionFailure):
        joint._quadrature_scores(*args, mapper)


def test_child_failure_aborts_the_stage(monkeypatch):
    args = setup(monkeypatch)
    def fail(*a):
        raise RuntimeError('quadrature failed')
    monkeypatch.setattr(joint, 'evidence', fail)
    with pytest.raises(ParallelFitFailure, match='quadrature failed'):
        joint._quadrature_scores(*args, map_grid_batches)


def test_child_cannot_silently_change_numerical_receipts(monkeypatch):
    args = setup(monkeypatch, numerical=True)
    context = args[3]
    before = deepcopy(context['numerical_policy'].receipt)
    def mutate(grid, p, x, d, method):
        d['numerical_policy'].receipt['problem_count'] += 1
        return 0.
    monkeypatch.setattr(joint, 'evidence', mutate)
    with pytest.raises(joint.QuadratureExecutionFailure, match='policy'):
        joint._quadrature_scores(*args, map_grid_batches)
    assert context['numerical_policy'].receipt == before
