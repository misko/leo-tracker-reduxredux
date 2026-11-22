import json
from contextlib import nullcontext

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.variants.experimental.receiver_decoded_ingress import (
    DirectDecode,
    WindowBuffers,
    decoded_window_buffers,
    direct_decoded_chunk,
)


def test_one_shot_returns_read_only_slices_and_defers_large_or_inexact_output():
    raw = bytes(range(250)) * 200
    for write_size in (False, True):
        compressed = zstd.ZstdCompressor(write_content_size=write_size).compress(raw)
        decoder = DirectDecode(zstd, len(raw))
        assert decoder.decode(compressed) == raw
        with decoder.stream_reader(compressed) as stream:
            prefix = stream.read(80)
            suffix = stream.read(len(raw) - 80)
            assert prefix.readonly and suffix.readonly
            assert prefix.obj is suffix.obj
            assert bytes(prefix) + bytes(suffix) == raw
            assert not stream.read(1)
        for size in (0, len(raw) - 1, len(raw) + 1, 128 * 1024**2 + 1):
            assert DirectDecode(zstd, size).decode(compressed) is None
            with DirectDecode(zstd, size).stream_reader(compressed) as stream:
                assert stream.read(len(raw)) == raw


def read_events(path, chunk_size, arm):
    windows = []
    try:
        with arm(chunk_size):
            for window in ShortWindowReader(path).windows(start_sequence=1, stop_sequence=2):
                assert not window.samples.flags.writeable
                windows.append((window.index, window.samples.tobytes()))
    except BundleCorruptionError as error:
        return windows, str(error), type(error.__cause__)
    return windows, None, None


def test_window_buffer_reuses_only_storage_that_numpy_no_longer_holds():
    width = 64
    raw = b"".join(bytes([i]) * width for i in range(5))
    compressed = zstd.ZstdCompressor(write_content_size=False).compress(raw)
    with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
        split = WindowBuffers(stream)
        first = np.frombuffer(split.read(width), dtype="u1").reshape(8, 8)
        second = np.frombuffer(split.read(width), dtype="u1")
        third = np.frombuffer(split.read(width), dtype="u1")
        address = first.ctypes.data
        fourth = split.read(width)
        assert fourth == bytes([3]) * width and isinstance(fourth, bytes)
        assert not first.any() and np.all(second == 1) and np.all(third == 2)
        del first
        fifth = np.frombuffer(split.read(width), dtype="u1")
        assert fifth.ctypes.data == address and np.all(fifth == 4)
        assert not fifth.flags.writeable and np.all(second == 1) and np.all(third == 2)


@pytest.mark.parametrize("damage", [
    None, "compressed_member", "oversized_member", "index_member", "index_digest", "index_geometry",
    "skipped_window_hash", "decoded_chunk_hash", "declared_decoded_size", "compressed_frame",
    "truncated_block", "truncated_checksum", "extra_decoded_bytes", "trailing_compressed_junk",
    "trailing_frame", "trailing_empty_frame",
])
def test_one_shot_preserves_the_released_reader_sequence_and_validation(tmp_path, damage):
    writer = ShortWindowWriter(tmp_path, "sealed", configuration={"window_ms": 20},
                               radio={"id": "synthetic"}, receiver_ids=(0, 1), chunk_windows=4)
    for sequence in range(5):
        n = 0 if sequence == 2 else 2000
        samples = np.random.default_rng(sequence).integers(-128, 129, (n, 2, 2), dtype="<i2")
        writer.append(sequence=sequence, target_id="t1", samples=samples,
                      acquisition={"sample_start": 2500 * sequence}, powers=({}, {}))
    path = writer.finish(stop_reason="max_visits")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][0]
    payload_path = path / chunk["payload_relative_path"]
    index_path = path / chunk["index_relative_path"]
    payload = payload_path.read_bytes()
    encode = zstd.ZstdCompressor(write_content_size=False, write_checksum=True).compress

    if damage == "compressed_member":
        payload_path.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    elif damage == "oversized_member":
        payload_path.write_bytes(payload + b"x")
    elif damage == "index_member":
        index_path.write_bytes(index_path.read_bytes() + b"x")
    elif damage == "index_digest":
        index_path.write_bytes(index_path.read_bytes().replace(b'"t1"', b'"t2"'))
    elif damage in ("skipped_window_hash", "index_geometry"):
        rows = [json.loads(row) for row in index_path.read_bytes().splitlines()]
        if damage == "skipped_window_hash":
            rows[3]["iq_sha256"] = "sha256:" + "0" * 64
        else:
            rows[3]["payload_offset_bytes"] += 1
        index = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index_path.write_bytes(index)
        chunk["index_bytes"], chunk["index_sha256"] = len(index), sha256_digest(index)
    elif damage == "decoded_chunk_hash":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    elif damage == "declared_decoded_size":
        chunk["uncompressed_bytes"] += 1
    elif damage is not None:
        if damage == "compressed_frame":
            payload = b"invalid zstd"
        elif damage == "truncated_block":
            payload = payload[:len(payload) // 2]
        elif damage == "truncated_checksum":
            payload = payload[:-1]
        elif damage == "extra_decoded_bytes":
            decoded = zstd.ZstdDecompressor().decompress(
                payload, max_output_size=chunk["uncompressed_bytes"],
            )
            payload = encode(decoded + b"extra")
        elif damage == "trailing_compressed_junk":
            payload += b"invalid zstd"
        elif damage == "trailing_frame":
            payload += encode(b"extra")
        elif damage == "trailing_empty_frame":
            payload += encode(b"")
        payload_path.write_bytes(payload)
        chunk["compressed_bytes"], chunk["compressed_sha256"] = len(payload), sha256_digest(payload)
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    size = chunk["uncompressed_bytes"]
    expected = read_events(path, size, nullcontext)
    assert read_events(path, size, direct_decoded_chunk) == expected
    assert read_events(path, size, lambda _: decoded_window_buffers()) == expected
    if damage in (None, "skipped_window_hash", "decoded_chunk_hash"):
        assert [window.sequence for window, _ in expected[0]] == [1]
