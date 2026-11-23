"""One decoded destination confined to the synchronous signed prefix runner."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from sys import getrefcount
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
import os

import numpy as np

from tools.pipeline_eval.variants.experimental import paired_sha256, receiver_member_prefetch, receiver_zstd_arena
from tools.pipeline_eval.variants.experimental.receiver_ingress import ChunkSlices

from .sparse_cold_input import WINDOWS_PER_MEMBER, verified


LIBZSTD = Path("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
LIBZSTD_SHA = "060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80"
DECODER_SHA = "7af0635dbcea007fedea9b44cbdd927eed9f2bddfa44c1badbc47b1022712b8b"
RAW_BYTES = 102_400_000


def check_pins():
    verified(LIBZSTD, LIBZSTD_SHA)
    verified(Path(receiver_zstd_arena.__file__), DECODER_SHA)


class SynchronousArena:
    """Release every active callback loan before replacing the decoded frame."""

    def __init__(self, decoder, size=RAW_BYTES, windows=WINDOWS_PER_MEMBER):
        self.decoder = decoder
        self.size = size
        self.windows = windows
        self.storage = None
        self.in_frame = False
        self.active = False
        self.consumed = 0
        self.counts = Counter()

    @contextmanager
    def frame(self, compressed):
        if self.active or self.in_frame:
            raise RuntimeError("The previous IQ loan has not closed")
        operation = "reuse" if self.storage is not None else "allocation"
        if self.storage is None:
            self.storage = np.empty(self.size, dtype=np.uint8)
        self.counts[operation] += 1
        if not self.decoder.decode(compressed, self.storage, self.size):
            raise ValueError("The authenticated frame failed the original bounded decoder")
        slices = ChunkSlices(memoryview(self.storage))
        self.in_frame = True
        self.consumed = 0
        try:
            yield slices
            if self.consumed != self.windows or slices.offset != self.size or self.active:
                raise RuntimeError("Decoded member was not completely consumed before releasing its loan")
            self.counts["completed_frames"] += 1
        finally:
            self.in_frame = False

    @contextmanager
    def consume(self, samples):
        if (not self.in_frame or self.active or self.consumed >= self.windows or samples.flags.writeable
                or samples.nbytes != self.size // self.windows
                or samples.ctypes.data != self.storage.ctypes.data + self.consumed * samples.nbytes):
            raise RuntimeError("Signed receiver got an unexpected or unowned IQ view")
        self.active = True
        references = getrefcount(samples)
        try:
            yield
            if getrefcount(samples) != references:
                raise RuntimeError("Signed receiver retained the loaned window")
            self.consumed += 1
            self.counts["released_callbacks"] += 1
        finally:
            self.active = False

    @contextmanager
    def install(self, library):
        from leo.storage.short_window import ShortWindowReader

        release = ShortWindowReader.windows
        zstd = release.__globals__["zstd"]
        substitute = SimpleNamespace(ZstdError=zstd.ZstdError,
                                     ZstdDecompressor=lambda: SimpleNamespace(stream_reader=self.frame))
        bound = FunctionType(release.__code__, release.__globals__ | {"zstd": substitute},
                             argdefs=release.__defaults__)
        bound.__kwdefaults__ = release.__kwdefaults__

        def windows(reader, **scope):
            return paired_sha256.paired_windows(reader, library, original=bound, **scope)

        with patch.object(ShortWindowReader, "windows", windows):
            yield


@contextmanager
def verify_members():
    """Record each passed stock compressed/index check and computed raw digest without rehashing."""
    from leo.storage.short_window import ShortWindowReader

    decoded = paired_sha256._DecodedDigests
    member, finalize = ShortWindowReader._member, decoded.hexdigest
    checked = dict(compressed_and_index=[], decoded_members=[])

    def read_checked(reader, name, size, digest):
        payload = member(reader, name, size, digest)
        checked["compressed_and_index"].append((name, size, digest))
        return payload

    def decoded_checked(state):
        digest = finalize(state)
        checked["decoded_members"].append("sha256:" + digest)
        return digest

    with (patch.object(ShortWindowReader, "_member", read_checked),
          patch.object(decoded, "hexdigest", decoded_checked)):
        yield checked


@contextmanager
def ingress(mode, hasher, advice):
    with ExitStack() as stack:
        checked = stack.enter_context(verify_members())
        if mode == "advice":
            stack.enter_context(paired_sha256.paired_decoded_hashes(hasher))
            yield stack.enter_context(advice()), None, checked
            return
        if mode != "prefetch-arena":
            raise ValueError("Unknown matched ingress comparison")

        member_prefetch = receiver_member_prefetch.prefetch_member
        cpus = set()

        def verify_affinity(*args):
            current = os.sched_getaffinity(0)
            if current != {2}:
                raise RuntimeError("Speculative compressed reads must share the pinned acquisition CPU")
            cpus.update(current)
            return member_prefetch(*args)

        decoder = stack.enter_context(receiver_zstd_arena.DecodeArena(receiver_zstd_arena.runtime(LIBZSTD)))
        arena = SynchronousArena(decoder)
        stack.enter_context(arena.install(hasher))
        stack.enter_context(patch.object(receiver_member_prefetch, "prefetch_member", verify_affinity))
        hints = stack.enter_context(receiver_member_prefetch.compressed_member_prefetch())
        yield hints, arena, checked
        checked["prefetch_cpu_affinity"] = sorted(cpus)
        checked["arena"] = dict(arena.counts, destination_bytes=arena.size)
