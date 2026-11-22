from collections import Counter
from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import position
from tools.pipeline_eval.variants.algo08_fit_reuse import repeated_fit_points


def test_reuse_tracks_exact_points_and_ends_before_model_changes(monkeypatch):
    calls = []
    state = [3.]
    def calculate(x):
        calls.append(tuple(x))
        return x + state[0]
    p = SimpleNamespace(calculate=calculate)
    p.residual = lambda x: p.calculate(x)
    def fit(problem):
        x = np.array([1., 2.])
        first = problem.residual(x).copy()
        problem.residual(x.copy())
        np.testing.assert_equal(first, problem.calculate(x))
        problem.residual(np.nextafter(x,np.inf))
        return first
    monkeypatch.setattr(position,"fit",fit)
    counts = Counter()
    with repeated_fit_points(counts):
        np.testing.assert_equal(position.fit(p), [4,5])
        state[0] = 8.
        np.testing.assert_equal(position.fit(p), [9,10])
    assert p.calculate is calculate
    assert counts == dict(fits=2, last_result_hits=2, residual_hits=2, residual_misses=4)
    assert len(calls) == 4
