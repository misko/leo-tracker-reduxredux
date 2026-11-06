"""Real process completion, isolation and cancellation for the owned pair port."""

import os
import signal
import threading
import time

import numpy as np
import pytest

from leo.operations.localization_v3_job import StageDeadline, stage_deadline
from leo.operations.localization_v3_parallel import (
    ParallelFitFailure,
    map_annotation_training,
    map_grid_batches,
    map_initial_arms,
    map_initial_branches,
    map_predictive_folds,
)

ARMS = ("c0", "fitted_c")
TRAINING = tuple((seed, arm) for seed in (13, 9, 4) for arm in ARMS)
BRANCHES = tuple((index, arm) for index in range(3) for arm in ARMS)


def test_grid_batches_run_in_separate_reaped_children_and_return_in_order(tmp_path):
    def operation(batch):
        (tmp_path / str(batch[0])).write_text(str(os.getpid()))
        return list(reversed(batch))
    batches = [(0, 1), (2, 3), (4, 5)]
    assert map_grid_batches(operation, batches) == [[1, 0], [3, 2], [5, 4]]
    paths = list(tmp_path.iterdir())
    assert len({p.read_text() for p in paths}) == 3
    assert_reaped(paths)
    with pytest.raises(ValueError, match='At most three'):
        map_grid_batches(operation, batches + [(6,)])


def test_grid_child_failure_aborts_instead_of_becoming_an_empty_batch():
    def operation(batch):
        raise RuntimeError('diagnostic process failed')
    with pytest.raises(ParallelFitFailure, match='diagnostic process failed'):
        map_grid_batches(operation, [(0,), (1,)])


@pytest.mark.parametrize('mapper,tasks', [(map_annotation_training, TRAINING),
                                        (map_initial_branches, BRANCHES)])
def test_training_queue_keeps_three_slots_and_order_without_waiting_for_first_task(
    tmp_path, mapper, tasks
):
    import multiprocessing

    context = multiprocessing.get_context('fork')
    active, maximum = context.Value('i', 0), context.Value('i', 0)

    def operation(item):
        index = tasks.index(item)
        (tmp_path / str(index)).write_text(str(os.getpid()))
        with active.get_lock():
            active.value += 1
            maximum.value = max(maximum.value, active.value)
        try:
            until = time.monotonic() + 2
            # The first task cannot finish until a queued task has started.
            required = ('3',) if index == 0 else ('0', '1', '2')
            while not all((tmp_path / name).exists() for name in required):
                if time.monotonic() >= until:
                    raise RuntimeError('Queue failed to advance independently')
                time.sleep(.001)
            time.sleep(.02)
            return item
        finally:
            with active.get_lock():
                active.value -= 1

    with stage_deadline(4):
        assert mapper(operation, tasks) == list(tasks)
    assert maximum.value == 3 and active.value == 0
    assert_reaped([tmp_path / str(i) for i in range(6)])


@pytest.mark.parametrize('cancel', [False, True])
@pytest.mark.parametrize('mapper,tasks', [(map_annotation_training, TRAINING),
                                        (map_initial_branches, BRANCHES)])
def test_training_queue_reaps_running_tasks_and_does_not_start_pending_after_failure(
    tmp_path, cancel, mapper, tasks
):
    def operation(item):
        index = tasks.index(item)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (tmp_path / str(index)).write_text(str(os.getpid()))
        if index == 1 and not cancel:
            until = time.monotonic() + 2
            while not all((tmp_path / str(i)).exists() for i in range(3)):
                if time.monotonic() >= until:
                    raise RuntimeError('Initial workers did not start')
                time.sleep(.001)
            return item
        if index == 3:
            raise RuntimeError('queued fit failed')
        time.sleep(60)

    with pytest.raises(StageDeadline if cancel else ParallelFitFailure), stage_deadline(.5):
        mapper(operation, tasks)
    paths = list(tmp_path.iterdir())
    assert {p.name for p in paths} == ({'0', '1', '2'} if cancel else {'0', '1', '2', '3'})
    assert_reaped(paths)


@pytest.mark.parametrize('tasks', [TRAINING[:1], TRAINING + TRAINING[:2],
                                  TRAINING[:2] * 2, tuple(reversed(TRAINING[:2])),
                                  ((13, 'c0'), (9, 'fitted_c'))])
