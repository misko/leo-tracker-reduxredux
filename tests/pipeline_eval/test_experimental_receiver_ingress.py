import json
import os

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.variants.experimental.receiver_ingress import (
    DecodeOnce,
    compressed_input_buffer,
    read_regular,
)


def test_read_into_one_buffer_preserves_sealed_file_checks(tmp_path):
    path = tmp_path / "chunk"
    payload = b"\x01\x02\x03\x04" * 300_000
    path.write_bytes(payload)
    assert read_regular(path, len(payload)) == payload
    with pytest.raises(BundleCorruptionError, match="bound"):
        read_regular(path, len(payload) - 1)
    os.link(path, tmp_path / "hardlink")
    with pytest.raises(BundleCorruptionError, match="one regular file"):
        read_regular(path, len(payload))


def test_chunk_slices_preserve_byte_order_and_detect_length_mismatch():
    raw = bytes(range(250)) * 200
    compressed = zstd.ZstdCompressor().compress(raw)
    with DecodeOnce(zstd.ZstdDecompressor(), len(raw)).stream_reader(compressed) as stream:
        a, b, c = stream.read(39), stream.read(len(raw) - 39), stream.read(1)
        assert a.readonly and b.readonly
        assert bytes(a) + bytes(b) == raw
        assert len(c) == 0
    with pytest.raises(BundleCorruptionError, match="trailing"):
        with DecodeOnce(zstd.ZstdDecompressor(), len(raw) - 1).stream_reader(compressed):
            pytest.fail("unexpected decoded size was accepted")
    with pytest.raises(BundleCorruptionError, match="ended"):
        with DecodeOnce(zstd.ZstdDecompressor(), len(raw) + 1).stream_reader(compressed):
            pytest.fail("truncated decoded size was accepted")


@pytest.mark.parametrize(("damage", "message"), [
    ("compressed", "member changed"),
    ("window", "IQ length or digest changed"),
    ("decoded", "chunk geometry or digest changed"),
])
def test_compressed_buffer_uses_original_sealed_reader(tmp_path, damage, message):
    writer = ShortWindowWriter(tmp_path, "test-raw", configuration={"window_ms": 20},
                               radio={"serial": "fake"}, receiver_ids=(0, 1), chunk_windows=2)
    samples = np.arange(1600, dtype="<i2").reshape(400, 2, 2)
    for sequence in range(3):
        writer.append(sequence=sequence, target_id="ch1", samples=samples + sequence,
                      acquisition={"sample_start": sequence * 400}, powers=({}, {}))
    path = writer.finish(stop_reason="max_visits")
    baseline = list(ShortWindowReader(path).windows())
    with compressed_input_buffer():
        observed = list(ShortWindowReader(path).windows())
    for a, b in zip(baseline, observed, strict=True):
        assert a.index == b.index
        np.testing.assert_array_equal(a.samples, b.samples)

    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][0]
    if damage == "compressed":
        payload_path = path / chunk["payload_relative_path"]
        payload = bytearray(payload_path.read_bytes())
        payload[-1] ^= 1
        payload_path.write_bytes(payload)
    elif damage == "window":
        index_path = path / chunk["index_relative_path"]
        rows = [json.loads(row) for row in index_path.read_bytes().splitlines()]
        rows[1]["iq_sha256"] = "sha256:" + "0" * 64
        index = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index_path.write_bytes(index)
        chunk["index_bytes"] = len(index)
        chunk["index_sha256"] = sha256_digest(index)
    else:
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with compressed_input_buffer(), pytest.raises(BundleCorruptionError, match=message):
        list(ShortWindowReader(path).windows())
