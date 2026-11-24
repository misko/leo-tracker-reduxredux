"""Produce the existing exception map while verifying one ordinary Zstandard member."""

import ctypes as ct
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile

import numpy as np

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.short_window import ShortWindowRead
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

from . import legacy_block_multi as multi, legacy_block_seek as core
from .legacy_block_seek import clock, elapsed


class Description(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in ("encoded", "length", "origin", "literals", "sequences")]


def build(path):
    from .sparse_cold_input import verified

    verified(multi.ZSTD, multi.ZSTD_PIN)
    source = Path(__file__).with_name("legacy_fused_history.c")
    command = ["cc", "-std=c11", "-O3", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
               str(source), str(multi.ZSTD.resolve()), "-o", str(path)]
    subprocess.run(command, check=True)
    return dict(native_source_sha256=sha256_digest(source.read_bytes()), binary_sha256=sha256_digest(path.read_bytes()),
                libzstd_sha256=multi.ZSTD_PIN, command=command)


def load(path):
    library = ct.CDLL(str(path))
    ptr, size = ct.c_void_p, ct.c_size_t
    declarations = (
        ("open", ptr, (ptr, size, size, ct.POINTER(Description), size, ct.POINTER(core.Block), ptr, size)),
        ("close", None, (ptr,)), ("read", ct.c_int, (ptr, ptr, size)), ("finish", ct.c_int, (ptr,)),
        ("scratch", size, (ptr,)),
    )
    for name, result, arguments in declarations:
        function = getattr(library, "fused_history_" + name)
        function.restype, function.argtypes = result, arguments
    return library


