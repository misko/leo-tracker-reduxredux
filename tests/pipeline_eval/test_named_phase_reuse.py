from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reports/ALGO08/v3'))

from named_phase_reuse import CAPACITY, STATIC_PREDICTION, Setup, memo_residual, retained_factory
from leo.analysis.localization_v3 import history_position


def test_fixed_phase_residual_memo_has_original_recent_counters_and_exact_coordinate_keys():
    calls, counters = [], Counter()

    def residual(x):
        calls.append(x.copy())
        return np.array([float(x[0]), float(np.signbit(x[1]))])

    cached = memo_residual(residual, counters)
    for value in range(10):
        cached(np.array([float(value), 0.0]))
    np.testing.assert_array_equal(cached(np.array([0.0, 0.0])), [0.0, 0.0])
    assert cached.cache_info().hits == 1
    assert counters['released_recent_hits'] == 0
    np.testing.assert_array_equal(cached(np.array([0.0, -0.0])), [0.0, 1.0])
    assert counters['released_recent_hits'] == 1
    for value in range(CAPACITY + 10):
        cached(np.array([float(value), 1.0]))
    assert cached.cache_info().currsize == CAPACITY
    next_phase = memo_residual(residual, Counter())
    next_phase(np.array([0.0, 0.0]))
    assert next_phase.cache_info().misses == 1


def test_setup_keeps_fixed_layout_but_refreshes_reference_and_phase_scale():
    calls, counters = [], Counter()

    def build(_scan, _node, _arm, _keep, reference):
        calls.append(reference)
        return SimpleNamespace(phase_sigma=np.array([2.0]), reference=reference)

    setup = Setup(build, counters)
    scan, node, keep = object(), object(), object()
    first = setup.problem(scan, node, 'c0', keep, np.array([0.0]))
    first.phase_sigma *= 4.0
    first.calculate = object()
    later = setup.problem(scan, node, 'c0', keep, np.array([3.0]))
    assert len(calls) == 1
    np.testing.assert_array_equal(later.phase_sigma, [2.0])
    np.testing.assert_array_equal(later.reference, [3.0])
    assert not hasattr(later, 'calculate')

    def linear(p, entries):
        return SimpleNamespace(reference=p.reference, **dict.fromkeys(STATIC_PREDICTION, entries)), 5, 6, 7, 8

    entries = []
    view0, *tail0 = setup.predictive(linear, first, entries)
    view1, *tail1 = setup.predictive(linear, later, entries)
    assert tail0 == tail1 == [5, 6, 7, 8]
    assert view0.flat_labels is view1.flat_labels
    np.testing.assert_array_equal(view1.reference, [3.0])
    with pytest.raises(ValueError, match='calibration arm'):
        setup.problem(scan, node, 'fitted_c', keep, np.zeros(1))
    with pytest.raises(ValueError, match='selected predictive entries'):
        setup.predictive(linear, later, [])


def test_retained_setup_keeps_bound_inputs_and_normalization_exact(monkeypatch):
    records = []

    def bound(y, u, sigma, groups, **kw):
        records.append((y.copy(), u.copy(), sigma.copy(), groups.copy(), kw['powers'].copy()))
        return dict(coefficient=np.arange(u.shape[1], dtype=float) * 0.01,
                    coefficient_prior_precision=np.ones(u.shape[1]), noise_precision=np.ones(2),
                    residual=np.array([1.25]))

    def problem(scan, _node, _arm, _keep, reference):
        return SimpleNamespace(scan=scan, reference=reference, phase_sigma=np.array([3.0]),
            hardware=np.empty((5, 8)), smooth=np.empty((5, 2)), labels=[0], supported=[], members=[1, 2],
            noise_groups=np.array([0, 0, 0, 1, 1]), values=np.arange(5, dtype=float), q=np.ones(5),
            point_noise=np.array([41., 42., 43., 49., 50.]))

    def calculate(p, x, *, geometry_only):
        assert geometry_only
        return dict(features=np.arange(65, dtype=float).reshape(5, 13) * (1. + x[0]) / 200,
                    intercept=np.full(5, x[0] + p.reference[0]))

    original = history_position.make_problem
    monkeypatch.setattr(history_position.JointMarginal, 'calculate', calculate)
    monkeypatch.setattr(history_position, 'problem', problem)
    monkeypatch.setattr(history_position, '_select', lambda x, scale, keep: (x * scale)[keep], raising=False)
    counters = Counter()
    setup = Setup(problem, counters)
    candidate = retained_factory(original, Path(history_position.__file__).read_text(), setup)
    scan, node, keep = SimpleNamespace(bound=bound), {}, np.array([False, True, True, False, True])
    for phase in [0.25, 0.4]:
        args = (scan, node, keep, 'c0', np.array([phase]), np.array([0.8, 0.99]), np.array([0.1]), 1.5, 4.0)
        before, after = [fn(*args).calculate(np.array([.25, .75])) for fn in (original, candidate)]
        assert before.keys() == after.keys()
        for key in before:
            np.testing.assert_array_equal(before[key], after[key], strict=True)
        for a, b in zip(*records[-2:], strict=True):
            np.testing.assert_array_equal(a, b, strict=True)
    assert counters == Counter(base_builds=1, base_reuses=1, retained_builds=1, retained_reuses=1)
