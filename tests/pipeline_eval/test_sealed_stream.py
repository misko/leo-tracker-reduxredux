from hashlib import sha256
import json
import os

import numpy as np
import pytest
import zstandard

from reports.ALGO08.v3.sealed_stream import Native, PAYLOAD, build, sealed_windows
from reports.ALGO08.v3.sealed_stream_descriptor import bounded_digest


def digest(value):
    return "sha256:" + sha256(value).hexdigest()


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    root = tmp_path_factory.mktemp("stream") / "build"
    build(root)
    return Native(root / "sealed-stream.so")


@pytest.fixture
def member(tmp_path):
    rng = np.random.default_rng(12041)
    windows = [rng.integers(0, 256, size=n, dtype=np.uint8).tobytes() for n in (160_000, 120_000, 200_000)]
    body = b"".join(windows)
    frame = zstandard.ZstdCompressor(write_checksum=True, write_content_size=False).compress(body)
    file = tmp_path / "stock.iq.zst"
    file.write_bytes(frame)
    chunk = dict(uncompressed_bytes=len(body), uncompressed_sha256=digest(body), compressed_bytes=len(frame),
                 compressed_sha256=digest(frame), window_count=len(windows))
    rows = [(len(window), sha256(window).digest()) for window in windows]
    return file, chunk, rows, body


def test_stable_output_seals_all_windows_and_retains_immutable_storage(native, member):
    file, chunk, rows, body = member
    code, slab = native.prepare(file, chunk, rows)
    assert code == 0 and slab.data.readonly and slab.data == body
    assert slab.windows == tuple(rows) and slab.digest == digest(body)[7:]
    assert slab.counters["reads"] > 1 and slab.counters["windows"] == len(rows)
    assert slab.counters["decoded_bytes"] == chunk["uncompressed_bytes"]
    with pytest.raises(TypeError):
        slab.data[0] = 0


@pytest.mark.parametrize(("field", "status"), (("compressed", 5), ("window", 6), ("uncompressed", 7)))
def test_each_signed_hash_authenticates_independently(native, member, field, status):
    file, chunk, rows, _ = member
    wrong_pin = sha256(b"unrelated").digest()
    if field == "window":
        rows[-1] = rows[-1][0], wrong_pin
    else:
        chunk[field + "_sha256"] = "sha256:" + wrong_pin.hex()
    assert native.prepare(file, chunk, rows) == (status, None)


def test_wrong_checksum_and_descriptor_fail_and_skippable_falls_back(native, member):
    file, chunk, rows, _ = member
    frame = bytearray(file.read_bytes())
    frame[-1] ^= 1
    file.write_bytes(frame)
    assert native.prepare(file, dict(chunk, compressed_sha256=digest(frame)), rows) == (3, None)
    assert native.prepare(file, dict(chunk, compressed_bytes=len(frame)+1), rows) == (2, None)
    skippable = b"\x50\x2a\x4d\x18\x01\x00\x00\x00v"
    file.write_bytes(skippable + frame)
    assert native.prepare(file, dict(chunk, compressed_bytes=len(skippable)+len(frame),
                                    compressed_sha256=digest(skippable+frame)), rows) == (1, None)


def test_bounded_descriptor_hash_checks_extent_and_last_partial_block(tmp_path):
    payload = b"0123456789"
    file = tmp_path / "input"
    file.write_bytes(payload)
    with file.open("rb") as stream:
        buffer = memoryview(bytearray(4))
        assert bounded_digest(stream.fileno(), len(payload), buffer) == digest(payload)[7:]
        os.lseek(stream.fileno(), 0, os.SEEK_SET)
        with pytest.raises(ValueError, match="exceeds"):
            bounded_digest(stream.fileno(), len(payload)-1, buffer)
        os.lseek(stream.fileno(), 0, os.SEEK_SET)
        with pytest.raises(ValueError, match="early"):
            bounded_digest(stream.fileno(), len(payload)+1, buffer)


@pytest.mark.parametrize("behavior", ("slab", "fallback", "reject"))
def test_original_window_reader_accepts_fallback_and_exposes_no_failed_window(native, tmp_path, behavior):
    from leo.contracts.digests import canonical_json_bytes
    from leo.storage.errors import BundleCorruptionError
    from leo.storage.short_window import ShortWindowReader, ShortWindowWriter

    writer = ShortWindowWriter(tmp_path, "scope", configuration={"window_ms": 20},
                               radio={"id": "synthetic"}, receiver_ids=(0, 1), chunk_windows=2)
    windows = [np.arange(4*100, dtype="<i2").reshape(100, 2, 2)+i for i in range(2)]
    for i, samples in enumerate(windows):
        writer.append(sequence=i, target_id="t", samples=samples, acquisition={}, powers=({}, {}))
    root = writer.finish(stop_reason="max_visits")
    path = root / "manifest.json"
    manifest = json.loads(path.read_bytes())
    chunk = manifest["chunks"][0]
    payload = zstandard.ZstdCompressor(write_checksum=behavior != "fallback").compress(
        b"".join(window.tobytes() for window in windows))
    (root / chunk["payload_relative_path"]).write_bytes(payload)
    chunk.update(compressed_bytes=len(payload), compressed_sha256=digest(payload))
    if behavior == "reject":
        chunk["uncompressed_sha256"] = digest(b"incorrect full decoded digest")
    path.write_bytes(canonical_json_bytes(manifest))
    stats = {}
    with sealed_windows(native, PAYLOAD / "paired-sha256.so", root, chunk, stats):
        reader = ShortWindowReader(root).windows()
        if behavior == "reject":
            with pytest.raises(BundleCorruptionError, match="decoded member"):
                next(reader)
        else:
            observed = [item.samples for item in reader]
            assert all(not samples.flags.writeable for samples in observed)
            assert all(np.array_equal(a, b) for a, b in zip(observed, windows, strict=True))
            assert stats.get("fallback") == (1 if behavior == "fallback" else None)
