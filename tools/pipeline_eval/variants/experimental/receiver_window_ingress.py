"""Reuse one canonical decoder and at most two output-window buffers."""

from collections import Counter
from contextlib import contextmanager
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
from weakref import ref

import numpy as np

from leo.storage.short_window import ShortWindowReader

from .paired_sha256 import paired_windows
from .receiver_arena_ingress import _Loan

_MAX_WINDOW_BYTES = 1_600_000


class _WindowReads:
    def __init__(self, source, slots, counts):
        self.source = source
        self.slots = slots
        self.counts = counts

    def read(self, count):
        # Keep EOF probes, other geometries and exhausted loans canonical.
        if not 1 < count <= _MAX_WINDOW_BYTES:
            return self.source.read(count)
        for index, slot in enumerate(self.slots):
            if slot is not None and slot[1]() is not None:
                continue
            try:
                if slot is None or slot[0].size < count:
                    self.slots[index] = slot = None
                    target = np.empty(count, dtype=np.uint8)
                    self.counts["allocations"] += 1
                else:
                    target = slot[0]
                    self.counts["reuses"] += 1
            except MemoryError:
                break
            target.setflags(write=True)
            with memoryview(target)[:count] as view:
                wrote = self.source.readinto(view)
            target.setflags(write=False)
            owner = _Loan(target, wrote)
            self.slots[index] = target, ref(owner)
            self.counts["loaned_windows"] += 1
            return memoryview(owner)
        self.counts["owned_windows"] += 1
        return self.source.read(count)


class WindowStreams:
    """Reuse decoder state in a serial scope without changing frame behavior."""

    def __init__(self, *, loan_buffers=False):
        self.loan_buffers = loan_buffers
        self.counts = Counter()
        self._slots = [None, None]

    @contextmanager
    def install(self, paired_library):
        release = ShortWindowReader.windows
        zstd = release.__globals__["zstd"]
        decoder = zstd.ZstdDecompressor()
        active = False

        @contextmanager
        def stream_reader(compressed):
            nonlocal active
            if active:
                self.counts["nested_streams"] += 1
                with zstd.ZstdDecompressor().stream_reader(compressed) as original:
                    yield original
                return
            active = True
            try:
                self.counts["streams"] += 1
                with decoder.stream_reader(compressed) as stream:
                    yield (
                        _WindowReads(stream, self._slots, self.counts)
                        if self.loan_buffers
                        else stream
                    )
            finally:
                active = False

        codec = SimpleNamespace(
            ZstdError=zstd.ZstdError,
            ZstdDecompressor=lambda: SimpleNamespace(stream_reader=stream_reader),
        )
        bound = FunctionType(
            release.__code__, release.__globals__ | {"zstd": codec}, argdefs=release.__defaults__
        )

        def windows(reader, **scope):
            if type(reader) is not ShortWindowReader:
                return release(reader, **scope)
            return paired_windows(reader, paired_library, original=bound, **scope)

        with patch.object(ShortWindowReader, "windows", windows):
            yield