def test_training_queue_refuses_incomplete_or_ambiguous_fold_pairs(tasks):
    with pytest.raises(ValueError):
        map_annotation_training(lambda item: item, tasks)


def test_empty_training_queue_has_no_children():
    assert map_annotation_training(lambda item: item, []) == []


@pytest.mark.parametrize('tasks', [BRANCHES[:1], BRANCHES[:2] * 2,
    tuple(reversed(BRANCHES[:2])), ((0, 'c0'), (1, 'fitted_c')),
    ((True, 'c0'), (True, 'fitted_c')), ((0., 'c0'), (0., 'fitted_c')),
    ((1, 'c0'), (1, 'fitted_c')), ([0, 'c0'], [0, 'fitted_c']),
    ((0,), (0, 'fitted_c'))])
def test_initial_queue_requires_contiguous_complete_ordered_branches(tasks):
    with pytest.raises(ValueError):
        map_initial_branches(lambda item: item, tasks)


@pytest.mark.parametrize('branches', [0, 1, 2, 3, 5])
def test_initial_queue_has_no_new_scientific_branch_limit(branches):
    tasks = [(index, arm) for index in range(branches) for arm in ARMS]
    matrix = np.asfortranarray(np.arange(12.).reshape(3, 4))
    actual = map_initial_branches(lambda item: (item, matrix), tasks)
    assert [r[0] for r in actual] == tasks
    assert all(r[1].strides == matrix.strides and r[1].tobytes() == matrix.tobytes()
               for r in actual)
    with pytest.raises(ValueError):
        map_initial_branches(None, tasks)


def assert_reaped(paths):
    for path in paths:
        pid = int(path.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def synchronize(tmp_path, arm):
    (tmp_path / arm).write_text(str(os.getpid()))
    until = time.monotonic() + 2
    while not all((tmp_path / a).exists() for a in ARMS):
        if time.monotonic() >= until:
            raise RuntimeError("Both arms did not start")
        time.sleep(0.001)


def test_concurrent_completion_is_ordered_and_scan_writes_are_private(tmp_path):
    parent_cache = []
    matrix = np.asfortranarray(np.arange(12, dtype=np.float64).reshape(3, 4))

    def operation(arm):
        synchronize(tmp_path, arm)
        parent_cache.append(arm)
        if arm == "c0":
            while not (tmp_path / "fitted-done").exists():
                time.sleep(0.001)
        else:
            (tmp_path / "fitted-done").write_text("done")
        return dict(arm=arm, matrix=matrix.copy(order="F"), cache=parent_cache)

    with stage_deadline(3):
        rows = map_initial_arms(operation, ARMS)
    assert [r["arm"] for r in rows] == list(ARMS)
    assert [r["cache"] for r in rows] == [["c0"], ["fitted_c"]]
    assert parent_cache == []
    for row in rows:
        assert row["matrix"].dtype == matrix.dtype and row["matrix"].flags.f_contiguous
        assert row["matrix"].tobytes() == matrix.tobytes()
    assert_reaped([tmp_path / a for a in ARMS])


@pytest.mark.parametrize("fault", ["exception", "exit", "unserializable"])
def test_failed_arm_aborts_and_reaps_its_signal_ignoring_sibling(tmp_path, fault):
    def operation(arm):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        synchronize(tmp_path, arm)
        if arm == "c0":
            if fault == "exception":
                raise ValueError("bad numerical fit")
            if fault == "exit":
                os._exit(7)
            return lambda: None
        time.sleep(60)

    with stage_deadline(4), pytest.raises(ParallelFitFailure):
        map_initial_arms(operation, ARMS)
    assert_reaped([tmp_path / a for a in ARMS])


def test_stage_timeout_kills_both_signal_ignoring_children(tmp_path):
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())

    def operation(arm):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        synchronize(tmp_path, arm)
        time.sleep(60)

    with pytest.raises(StageDeadline), stage_deadline(0.4):
        map_initial_arms(operation, ARMS)
    assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == old_mask
    assert_reaped([tmp_path / a for a in ARMS])


def test_successful_worker_teardown_is_not_an_extra_scientific_deadline(tmp_path):
    class Result:
        def __init__(self, arm):
            self.arm = arm

        def __reduce__(self):
            return str, (self.arm,)

        def __del__(self):
            time.sleep(0.35)
            (tmp_path / (self.arm + "-exited")).write_text("done")

    def operation(arm):
        synchronize(tmp_path, arm)
        return Result(arm)

    with stage_deadline(3):
        assert map_initial_arms(operation, ARMS) == list(ARMS)
    assert all((tmp_path / (a + "-exited")).exists() for a in ARMS)
    assert_reaped([tmp_path / a for a in ARMS])


