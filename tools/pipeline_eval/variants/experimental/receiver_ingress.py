"""Read sealed compressed I/Q into one buffer, then lend verified window slices."""

import os
import stat
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError
from leo.storage.scanner import ScannerIqStore


def read_regular(path, maximum_bytes, *, hash_block=None):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise BundleCorruptionError("scanner IQ bundle member is not one regular file")
        if before.st_size > maximum_bytes:
            raise BundleCorruptionError("scanner IQ bundle member exceeds its declared bound")
        view = memoryview(np.empty(before.st_size, dtype=np.uint8))
        offset = 0
        while offset < len(view):
            block = view[offset:] if hash_block is None else view[offset:offset + 256 * 1024]
            count = os.readv(descriptor, [block])
            if not count:
                raise BundleCorruptionError("scanner IQ bundle member ended while reading")
            if hash_block is not None:
                hash_block(block[:count])
            offset += count
        extra = os.read(descriptor, 1)
        after = os.fstat(descriptor)
        if extra or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise BundleCorruptionError("scanner IQ bundle member changed while reading")
        return view.toreadonly()
    finally:
        os.close(descriptor)


class ChunkSlices:
    def __init__(self, view):
        self.view = view.toreadonly()
        self.offset = 0

    def read(self, count):
        window = self.view[self.offset:self.offset + count]
        self.offset += len(window)
        return window


class DecodeOnce:
    def __init__(self, original, size):
        self.original = original
        self.size = size

    @contextmanager
    def stream_reader(self, compressed):
        view = memoryview(bytearray(self.size))
        with self.original.stream_reader(compressed) as stream:
            offset = 0
            while offset < self.size:
                count = stream.readinto(view[offset:])
                if not count:
                    raise BundleCorruptionError("short-window payload ended before declared size")
                offset += count
            if stream.read(1):
                raise BundleCorruptionError("unexpected trailing IQ bytes")
        yield ChunkSlices(view)


@contextmanager
def compressed_input_buffer():
    """Supply the normal decoder one copy of each bounded compressed member."""
    original = ScannerIqStore._read_regular

    def read(path, maximum_bytes):
        return read_regular(path, maximum_bytes) if path.suffix == ".zst" else original(path, maximum_bytes)

    with patch.object(ScannerIqStore, "_read_regular", staticmethod(read)):
        yield


@contextmanager
def decoded_chunk_buffer(size):
    """Bound the additional raw allocation while comparing decoded chunk slices."""
    if not 0 < size <= 128 * 1024**2:
        raise ValueError("experimental decoded buffering is bounded to 128 MiB")
    zstd = short_window.zstd
    buffered = SimpleNamespace(ZstdError=zstd.ZstdError,
                               ZstdDecompressor=lambda: DecodeOnce(zstd.ZstdDecompressor(), size))
    with compressed_input_buffer(), patch.object(short_window, "zstd", buffered):
        yield
