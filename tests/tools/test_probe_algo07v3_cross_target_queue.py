import numpy as np
import pytest
from probe_algo07v3_cross_target_queue import TrainingPlan, replay, run_annotations


def evidence():
    return dict(inventory={}, publication_support={}, selected_targets=[
        dict(track_id=i, inactive_fragment=False) for i in range(3)])


def annotation(context, inventory, track, *, map_training, map_folds, **kwargs):
    if track == 1:
        return dict(target=track, insufficient_support=True)
    tasks = [(seed, arm) for seed in (1, 2, 3) for arm in ('c0', 'fitted_c')]

    def train(item):
        return dict(value=(track, item), keep=np.array([True]),
                    metadata=dict(history=[dict(phase_change_s=.1)]))
    rows = map_training(train, tasks)
    return dict(target=track, values=list(map_folds(
        lambda i: (rows[2*i]['value'], rows[2*i + 1]['value']), range(3))))


def test_combining_preserves_target_and_fold_order_with_empty_target():
    results, blocks = [], []
    for combined in (False, True):
        results.append(run_annotations({}, evidence(), combined=combined, blocks=blocks,
                                       annotate_fn=annotation, training_mapper=map,
                                       global_mapper=map, fold_mapper=map))
    assert results[0] == results[1]
    assert results[1][1] == dict(target=1, insufficient_support=True)
    assert len([b for b in blocks if b['kind'] == 'global_task_labels'][0]['entries']) == 12


def test_stateful_context_fails_before_preparation():
    with pytest.raises(ValueError, match='Stateful'):
        run_annotations({'numerical_policy': {}}, evidence(), combined=True, blocks=[])


def test_missing_and_mismatched_recipes_fail():
    plan = TrainingPlan(None, [(1, 'c0')])
    with pytest.raises(ValueError, match='Incomplete'):
        replay(plan, [])
    with pytest.raises(ValueError, match='schedule changed'):
        replay(plan, [object()])(None, [(2, 'c0')])


def test_unrelated_preparation_error_propagates():
    def broken(*args, **kwargs):
        raise RuntimeError('broken target')
    with pytest.raises(RuntimeError, match='broken target'):
        run_annotations({}, evidence(), combined=True, blocks=[], annotate_fn=broken)


def test_real_three_worker_adapter_retains_all_fold_arm_records():
    expected = run_annotations({}, evidence(), combined=False, blocks=[],
                               annotate_fn=annotation, training_mapper=map, fold_mapper=map)
    blocks = []
    actual = run_annotations({}, evidence(), combined=True, blocks=blocks,
                             annotate_fn=annotation, fold_mapper=map)
    assert actual == expected
    training = next(b for b in blocks if b['kind'] == 'training')
    assert len(training['tasks']) == 12
    events = sorted([(r['start'], 1) for r in training['tasks']]
                    + [(r['end'], -1) for r in training['tasks']])
    active = 0
    for _, change in events:
        active += change
        assert 0 <= active <= 3
    assert active == 0
