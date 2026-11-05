"""Real process completion, isolation and cancellation for the owned pair port."""

import os
import signal
import threading
import time

import numpy as np
import pytest

from leo.operations.localization_v3_job import StageDeadline, stage_deadline
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms

ARMS = ("c0", "fitted_c")


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
            (tmp_path / (self.arm + '-exited')).write_text('done')

    def operation(arm):
        synchronize(tmp_path, arm)
        return Result(arm)

    with stage_deadline(3):
        assert map_initial_arms(operation, ARMS) == list(ARMS)
    assert all((tmp_path / (a + '-exited')).exists() for a in ARMS)
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
    with pytest.raises(OSError, match="second fork failed"):
        map_initial_arms(lambda arm: time.sleep(60), ARMS)
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


@pytest.mark.parametrize("arms", [[], ["c0"], ["fitted_c", "c0"], ["c0", "fitted_c", "extra"]])
def test_only_declared_matched_pair_is_admitted(arms):
    with pytest.raises(ValueError, match="ordered"):
        map_initial_arms(lambda arm: arm, arms)
