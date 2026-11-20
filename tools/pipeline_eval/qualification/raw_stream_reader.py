"""Bounded authenticated decompression for an archive replay's short-window port."""

import hashlib
import os
import stat
from contextlib import contextmanager

import numpy as np
import zstandard as zstd

READ_BYTES = 128 * 1024


class CompressedInput:
    def __init__(self, descriptor, size):
        self.descriptor, self.remaining = descriptor, size
        self.digest = hashlib.sha256()
        self.bytes_read = 0
        self.largest_read = 0

    def read(self, size):
        block = os.read(self.descriptor, min(size, READ_BYTES, self.remaining))
        count = len(block)
        self.remaining -= count
        self.bytes_read += count
        self.largest_read = max(self.largest_read, count)
        self.digest.update(block)
        return block


def file_identity(info):
    return info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def compressed_input(path, size, digest):
    from leo.storage.errors import BundleCorruptionError

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != size:
            raise BundleCorruptionError("compressed IQ is outside its sealed file geometry")
        source = CompressedInput(descriptor, size)
        yield source
        if (
            source.remaining
            or "sha256:" + source.digest.hexdigest() != digest
            or file_identity(os.fstat(descriptor)) != file_identity(before)
        ):
            raise BundleCorruptionError("compressed IQ changed or did not reach its sealed end")
    finally:
        os.close(descriptor)


def streamed_windows(reader, stats, *, start_sequence=0, stop_sequence=None):
    from leo.contracts.digests import sha256_digest
    from leo.contracts.multirate_window_recording import ShortWindowIndexV2
    from leo.contracts.short_window_recording import ShortWindowIndexV1
    from leo.storage.errors import BundleCorruptionError
    from leo.storage.short_window import ShortWindowRead
    from leo.storage.uri import confined_path

    manifest = reader.manifest
    end = manifest.window_count if stop_sequence is None else stop_sequence
    if (
        type(start_sequence) is not int
        or type(end) is not int
        or not 0 <= start_sequence <= end <= manifest.window_count
    ):
        raise ValueError("window range must be inside the sealed inventory")
    if start_sequence == end:
        return
    index_type = ShortWindowIndexV2 if manifest.schema_version == 2 else ShortWindowIndexV1
    stats["manifest_bytes"] += (reader.path / "manifest.json").stat().st_size
    for chunk in manifest.chunks:
        if (
            chunk.first_sequence + chunk.window_count <= start_sequence
            or chunk.first_sequence >= end
        ):
            continue
        index = reader._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
        try:
            rows = [index_type.model_validate_json(line) for line in index.splitlines()]
        except ValueError as error:
            raise BundleCorruptionError("invalid short-window index") from error
        if len(rows) != chunk.window_count:
            raise BundleCorruptionError("window index count differs from manifest")
        path = confined_path(
            reader.path, reader.path / chunk.payload_relative_path, must_exist=True
        )
        raw_hash = hashlib.sha256()
        offset = 0
        try:
            with (
                compressed_input(path, chunk.compressed_bytes, chunk.compressed_sha256) as source,
                zstd.ZstdDecompressor().stream_reader(source, read_size=READ_BYTES) as stream,
            ):
                for number, row in enumerate(rows):
                    if (
                        row.sequence != chunk.first_sequence + number
                        or row.payload_offset_bytes != offset
                        or row.receiver_count != len(manifest.receiver_ids)
                        or row.sample_count > manifest.sample_rate_hz // 50
                    ):
                        raise BundleCorruptionError("window index geometry is not consecutive")
                    raw = stream.read(row.payload_bytes)
                    if len(raw) != row.payload_bytes or sha256_digest(raw) != row.iq_sha256:
                        raise BundleCorruptionError("window IQ length or digest changed")
                    raw_hash.update(raw)
                    offset += len(raw)
                    if start_sequence <= row.sequence < end:
                        yield ShortWindowRead(
                            row,
                            np.frombuffer(raw, dtype="<i2").reshape(
                                row.sample_count, row.receiver_count, 2
                            ),
                        )
                if stream.read(1):
                    raise BundleCorruptionError("unexpected trailing IQ bytes")
        except zstd.ZstdError as error:
            raise BundleCorruptionError("invalid short-window compressed IQ") from error
        if (
            offset != chunk.uncompressed_bytes
            or "sha256:" + raw_hash.hexdigest() != chunk.uncompressed_sha256
        ):
            raise BundleCorruptionError("short-window chunk geometry or digest changed")
        stats["chunks"] += 1
        stats["compressed_bytes"] += source.bytes_read
        stats["largest_compressed_member_bytes"] = max(
            stats["largest_compressed_member_bytes"], source.bytes_read
        )
        stats["largest_read_bytes"] = max(stats["largest_read_bytes"], source.largest_read)
        stats["index_bytes"] += len(index)
        stats["decoded_bytes"] += offset
        stats["decoded_visits"] += len(rows)
