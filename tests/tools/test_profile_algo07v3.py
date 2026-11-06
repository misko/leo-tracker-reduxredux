import profile_algo07v3 as profiler
import pytest
from profile_algo07v3 import timed


def test_timed_returns_same_object_and_records_cpu():
    rows, answer = [], object()
    assert timed(lambda x: x, rows, 'example', answer) is answer
    assert len(rows) == 1 and rows[0]['completed']
    assert rows[0]['seconds'] >= 0
    assert rows[0]['self_cpu_seconds'] >= 0
    assert rows[0]['children_cpu_seconds'] >= 0


def test_timed_preserves_cancellation_and_records_incomplete():
    class Cancel(BaseException):
        pass

    def cancel():
        raise Cancel('interrupted')

    rows = []
    with pytest.raises(Cancel, match='interrupted'):
        timed(cancel, rows, 'cancelled')
    assert rows[0]['completed'] is False


def test_repeated_substage_names_retain_parent_identity():
    rows = []
    for stage in ('predictive', 'numerical'):
        assert timed(lambda s=stage: s, rows, 'control-c0', parent_stage=stage) == stage
    assert [r['parent_stage'] for r in rows] == ['predictive', 'numerical']
    assert [r['name'] for r in rows] == ['control-c0', 'control-c0']


def test_forked_workers_replace_inherited_profiler_and_write_independent_profiles(
    monkeypatch, tmp_path
):
    import pstats

    from leo.operations.localization_v3_parallel import map_initial_arms

    def worker(*args):
        assert map_initial_arms(lambda arm: arm, ('c0', 'fitted_c')) == ['c0', 'fitted_c']
        return 0

    monkeypatch.setattr(profiler, 'worker', worker)
    assert profiler.profile_worker(tmp_path) == 0
    profiles = list(tmp_path.glob('profile-*.pstats'))
    assert len(profiles) == 3
    assert all(pstats.Stats(str(p)).total_calls > 0 for p in profiles)


def test_predictive_only_profiles_and_labels_its_children(monkeypatch, tmp_path):
    import json

    from leo.application import localization_v3 as policy
    from leo.operations.localization_v3_parallel import map_initial_arms

    calls = []

    def predictive(*args, **kwargs):
        return map_initial_arms(lambda arm: arm, ('c0', 'fitted_c'))

    def worker(*args):
        calls.append(map_initial_arms(lambda arm: arm, ('c0', 'fitted_c')))
        assert not list(tmp_path.glob('profile-*.json'))
        calls.append(policy.recover_predictive_checkpoint())
        return 0

    monkeypatch.setattr(policy, 'recover_predictive_checkpoint', predictive)
    monkeypatch.setattr(profiler, 'worker', worker)
    assert profiler.profile_worker(tmp_path, 'predictive') == 0
    assert policy.recover_predictive_checkpoint is predictive
    metadata = [json.loads(p.read_text()) for p in tmp_path.glob('profile-*.json')]
    assert sorted(r['item'] for r in metadata) == ['c0', 'fitted_c']
    assert len(list(tmp_path.glob('profile-*.pstats'))) == 3
    assert calls == [['c0', 'fitted_c'], ['c0', 'fitted_c']]


def test_queued_training_profiles_identify_both_fold_and_arm(monkeypatch, tmp_path):
    import json

    from leo.operations.localization_v3_parallel import map_annotation_training

    tasks = tuple((seed, arm) for seed in (13, 9, 4) for arm in ('c0', 'fitted_c'))

    def worker(*args):
        assert map_annotation_training(lambda item: item, tasks) == list(tasks)
        return 0

    monkeypatch.setattr(profiler, 'worker', worker)
    assert profiler.profile_worker(tmp_path) == 0
    metadata = [json.loads(p.read_text()) for p in tmp_path.glob('profile-*.json')]
    assert sorted(tuple(r['item']) for r in metadata) == sorted(tasks)
    assert len(list(tmp_path.glob('profile-*.pstats'))) == 7


def test_profile_item_keeps_opaque_array_tasks_out_of_metadata():
    import numpy as np

    assert profiler.profile_item((1, np.zeros(3))) == "<class 'tuple'>"