def test_failed_second_start_reaps_first_child(monkeypatch):
    from leo.operations import localization_v3_parallel as adapter

    original = adapter.multiprocessing.get_context("fork")
    started = []

    class Context:
        Pipe = staticmethod(original.Pipe)

        @staticmethod
        def Process(**kwargs):
            process = original.Process(**kwargs)
            start = process.start

            def launch():
                if started:
                    raise OSError("second fork failed")
                start()
                started.append(process.pid)

            process.start = launch
            return process

    monkeypatch.setattr(adapter.multiprocessing, "get_context", lambda name: Context())
    with pytest.raises(ParallelFitFailure, match="second fork failed") as failure:
        map_initial_arms(lambda arm: time.sleep(60), ARMS)
    assert isinstance(failure.value.__cause__, OSError)
    assert len(started) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(started[0], 0)


def test_threaded_owner_is_refused_before_fork():
    entered, finish = threading.Event(), threading.Event()

    def wait():
        entered.set()
        finish.wait(3)

    thread = threading.Thread(target=wait)
    thread.start()
    entered.wait(1)
    try:
        with pytest.raises(ParallelFitFailure, match="single-threaded"):
            map_initial_arms(lambda arm: arm, ARMS)
    finally:
        finish.set()
        thread.join()


def test_pipe_allocation_failure_cannot_become_a_scientific_fallback(monkeypatch):
    from leo.operations import localization_v3_parallel as adapter

    class Context:
        @staticmethod
        def Pipe(**kwargs):
            raise OSError("pipe allocation failed")

    monkeypatch.setattr(adapter.multiprocessing, "get_context", lambda name: Context())
    with pytest.raises(ParallelFitFailure, match="pipe allocation failed"):
        try:
            map_predictive_folds(lambda seed: seed, [13, 9, 4])
        except Exception:
            pytest.fail("Process infrastructure failure became a scientific rejection")


@pytest.mark.parametrize("arms", [[], ["c0"], ["fitted_c", "c0"], ["c0", "fitted_c", "extra"]])
def test_only_declared_matched_pair_is_admitted(arms):
    with pytest.raises(ValueError, match="ordered"):
        map_initial_arms(lambda arm: arm, arms)


def test_three_folds_run_concurrently_and_return_original_seed_order(tmp_path):
    seeds = (13, 9, 4)

    def operation(seed):
        (tmp_path / str(seed)).write_text(str(os.getpid()))
        until = time.monotonic() + 2
        while not all((tmp_path / str(v)).exists() for v in seeds):
            if time.monotonic() >= until:
                raise RuntimeError("All folds must start before any completes")
            time.sleep(0.001)
        return dict(seed=seed, values=np.array([seed, seed + 1.0], dtype="<f8"))

    with stage_deadline(3):
        rows = map_predictive_folds(operation, seeds)
    assert [r["seed"] for r in rows] == list(seeds)
    assert len({int((tmp_path / str(s)).read_text()) for s in seeds}) == 3
    assert_reaped([tmp_path / str(s) for s in seeds])


def test_failed_fold_reaps_all_three_workers(tmp_path):
    seeds = (13, 9, 4)

    def operation(seed):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (tmp_path / str(seed)).write_text(str(os.getpid()))
        until = time.monotonic() + 2
        while not all((tmp_path / str(v)).exists() for v in seeds):
            if time.monotonic() >= until:
                raise RuntimeError("All folds did not start")
            time.sleep(0.001)
        if seed == 9:
            raise ValueError("fold failed")
        time.sleep(60)

    with stage_deadline(4), pytest.raises(ParallelFitFailure, match="fold failed"):
        map_predictive_folds(operation, seeds)
    assert_reaped([tmp_path / str(s) for s in seeds])


def test_fold_work_is_bounded_and_empty_or_single_fold_needs_no_process():
    assert map_predictive_folds(lambda seed: os.getpid(), []) == []
    assert map_predictive_folds(lambda seed: os.getpid(), [13]) == [os.getpid()]
    with pytest.raises(ValueError, match="three"):
        map_predictive_folds(lambda seed: seed, range(4))
