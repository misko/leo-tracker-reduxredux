"""Examine a sparse decoded exception to otherwise independent legacy blocks."""

from bisect import bisect_right
from collections import Counter
import ctypes as ct
import json

import numpy as np

from leo.contracts.digests import canonical_json_bytes, sha256_digest

from .seekable_member_trial import clock, elapsed
from .zstd_structure import MAX_BLOCK, inspect, literal_section


SCHEMA = "private-legacy-zstd-block-exception-v1"
PREFIX = 80_000 * 8
MAX_HEADER = 96_000


def exception_layout(frame, expected):
    """Locate one match-bearing block and prove its decoded length by conservation."""
    spans = []
    info = inspect(frame, expected, block_spans=spans)
    if (not info["checksum"] or frame[4] & 3 or not 0 < expected < 2**32 or len(frame) >= 2**32
            or sum(bool(sequences) for _, _, _, sequences in spans) != 1
            or info["block_counts"] != {"compressed": len(spans)}
            or set(info["literal_counts"]) - {"huffman_new", "huffman_reused"}):
        raise ValueError("Expected one checksummed Huffman frame with exactly one match-bearing block")
    view, blocks = memoryview(frame), []
    origin, decoded, exception, table = None, 0, None, None
    for ordinal, (encoded, length, count, sequences) in enumerate(spans):
        mode, header, payload, _, streams = literal_section(view[encoded:encoded+length])
        if mode == "huffman_new":
            origin = ordinal
        if sequences:
            exception = ordinal
            if mode == "huffman_new":
                table = (ordinal, header + payload, count)
            count += info["match_bytes"]
        if streams != 4 or not 0 < count <= MAX_BLOCK or origin is None:
            raise ValueError("Invalid four-stream block or table origin")
        blocks.append([encoded, length, decoded, count, origin])
        decoded += count
    if decoded != expected or exception is None:
        raise ValueError("The block map does not cover the signed member exactly")
    if not any(row[4] == exception for row in blocks[exception + 1:]):
        table = None
    return blocks, exception, table


def layout(frame, expected):
    """The original isolated four-byte exception proof."""
    blocks, ordinal, table = exception_layout(frame, expected)
    encoded, length, _, count, _ = blocks[ordinal]
    _, header, payload, literals, _ = literal_section(memoryview(frame)[encoded:encoded+length])
    if table or count - literals != 4 or frame[encoded+header+payload] != 1:
        raise ValueError("Expected one four-byte match and no later use of its table")
    return blocks, ordinal


def overlaps(block, start, length):
    _, _, decoded, size, _ = block
    end = min(start + length, decoded + size)
    return max(start, decoded), end


def encode_sidecar(core, reader, chunk, frame, windows, *, replay_table=False):
    """Require the complete verified stock result, including trailing checks."""
    if replay_table:
        blocks, ordinal, _ = exception_layout(frame, chunk.uncompressed_bytes)
    else:
        blocks, ordinal = layout(frame, chunk.uncompressed_bytes)
    offset, prefixes, captured = 0, [], bytearray()
    for sequence, window in enumerate(windows, chunk.first_sequence):
        row = window.index
        raw = memoryview(window.samples.reshape(-1)).cast("B")
        if (row.sequence != sequence or row.payload_offset_bytes != offset or row.payload_bytes != len(raw)
                or sha256_digest(raw) != row.iq_sha256):
            raise ValueError("The original complete signed visits are required to seal an exception")
        start, end = overlaps(blocks[ordinal], offset, len(raw))
        if start < end:
            captured.extend(raw[start-offset:end-offset])
        prefixes.append(sha256_digest(raw[:PREFIX]))
        offset += len(raw)
    if (offset != chunk.uncompressed_bytes or len(captured) != blocks[ordinal][3]
            or len(prefixes) != chunk.window_count or sha256_digest(frame) != chunk.compressed_sha256):
        raise ValueError("The certified exception exceeds decoded or encoded member geometry")
    document = dict(schema=SCHEMA, **core.identity(reader, chunk), blocks=blocks, ordinal=ordinal,
                    prefixes=prefixes, exact_decoded_exception_sha256=sha256_digest(captured))
    header = canonical_json_bytes(document)
    return len(header).to_bytes(4, "little") + header + captured


