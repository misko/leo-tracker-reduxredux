"""Shared existing desktop-analysis lease, using no-follow local capabilities."""

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from leo.storage.errors import BundleCorruptionError
from leo.storage.pinned import PinnedLocalRoot


@contextmanager
def analysis_worker_lock(root: Path) -> Iterator[bool]:
    """Same lease inode used by fixed analysis; no capture or IQ ownership claim."""
    with ExitStack() as resources:
        parent = PinnedLocalRoot(root)
        resources.callback(parent.close)
        for name in ("control", "persistent-hop-analysis"):
            child = parent.child(name, create=True)
            resources.callback(child.close)
            os.fsync(parent.fileno())
            parent = child
        descriptor = os.open(
            "worker.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o640,
            dir_fd=parent.fileno(),
        )
        resources.callback(os.close, descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size:
            raise BundleCorruptionError("analysis worker lock must be an empty single-link file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
