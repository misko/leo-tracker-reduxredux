"""Chunk-level verified suffix for the first-third ALGO08v3 experiment."""

from contextlib import closing
from dataclasses import dataclass
from time import process_time_ns
from types import SimpleNamespace

import numpy as np
import zstandard as zstd

from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256
from tools.pipeline_eval.variants.experimental.receiver_ingress import DecodeOnce


MAX_BUFFER_BYTES = 128 * 1024**2


@dataclass(frozen=True)
class PrefixPlan:
    count: int
    admitted: int
    keep: int
    cutoff: int
    indexes: dict


def chunk_rows(source, chunk):
    reader = source.reader
    index = reader._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
    try:
        rows = tuple(ShortWindowIndexV2.model_validate_json(line) for line in bytes(index).splitlines())
    except ValueError as exc:
        raise BundleCorruptionError("invalid short-window index") from exc
    if len(rows) != chunk.window_count:
        raise BundleCorruptionError("window index count differs from manifest")
    offset = 0
    for number, row in enumerate(rows):
        if (row.sequence != chunk.first_sequence + number or row.payload_offset_bytes != offset
                or row.receiver_count != len(source.receiver_ids)
                or row.sample_count > reader.manifest.sample_rate_hz // 50):
            raise BundleCorruptionError("window index geometry is not consecutive")
        offset += row.payload_bytes
    if offset != chunk.uncompressed_bytes:
        raise BundleCorruptionError("short-window chunk geometry or digest changed")
    return rows


def scope_chunks(source):
    for chunk in source.reader.manifest.chunks:
        if chunk.first_sequence + chunk.window_count > source.start_sequence and chunk.first_sequence < source.stop_sequence:
            yield chunk


def admitted_prefix(entries, stops):
    """Determine the cutoff from authenticated indexes and released quality rules."""
    policy = FastScanPolicyV2()
    valid, indexes, count = [], {}, 0
    for entry, stop in zip(entries, stops, strict=True):
        source = FastSegmentSource(entry, stop_sequence=stop)
        manifest = source.reader.manifest
        if manifest.schema_version != 2 or manifest.sample_rate_hz != policy.sample_rate_hz or source.receiver_ids != (0, 1):
            raise ValueError("first-third plan requires native v2 stereo geometry")
        for chunk in scope_chunks(source):
            rows = chunk_rows(source, chunk)
            indexes[(source.manifest_digest, chunk.first_sequence)] = rows
            for row in rows:
                if row.sequence >= source.stop_sequence:
                    break
                visit = row.acquisition["global_visit"]
                if visit != count or row.target_id not in source.targets:
                    raise ValueError("Unexpected authenticated visit order or RF target")
                count += 1
                shape = (row.sample_count, row.receiver_count, 2)
                if valid_window_support(row.acquisition, manifest.sample_rate_hz, shape, source.receiver_ids, policy):
                    valid.append(visit)
    keep = len(valid) // 3
    cutoff = valid[keep - 1] + 1 if keep else 0
    return PrefixPlan(count, len(valid), keep, cutoff, indexes)


def verified_payload(reader, chunk, rows, library, stats):
    """Verify the bounded decoded region and each original row against its digest."""
    if chunk.uncompressed_bytes > MAX_BUFFER_BYTES:
        raise ValueError("prototype bulk decode is limited to 128 MiB per member")
    start = process_time_ns()
    compressed = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    stats["compressed_cpu_ns"] += process_time_ns() - start
    start = process_time_ns()
    try:
        with DecodeOnce(zstd.ZstdDecompressor(), chunk.uncompressed_bytes).stream_reader(compressed) as decoded:
            stats["decode_cpu_ns"] += process_time_ns() - start
            start = process_time_ns()
            digests = PairedSha256(library)
            for row in rows:
                view = decoded.read(row.payload_bytes)
                if len(view) != row.payload_bytes or "sha256:" + digests.window(view).hex() != row.iq_sha256:
                    raise BundleCorruptionError("window IQ length or digest changed")
            if (len(decoded.read(1)) or decoded.offset != chunk.uncompressed_bytes
                    or "sha256:" + digests.digest().hex() != chunk.uncompressed_sha256):
                raise BundleCorruptionError("short-window chunk geometry or digest changed")
            stats["decoded_hash_cpu_ns"] += process_time_ns() - start
            stats["bulk_members"] += 1
            stats["decoded_bytes"] += chunk.uncompressed_bytes
            return decoded.view
    except zstd.ZstdError as exc:
        raise BundleCorruptionError("invalid short-window compressed IQ") from exc


def verified_stream(reader, chunk, rows, library, cutoff, stats):
    """Drain empty windows into one reusable buffer and lend only paid data."""
    start = process_time_ns()
    compressed = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    stats["compressed_cpu_ns"] += process_time_ns() - start
    scratch = memoryview(bytearray(max(row.payload_bytes for row in rows)))
    digests, offset = PairedSha256(library), 0
    try:
        with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
            for row in rows:
                start = process_time_ns()
                paid = row.acquisition["global_visit"] < cutoff
                if paid:
                    raw = stream.read(row.payload_bytes)
                else:
                    raw = scratch[:row.payload_bytes]
                    filled = 0
                    while filled < len(raw):
                        step = stream.readinto(raw[filled:])
                        if not step:
                            raise BundleCorruptionError("short-window payload ended before declared size")
                        filled += step
                stats["decode_cpu_ns"] += process_time_ns() - start
                start = process_time_ns()
                if len(raw) != row.payload_bytes or "sha256:" + digests.window(raw).hex() != row.iq_sha256:
                    raise BundleCorruptionError("window IQ length or digest changed")
                offset += len(raw)
                stats["decoded_hash_cpu_ns"] += process_time_ns() - start
                yield row, raw if paid else None
            if stream.read(1):
                raise BundleCorruptionError("unexpected trailing IQ bytes")
    except zstd.ZstdError as exc:
        raise BundleCorruptionError("invalid short-window compressed IQ") from exc
    if offset != chunk.uncompressed_bytes or "sha256:" + digests.digest().hex() != chunk.uncompressed_sha256:
        raise BundleCorruptionError("short-window chunk geometry or digest changed")
    stats["bulk_members"] += 1
    stats["decoded_bytes"] += offset


def window(source, row, samples):
    return SimpleNamespace(sequence=row.sequence, iq_sha256=row.iq_sha256, acquisition=row.acquisition,
                           target=source.targets[row.target_id], samples=samples,
                           sample_rate_hz=source.reader.manifest.sample_rate_hz)


def buffered_rows(source, chunk, rows, library, cutoff, stats):
    payload = verified_payload(source.reader, chunk, rows, library, stats)
    for row in rows:
        raw = None
        if row.acquisition["global_visit"] < cutoff:
            offset = row.payload_offset_bytes
            raw = payload[offset:offset + row.payload_bytes]
        yield row, raw


def drained_windows(source, plan, library, stats, *, streamed=False):
    for chunk in scope_chunks(source):
        rows = plan.indexes[(source.manifest_digest, chunk.first_sequence)]
        start = max(source.start_sequence, chunk.first_sequence)
        stop = min(source.stop_sequence, chunk.first_sequence + chunk.window_count)
        local = [r for r in rows if start <= r.sequence < stop]
        if (local[-1].acquisition["global_visit"] < plan.cutoff
                or (not streamed and chunk.uncompressed_bytes > MAX_BUFFER_BYTES)):
            # Preserve the released paired-hash reader for wholly paid or
            # oversized members, with its original complete-member checks.
            with closing(source.reader.windows(start_sequence=start, stop_sequence=stop)) as original:
                for item in original:
                    stats["original_array_rows"] += 1
                    yield window(source, item.index, item.samples)
            continue
        verified = (verified_stream(source.reader, chunk, rows, library, plan.cutoff, stats) if streamed
                    else buffered_rows(source, chunk, rows, library, plan.cutoff, stats))
        with closing(verified):
            for row, raw in verified:
                if not start <= row.sequence < stop:
                    continue
                shape = (row.sample_count, row.receiver_count, 2)
                if raw is not None:
                    samples = np.frombuffer(raw, dtype="<i2").reshape(shape)
                    stats["bulk_array_rows"] += 1
                else:
                    samples = SimpleNamespace(shape=shape)
                    stats["metadata_only_rows"] += 1
                yield window(source, row, samples)
