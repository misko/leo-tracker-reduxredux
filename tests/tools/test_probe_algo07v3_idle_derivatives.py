"""Idle derivative work keeps exact ordering, bounded capacity and cleanup."""

import multiprocessing
import os
import signal
import threading
import time
from contextlib import suppress

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_idle_derivatives import IdleDerivatives

from leo.analysis.localization_v3 import position
from leo.operations.localization_v3_job import JobInterrupted
from leo.operations.localization_v3_parallel import ParallelFitFailure

TASKS = [(i, arm) for i in range(3) for arm in ('c0', 'fitted_c')]


def problem():
    return object.__new__(position.NormalPosition)


def test_complete_fit_exact_with_idle_helper_and_three_unit_cap(monkeypatch):
    context = multiprocessing.get_context('fork')
    lock, active, maximum = context.Lock(), context.Value('i', 0), context.Value('i', 0)
    def update(delta):
        with lock:
            active.value += delta
            maximum.value = max(maximum.value, active.value)
    def residual(self, x):
        helper = threading.current_thread() is not threading.main_thread()
        if helper:
            update(1)
        try:
            time.sleep(.003)
            return np.asarray(x)-[.7, -.4]
        finally:
            if helper:
                update(-1)
    monkeypatch.setattr(position.NormalPosition, 'residual', residual)
    old = position.bounded_gauss_newton
    expected = old(problem().residual, [0., 0.], [-2., -2.], [2., 2.])
    def operation(item):
        update(1)
        try:
            if item != TASKS[-1]:
                time.sleep(.01)
                return item
            time.sleep(.12)
            return position.bounded_gauss_newton(problem().residual,
                                                 [0., 0.], [-2., -2.], [2., 2.])
        finally:
            update(-1)
    pool = IdleDerivatives()
    actual = pool.map(operation, TASKS)
    assert actual[:-1] == TASKS[:-1]
    assert fingerprint(actual[-1]) == fingerprint(expected)
    assert pool.records[-1]['borrowed_gradients'] > 0
    assert pool.records[-1]['cloned_problems'] == 1
    assert all(r['borrowed_gradients'] == 0 for r in pool.records[:-1])
    assert maximum.value <= 3 and active.value == 0
    assert position.bounded_gauss_newton is old
    assert not multiprocessing.active_children()


def test_helper_failure_aborts_and_reaps_outer_workers(monkeypatch):
    def residual(self, x):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('helper failure')
        return np.asarray(x)-1
    monkeypatch.setattr(position.NormalPosition, 'residual', residual)
    def operation(item):
        if item != TASKS[-1]:
            return item
        time.sleep(.1)
        return position.bounded_gauss_newton(problem().residual,
                                             [0., 0.], [-2., -2.], [2., 2.])
    with pytest.raises(ParallelFitFailure, match='helper failure'):
        IdleDerivatives().map(operation, TASKS)
    assert not multiprocessing.active_children()


def test_custom_residual_uses_serial_path_even_with_spare_capacity():
    pool = IdleDerivatives()
    pool.spare.value = 1
    seen = []
    def residual(x):
        seen.append(x.copy())
        return x*x
    values = pool.columns(residual, np.zeros(2), np.full(2, -1), np.ones(2), .01)
    assert len(seen) == 4 and len(values) == 2
    assert pool.executor is None and pool.counts['borrowed_gradients'] == 0


def test_parent_cancellation_removes_worker_with_active_helper(monkeypatch):
    context = multiprocessing.get_context('fork')
    helper_started, worker_pid = context.Event(), context.Value('i', 0)
    def residual(self, x):
        if threading.current_thread() is not threading.main_thread():
            helper_started.set()
            time.sleep(30)
        return np.asarray(x)-1
    monkeypatch.setattr(position.NormalPosition, 'residual', residual)
    def operation(item):
        if item != TASKS[-1]:
            return item
        worker_pid.value = os.getpid()
        time.sleep(.1)
        return position.bounded_gauss_newton(problem().residual,
                                             [0., 0.], [-2., -2.], [2., 2.])
    def driver():
        def stop(*args):
            raise JobInterrupted('cancel')
        signal.signal(signal.SIGTERM, stop)
        with suppress(JobInterrupted):
            IdleDerivatives().map(operation, TASKS)
    child = context.Process(target=driver)
    child.start()
    try:
        assert helper_started.wait(5)
        child.terminate()
        child.join(5)
        assert child.exitcode == 0
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid.value, 0)
    finally:
        if child.is_alive():
            child.kill()
        child.join()
        child.close()


@pytest.mark.parametrize('items', [[(1, 'c0'), (1, 'fitted_c')], [(0, 'c0')]])
def test_original_initial_port_validation_is_retained(items):
    with pytest.raises(ValueError):
        IdleDerivatives().map(lambda x: x, items)
