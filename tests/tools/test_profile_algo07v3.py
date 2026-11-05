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
