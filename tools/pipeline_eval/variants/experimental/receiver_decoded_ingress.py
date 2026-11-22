"""Experimental full-frame and reusable-window decoding under the sealed reader."""

import weakref
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.storage import short_window

from .receiver_ingress import ChunkSlices, compressed_input_buffer


class DirectDecode:
    """Use the decoder's bytes allocation for exact-size single frames."""

    def __init__(self, zstd, size):
        self.zstd = zstd
        self.size = size

    def decode(self, compressed):
        if not 0 < self.size <= 128 * 1024**2:
            return None
        try:
            advertised = self.zstd.frame_content_size(compressed)
            # A known content size can override max_output_size in this API.
            if advertised not in (-1, self.size):
                return None
            decoded = self.zstd.ZstdDecompressor().decompress(
                compressed, max_output_size=self.size, allow_extra_data=False,
            )
        except (self.zstd.ZstdError, MemoryError):
            return None
        return decoded if len(decoded) == self.size else None

    @contextmanager
    def stream_reader(self, compressed):
        decoded = self.decode(compressed)
        if decoded is None:
            with self.zstd.ZstdDecompressor().stream_reader(compressed) as stream:
                yield stream
        else:
            yield ChunkSlices(memoryview(decoded))


class WindowBuffers:
    """Lend decoded windows without overwriting samples retained by the caller."""

    def __init__(self, original):
        self.original = original
        # The bounded reader can hold both the last yielded window and the
        # current unyielded window while validating the rest of a chunk.
        self.slots = [None, None, None]

    def read(self, count):
        if count <= 1:
            return self.original.read(count)
        for index, slot in enumerate(self.slots):
            if slot is not None:
                buffer, borrowed = slot
                if borrowed() is not None:
                    continue
            if slot is None or len(buffer) < count:
                buffer = np.empty(count, dtype=np.uint8)
            buffer.setflags(write=True)
            owner = buffer[:count]
            with memoryview(owner) as view:
                decoded = self.original.readinto(view)
            buffer.setflags(write=False)
            owner.setflags(write=False)
            self.slots[index] = buffer, weakref.ref(owner)
            return memoryview(owner)[:decoded]
        return self.original.read(count)


class WindowDecode:
    def __init__(self, original):
        self.original = original

    @contextmanager
    def stream_reader(self, compressed):
        with self.original.stream_reader(compressed) as stream:
            yield WindowBuffers(stream)


@contextmanager
def direct_decoded_chunk(size):
    """Try one-shot decoding within a bounded prefix, preserving streaming fallback."""
    zstd = short_window.zstd
    buffered = SimpleNamespace(ZstdError=zstd.ZstdError,
                               ZstdDecompressor=lambda: DirectDecode(zstd, size))
    with compressed_input_buffer(), patch.object(short_window, "zstd", buffered):
        yield


@contextmanager
def decoded_window_buffers():
    """Stream through at most three reusable buffers, then fall back to owned bytes."""
    zstd = short_window.zstd
    buffered = SimpleNamespace(ZstdError=zstd.ZstdError,
                               ZstdDecompressor=lambda: WindowDecode(zstd.ZstdDecompressor()))
    with compressed_input_buffer(), patch.object(short_window, "zstd", buffered):
        yield
