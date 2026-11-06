import numpy as np
import probe_algo07v3_initial_priority as probe
import pytest

from leo.operations.localization_v3_parallel import ParallelFitFailure


@pytest.mark.parametrize('branches', [0, 1, 2, 3])
def test_fixed_priority_executes_each_task_once_and_restores_order(monkeypatch, branches):
    tasks = tuple((i, arm) for i in range(branches) for arm in ('c0', 'fitted_c'))
    calls = []

    def operation(item):
        calls.append(item)
        return dict(item=item)

    monkeypatch.setattr(probe, 'map_annotation_training', lambda f, items: list(map(f, items)))
    actual = probe.fitted_first(operation, tasks)
    assert calls == [t for t in tasks if t[1] == 'fitted_c'] + [t for t in tasks if t[1] == 'c0']
    assert actual == [dict(item=t) for t in tasks]


def test_real_workers_preserve_values_and_array_layout():
    tasks = tuple((i, arm) for i in range(3) for arm in ('c0', 'fitted_c'))
    array = np.asfortranarray(np.arange(12.).reshape(3, 4))
    result = probe.fitted_first(lambda item: (item, array), tasks)
    assert [r[0] for r in result] == list(tasks)
    assert all(r[1].tobytes() == array.tobytes() and r[1].strides == array.strides for r in result)


def test_failure_cannot_return_partial_ordered_values():
    def operation(item):
        raise RuntimeError('deliberate priority task failure')

    with pytest.raises(ParallelFitFailure, match='deliberate priority task failure'):
        probe.fitted_first(operation, ((0, 'c0'), (0, 'fitted_c')))
