"""Bounded process execution for the two independent initial calibration fits.

Linux fork shares the large read-only scan until either worker writes its own
cache. No global task, worker pool thread or scientific result file is needed.
Children stay in the CLI worker's process group for outer deadline cleanup.
"""

import multiprocessing
import signal
import threading
import traceback
from multiprocessing.connection import wait

from leo.operations.localization_v3_job import JobInterrupted

_INTERRUPTS = {signal.SIGTERM, signal.SIGINT, signal.SIGALRM}


class ParallelFitFailure(JobInterrupted):
    """An incomplete child must not become a scientific rejection/fallback."""


def _invoke(operation, value, receive, send, signal_mask):
    receive.close()
    # The parent owns cancellation. Do not inherit its Python exception handler
    # into a worker that could then block while reporting an interrupt.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_SETMASK, signal_mask)
    try:
        try:
            result = operation(value)
            send.send((True, result))
        except BaseException:
            send.send((False, traceback.format_exc()))
    finally:
        send.close()


def _stop(processes):
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, _INTERRUPTS)
    try:
        started = [p for p in processes if p.pid is not None]
        for process in started:
            if process.is_alive():
                process.terminate()
        for process in started:
            process.join(timeout=0.2)
        for process in started:
            if process.is_alive():
                process.kill()
        for process in started:
            process.join()
        for process in processes:
            process.close()
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def map_initial_arms(operation, arms):
    """Return both completed results in c0/fitted-c order, or abort the stage.

    This adapter is only for a single-threaded owned job with BLAS pinned to one
    thread by its supervisor. Numerical code receives this function as a port.
    The outer job deadline bounds hung native calls; any parent interruption
    closes pipes, terminates/kills and reaps both children before propagating.
    """
    arms = tuple(arms)
    if arms != ("c0", "fitted_c") or not callable(operation):
        raise ValueError("Exactly the ordered c0/fitted_c pair is required")
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise ParallelFitFailure("Forked fitting requires a single-threaded job owner")
    context = multiprocessing.get_context("fork")
    processes, receivers, pending, results = [], [], {}, [None, None]
    try:
        for index, arm in enumerate(arms):
            receive, send = context.Pipe(duplex=False)
            receivers.append(receive)
            # Defer cancellation across process creation/registration so an
            # interrupt cannot leave a forked child outside the cleanup list.
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, _INTERRUPTS)
            try:
                process = context.Process(
                    target=_invoke, args=(operation, arm, receive, send, previous)
                )
                processes.append(process)
                process.start()
            finally:
                send.close()
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            pending[index] = (receive, process)
        while pending:
            ready = wait([item for r, p in pending.values() for item in (r, p.sentinel)])
            for index, (receive, process) in list(pending.items()):
                if receive in ready:
                    try:
                        complete, value = receive.recv()
                    except (EOFError, OSError) as error:
                        raise ParallelFitFailure(
                            "Initial fit ended without a complete result"
                        ) from error
                    if not complete:
                        raise ParallelFitFailure(f"{arms[index]} fit failed:\n{value}")
                    results[index] = value
                    del pending[index]
                elif process.sentinel in ready:
                    raise ParallelFitFailure("Initial fit process exited without a result")
        for process in processes:
            # Successful work has no new local deadline. The owning job/stage
            # timer still interrupts this wait and triggers bounded cleanup.
            process.join()
            if process.exitcode != 0:
                raise ParallelFitFailure("Initial fit did not exit cleanly after its result")
        return results
    finally:
        for receive in receivers:
            receive.close()
        _stop(processes)
