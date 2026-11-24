"""Detached exact exceptions for original checksummed Huffman-compressed members."""

from bisect import bisect_right
from collections import Counter
import ctypes as ct
import json
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_json_bytes, sha256_digest

from . import legacy_block_seek as core
from .legacy_block_exception import PREFIX, UnsupportedExceptionLayout
from .seekable_member_trial import clock, elapsed
from .sparse_cold_input import verified
from .zstd_structure import MAX_BLOCK, inspect, literal_section


SCHEMA = "private-legacy-zstd-block-exceptions-v1"
MAX_EXCEPTIONS = 16
MAX_HEADER = 262_144
MAX_SIDECAR = 4 + MAX_HEADER + MAX_EXCEPTIONS * MAX_BLOCK
ZSTD = Path("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
ZSTD_PIN = "060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80"
DATA_TYPES = (2, 3)  # ZSTDnit_block and ZSTDnit_lastBlock in the pinned header ABI.


def describe(frame, expected):
    """Get exact encoded block extents and Huffman dependencies from the frame itself."""
    spans = []
    try:
        structure = inspect(frame, expected, block_spans=spans)
    except ValueError as error:
        raise UnsupportedExceptionLayout(str(error)) from error
    if (not structure["checksum"] or frame[4] & 3 or not 0 < expected < 2**32 or len(frame) >= 2**32
            or structure["block_counts"] != {"compressed": len(spans)}
            or set(structure["literal_counts"]) - {"huffman_new", "huffman_reused"}):
        raise UnsupportedExceptionLayout("Expected a checksummed dictionary-free frame of Huffman blocks")
    source, blocks, origin = memoryview(frame), [], None
    for index, (offset, count, plain, sequences) in enumerate(spans):
        kind, header, packed, literals, streams = literal_section(source[offset:offset+count])
        if kind == "huffman_new":
            origin = index
        if origin is None or literals != plain or streams != 4 or not 0 < plain <= MAX_BLOCK:
            raise UnsupportedExceptionLayout("Expected a real four-stream literal table and valid extent")
        blocks.append((offset, count, origin, plain, sequences, header+packed))
    exceptions = tuple(index for index, row in enumerate(blocks) if row[4])
    owners = {row[2] for row in blocks if not row[4]} & set(exceptions)
    if len(exceptions) > MAX_EXCEPTIONS or len(owners) > 1:
        raise UnsupportedExceptionLayout("The explicit exception or table-owner budget was exceeded")
    return blocks, exceptions, next(iter(owners), None)


def load_history():
    verified(ZSTD, ZSTD_PIN)
    lib = ct.CDLL(str(ZSTD))
    address, size = ct.c_void_p, ct.c_size_t
    for name, result, arguments in (
        ("ZSTD_createDCtx", address, ()), ("ZSTD_freeDCtx", size, (address,)),
        ("ZSTD_decompressBegin", size, (address,)), ("ZSTD_nextSrcSizeToDecompress", size, (address,)),
        ("ZSTD_nextInputType", ct.c_int, (address,)), ("ZSTD_isError", ct.c_uint, (size,)),
        ("ZSTD_decompressContinue", size, (address, address, size, address, size)),
    ):
        function = getattr(lib, name)
        function.restype, function.argtypes = result, arguments
    return lib


def decode_boundaries(library, frame, expected, descriptions):
    """Let libzstd regenerate every consecutive original block with complete history."""
    ctx = library.ZSTD_createDCtx()
    if not ctx:
        raise UnsupportedExceptionLayout("The historical decoder could not allocate a context")
    source = np.frombuffer(frame, dtype=np.uint8)
    raw = bytearray(expected)
    output = np.frombuffer(raw, dtype=np.uint8)
    at = decoded = 0
    blocks = []
    try:
        if library.ZSTD_isError(library.ZSTD_decompressBegin(ctx)):
            raise core.MapError("Cannot initialize the authoritative native decode")
        while count := library.ZSTD_nextSrcSizeToDecompress(ctx):
            input_type = library.ZSTD_nextInputType(ctx)
            if at + count > len(frame) or (input_type not in (0, 1, *DATA_TYPES, 4)):
                raise core.MapError("Frame has an unexpected native stage or truncated source")
            result = library.ZSTD_decompressContinue(ctx, output.ctypes.data+decoded, expected-decoded,
                                                     source.ctypes.data+at, count)
            if library.ZSTD_isError(result) or result > expected-decoded:
                raise core.MapError("Complete native frame decode rejected a block or checksum")
            if input_type in DATA_TYPES:
                if len(blocks) >= len(descriptions):
                    raise core.MapError("The native decoder emitted an uncharted block")
                offset, size, owner, literals, sequences, _ = descriptions[len(blocks)]
                if (offset, size) != (at, count) or not valid_length(result, literals, sequences):
                    raise core.MapError("Native block extent disagrees with the authenticated frame layout")
                blocks.append([at, count, decoded, result, owner])
            elif result:
                raise core.MapError("Frame metadata generated unexpected sample bytes")
            decoded += result
            at += count
    finally:
        library.ZSTD_freeDCtx(ctx)
    if at != len(frame) or len(blocks) != len(descriptions) or decoded != expected:
        raise core.MapError("Native block decode did not cover the full original member and checksum")
    return raw, blocks


def valid_length(count, literals, sequences):
    return count == literals if not sequences else literals+3*sequences <= count <= MAX_BLOCK


def seal(reader, chunk, frame, stock_windows, *, history=None):
    """Exhaust the released verifier separately, then bind exact native block boundaries."""
    if sha256_digest(frame) != chunk.compressed_sha256:
        raise core.MapError("The input frame did not bind the released compressed hash")
    rows = core.read_rows(reader, chunk)
    descriptions, exceptions, _ = describe(frame, chunk.uncompressed_bytes)
    if not exceptions:
        raise UnsupportedExceptionLayout("Use the ordinary legacy block map for literal-only members")
    raw, blocks = decode_boundaries(history or load_history(), frame, chunk.uncompressed_bytes, descriptions)
    if sha256_digest(raw) != chunk.uncompressed_sha256:
        raise core.MapError("The full native decoded stream differs from the released member hash")
    view = memoryview(raw)
    prefixes = []
    for row, stock in zip(rows, stock_windows, strict=True):
        start = row.payload_offset_bytes
        word = view[start:start+row.payload_bytes]
        expected = memoryview(stock.samples.reshape(-1)).cast("B")
        if row != stock.index or word != expected:
            raise core.MapError("The complete independent native decode disagrees with the released stock window")
        prefixes.append(sha256_digest(word[:PREFIX]))
    pieces, declarations = [], []
    for index in exceptions:
        _, _, offset, count, _ = blocks[index]
        piece = view[offset:offset+count]
        pieces.append(piece)
        declarations.append([index, sha256_digest(piece)])
    document = dict(schema=SCHEMA, **core.identity(reader, chunk), blocks=blocks, prefixes=prefixes,
                    exceptions=declarations)
    header = canonical_json_bytes(document)
    if len(header) > MAX_HEADER:
        raise UnsupportedExceptionLayout("The block metadata exceeds the accepted sidecar budget")
    return b"".join((len(header).to_bytes(4, "little"), header, *pieces))


def trusted_header(reader, chunk, sidecar, pin):
    if not isinstance(sidecar, bytes) or len(sidecar) > MAX_SIDECAR or sha256_digest(sidecar) != pin:
        raise core.MapError("A detached block-exceptions map needs immutable externally pinned bytes")
    size = int.from_bytes(sidecar[:4], "little")
    if not 0 < size <= MAX_HEADER or 4+size >= len(sidecar):
        raise core.MapError("Detached block-exceptions map header is incomplete")
    try:
        header = json.loads(sidecar[4:4+size])
    except ValueError as error:
        raise core.MapError("Detached block-exceptions map header is malformed") from error
    expected = core.identity(reader, chunk)
    if (not isinstance(header, dict) or set(header) != {*expected, "schema", "blocks", "prefixes", "exceptions"}
            or header["schema"] != SCHEMA or any(header[key] != val for key, val in expected.items())
            or not isinstance(header["prefixes"], list) or len(header["prefixes"]) != chunk.window_count
            or any(not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:")
                   for value in header["prefixes"])):
        raise core.MapError("Detached block-exceptions map does not bind original geometry and commitments")
    return header, memoryview(sidecar)[4+size:]


def bind_map(header, payload, descriptions, ordinals, expected):
    blocks, exceptions = header["blocks"], header["exceptions"]
    if (not isinstance(blocks, list) or len(blocks) != len(descriptions) or not ordinals
            or not isinstance(exceptions, list) or len(exceptions) != len(ordinals)):
        raise core.MapError("Detached map does not cover the original block and exception roster")
    accumulated = 0
    for row, (offset, size, owner, raw, sequences, _) in zip(blocks, descriptions, strict=True):
        if (not isinstance(row, list) or len(row) != 5 or any(type(value) is not int for value in row)
                or (row[0], row[1], row[2], row[4]) != (offset, size, accumulated, owner)
                or not valid_length(row[3], raw, sequences)):
            raise core.MapError("Detached map disagrees with authentic encoded ranges or decoded extent")
        accumulated += row[3]
    active, extent = [], 0
    for ordinal, record in zip(ordinals, exceptions, strict=True):
        _, _, start, count, _ = blocks[ordinal]
        raw = payload[extent:extent+count]
        if (not isinstance(record, list) or len(record) != 2 or type(record[0]) is not int or record[0] != ordinal
                or len(raw) != count or sha256_digest(raw) != record[1]):
            raise core.MapError("Detached exception changed identity, offset or exact decoded bytes")
        active.append((start, start+count, raw))
        extent += count
    if accumulated != expected or extent != len(payload):
        raise core.MapError("Detached map has unassigned or missing bytes")
    return blocks, active


class Selective:
    """Authenticate the original encoded member and expose one checked span at a time."""

    def __init__(self, reader, chunk, sidecar, external_pin, library):
        self.chunk, self.library, self.context = chunk, library, None
        stage = clock()
        if (reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
                or reader.manifest.sample_rate_hz != 10_000_000 or chunk not in reader.manifest.chunks):
            raise UnsupportedExceptionLayout("Expected the signed original two-receiver 10 MS/s V2 member")
        header, payload = trusted_header(reader, chunk, sidecar, external_pin)
        self.rows = core.read_rows(reader, chunk)
        self.prefixes = header["prefixes"]
        self.metadata = elapsed(stage)
        stage = clock()
        self.frame = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
        self.pointer = ct.c_char_p(self.frame)
        self.authentication = elapsed(stage)
        stage = clock()
        descriptions, ordinals, owner = describe(self.frame, chunk.uncompressed_bytes)
        blocks, self.exceptions = bind_map(header, payload, descriptions, ordinals, chunk.uncompressed_bytes)
        self.offsets = [row[2] for row in blocks]
        self.exception_ends = [last for _, last, _ in self.exceptions]
        self.blocks = (core.Block * len(blocks))(*(core.Block(*row) for row in blocks))
        self.counts, self.requests = core.Counts(), Counter()
        self.context = library.legacy_open()
        if not self.context:
            raise UnsupportedExceptionLayout("The common legacy decoder could not initialize")
        if owner is not None:
            configure = getattr(library, "legacy_configure_origin", None)
            _, _, _, plain, _, encoded = descriptions[owner]
            if configure is None or not configure(self.context, owner, encoded, plain):
                self.close()
                raise UnsupportedExceptionLayout("The required exceptional owner cannot seed the native Huffman table")
        self.owner = owner
        self.setup = elapsed(stage)

    def close(self):
        if self.context is not None:
            self.library.legacy_close(self.context)
            self.context = None

    def decode(self, start, stop, target):
        if start < stop:
            at = bisect_right(self.offsets, start) - 1
            if not self.library.legacy_span(self.context, self.pointer, len(self.frame), self.blocks, len(self.blocks),
                                            at, start, stop-start, target, ct.byref(self.counts)):
                raise core.UnsupportedLayout("Native independent block decode declined")

    def read(self, row, *, full):
        if not self.context:
            raise core.MapError("A closed or tainted exception reader cannot issue visits")
        slot = row.sequence - self.chunk.first_sequence
        if not 0 <= slot < len(self.rows) or row != self.rows[slot]:
            raise core.MapError("Requested visit is outside the verified original index")
        length = row.payload_bytes if full else min(row.payload_bytes, PREFIX)
        output = np.empty((length // 8, 2, 2), dtype="<i2")
        raw = memoryview(output.reshape(-1)).cast("B")
        start, address = row.payload_offset_bytes, output.ctypes.data
        cursor, stop = start, start+length
        try:
            slot_exception = bisect_right(self.exception_ends, cursor)
            for position in range(slot_exception, len(self.exceptions)):
                low, high, alternate = self.exceptions[position]
                if low >= stop or cursor == stop:
                    break
                left, right = max(cursor, low), min(stop, high)
                self.decode(cursor, left, address+cursor-start)
                raw[left-start:right-start] = alternate[left-low:right-low]
                cursor = right
                self.requests["exception_spans"] += 1
                self.requests["exception_bytes"] += right-left
            self.decode(cursor, stop, address+cursor-start)
            if sha256_digest(raw) != (row.iq_sha256 if full else self.prefixes[slot]):
                raise core.MapError("Original signed full or committed prefix hash did not verify")
        except (core.MapError, core.UnsupportedLayout):
            self.close()
            raise
        self.requests["returned_bytes"] += length
        self.requests["full" if full else "prefix"] += 1
        output.flags.writeable = False
        return output


def open_optional(reader, chunk, sidecar, external_pin, library):
    """Decline only before any visit can be handed to the downstream detector."""
    if sidecar is None:
        return None
    try:
        return Selective(reader, chunk, sidecar, external_pin, library)
    except UnsupportedExceptionLayout:
        return None
