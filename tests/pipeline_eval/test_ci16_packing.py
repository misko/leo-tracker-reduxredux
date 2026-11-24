from hashlib import sha256
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import seekable_member as seek
from reports.ALGO08.v3.ci16_packing import Packing, SOURCE
from reports.ALGO08.v3.future_capture_storage import capture, full_recovery


@pytest.fixture(scope="module", params=["", pytest.param("-mssse3", marks=pytest.mark.hardware)])
def codec(request, tmp_path_factory):
    binary = tmp_path_factory.mktemp("packing") / "packing.so"
    isa = [request.param] if request.param else []
    subprocess.run(["cc", "-std=c11", "-O3", "-shared", "-fPIC", "-Wall", "-Wextra",
                    "-Werror", *isa, str(SOURCE), "-o", str(binary)], check=True)
    return Packing(binary)


def ci16(values):
    return np.asarray(values, dtype="<i2").tobytes()


def test_signed_twelve_bit_wire_order(codec):
    raw = ci16([0, -1, -2048, 2047])
    encoded = codec.compress(raw)
    assert bytes(encoded) == b"\x0c\x00\x00\xf0\xff\x00\xf8\x7f"
    assert codec.decode(encoded, len(raw)) == raw


def test_every_signed_width_shift_and_unaligned_vector_tail(codec):
    for bits in range(1, 17):
        for shift in range(17 - bits):
            unit = 1 << shift
            bound = 1 << (bits - 1)
            words = [x * unit for x in ([-bound, bound - 1, 0, -1] * 5)[:-1]]
            raw = ci16(words)
            encoded = codec.compress(raw)
            assert (encoded[0], encoded[1]) == (bits, shift)
            assert len(encoded) == 2 + (len(words) * bits + 7) // 8
            assert codec.decode(encoded, len(raw)) == raw


def test_vector_wire_matches_independent_bit_reservoir_with_unaligned_input(codec):
    words = [-2048, 2047, *np.random.default_rng(29).integers(-2048, 2048, size=41).tolist()]
    raw = ci16([value * 16 for value in words])
    unaligned = memoryview(bytearray(b"_" + raw))[1:]
    bits = sum((word & 4095) << (12*i) for i,word in enumerate(words))
    expected = b"\x0c\x04" + bits.to_bytes((12 * len(words) + 7) // 8, "little")
    assert bytes(codec.compress(unaligned)) == expected
    assert codec.decode(expected, len(raw)) == raw


def test_full_width_and_zeros_and_short_raw_fallback(codec):
    raw = ci16([-32768, 32767, 31, -15, 0])
    encoded = codec.compress(raw)
    assert bytes(encoded) == b"\x10\x00" + raw
    assert codec.decode(encoded, len(raw)) == raw
    raw = ci16([0]*19)
    zero = codec.compress(raw)
    assert bytes(zero) == b"\x01\x00\x00\x00\x00"
    assert codec.decode(zero, len(raw)) == raw
    assert bytes(codec.compress(ci16([2047]))) == b"\x10\x00\xff\x07"


def test_malformed_metadata_and_padding_rejected(codec):
    raw = ci16([-2048, 2047, 7])
    valid = bytes(codec.compress(raw))
    for invalid in (valid[:-1], valid + b"\x00", bytes([0, 0]) + valid[2:],
                    bytes([12, 5]) + valid[2:], valid[:-1] + bytes([valid[-1] | 0x80])):
        with pytest.raises(ValueError):
            codec.decode(invalid, len(raw))
    with pytest.raises(ValueError, match="whole-word"):
        codec.compress(b"\x01")


def test_split_capture_recovery_and_unused_tail_corruption(codec, tmp_path):
    template = SimpleNamespace(configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
                               radio={}, receiver_ids=(0, 1))
    samples = np.resize(np.asarray([-2048, 2047, 99, -47], dtype="<i2"), (seek.SAMPLES, 2, 2))
    index = SimpleNamespace(sequence=0, target_id="target", acquisition={"visit": 0}, powers=({}, {}))
    directory, pin, output = capture(tmp_path, "packed-ci16", template,
                                     (SimpleNamespace(samples=samples, index=index),), codec=codec)
    expected = "sha256:" + sha256(memoryview(samples).cast("B")).hexdigest()
    assert output["decoded_sha256"] == expected
    assert full_recovery(directory, "packed-ci16", pin, expected, codec=codec)["decoded"] == expected
    with seek.open_member(directory, pin, codec=codec) as member:
        member.verify_encoded()
        assert member.verified_encoded_frames == 2
        assert member.read(0, full=False) == samples[:seek.PREFIX_SAMPLES].tobytes()
    with pytest.raises(ValueError, match="Unknown"), seek.open_member(directory, pin):
        pytest.fail("packed payload opened under Zstandard schema")
    tail = directory / codec.part_files[1]
    damaged = bytearray(tail.read_bytes())
    damaged[-1] ^= 128
    tail.chmod(0o600)
    tail.write_bytes(damaged)
    with seek.open_member(directory, pin, codec=codec) as member, pytest.raises(ValueError, match="digest"):
        member.verify_encoded()
