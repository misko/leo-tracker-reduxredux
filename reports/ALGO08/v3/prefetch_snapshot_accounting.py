"""Account for pinned lookahead reads and test optional private snapshot leases."""

from contextlib import contextmanager, ExitStack
from dataclasses import asdict
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from resource import RUSAGE_THREAD
from time import thread_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from .legacy_snapshot_reuse import INGRESS_SHA, MAX_BYTES, SnapshotSlot
from .owned_window_recycle_trial import clock, delta


class AlternatingSnapshots:
    """One serial producer, up to two independently retained array exports."""

    def __init__(self, maximum=MAX_BYTES):
        self.slots = SnapshotSlot(maximum), SnapshotSlot(maximum)
        self.next_slot = 0

    def borrow(self, size, *, dtype):
        slot = self.slots[self.next_slot]
        self.next_slot = 1 - self.next_slot
        # A live slot falls back to a new private array. Its export controls
        # lifetime even when the original future no longer holds a reference.
        return slot.borrow(size)

    def close(self):
        for slot in self.slots:
            slot.close()


class PrefetchAccounting:
    def __init__(self, reuse):
        self.reuse = reuse
        self.members = []
        self.active = None
        self.stats = None
        self.pool = AlternatingSnapshots() if reuse else None

    def measure(self, label, function):
        def invoke(*args, **kwargs):
            if self.active is None:
                raise RuntimeError("Expected one serial lookahead producer")
            start, cpu = clock(RUSAGE_THREAD), thread_time_ns()
            answer = None
            try:
                answer = function(*args, **kwargs)
                return answer
            finally:
                spent = thread_time_ns() - cpu
                self.active.append(dict(operation=label, cpu_ns=spent,
                                        bytes=answer if label == "readv" else None,
                                        **delta(start, clock(RUSAGE_THREAD))))
        return invoke

    def descriptor(self, original):
        source = Path(original.__code__.co_filename)
        if sha256(source.read_bytes()).hexdigest() != INGRESS_SHA:
            raise ValueError("Expected the reviewed original descriptor source")
        namespace = dict(original.__globals__)
        os, np = (namespace[key] for key in ("os", "np"))
        namespace["np"] = SimpleNamespace(uint8=np.uint8, empty=self.measure(
            "allocate", self.pool.borrow if self.pool is not None else np.empty))
        namespace["os"] = SimpleNamespace(fstat=self.measure("descriptor_fstat", os.fstat),
                                          read=self.measure("eof_read", os.read),
                                          readv=self.measure("readv", os.readv))
        exec(compile(getsource(original), str(source), "exec"), namespace)
        return namespace[original.__name__]

    @contextmanager
    def binding(self, frontier):
        load = frontier.load_prefetch

        def observed():
            ordinary = load()
            namespace = ordinary.__wrapped__.__globals__
            producer = namespace["prefetch_member"]
            descriptor = self.descriptor(namespace["read_regular_descriptor"])

            def read(root, name, size, stats):
                clock_before, cpu_before = clock(RUSAGE_THREAD), stats.worker_cpu_ns
                calls = []
                output = None
                self.active = calls
                try:
                    output = producer(root, name, size, stats)
                    return output
                finally:
                    self.active = None
                    self.members.append(dict(segment=root.name, name=name, bytes=size,
                                             supplied=output is not None, calls=calls,
                                             cpu_ns=stats.worker_cpu_ns - cpu_before,
                                             **delta(clock_before, clock(RUSAGE_THREAD))))

            @contextmanager
            def scoped():
                stats = None
                try:
                    with (patch.dict(namespace, prefetch_member=read, read_regular_descriptor=descriptor),
                          ordinary() as stats):
                        yield stats
                finally:
                    if stats is not None:
                        self.stats = asdict(stats)

            return scoped

        try:
            with patch.object(frontier, "load_prefetch", observed):
                yield
        finally:
            if self.pool is not None:
                self.pool.close()

    def result(self):
        slots = [] if self.pool is None else [dict(slot.counts) for slot in self.pool.slots]
        return dict(members=self.members, prefetch=self.stats, slots=slots)
