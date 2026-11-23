"""Measure independent compressed buffer ownership inside the checked reader."""

from collections import Counter
from contextlib import contextmanager
from time import process_time_ns, perf_counter_ns
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
from weakref import ref

import numpy as np


class CompressedSlots:
    """Lend bounded storage while a decoder or a view still owns the slice."""

    def __init__(self, capacity):
        if not 0 < capacity <= 96 * 1024**2:
            raise ValueError("Compressed destinations must fit the bounded prefix")
        self.capacity = capacity
        self.slots = []
        self.counts = Counter()

    def empty(self, size, dtype):
        if 0 < size <= self.capacity and dtype == np.uint8:
            for i, (buffer, owner) in enumerate(self.slots):
                if owner() is None:
                    return self._lend(i, buffer, size, "reuse")
            if len(self.slots) < 2:
                buffer = np.empty(self.capacity, dtype=dtype)
                return self._lend(len(self.slots), buffer, size, "allocation")
        self.counts["fallback"] += 1
        return np.empty(size, dtype=dtype)

    def _lend(self, index, buffer, size, event):
        owner = buffer[:size]
        previous = (buffer, ref(owner))
        self.slots[index:index+1] = [previous]
        self.counts[event] += 1
        return owner


def bind_allocator(original, pool):
    """Keep the verified descriptor implementation and replace only np.empty."""
    if "np" not in original.__code__.co_names or "empty" not in original.__code__.co_names:
        raise ValueError("The installed descriptor allocation port changed")
    globals_ = original.__globals__ | {"np": SimpleNamespace(empty=pool.empty, uint8=np.uint8)}
    bound = FunctionType(original.__code__, globals_, argdefs=original.__defaults__)
    bound.__kwdefaults__ = original.__kwdefaults__
    return bound


class AcquisitionCosts:
    def __init__(self):
        self.cpu_ns, self.wall_ns, self.calls = Counter(), Counter(), Counter()
        self.members, self.decoded_members = [], []

    def time(self, stage, operation, *args, **kwargs):
        cpu, wall = process_time_ns(), perf_counter_ns()
        try:
            return operation(*args, **kwargs)
        finally:
            self.cpu_ns[stage] += process_time_ns()-cpu
            self.wall_ns[stage] += perf_counter_ns()-wall
            self.calls[stage] += 1

    def receipt(self):
        return dict(cpu_ns=dict(self.cpu_ns), wall_ns=dict(self.wall_ns), calls=dict(self.calls),
                    verified_members=self.members, decoded_members=self.decoded_members)


@contextmanager
def measured_ingress(buffer, costs, pool=None):
    from leo.storage import short_window
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

    globals_ = buffer.__wrapped__.__globals__
    port = "read_regular_descriptor" if "read_regular_descriptor" in globals_ else "read_regular"
    original = globals_[port]
    descriptor = original if pool is None else bind_allocator(original, pool)
    stock_member = short_window.ShortWindowReader._member
    stock_zstd = short_window.zstd
    stock_window, stock_digest = PairedSha256.window, PairedSha256.digest

    def read(*args, **kwargs):
        return costs.time("compressed_descriptor", descriptor, *args, **kwargs)

    def member(reader, name, size, digest):
        stage = "compressed_verified" if name.endswith(".zst") else "index_verified"
        result = costs.time(stage, stock_member, reader, name, size, digest)
        costs.members.append([name, size, digest])
        return result

    class Decoder:
        @contextmanager
        def stream_reader(self, compressed):
            engine = costs.time("zstd_setup", stock_zstd.ZstdDecompressor)
            original_stream = costs.time("zstd_setup", engine.stream_reader, compressed)
            with original_stream as stream:
                yield SimpleNamespace(read=lambda size: costs.time("zstd_read", stream.read, size))

    def decoded_window(owner, raw):
        return costs.time("decoded_sha", stock_window, owner, raw)

    def decoded_member(owner):
        digest = costs.time("decoded_sha", stock_digest, owner)
        costs.decoded_members.append("sha256:" + digest.hex())
        return digest

    zstd = SimpleNamespace(ZstdError=stock_zstd.ZstdError, ZstdDecompressor=Decoder)
    with (patch.dict(globals_, {port: read}),
          patch.object(short_window.ShortWindowReader, "_member", member), patch.object(short_window, "zstd", zstd),
          patch.object(PairedSha256, "window", decoded_window), patch.object(PairedSha256, "digest", decoded_member),
          buffer()):
        yield
