"""Prevent serial overlap and duplicate input workers for a dataset."""

import fcntl
from contextlib import ExitStack


def acquire_locks(root, dataset):
    if dataset not in ("DS8", "DS9"):
        raise ValueError("parallel input worker requires DS8 or DS9")
    stack = ExitStack()
    try:
        global_lock = stack.enter_context((root / ".worker.lock").open("a"))
        fcntl.flock(global_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        dataset_lock = stack.enter_context((root / f".{dataset}.worker.lock").open("a"))
        fcntl.flock(dataset_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stack.close()
        raise
    return stack
