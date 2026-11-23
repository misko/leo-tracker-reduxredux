"""Bind a direct native decoder to the released integrity and consumer path."""

from contextlib import contextmanager
import ctypes as ct
from inspect import getsource
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants.experimental.paired_sha256 import _DecodedDigests


class Native:
    def __init__(self, path):
        self.library = ct.CDLL(str(path))
        types = {
            "frame_supported": (ct.c_int, ct.c_void_p, ct.c_size_t, ct.c_size_t),
            "member_create": (ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p, ct.c_size_t),
            "member_free": (None, ct.c_void_p),
            "member_window": (ct.c_int, ct.c_void_p, ct.c_size_t, ct.c_void_p),
            "member_end": (ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_void_p),
        }
        for name, (result, *arguments) in types.items():
            function = getattr(self.library, "fused_" + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)


class VerifiedDecode:
    def __init__(self, bridge, paired, zstd, record):
        self.bridge, self.paired, self.zstd, self.record = bridge, paired, zstd, record
        self.stock = _DecodedDigests(paired)
        self.pending = self.final = None

    def new_chunk(self):
        self.pending = self.final = None
        return self

    @contextmanager
    def stream_reader(self, compressed, extent):
        source = np.frombuffer(compressed, dtype=np.uint8)
        if self.bridge.frame_supported(source.ctypes.data, source.nbytes, extent):
            self.record["fallbacks"] += 1
            self.fused = False
            self.stock.new_chunk()
            with self.zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                yield reader
            return
        self.fused = True
        self.record["fused_frames"] += 1
        # Each member owns its storage. NumPy consumers may retain any view.
        owner = np.empty(extent, dtype=np.uint8)
        context = self.bridge.member_create(source.ctypes.data, source.nbytes, owner.ctypes.data, extent)
        if not context:
            raise MemoryError("Could not initialize the block decoder")
        try:
            yield self.window_stream(context, memoryview(owner).toreadonly())
        finally:
            self.bridge.member_free(context)

    def window_stream(self, context, owner):
        offset, digest = 0, ct.create_string_buffer(32)

        def read(size):
            nonlocal offset
            if self.pending is not None:
                raise RuntimeError("A prior window still needs its original digest check")
            if size == 1 and offset == len(owner):
                counts = (ct.c_uint64 * 4)()
                if self.bridge.member_end(context, digest, counts):
                    raise self.zstd.ZstdError("Incomplete or inconsistent decoded member")
                self.record.update(dict(zip(("decode_cpu_ns", "hash_cpu_ns", "steps", "windows"), counts, strict=True)))
                self.final = digest.raw.hex()
                self.record["decoded_member"] = "sha256:" + self.final
                return b""
            if size % 4 or self.bridge.member_window(context, size, digest):
                raise self.zstd.ZstdError("Could not decode the requested CI16 window")
            raw = owner[offset:offset+size]
            offset += size
            self.pending = (raw, digest.raw)
            return raw

        return SimpleNamespace(read=read)

    def window_digest(self, raw):
        if not self.fused:
            return self.stock.window_digest(raw)
        if self.pending is None or raw is not self.pending[0]:
            raise RuntimeError("Digest is detached from its decoded window")
        return "sha256:" + self.pending[1].hex()

    def update(self, raw):
        if not self.fused:
            self.stock.update(raw)
        elif self.pending is None or raw is not self.pending[0]:
            raise RuntimeError("Whole-member state is detached from the checked window")
        else:
            self.pending = None

    def hexdigest(self):
        if not self.fused:
            return self.stock.hexdigest()
        if self.final is None or self.pending is not None:
            raise RuntimeError("The original reader has not finished verifying this member")
        return self.final


@contextmanager
def fused_windows(library, paired, stats):
    from leo.storage.short_window import ShortWindowReader

    release = ShortWindowReader.windows
    shape = "stream_reader(compressed)"
    source = dedent(getsource(release))
    if source.count(shape) != 1:
        raise ValueError("The released decoded-span contract changed")
    code = compile(source.replace(shape, "stream_reader(compressed, chunk.uncompressed_bytes)"),
                   release.__code__.co_filename, "exec")

    def windows(reader, **scope):
        stock = release.__globals__["zstd"]
        engine = VerifiedDecode(library, paired, stock, stats)
        zstd = SimpleNamespace(ZstdError=stock.ZstdError, ZstdDecompressor=lambda: engine)
        bindings = release.__globals__ | dict(zstd=zstd, sha256_digest=engine.window_digest,
                                             hashlib=SimpleNamespace(sha256=engine.new_chunk))
        exec(code, bindings)
        yield from bindings[release.__name__](reader, **scope)

    with patch.object(ShortWindowReader, "windows", windows):
        yield
