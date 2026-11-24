from dataclasses import replace
import subprocess

import numpy as np
import pytest
import zstandard as zstd

from reports.ALGO08.v3.ci16_planes_trial import SOURCE, Planes, decode, encode


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    path = tmp_path_factory.mktemp("ci16-planes") / "planes.so"
    subprocess.run(["cc", "-std=c11", "-O3", "-shared", "-fPIC", SOURCE, "-o", path], check=True)
    return path


@pytest.mark.parametrize("kind", ["lz4", "zstd"])
def test_roundtrip_signed_words_and_unaligned_input(native, kind):
    codec = Planes(native, kind)
    bins = np.arange(65_536, dtype="<u2").view("<i2")
    frame = np.stack((bins, bins ^ 23, -bins, bins[::-1]), axis=-1).astype("<i2").tobytes()
    for samples in (1, 3, 19, 65_536):
        expected = frame[:8 * samples]
        raw = memoryview(b"p" + expected)[1:]
        encoded = codec.compress(raw)
        assert bytes(encoded[:len(raw) // 2]) == expected[::2]
        assert bytes(codec.decode(encoded, len(raw))) == expected
        with pytest.raises((ValueError, zstd.ZstdError)):
            codec.decode(encoded[:-1], len(raw))
        with pytest.raises(ValueError, match="integral"):
            codec.compress(raw[:-1])


@pytest.mark.parametrize("kind", ["lz4", "zstd"])
def test_ready_authenticates_unused_tail_and_full_verification_rechecks_original(native, kind):
    codec = Planes(native, kind)
    rows = (bytes(range(256)), bytes(range(255, -1, -1)))
    identity = {"index": "signed-original", "chunk": 0}
    capture, pin, _ = encode(kind, codec, rows, identity, prefix=96)
    verified = decode(kind, codec, capture, pin, rows, identity, prefix=96)
    assert verified["decoded_bytes"] == 512
    assert verified["complete_windows"] == 2
    ready = decode(kind, codec, capture, pin, rows, identity, requests=(1, 2), prefix=96)
    assert ready["decoded_bytes"] == 352
    assert ready["complete_windows"] == 1
    assert ready["authenticated_encoded_bytes"] == verified["authenticated_encoded_bytes"]

    damaged = bytearray(capture.encoded[1])
    damaged[-1] ^= 1
    altered = replace(capture, encoded=(capture.encoded[0], damaged, *capture.encoded[2:]))
    with pytest.raises(ValueError, match="Changed encoded part"):
        decode(kind, codec, altered, pin, rows, identity, requests=(1, 2), prefix=96)
    with pytest.raises(ValueError, match="Changed aperture table"):
        decode(kind, codec, replace(capture, table=capture.table + b" "), pin, rows, identity, prefix=96)
    with pytest.raises(ValueError, match="Original CI16 bytes differ"):
        decode(kind, codec, capture, pin, (rows[0][::-1], rows[1]), identity, prefix=96)
