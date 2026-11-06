"""Exact arithmetic, scoped process ownership, hard failures and parent-death cleanup."""

import multiprocessing
import os
import signal
import time

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_idle_process import IdleProcessDerivatives, children, subreaper

from leo.analysis.localization_v3 import position
from leo.operations.localization_v3_job import JobInterrupted
from leo.operations.localization_v3_parallel import ParallelFitFailure

TASKS = [(i, arm) for i in range(3) for arm in ('c0', 'fitted_c')]


def problem():
    p = object.__new__(position.NormalPosition)
    p.worker_pid = os.getpid()
    return p


def test_exact_complete_optimizer_and_capacity(monkeypatch):
    context = multiprocessing.get_context('fork')
    lock, active, maximum = context.Lock(), context.Value('i',0), context.Value('i',0)
    def change(delta):
        with lock:
            active.value += delta
            maximum.value = max(maximum.value,active.value)
    def residual(self,x):
        helper = os.getpid()!=self.worker_pid
        if helper:
            change(1)
        try:
            time.sleep(.002)
            return np.asarray(x)-[.7,-.4]
        finally:
            if helper:
                change(-1)
    monkeypatch.setattr(position.NormalPosition,'residual',residual)
    original = position.bounded_gauss_newton
    expected = original(problem().residual,[0.,0.],[-2.,-2.],[2.,2.])
    def operation(item):
        change(1)
        try:
            if item!=TASKS[-1]:
                time.sleep(.01)
                return item
            time.sleep(.1)
            return position.bounded_gauss_newton(problem().residual,[0.,0.],[-2.,-2.],[2.,2.])
        finally:
            change(-1)
    prior = subreaper()
    queue = IdleProcessDerivatives()
    actual = queue.map(operation,TASKS)
    assert actual[:-1]==TASKS[:-1]
    assert fingerprint(actual[-1])==fingerprint(expected)
    assert queue.records[-1]['borrowed_gradients']>0
    assert queue.records[-1]['cloned_problems']==1
    assert all(r['borrowed_gradients']==0 for r in queue.records[:-1])
    assert active.value==0 and maximum.value<=3
    assert not children() and subreaper()==prior
    assert position.bounded_gauss_newton is original


@pytest.mark.parametrize('failure',['exception','helper_exit','owner_kill'])
def test_process_failure_is_fatal_and_all_descendants_reaped(monkeypatch,failure):
    context = multiprocessing.get_context('fork')
    helper_pid = context.Value('i',0)
    def residual(self,x):
        if os.getpid()!=self.worker_pid:
            helper_pid.value = os.getpid()
            if failure=='exception':
                raise ValueError('numerical helper failure')
            if failure=='helper_exit':
                os._exit(7)
            os.kill(self.worker_pid,signal.SIGKILL)
            time.sleep(30)
        return np.asarray(x)-1
    monkeypatch.setattr(position.NormalPosition,'residual',residual)
    def operation(item):
        if item!=TASKS[-1]:
            return item
        time.sleep(.1)
        return position.bounded_gauss_newton(problem().residual,[0.,0.],[-2.,-2.],[2.,2.])
    prior = subreaper()
    with pytest.raises(ParallelFitFailure):
        IdleProcessDerivatives().map(operation,TASKS)
    assert helper_pid.value>0
    with pytest.raises(ProcessLookupError):
        os.kill(helper_pid.value,0)
    assert not children() and subreaper()==prior


