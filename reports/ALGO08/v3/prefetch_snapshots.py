"""Lease two alternating private destinations to ordinary compressed lookahead."""

from contextlib import contextmanager
from unittest.mock import patch

from .legacy_snapshot_reuse import MAX_BYTES, SnapshotSlot, descriptor_port


class AlternatingSnapshots:
    """One producer, with lifetimes tied to each consumer's buffer export."""

    def __init__(self, maximum=MAX_BYTES):
        self._slots = SnapshotSlot(maximum), SnapshotSlot(maximum)
        self._next = 0

    def borrow(self, size):
        slot = self._slots[self._next]
        self._next = 1 - self._next
        return slot.borrow(size)

    def close(self):
        for slot in self._slots:
            slot.close()

    def counts(self):
        return [dict(slot.counts) for slot in self._slots]


@contextmanager
def binding(frontier, audit):
    """Replace the allocation only inside the already verified producer."""
    ordinary = frontier.load_prefetch

    def load():
        fetch = ordinary()
        namespace = fetch.__wrapped__.__globals__
        pool = AlternatingSnapshots()
        read = descriptor_port(namespace["read_regular_descriptor"], pool)

        @contextmanager
        def scoped():
            try:
                with patch.dict(namespace, read_regular_descriptor=read), fetch() as stats:
                    yield stats
            finally:
                # The original worker scope has already joined its sole
                # producer. Outstanding consumers still own their leases.
                pool.close()
                audit.append(pool.counts())

        return scoped

    with patch.object(frontier, "load_prefetch", load):
        yield
