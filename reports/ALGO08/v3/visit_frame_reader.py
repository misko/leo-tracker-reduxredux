"""Verified prefix and full-window reads from one ordinary Zstandard member."""

from collections import Counter
import json
from pathlib import Path
import resource
from time import perf_counter_ns, process_time_ns

import numpy as np
import zstandard as zstd

from leo.contracts.digests import sha256_digest
from leo.contracts.multirate_window_recording import ShortWindowChunkV2, ShortWindowIndexV2
from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError


SCHEMA = "private-zstd-visit-frames-8ms-v1"
SIDE = "visit-frames.json"
PREFIX_BYTES = 80_000 * 8
MAX_SIDE_BYTES = 256_000


def clock():
    return perf_counter_ns(), process_time_ns(), resource.getrusage(resource.RUSAGE_SELF).ru_inblock


def elapsed(start):
    return dict(zip(("wall_ns", "cpu_ns", "input_blocks"),
                    (end - begin for begin, end in zip(start, clock(), strict=True)), strict=True))


def bound_chunk(reader, chunk):
    chunks = reader.manifest.chunks
    if chunk is None and len(chunks) == 1:
        chunk = chunks[0]
    if (not isinstance(chunk, ShortWindowChunkV2) or not 0 <= chunk.chunk_index < len(chunks)
            or chunk != chunks[chunk.chunk_index]):
        raise BundleCorruptionError("visit table requires a chunk bound to the installed manifest")
    return chunk


def read_table(reader, pin, *, chunk=None, side_name=SIDE):
    """Accept one externally pinned table for the declared segment member."""
    chunk = bound_chunk(reader, chunk)
    if (not isinstance(side_name, str) or not side_name or side_name in (".", "..")
            or Path(side_name).name != side_name):
        raise BundleCorruptionError("visit sidecar name must stay inside the segment")
    path = reader.path / side_name
    data = short_window.ScannerIqStore._read_regular(path, MAX_SIDE_BYTES)
    if sha256_digest(data) != pin:
        raise BundleCorruptionError("visit sidecar differs from its frozen pin")
    document = json.loads(data)
    if (not isinstance(document, dict) or set(document) != {
            "schema", "manifest_sha256", "index_sha256", "compressed_sha256", "records"}
            or [document[key] for key in ("schema", "manifest_sha256", "index_sha256",
                                         "compressed_sha256")] != [
                SCHEMA, reader.manifest_sha256, chunk.index_sha256, chunk.compressed_sha256]
            or not isinstance(document["records"], list)
            or len(document["records"]) != chunk.window_count
            or reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
            or reader.manifest.sample_rate_hz != 10_000_000):
        raise BundleCorruptionError("visit sidecar identity or geometry differs from the member")
    offset = 0
    for sequence, record in enumerate(document["records"], start=chunk.first_sequence):
        names = ("sequence", "offset", "frame_bytes", "prefix_end", "prefix_bytes")
        if (not isinstance(record, dict) or set(record) != {*names, "prefix_sha256"}
                or any(type(record[key]) is not int for key in names)):
            raise BundleCorruptionError("invalid visit-frame record fields")
        finish = offset + record["frame_bytes"]
        if (record["sequence"] != sequence or record["offset"] != offset
                or not offset <= record["prefix_end"] <= finish <= chunk.compressed_bytes
                or not 0 <= record["prefix_bytes"] <= PREFIX_BYTES
                or bool(record["frame_bytes"]) != bool(record["prefix_bytes"])
                or bool(record["prefix_end"] - offset) != bool(record["prefix_bytes"])):
            raise BundleCorruptionError("visit-frame extents do not form a consecutive partition")
        offset = finish
    # The released index requires a positive encoded member, even for all-empty visits.
    if offset != chunk.compressed_bytes and (offset or chunk.uncompressed_bytes):
        raise BundleCorruptionError("visit frames do not cover the encoded member")
    return document["records"], len(data)


def check_raw(raw, count, pin):
    if len(raw) != count or sha256_digest(raw) != pin:
        raise BundleCorruptionError("decoded visit extent or digest changed")


class SelectiveMember:
    """Verify the whole encoded file before exposing any checked decoded span."""

    def __init__(self, reader, side_pin, *, chunk=None, side_name=SIDE):
        self.reader = reader
        self.chunk = bound_chunk(reader, chunk)
        stage = clock()
        self.records, side_bytes = read_table(reader, side_pin, chunk=self.chunk, side_name=side_name)
        data = reader._member(self.chunk.index_relative_path, self.chunk.index_bytes, self.chunk.index_sha256)
        self.rows = [ShortWindowIndexV2.model_validate_json(line) for line in data.splitlines()]
        offset = 0
        if len(self.rows) != len(self.records):
            raise BundleCorruptionError("visit index count differs from its frame table")
        for row, record in zip(self.rows, self.records, strict=True):
            if (row.sequence != record["sequence"] or row.payload_offset_bytes != offset
                    or row.receiver_count != 2 or row.sample_count > 200_000
                    or row.payload_bytes != row.sample_count * 8
                    or record["prefix_bytes"] != min(row.payload_bytes, PREFIX_BYTES)):
                raise BundleCorruptionError("visit index disagrees with frame geometry")
            offset += row.payload_bytes
        if offset != self.chunk.uncompressed_bytes:
            raise BundleCorruptionError("visit index does not cover the decoded member")
        self.metadata = elapsed(stage)
        stage = clock()
        self.encoded = memoryview(reader._member(
            self.chunk.payload_relative_path, self.chunk.compressed_bytes, self.chunk.compressed_sha256))
        self.authentication = elapsed(stage)
        self.decoder = zstd.ZstdDecompressor()
        if not offset and (zstd.frame_content_size(self.encoded) != 0
                           or self.decoder.decompress(self.encoded, allow_extra_data=False)):
            raise BundleCorruptionError("all-empty visit member decodes to nonempty CI16")
        self.counts = Counter(metadata_bytes=side_bytes + len(data) + (reader.path/"manifest.json").stat().st_size,
                              authenticated_encoded_bytes=len(self.encoded))

    def read(self, row, *, full):
        index = row.sequence - self.chunk.first_sequence
        if not 0 <= index < len(self.rows) or row != self.rows[index]:
            raise BundleCorruptionError("requested visit is outside the verified chunk index")
        record = self.records[index]
        start = record["offset"]
        if full:
            end = start + record["frame_bytes"]
            frame = self.encoded[start:end]
            raw = b""
            if frame:
                if zstd.frame_content_size(frame) != row.payload_bytes:
                    raise BundleCorruptionError("frame content size conflicts with the sealed index")
                raw = self.decoder.decompress(frame, allow_extra_data=False)
            check_raw(raw, row.payload_bytes, row.iq_sha256)
        else:
            end = record["prefix_end"]
            raw = b""
            if end > start:
                with self.decoder.stream_reader(self.encoded[start:end]) as stream:
                    raw = stream.read(record["prefix_bytes"] + 1)
            check_raw(raw, record["prefix_bytes"], record["prefix_sha256"])
        self.counts["decoded_bytes"] += len(raw)
        self.counts["encoded_bytes_fed_to_decoder"] += end - start
        self.counts["full_checks" if full else "prefix_checks"] += 1
        return np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
