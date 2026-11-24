"""Recycle one private encoded snapshot without lending it twice."""

from collections import Counter
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from threading import Lock
from weakref import finalize

import numpy as np


MAX_BYTES = 128 * 1024**2
INGRESS_SHA = "c58f76ae56022aca3893b04bfe4732f24185e9b98294c543a31abf752c264fa8"


class SnapshotSlot:
    """Offer one buffer-backed lease, even if its last reference is a view."""

    def __init__(self, maximum=MAX_BYTES, *, reserve=0):
        if not 0 < maximum <= MAX_BYTES or type(reserve) is not int or not 0 <= reserve <= maximum:
            raise ValueError("Expected a bounded private snapshot slot")
        self.maximum = maximum
        self.reserve = reserve
        self.buffer = None
        self.in_use = False
        self.closed = False
        self.lock = Lock()
        self.counts = Counter()

    def close(self):
        with self.lock:
            self.closed = True
            self.buffer = None

    def release(self):
        with self.lock:
            self.in_use = False

    def borrow(self, size):
        with self.lock:
            if self.closed or self.in_use or not 0 < size <= self.maximum:
                self.counts["ordinary"] += 1
                return np.empty(size, dtype=np.uint8)
            if self.buffer is None or self.buffer.size < size:
                capacity = max(size, self.reserve)
                self.buffer = np.empty(capacity, dtype=np.uint8)
                self.counts["allocations"] += 1
                self.counts["peak_bytes"] = max(capacity, self.counts["peak_bytes"])
            else:
                self.counts["reuses"] += 1
            lease = self.buffer[:size]
            # The released memoryview exports the lease itself. Its NumPy
            # frombuffer descendants retain that export, including in the native
            # reader's live pointer scope. The pool keeps only the base array.
            finalize(lease, self.release)
            self.in_use = True
            return lease


def descriptor_port(original, slot):
    """Use the checked ingress implementation with only its allocation changed."""
    if sha256(Path(original.__code__.co_filename).read_bytes()).hexdigest() != INGRESS_SHA:
        raise ValueError("Expected the reviewed original ingress source")
    source = getsource(original)
    ordinary = "np.empty(before.st_size, dtype=np.uint8)"
    if source.count(ordinary) != 1:
        raise ValueError("Expected one original compressed allocation")
    namespace = dict(original.__globals__, _snapshot_slot=slot)
    changed = source.replace(ordinary, "_snapshot_slot.borrow(before.st_size)")
    exec(compile(changed, original.__code__.co_filename, "exec"), namespace)
    return namespace[original.__name__]
