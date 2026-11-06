from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import predictive_annotation as annotation


def configure(monkeypatch):
    calls = []

    def view(context, inventory, track_id, **kwargs):
        if track_id == 'broken':
            raise ValueError('invalid target')
        d = dict(context, target=track_id)
        target = dict(track_index=0)
        return d, target, np.arange(20.), 10, [11, 22, 33], {}

    def plan(d, track, full, n, seeds, schedule, shifted_origin):
        tasks = [] if d['target'] == 'empty' else [(s, a) for s in seeds
                                                for a in ('c0', 'fitted_c')]

        def operation(task):
            calls.append((d['target'], task))
            return d['target'], task
        return tasks, operation

    monkeypatch.setattr(annotation, '_annotation_view', view)
    monkeypatch.setattr(annotation, '_annotation_training', plan)
    context = dict(scan=SimpleNamespace(tracks=[{}]))
    targets = [dict(track_id=t, inactive_fragment=False) for t in ('a', 'empty', 'broken', 'b')]
    return context, targets, calls


def test_batch_preserves_individual_tasks_and_defers_invalid_targets(monkeypatch):
    context, targets, calls = configure(monkeypatch)
    submitted = []

    def mapper(operation, tasks):
        submitted.extend(tasks)
        values = {task: operation(task) for task in reversed(tasks)}
        return [values[task] for task in tasks]

    mappers, errors = annotation.prepare_training_batch(context, {}, targets, mapper)
    assert len(submitted) == len(calls) == 12
    assert list(errors) == [2]
    assert str(errors[2]) == 'invalid target'
    tasks = [(s, a) for s in (11, 22, 33) for a in ('c0', 'fitted_c')]
    assert mappers[0](None, tasks) == [('a', task) for task in tasks]
    assert mappers[3](None, tasks) == [('b', task) for task in tasks]
    assert mappers[1](None, []) == []
    with pytest.raises(ValueError, match='schedule'):
        mappers[0](None, list(reversed(tasks)))


def test_batch_rejects_incomplete_results(monkeypatch):
    context, targets, _ = configure(monkeypatch)
    with pytest.raises(ValueError):
        annotation.prepare_training_batch(context, {}, targets, lambda operation, tasks: [])


def test_batch_does_not_detach_stateful_numerical_replay():
    with pytest.raises(ValueError, match='Stateful'):
        annotation.prepare_training_batch({'numerical_policy': {}}, {}, [], map)