def test_top_level_accounting_labels_children_and_preserves_result(monkeypatch, tmp_path):
    import json
    import time

    from leo.application.localization_v3_engine import _Timing
    from leo.operations.localization_v3_parallel import map_initial_arms

    original, expected = _Timing.run, object()

    def worker(*args):
        timer = _Timing(time.monotonic, None)
        def operation():
            assert map_initial_arms(lambda arm: arm, ('c0', 'fitted_c')) == ['c0', 'fitted_c']
            return expected
        assert timer.run('initial', operation) is expected
        return 0

    monkeypatch.setattr(profiler, 'worker', worker)
    assert profiler.profile_worker(tmp_path) == 0
    assert _Timing.run is original
    rows = json.loads((tmp_path / 'stage-resources.json').read_text())
    assert len(rows) == 1 and rows[0]['name'] == 'initial' and rows[0]['completed']
    assert rows[0]['self_cpu_seconds'] >= 0 and rows[0]['children_cpu_seconds'] > 0
    metadata = [json.loads(p.read_text()) for p in tmp_path.glob('profile-*.json')]
    assert all(r['top_stage'] == 'initial' and r['stage'] is None for r in metadata)


def test_top_level_instrumentation_restores_after_failure(monkeypatch, tmp_path):
    import json
    import time

    from leo.application.localization_v3_engine import _Timing

    original = _Timing.run
    def worker(*args):
        def fail():
            raise RuntimeError('stage failed')
        _Timing(time.monotonic, None).run('native_preparation', fail)

    monkeypatch.setattr(profiler, 'worker', worker)
    with pytest.raises(RuntimeError, match='stage failed'):
        profiler.profile_worker(tmp_path)
    assert _Timing.run is original
    assert json.loads((tmp_path / 'stage-resources.json').read_text())[0]['completed'] is False
    assert json.loads((tmp_path / 'worker-resources.json').read_text())[0]['completed'] is False


def test_control_labels_use_named_defaults_not_context_position():
    def shared(arm, entries=(), extras=('target',), d=None):
        return arm
    shared.__qualname__ = 'fit_shared.<locals>.fit_arm'
    assert profiler.fit_metadata(shared)['extra_count'] == 1
    def new(arm, include=False, d=None):
        return arm
    new.__qualname__ = 'fit_new.<locals>.fit_arm'
    assert profiler.fit_metadata(new)['variant'] == 'control'


def test_frequency_samples_record_missing_counters_explicitly(tmp_path):
    path = tmp_path / 'cpu1/cpufreq/scaling_cur_freq'
    path.parent.mkdir(parents=True)
    path.write_text('1234567\n')
    assert profiler.frequencies(tmp_path, [1, 2]) == {'1': 1234567, '2': None}


@pytest.mark.parametrize('only_stage', [None, 'predictive'])
def test_timer_mode_keeps_complete_child_clocks_without_tracing(monkeypatch, tmp_path, only_stage):
    import json

    from leo.application import localization_v3 as policy
    from leo.operations.localization_v3_parallel import map_initial_arms

    def predictive():
        return map_initial_arms(lambda arm: arm, ('c0', 'fitted_c'))
    def worker(*args):
        result = policy.recover_predictive_checkpoint() if only_stage else predictive()
        assert result == ['c0', 'fitted_c']
        return 0
    monkeypatch.setattr(policy, 'recover_predictive_checkpoint', predictive)
    monkeypatch.setattr(profiler, 'worker', worker)
    assert profiler.profile_worker(tmp_path, only_stage, timers_only=True) == 0
    assert not list(tmp_path.glob('*.pstats'))
    rows = [json.loads(path.read_bytes()) for path in tmp_path.glob('profile-*.json')]
    assert len(rows) == 2 and all(r['timers_only'] for r in rows)
    assert all(r['seconds'] >= r['self_cpu_seconds'] >= 0 for r in rows)
    assert all(r['start'] <= r['end'] and r['children_cpu_seconds'] >= 0 for r in rows)