def open_sidecar(core, reader, chunk, sidecar, pin):
    if len(sidecar) > 4 + MAX_HEADER + MAX_BLOCK or sha256_digest(sidecar) != pin:
        raise core.MapError("The detached exception sidecar disagrees with its external pin")
    header = int.from_bytes(sidecar[:4], "little")
    if not 0 < header <= MAX_HEADER or not 4 + header < len(sidecar):
        raise core.MapError("The detached exception header is incomplete")
    try:
        document = json.loads(sidecar[4:4+header])
    except ValueError as error:
        raise core.MapError("The detached exception header is malformed") from error
    expected = core.identity(reader, chunk)
    material = memoryview(sidecar)[4+header:]
    if (not isinstance(document, dict) or set(document) != {*expected, "schema", "blocks", "ordinal", "prefixes",
                                                          "exact_decoded_exception_sha256"}
            or any(document[key] != value for key, value in expected.items()) or document["schema"] != SCHEMA
            or sha256_digest(material) != document["exact_decoded_exception_sha256"]
            or not isinstance(document["prefixes"], list) or len(document["prefixes"]) != chunk.window_count
            or any(not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71
                   for value in document["prefixes"])):
        raise core.MapError("The exception sidecar does not bind the original member and all prefix commitments")
    return document, material


class SelectiveException:
    """Use the common literal decoder on independent spans of the same signed frame."""

    def __init__(self, core, reader, chunk, sidecar, pin, binary, *, replay_table=False):
        self.core, self.chunk, self.binary, self.context = core, chunk, binary, None
        stage = clock()
        if (reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
                or reader.manifest.sample_rate_hz != 10_000_000 or chunk not in reader.manifest.chunks):
            raise core.UnsupportedLayout("Requires a sealed two-receiver 10 MS/s V2 member")
        self.document, self.exception = open_sidecar(core, reader, chunk, sidecar, pin)
        self.rows = core.read_rows(reader, chunk)
        self.metadata = elapsed(stage)
        stage = clock()
        self.frame = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
        self.pointer = ct.cast(np.frombuffer(self.frame, dtype=np.uint8).ctypes.data, ct.c_char_p)
        self.authentication = elapsed(stage)
        stage = clock()
        self.seed = None
        try:
            if replay_table:
                self.blocks, self.ordinal, self.seed = exception_layout(self.frame, chunk.uncompressed_bytes)
            else:
                self.blocks, self.ordinal = layout(self.frame, chunk.uncompressed_bytes)
        except ValueError as error:
            raise core.UnsupportedLayout(str(error)) from error
        if (self.blocks != self.document["blocks"] or self.ordinal != self.document["ordinal"]
                or len(self.exception) != self.blocks[self.ordinal][3]):
            raise core.MapError("The certified exception layout differs from the original authenticated bytes")
        self.native_blocks = (core.Block * len(self.blocks))(*(core.Block(*row) for row in self.blocks))
        self.offsets = [row[2] for row in self.blocks]
        self.decoded_offsets = self.offsets
        self.counts = core.Counts()
        self.reads = Counter()
        self.context = binary.legacy_open()
        if not self.context:
            raise core.UnsupportedLayout("The common legacy decoder failed to initialize")
        if self.seed and not binary.legacy_configure_origin(self.context, *self.seed):
            self.close()
            raise core.UnsupportedLayout("The authenticated literal section cannot restore the table")
        self.scratch = binary.legacy_scratch(self.context)
        self.setup = elapsed(stage)

    def close(self):
        if self.context is not None:
            self.binary.legacy_close(self.context)
            self.context = None

    def decode(self, start, count, address):
        if count:
            at = bisect_right(self.offsets, start) - 1
            if not self.binary.legacy_span(self.context, self.pointer, len(self.frame), self.native_blocks,
                                           len(self.blocks), at, start, count, address, ct.byref(self.counts)):
                raise self.core.UnsupportedLayout("The common decoder declined an independent block span")

    def read(self, row, *, full):
        if not self.context:
            raise self.core.MapError("A closed or tainted exception reader cannot expose decoded data")
        slot = row.sequence - self.chunk.first_sequence
        if not 0 <= slot < len(self.rows) or row != self.rows[slot]:
            raise self.core.MapError("Requested row is outside the verified member index")
        length = row.payload_bytes if full else min(row.payload_bytes, PREFIX)
        out = np.empty((length // 8, 2, 2), dtype="<i2")
        value = memoryview(out.reshape(-1)).cast("B")
        start = row.payload_offset_bytes
        address = out.ctypes.data
        low, high = overlaps(self.blocks[self.ordinal], start, length)
        try:
            if low < high:
                self.decode(start, low-start, address)
                base = self.offsets[self.ordinal]
                value[low-start:high-start] = self.exception[low-base:high-base]
                self.decode(high, start+length-high, address+high-start)
                self.reads["exception_visits"] += 1
                self.reads["exception_bytes"] += high-low
            else:
                self.decode(start, length, address)
            expected = row.iq_sha256 if full else self.document["prefixes"][slot]
            if sha256_digest(value) != expected:
                raise self.core.MapError("Requested span differs from its original prefix or full window hash")
        except (self.core.MapError, self.core.UnsupportedLayout):
            self.close()
            raise
        self.reads["returned_bytes"] += length
        self.reads["full" if full else "prefix"] += 1
        out.flags.writeable = False
        return out
