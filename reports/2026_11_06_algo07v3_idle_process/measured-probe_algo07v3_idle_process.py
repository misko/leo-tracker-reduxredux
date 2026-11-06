"""Research-only initial derivative helper with bounded capacity and owned cleanup.

Linux only. The private queue owner temporarily becomes a child subreaper so
an abruptly killed fit cannot leave an unreaped helper. It must start with no
other children. No runtime module imports this experiment.
"""

import ctypes
import multiprocessing
import os
import signal
import threading
import time
import traceback
from contextlib import suppress
from multiprocessing.connection import wait
from pathlib import Path

from probe_algo07v3_idle_derivatives import IdleDerivatives, main
from profile_algo07v3 import cpu

from leo.analysis.localization_v3 import position
from leo.operations.localization_v3_job import JobInterrupted
from leo.operations.localization_v3_parallel import ParallelFitFailure

INTERRUPTS = {signal.SIGTERM, signal.SIGINT, signal.SIGALRM}


def prctl(option, value):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, value, 0, 0, 0):
        raise OSError(ctypes.get_errno(), 'prctl failed')


def subreaper():
    flag = ctypes.c_int()
    prctl(37, ctypes.byref(flag))  # PR_GET_CHILD_SUBREAPER
    return flag.value


def children():
    return [int(v) for v in Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()]


def helper_main(residual, connection, unused, owner, mask):
    unused.close()
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG before the parent-race check.
        if os.getppid() != owner:
            return
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        connection.send((True, 'ready'))
        while True:
            pair = connection.recv()
            if pair is None:
                return
            connection.send((True, (residual(pair[0]), residual(pair[1]))))
    except (EOFError, BrokenPipeError):
        return
    except BaseException:
        with suppress(OSError, EOFError):
            connection.send((False, traceback.format_exc()))
    finally:
        connection.close()


class Helper:
    def __init__(self, residual):
        self.connection, remote = multiprocessing.get_context('fork').Pipe()
        self.process, self.pending = None, False
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPTS)
        try:
            self.process = multiprocessing.get_context('fork').Process(
                target=helper_main, args=(residual, remote, self.connection, os.getpid(), previous))
            self.process.start()
        except BaseException:
            self.shutdown()
            raise
        finally:
            remote.close()
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        try:
            if self.receive() != 'ready':
                raise ParallelFitFailure('Unexpected helper handshake')
        except BaseException:
            self.shutdown()
            raise

    def receive(self):
        ready = wait([self.connection, self.process.sentinel])
        if self.connection not in ready:
            raise ParallelFitFailure('Derivative helper exited without a result')
        try:
            success, result = self.connection.recv()
        except (OSError, EOFError) as error:
            raise ParallelFitFailure('Derivative helper ended without a result') from error
        if not success:
            raise ParallelFitFailure('Derivative helper failed:\n'+result)
        return result

    def submit(self, pair):
        if self.pending:
            raise ParallelFitFailure('Only one helper request may be outstanding')
        self.pending = True
        self.connection.send(pair)

    def result(self):
        value = self.receive()
        self.pending = False
        return value

    def shutdown(self):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPTS)
        try:
            if self.process is not None and self.process.pid is not None:
                if self.process.is_alive():
                    if self.pending:
                        self.process.kill()
                    else:
                        with suppress(OSError, EOFError):
                            self.connection.send(None)
                    self.process.join(timeout=.05)
                    if self.process.is_alive():
                        self.process.kill()
                self.process.join()
                self.process.close()
            self.process = None
            self.connection.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


class IdleProcessDerivatives(IdleDerivatives):
    def columns(self, residual, x, lo, hi, step):
        owner = getattr(residual, '__self__', None)
        safe = (type(owner) is position.NormalPosition and
                getattr(residual, '__func__', None) is position.NormalPosition.residual and
                not any(callable(v) for v in vars(owner).values()))
        if not self.spare.value or len(x) != 2 or not safe:
            return super().columns(residual, x, lo, hi, step)
        if self.problem is not owner:
            if self.executor is not None:
                self.executor.shutdown()
            self.executor = None
            self.executor = Helper(residual)
            self.problem = owner
            self.counts['cloned_problems'] += 1
        pairs = []
        for k in range(len(x)):
            a, b = x.copy(), x.copy()
            a[k], b[k] = max(lo[k], x[k]-step), min(hi[k], x[k]+step)
            pairs.append((b, a))
        self.counts['borrowed_gradients'] += 1
        self.executor.submit(pairs[1])
        left = (residual(pairs[0][0]), residual(pairs[0][1]))
        values = [left, self.executor.result()]
        return [(v[0]-v[1])/(pair[0][k]-pair[1][k])
                for k,(v,pair) in enumerate(zip(values,pairs,strict=True))]

    def task(self, operation, item):
        original = position.bounded_gauss_newton
        handlers = {s:signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        def cancel(*args):
            raise JobInterrupted('Initial fit with derivative helper cancelled')
        for sig in handlers:
            signal.signal(sig, cancel)
        position.bounded_gauss_newton = self.gradient
        began, before = time.perf_counter(), cpu()
        try:
            value = operation(item)
        finally:
            try:
                if self.executor is not None:
                    self.executor.shutdown()
            finally:
                position.bounded_gauss_newton = original
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
                self.problem = self.executor = None
        after = cpu()
        return value, dict(item=item, seconds=time.perf_counter()-began,
                           cpu_seconds=sum(b-a for a,b in zip(before,after,strict=True)),
                           **self.counts)

    def map(self, operation, items):
        if threading.active_count()!=1 or children():
            raise ParallelFitFailure(
                'Private process-helper queue requires an idle single-thread owner')
        previous = subreaper()
        prctl(36, 1)  # PR_SET_CHILD_SUBREAPER; restored after all owned descendants are reaped.
        try:
            return super().map(operation, items)
        finally:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPTS)
            try:
                # The original executor has already joined all direct fit children.
                # Any remaining adopted children belong to this private helper queue.
                for pid in children():
                    with suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
            finally:
                try:
                    prctl(36, previous)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK, mask)


if __name__ == '__main__':
    main(IdleProcessDerivatives, (Path(__file__),))
