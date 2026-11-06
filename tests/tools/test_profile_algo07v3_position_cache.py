from types import SimpleNamespace

import numpy as np
import pytest
from profile_algo07v3_position_cache import Census, observe

from leo.analysis.localization_v3 import event_position, prediction


def test_shadow_counts_evicted_work_without_reusing_it():
    calls = []

    def calculate(x):
        calls.append(tuple(x))
        return {'call': len(calls)}

    problem = SimpleNamespace(calculate=calculate)
    census = Census()
    assert census.attach(problem, event_position.cached) is problem
    first = problem.calculate((0., 0.))
    assert problem.calculate((0., 0.)) is first
    for n in range(1, 9):
        problem.calculate((float(n), 0.))
    last = problem.calculate((0., 0.))
    assert last is not first and last['call'] == 10
    row, = census.rows
    assert row['calls'] == 11 and row['actual_misses'] == 10
    assert row['shadows']['8']['avoidable_calls'] == 0
    assert row['shadows']['16']['avoidable_calls'] == 1
    assert row['shadows']['16']['misses'] == 9


def test_separate_problem_caches_and_original_signed_zero_behavior():
    census = Census()
    for _ in range(2):
        p = SimpleNamespace(calculate=lambda x: x.copy())
        census.attach(p, event_position.cached)
        negative = p.calculate(np.array([-0., 0.]))
        assert np.signbit(negative[0])
        assert p.calculate(np.array([0., 0.])) is negative
    assert [r['actual_misses'] for r in census.rows] == [1, 1]


def test_failure_is_not_a_shadow_entry():
    def fail(x):
        raise RuntimeError('intentional')

    census = Census()
    p = SimpleNamespace(calculate=fail)
    census.attach(p, event_position.cached)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='intentional'):
            p.calculate((0., 0.))
    assert census.rows[0]['calls'] == census.rows[0]['actual_misses'] == 0


def test_observer_restores_both_aliases_after_failure():
    originals = prediction.cached, event_position.cached
    census = Census()
    with pytest.raises(RuntimeError, match='intentional'), observe(census):
        p = SimpleNamespace(calculate=lambda x: x)
        prediction.cached(p)
        assert p.calculate((1., 2.)).tolist() == [1., 2.]
        raise RuntimeError('intentional')
    assert (prediction.cached, event_position.cached) == originals


@pytest.mark.parametrize('capacities', [(), (16,), (8, 0), (8, -1), (8, 8.5), (8, True)])
def test_invalid_capacities(capacities):
    with pytest.raises(ValueError):
        Census(capacities)