class FusedMember:
    def __init__(self, reader, chunk, library, hasher, *, allow_literal=False):
        began = clock()
        if (reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
                or reader.manifest.sample_rate_hz != 10_000_000 or chunk not in reader.manifest.chunks):
            raise multi.UnsupportedExceptionLayout("Expected original sealed two-antenna V2 geometry")
        self.reader, self.chunk, self.library = reader, chunk, library
        self.rows = core.read_rows(reader, chunk)
        self.metadata = elapsed(began)
        began = clock()
        self.compressed = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
        self.frame = np.frombuffer(self.compressed, dtype=np.uint8)
        self.encoded_auth = elapsed(began)
        began = clock()
        descriptions, self.exceptions, _ = multi.describe(self.compressed, chunk.uncompressed_bytes)
        if not self.exceptions and not allow_literal:
            raise multi.UnsupportedExceptionLayout("Use the ordinary literal-only map for this member")
        self.plan = (Description * len(descriptions))(*(Description(*row[:5]) for row in descriptions))
        self.blocks = (core.Block * len(descriptions))()
        self.retained = np.empty(len(self.exceptions) * multi.MAX_BLOCK, dtype=np.uint8)
        self.digests = PairedSha256(hasher)
        self.prefixes = []
        self.eof = False
        self.metrics = dict(native_read_cpu_ns=0, native_read_wall_ns=0, hash_cpu_ns=0, hash_wall_ns=0)
        self.context = library.fused_history_open(
            self.frame.ctypes.data, len(self.frame), chunk.uncompressed_bytes, self.plan, len(self.plan), self.blocks,
            self.retained.ctypes.data, len(self.exceptions))
        if not self.context:
            raise multi.UnsupportedExceptionLayout("Frame requires unsupported native history or allocation")
        self.scratch = library.fused_history_scratch(self.context)
        self.setup = elapsed(began)

    def close(self):
        if self.context:
            self.library.fused_history_close(self.context)
            self.context = None

    def windows(self):
        if self.prefixes or self.eof or not self.context:
            raise RuntimeError("The fused member is a single traversal")
        for row in self.rows:
            raw = np.empty((row.sample_count, row.receiver_count, 2), dtype="<i2")
            began = clock()
            if not self.library.fused_history_read(self.context, raw.ctypes.data, raw.nbytes):
                raise core.MapError("Original continuous frame decode rejected a block or extent")
            self.charge("native_read", began)
            began = clock()
            payload = memoryview(raw.reshape(-1)).cast("B")
            if "sha256:" + self.digests.window(payload).hex() != row.iq_sha256:
                raise core.MapError("Original decoded visit differs from its index digest")
            self.prefixes.append(sha256_digest(payload[:multi.PREFIX]))
            self.charge("hash", began)
            raw.flags.writeable = False
            yield ShortWindowRead(row, raw)
        began = clock()
        if not self.library.fused_history_finish(self.context):
            raise core.MapError("Original continuous frame EOF, checksum or complete extent changed")
        self.charge("native_read", began)
        if "sha256:" + self.digests.digest().hex() != self.chunk.uncompressed_sha256:
            raise core.MapError("Original complete decoded member differs from its manifest digest")
        self.eof = True

    def charge(self, name, began):
        time = elapsed(began)
        self.metrics[name + "_cpu_ns"] += time["cpu_ns"]
        self.metrics[name + "_wall_ns"] += time["wall_ns"]

    def sidecar(self):
        if not self.eof:
            raise core.MapError("Cannot seal provenance before clean original EOF")
        blocks = [[block.encoded, block.length, block.decoded, block.count, block.origin]
                  for block in self.blocks]
        if not self.exceptions:
            raw = canonical_json_bytes(dict(schema=core.SCHEMA, **core.identity(self.reader, self.chunk),
                                            blocks=blocks, prefixes=self.prefixes))
            if len(raw) > core.MAX_MAP:
                raise multi.UnsupportedExceptionLayout("The literal map exceeds its existing format bound")
            return raw, sha256_digest(raw)
        pieces = [memoryview(self.retained)[i * multi.MAX_BLOCK:i * multi.MAX_BLOCK + blocks[ordinal][3]]
                  for i, ordinal in enumerate(self.exceptions)]
        raw = multi.encode_verified(self.reader, self.chunk, blocks, self.prefixes, self.exceptions, pieces)
        return raw, sha256_digest(raw)

    def audit(self):
        return dict(**self.metrics, metadata=self.metadata, complete_encoded_auth=self.encoded_auth,
                    plan_and_history=self.setup, history_and_context_bytes=self.scratch,
                    block_map_workspace_bytes=ct.sizeof(self.blocks) + ct.sizeof(self.plan),
                    retained_exception_buffer=self.retained.nbytes,
                    largest_sample_window_bytes=max(row.payload_bytes for row in self.rows),
                    exceptional_ordinals=list(self.exceptions))


def publish(path, raw):
    with NamedTemporaryFile(dir=path.parent, prefix=path.name + "-", delete=False) as stream:
        staged = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(staged, path)
        finally:
            staged.unlink()
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def analyze_and_seal(reader, chunk, native, hasher, analyze, path):
    """Propagate validation and detector failures before creating the map pathname."""
    try:
        source = FusedMember(reader, chunk, native, hasher)
    except multi.UnsupportedExceptionLayout as error:
        first = chunk.first_sequence
        return analyze(reader.windows(start_sequence=first, stop_sequence=first + chunk.window_count)), dict(
            fallback=str(error))
    try:
        result = analyze(source.windows())
        began = clock()
        document, pin = source.sidecar()
        publish(path, document)
        seal = elapsed(began)
        return result, dict(
            **source.metrics, metadata=source.metadata, complete_encoded_auth=source.encoded_auth,
            plan_and_history=source.setup, seal_and_sync=seal, map_bytes=len(document), map_sha256=pin,
            history_and_context_bytes=source.scratch, block_map_workspace_bytes=ct.sizeof(source.blocks) + ct.sizeof(source.plan),
            retained_exception_buffer=source.retained.nbytes, largest_sample_window_bytes=max(row.payload_bytes for row in source.rows),
            exceptional_ordinals=source.exceptions,
        )
    finally:
        source.close()
