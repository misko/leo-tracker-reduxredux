from hashlib import sha256

import numpy as np
import pytest
import zstandard

from reports.ALGO08.v3.sealed_stream import Native, build


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
