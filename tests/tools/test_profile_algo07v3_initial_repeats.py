from types import SimpleNamespace

import numpy as np
import pytest
from profile_algo07v3_initial_repeats import RepeatProfile, observe

from leo.analysis.localization_v3.position import NormalPosition


class Problem:
    fitted_c = False


def test_repeat_count_executes_all_calls_and_simulates_bounded_lru():
    profile, p, called = RepeatProfile(), Problem(), []

    def calculate(problem, x):
        called.append(float(x[0]))
        return {'array': np.array(x), 'value': 7.}

    for x in (0., 1., 0., 2., 0.):
        profile.calculate(calculate, p, [x], 'fixture')
    row = profile.rows[0]
    assert len(called) == row['calls'] == 5
    assert (row['unique'], row['repeated']) == (3, 2)
    assert row['hits'] == {'1': 0, '2': 2, '8': 2}


def test_signed_zero_distinct_and_model_changes_rejected():
    profile, p = RepeatProfile(), Problem()
    state = SimpleNamespace(value=1.)
    def fn(p, x):
        return dict(x=np.asarray(x), value=state.value)
    profile.calculate(fn, p, [0.], 'fixture')
    profile.calculate(fn, p, [-0.], 'fixture')
    assert profile.rows[0]['unique'] == 2
    state.value = 2.
    with pytest.raises(ValueError, match='Same position changed'):
        profile.calculate(fn, p, [0.], 'fixture')


def test_observer_restores_original_method_on_exception():
    original = NormalPosition.calculate
    with pytest.raises(RuntimeError), observe(RepeatProfile()):
        assert NormalPosition.calculate is not original
        raise RuntimeError('abort')
    assert NormalPosition.calculate is original