def test_parent_cancellation_during_helper_work(monkeypatch):
    context = multiprocessing.get_context('fork')
    ready, helper_pid, worker_pid = context.Event(), context.Value('i',0), context.Value('i',0)
    def residual(self,x):
        if os.getpid()!=self.worker_pid:
            helper_pid.value = os.getpid()
            ready.set()
            time.sleep(30)
        return np.asarray(x)-1
    monkeypatch.setattr(position.NormalPosition,'residual',residual)
    def operation(item):
        if item!=TASKS[-1]:
            return item
        worker_pid.value = os.getpid()
        time.sleep(.1)
        return position.bounded_gauss_newton(problem().residual,[0.,0.],[-2.,-2.],[2.,2.])
    def driver():
        def cancel(*args):
            raise JobInterrupted('cancel')
        signal.signal(signal.SIGTERM,cancel)
        try:
            IdleProcessDerivatives().map(operation,TASKS)
        except JobInterrupted:
            assert not children()
    child = context.Process(target=driver)
    child.start()
    try:
        assert ready.wait(5)
        child.terminate()
        child.join(5)
        assert child.exitcode==0
        for pid in (helper_pid.value,worker_pid.value):
            with pytest.raises(ProcessLookupError):
                os.kill(pid,0)
    finally:
        if child.is_alive():
            child.kill()
        child.join()
        child.close()


def test_foreign_child_is_not_adopted_or_killed():
    child = multiprocessing.get_context('fork').Process(target=time.sleep,args=(30,))
    child.start()
    prior = subreaper()
    try:
        with pytest.raises(ParallelFitFailure,match='idle single-thread owner'):
            IdleProcessDerivatives().map(lambda x:x,TASKS)
        assert child.is_alive() and subreaper()==prior
    finally:
        child.terminate()
        child.join()
        child.close()


def test_custom_residual_remains_serial():
    queue = IdleProcessDerivatives()
    queue.spare.value = 1
    calls = []
    def residual(x):
        calls.append(x.copy())
        return x*x
    queue.columns(residual,np.zeros(2),-np.ones(2),np.ones(2),.01)
    assert len(calls)==4 and queue.executor is None and not children()


def test_capacity_activation_between_checks_cannot_start_thread_helper(monkeypatch):
    """An unavailable-capacity decision stays serial even if the queue drains."""
    class ActivatingFlag:
        reads = 0

        @property
        def value(self):
            self.reads += 1
            return int(self.reads > 1)

    def residual(self, x):
        return np.asarray(x) ** 2

    monkeypatch.setattr(position.NormalPosition, 'residual', residual)
    queue = IdleProcessDerivatives()
    queue.spare = ActivatingFlag()
    try:
        actual = queue.columns(problem().residual, np.asarray([.2, -.4]),
                               -np.ones(2), np.ones(2), .01)
        assert queue.executor is None
        assert queue.spare.reads == 1
        assert queue.counts['serial_gradients'] == 1
        assert queue.counts['borrowed_gradients'] == 0
        np.testing.assert_allclose(actual, [[.4, 0.], [0., -.8]])
    finally:
        if queue.executor is not None:
            queue.executor.shutdown()


def test_new_phase_replaces_helper_and_preserves_both_results(monkeypatch):
    context = multiprocessing.get_context('fork')
    helper_pids = context.Array('i',2)
    def residual(self,x):
        if os.getpid()!=self.worker_pid:
            helper_pids[self.phase] = os.getpid()
        return np.asarray(x)-[.2+self.phase*.1,-.4]
    monkeypatch.setattr(position.NormalPosition,'residual',residual)
    def fits():
        values = []
        for phase in range(2):
            p = problem()
            p.phase = phase
            values.append(position.bounded_gauss_newton(p.residual,[0.,0.],[-2.,-2.],[2.,2.]))
        return values
    expected = fits()
    def operation(item):
        if item!=TASKS[-1]:
            return item
        time.sleep(.1)
        return fits()
    queue = IdleProcessDerivatives()
    actual = queue.map(operation,TASKS)
    assert fingerprint(actual[-1])==fingerprint(expected)
    assert queue.records[-1]['cloned_problems']==2
    assert helper_pids[0]>0 and helper_pids[1]>0 and helper_pids[0]!=helper_pids[1]
    for pid in helper_pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid,0)
    assert not children()
