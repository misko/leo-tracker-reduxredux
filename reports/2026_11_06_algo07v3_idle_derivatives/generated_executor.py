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
                    process.join()
                    if process.exitcode != 0:
                        raise ParallelFitFailure("Initial child failed during teardown")
                    _spare.value = int(next_item == len(items) and len(pending) == 1)
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
