"""Loan at most two decoded arenas to the serial research receiver."""

import weakref
from collections import Counter
from contextlib import contextmanager
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.storage.short_window import ShortWindowReader

from .paired_sha256 import paired_windows
from .receiver_ingress import ChunkSlices
from .receiver_zstd_arena import _MAX_BYTES, DecodeArena


class _Loan:
    # PEP 688 makes the read-only export itself hold this object. Slices and
    # NumPy views carry the export through even after their parent is dropped.
    __slots__ = ("_view", "__weakref__")

    def __init__(self, slot, size):
        self._view = memoryview(slot)[:size].toreadonly()

    def __buffer__(self, flags):
        return self._view


class RotatingArenas:
    def __init__(self, decoder):
        self._decoder = decoder
        self._slots = [None, None]
        self.counts = Counter()

    def _loan(self, compressed, expected):
        if self._decoder is None or not 0 < expected <= _MAX_BYTES:
            self.counts["unsupported"] += 1
            return None
        for index, slot in enumerate(self._slots):
            if slot is not None and slot[1]() is not None:
                continue
            try:
                if slot is None or slot[0].nbytes < expected:
                    self._slots[index] = slot = None
                    storage = np.empty(expected, dtype=np.uint8)
                    self.counts["allocations"] += 1
                else:
                    storage = slot[0]
                    self.counts["reuses"] += 1
                storage.setflags(write=True)
                ok = self._decoder.decode(compressed, storage, expected)
            except MemoryError:
                self.counts["allocation_failure"] += 1
                return None
            if not ok:
                self.counts["frame_fallback"] += 1
                return None
            storage.setflags(write=False)
            owner = _Loan(storage, expected)
            self._slots[index] = storage, weakref.ref(owner)
            self.counts["decoded"] += 1
            return ChunkSlices(memoryview(owner))
        self.counts["borrowed_fallback"] += 1
        return None

    def _zstd(self, zstd, reader, start, stop):
        chunks = (
            chunk
            for chunk in reader.manifest.chunks
            if chunk.first_sequence < stop and chunk.first_sequence + chunk.window_count > start
        )

        @contextmanager
        def stream_reader(compressed):
            chunk = next(chunks, None)
            decoded = None
            if chunk is not None and len(compressed) == chunk.compressed_bytes:
                decoded = self._loan(compressed, chunk.uncompressed_bytes)
            if decoded is not None:
                yield decoded
            else:
                with zstd.ZstdDecompressor().stream_reader(compressed) as original:
                    yield original

        return SimpleNamespace(
            ZstdError=zstd.ZstdError,
            ZstdDecompressor=lambda: SimpleNamespace(stream_reader=stream_reader),
        )

    @contextmanager
    def install(self, paired_library):
        """Keep the released checks and alter its private codec binding only."""
        release = ShortWindowReader.windows
        original_zstd = release.__globals__["zstd"]

        def windows(reader, *, start_sequence=0, stop_sequence=None):
            scope = dict(start_sequence=start_sequence, stop_sequence=stop_sequence)
            if type(reader) is not ShortWindowReader:
                return release(reader, **scope)
            stop = reader.manifest.window_count if stop_sequence is None else stop_sequence
            zstd = self._zstd(original_zstd, reader, start_sequence, stop)
            bound = FunctionType(
                release.__code__, release.__globals__ | {"zstd": zstd}, argdefs=release.__defaults__
            )
            return paired_windows(reader, paired_library, original=bound, **scope)

        with patch.object(ShortWindowReader, "windows", windows):
            yield


@contextmanager
def rotating_arenas(library):
    try:
        decoder = DecodeArena(library) if library is not None else None
    except MemoryError:
        decoder = None
    try:
        yield RotatingArenas(decoder)
    finally:
        if decoder is not None:
            decoder.close()
