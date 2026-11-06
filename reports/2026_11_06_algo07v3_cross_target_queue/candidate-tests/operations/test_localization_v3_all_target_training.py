import pytest

from leo.operations import localization_v3_parallel as parallel


def test_global_training_keeps_target_seed_arm_order():
    tasks = [(target, seed, arm) for target in (0, 2, 5) for seed in (11, 22, 33)
             for arm in ('c0', 'fitted_c')]
    assert parallel.map_all_target_training(lambda item: item, tasks) == tasks


@pytest.mark.parametrize('tasks', [
    [(0, 1, 'c0')],
    [(0, 1, 'fitted_c'), (0, 1, 'c0')],
    [(0, 1, 'c0'), (0, 2, 'fitted_c')],
    [(0, 1, 'c0'), (1, 1, 'fitted_c')],
    [(-1, 1, 'c0'), (-1, 1, 'fitted_c')],
    [(True, 1, 'c0'), (True, 1, 'fitted_c')],
    [(0, 1, 'c0'), (0, 1, 'fitted_c')] * 2,
    [(1, 1, 'c0'), (1, 1, 'fitted_c'), (0, 2, 'c0'), (0, 2, 'fitted_c')],
])
def test_malformed_global_training_schedule_rejected(tasks):
    with pytest.raises(ValueError):
        parallel.map_all_target_training(lambda item: item, tasks)


def test_global_training_empty_and_invalid_operation():
    assert parallel.map_all_target_training(lambda item: item, []) == []
    with pytest.raises(ValueError):
        parallel.map_all_target_training(None, [])


def test_global_training_delegates_with_exactly_three_slots(monkeypatch):
    calls = []

    def execute(operation, items, *, workers):
        calls.append(workers)
        return [operation(item) for item in items]

    monkeypatch.setattr(parallel, '_ordered', execute)
    tasks = [(0, 1, arm) for arm in ('c0', 'fitted_c')]
    assert parallel.map_all_target_training(lambda item: item, tasks) == tasks
    assert calls == [3]
