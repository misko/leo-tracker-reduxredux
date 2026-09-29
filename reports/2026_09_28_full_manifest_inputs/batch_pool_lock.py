"""Bound input concurrency and exclude overlapping batches or older launchers."""

import fcntl
from contextlib import ExitStack


def acquire_locks(root, dataset, batch):
    if dataset not in ("DS8", "DS9") or type(batch) is not int or batch < 0:
        raise ValueError("requires DS8/DS9 and a nonnegative integer batch")
    stack = ExitStack()
    try:
        for name in (".worker.lock", ".DS8.worker.lock", ".DS9.worker.lock"):
            handle = stack.enter_context((root / name).open("a"))
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        handle = stack.enter_context((root / f".{dataset}-batch{batch}.worker.lock").open("a"))
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for slot in range(4):
            handle = (root / f".pool-slot{slot}.worker.lock").open("a")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
            except BaseException:
                handle.close()
                raise
            else:
                stack.enter_context(handle)
                break
        else:
            raise BlockingIOError("all four input worker slots are occupied")
    except BaseException:
        stack.close()
        raise
    return stack
