"""Use an owned window per consumer and a bounded circular native history."""

from contextlib import contextmanager
import ctypes as ct
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from . import fused_block_input
from .dense_zstd_backend import _bytes_data, _bytes_new


class Ring:
    def __init__(self, path):
        self.library = ct.CDLL(str(path))
        types = {
            "capacity": (ct.c_size_t, ct.c_void_p, ct.c_size_t, ct.c_size_t, ct.c_void_p),
            "create": (ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_size_t, ct.c_size_t, ct.c_size_t),
            "free": (None, ct.c_void_p),
            "window": (ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p),
            "end": (ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_void_p),
        }
        for name, (result, *arguments) in types.items():
            function = getattr(self.library, "fused_ring_" + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)


class VerifiedRing(fused_block_input.VerifiedDecode):
    @contextmanager
    def stream_reader(self, compressed, extent):
        source = np.frombuffer(compressed, dtype=np.uint8)
        geometry = (ct.c_uint64 * 2)()
        capacity = self.bridge.capacity(source.ctypes.data, source.nbytes, extent, geometry)
        self.fused = bool(capacity)
        if not self.fused:
            self.record["fallbacks"] += 1
            self.stock.new_chunk()
            with self.zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                yield reader
            return

        history, block = geometry
        self.record["fused_frames"] += 1
        self.record["ring_bytes"] = max(self.record.get("ring_bytes", 0), capacity)
        self.record["history_bytes"] = max(self.record.get("history_bytes", 0), history)
        self.record["block_bytes"] = max(self.record.get("block_bytes", 0), block)
        context = self.bridge.create(source.ctypes.data, source.nbytes, extent, capacity, block)
        if not context:
            raise MemoryError("Could not initialize the native Zstandard history")
        try:
            yield self.window_stream(context, extent)
        finally:
            self.bridge.free(context)

    def window_stream(self, context, extent):
        offset, digest = 0, ct.create_string_buffer(32)

        def read(size):
            nonlocal offset
            if self.pending is not None:
                raise RuntimeError("A prior window still needs its original digest check")
            if size == 1 and offset == extent:
                stats = (ct.c_uint64 * 6)()
                if self.bridge.end(context, digest, stats):
                    raise self.zstd.ZstdError("Incomplete or inconsistent decoded member")
                self.record.update(dict(zip(("decode_cpu_ns", "hash_cpu_ns", "steps", "windows",
                                             "wraps", "copied_bytes"), stats, strict=True)))
                self.final = digest.raw.hex()
                self.record["decoded_member"] = "sha256:" + self.final
                return b""
            if size % 4 or size > extent-offset:
                raise self.zstd.ZstdError("Invalid decoded CI16 window extent")
            raw = _bytes_new(None, size)
            if self.bridge.window(context, _bytes_data(raw), size, digest):
                raise self.zstd.ZstdError("Could not decode the requested CI16 window")
            offset += size
            self.pending = (raw, digest.raw)
            return raw

        return SimpleNamespace(read=read)


@contextmanager
def ring_windows(library, paired, stats):
    with patch.object(fused_block_input, "VerifiedDecode", VerifiedRing), fused_block_input.fused_windows(library, paired, stats):
        yield
