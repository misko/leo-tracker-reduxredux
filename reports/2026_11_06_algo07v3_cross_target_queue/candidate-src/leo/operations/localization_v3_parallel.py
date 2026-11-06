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


def map_initial_branches(operation, tasks):
    """Queue independent branch/arm fits on three workers in canonical order.

    The numerical caller owns the branch budget. This port bounds simultaneous
    workers, never the number of scientific hypotheses. Partial results abort.
    """
    tasks = tuple(tasks)
    if not callable(operation) or len(tasks) % 2:
        raise ValueError('Complete ordered initial branch/arm pairs required')
    for index, (left, right) in enumerate(zip(tasks[::2], tasks[1::2], strict=True)):
        for item, arm in ((left, 'c0'), (right, 'fitted_c')):
            if (not isinstance(item, tuple) or len(item) != 2
                    or not isinstance(item[0], int) or isinstance(item[0], bool)
                    or item != (index, arm)):
                raise ValueError('Contiguous ordered initial branch/arm pairs required')
    return _ordered(operation, tasks, workers=3) if tasks else []


def map_annotation_training(operation, tasks):
    """Queue up to three complete fold/arm pairs on at most three children."""
    tasks = tuple(tasks)
    if not callable(operation) or len(tasks) > 6 or len(tasks) % 2:
        raise ValueError("At most three ordered fold/arm pairs are supported")
    seeds = []
    for left, right in zip(tasks[::2], tasks[1::2], strict=True):
        if (not isinstance(left, tuple) or not isinstance(right, tuple)
                or len(left) != 2 or len(right) != 2
                or left[0] != right[0] or (left[1], right[1]) != ('c0', 'fitted_c')):
            raise ValueError("Each fold requires its ordered c0/fitted_c pair")
        seeds.append(left[0])
    if len(set(seeds)) != len(seeds):
        raise ValueError("Training fold seeds must be distinct")
    return _ordered(operation, tasks, workers=3) if tasks else []


def map_grid_batches(operation, batches):
    """Evaluate at most three independent diagnostic batches in declared order."""
    batches = tuple(batches)
    if len(batches) > 3 or not callable(operation):
        raise ValueError("At most three diagnostic grid batches are supported")
    if len(batches) < 2:
        return [operation(batch) for batch in batches]
    return _ordered(operation, batches, workers=3)


def map_all_target_training(operation, tasks):
    """Queue declared target/fold/arm pairs under explicit all-work admission.

    The caller owns the target budget. This port caps simultaneous children at
    three and preserves every pair's output order; it does not cache any fit.
    """
    tasks = tuple(tasks)
    if not callable(operation) or len(tasks) % 2:
        raise ValueError('Complete ordered target/fold/arm pairs required')
    seen, previous = set(), -1
    for left, right in zip(tasks[::2], tasks[1::2], strict=True):
        if (not isinstance(left, tuple) or not isinstance(right, tuple)
                or len(left) != 3 or len(right) != 3
                or left[:2] != right[:2] or (left[2], right[2]) != ('c0', 'fitted_c')
                or not isinstance(left[0], int) or isinstance(left[0], bool)
                or left[0] < previous or left[0] < 0):
            raise ValueError('Ordered target/fold c0/fitted_c pairs required')
        if left[:2] in seen:
            raise ValueError('Target/fold pairs must be unique')
        seen.add(left[:2])
        previous = left[0]
    return _ordered(operation, tasks, workers=3) if tasks else []


def _ordered(operation, items, *, workers=None):
    try:
        return _execute(operation, items, workers=workers)
    except Exception as error:
        # Process/pipe startup and transport failures are operational failures,
        # just like child crashes. They must bypass scientific fallback gates.
        raise ParallelFitFailure(f"Parallel execution failed: {error}") from error


def _execute(operation, items, *, workers=None):
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise ParallelFitFailure("Forked fitting requires a single-threaded job owner")
    context = multiprocessing.get_context("fork")
    processes, receivers, pending, results = [], [], {}, [None] * len(items)

    def launch(index):
        receive, send = context.Pipe(duplex=False)
        receivers.append(receive)
        # Defer cancellation across process creation/registration so an
        # interrupt cannot leave a forked child outside the cleanup list.
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, _INTERRUPTS)
        try:
            process = context.Process(
                target=_invoke, args=(operation, items[index], receive, send, previous)
            )
            processes.append(process)
            process.start()
        finally:
            send.close()
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        pending[index] = (receive, process)

    try:
        next_item = len(items) if workers is None else min(workers, len(items))
        for index in range(next_item):
            launch(index)
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
                    if next_item < len(items):
                        # Reap before reusing a slot: successful teardown must
                        # not transiently exceed the worker limit. The owning
                        # deadline still bounds this wait; add no local cutoff.
                        process.join()
                        if process.exitcode != 0:
                            raise ParallelFitFailure("Training child failed during teardown")
                        launch(next_item)
                        next_item += 1
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
