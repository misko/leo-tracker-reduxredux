"""Bounded process execution for independent calibration fits and grouped folds.

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
    return _ordered(operation, arms)


def map_predictive_folds(operation, seeds):
    """Run at most the three predeclared grouped folds, retaining their order."""
    seeds = tuple(seeds)
    if len(seeds) > 3 or not callable(operation):
        raise ValueError("At most three predeclared predictive folds are supported")
    if len(seeds) < 2:
        return [operation(seed) for seed in seeds]
    return _ordered(operation, seeds)


def _ordered(operation, items):
    try:
        return _execute(operation, items)
    except Exception as error:
        # Process/pipe startup and transport failures are operational failures,
        # just like child crashes. They must bypass scientific fallback gates.
        raise ParallelFitFailure(f"Parallel execution failed: {error}") from error


def _execute(operation, items):
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise ParallelFitFailure("Forked fitting requires a single-threaded job owner")
    context = multiprocessing.get_context("fork")
    processes, receivers, pending, results = [], [], {}, [None] * len(items)
    try:
        for index, item in enumerate(items):
            receive, send = context.Pipe(duplex=False)
            receivers.append(receive)
            # Defer cancellation across process creation/registration so an
            # interrupt cannot leave a forked child outside the cleanup list.
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, _INTERRUPTS)
            try:
                process = context.Process(
                    target=_invoke, args=(operation, item, receive, send, previous)
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
                            "Numerical child ended without a complete result"
                        ) from error
                    if not complete:
                        raise ParallelFitFailure(f"{items[index]} numerical task failed:\n{value}")
                    results[index] = value
                    del pending[index]
                elif process.sentinel in ready:
                    raise ParallelFitFailure("Numerical child process exited without a result")
        for process in processes:
            # Successful work has no new local deadline. The owning job/stage
            # timer still interrupts this wait and triggers bounded cleanup.
            process.join()
            if process.exitcode != 0:
                raise ParallelFitFailure("Numerical child did not exit cleanly after its result")
        return results
    finally:
        for receive in receivers:
            receive.close()
        _stop(processes)
