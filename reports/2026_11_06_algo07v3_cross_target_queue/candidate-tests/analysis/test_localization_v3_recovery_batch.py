import pytest
from test_localization_v3_recovery_controller import execute, setup

from leo.analysis.localization_v3 import recovery_controller as controller


def prepared(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    evidence['selected_targets'].append(dict(track_id='t2', observation_ids=['n2'],
                                             inactive_fragment=False))
    return evidence


def test_batch_training_is_charged_inside_first_annotation_and_keeps_order(monkeypatch):
    evidence = prepared(monkeypatch)
    port, calls = object(), []
    mappers = {i: object() for i in range(3)}

    def prepare(context, inventory, targets, mapper):
        assert mapper is port and targets is evidence['selected_targets']
        calls.append('training')
        return mappers, {}

    def annotate(context, inventory, tid, **kwargs):
        assert kwargs['map_training'] is mappers[int(tid[-1])]
        calls.append(tid)
        return dict(result=dict(folds=[tid]), protocol={})

    def stage(name, operation):
        calls.append(name)
        return execute(name, operation)

    monkeypatch.setattr(controller, 'prepare_training_batch', prepare)
    monkeypatch.setattr(controller, 'annotate', annotate)
    result = controller.recover_tracks({}, evidence, run_stage=stage,
                                      discovery_allowed=lambda: True,
                                      map_all_target_training=port)
    assert calls[:3] == ['target-0-annotation', 'training', 't0']
    assert calls.count('training') == 1
    assert calls.index('target-0-audit') < calls.index('target-1-annotation')
    assert result['selected']['targets'][0]['norad'] == 2


@pytest.mark.parametrize('stateful', [False, True])
def test_batch_disabled_for_stateful_replay_or_unadmitted_work(monkeypatch, stateful):
    evidence = prepared(monkeypatch)

    def forbidden(*args):
        raise AssertionError('Batch must not run')

    monkeypatch.setattr(controller, 'prepare_training_batch', forbidden)
    context = {'numerical_policy': object()} if stateful else {}
    result = controller.recover_tracks(context, evidence, run_stage=execute,
                                      discovery_allowed=lambda: stateful,
                                      map_all_target_training=forbidden)
    assert len(result['attempts']) == 3


def test_invalid_target_is_reported_at_its_original_stage(monkeypatch):
    evidence = prepared(monkeypatch)
    monkeypatch.setattr(controller, 'prepare_training_batch', lambda *a: (
        {1: map, 2: map}, {0: ValueError('invalid prepared target')}))
    failed = []

    def stage(name, operation):
        try:
            return True, operation()
        except ValueError as error:
            failed.append((name, str(error)))
            return False, None

    result = controller.recover_tracks({}, evidence, run_stage=stage,
                                      discovery_allowed=lambda: True,
                                      map_all_target_training=map)
    assert failed == [('target-0-annotation', 'invalid prepared target')]
    assert result['attempts'][0]['status'] == 'annotation_execution_failed'
    assert result['selected']['targets'][0]['norad'] == 3


def test_small_workload_keeps_existing_per_target_queue(monkeypatch):
    evidence = setup(monkeypatch, shared=True)

    def forbidden(*args):
        raise AssertionError('Small workloads retain the existing queue')

    monkeypatch.setattr(controller, 'prepare_training_batch', forbidden)
    result = controller.recover_tracks({}, evidence, run_stage=execute,
                                      discovery_allowed=lambda: True,
                                      map_all_target_training=forbidden)
    assert result['selected']['targets'][0]['norad'] == 2
