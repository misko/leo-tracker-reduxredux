"""Independent C/Python wire parity; no radio, archive, PostgreSQL, or daemon."""

import ctypes as ct
import random
import struct
import subprocess
from pathlib import Path

import pytest

from leo.contracts.scanner_glrt_frame import (
    DRAIN,
    FINAL,
    HEADER_BYTES,
    ScannerGlrtClassificationV1,
    ScannerGlrtFrameV1,
    decode_frame,
    encode_frame,
    extract_legacy_metadata,
)

ROOT = Path(__file__).resolve().parents[2]


class Record(ct.Structure):
    _fields_ = (
        [
            (k, ct.c_uint64)
            for k in (
                "sequence",
                "visit",
                "valid_start",
                "valid_end",
                "search_start",
                "search_end",
                "confirmation_start",
                "confirmation_end",
            )
        ]
        + [("rate_hz", ct.c_uint32)]
        + [(k, ct.c_uint8) for k in ("channel", "edge", "rx", "verdict")]
        + [(k, ct.c_uint32) for k in ("reason", "search_window_mask")]
        + [(k, ct.c_double) for k in ("exact_score", "control_score", "margin", "cfo_hz")]
        + [("epoch_sample_counter", ct.c_uint64)]
        + [(k, ct.c_double) for k in ("fractional_offset_samples", "cpu_ms", "wall_ms")]
    )


class Frame(ct.Structure):
    _fields_ = (
        [
            (k, ct.c_uint64)
            for k in (
                "session",
                "generation",
                "frame_sequence",
                "result_sequence_limit",
                "dropped_results",
            )
        ]
        + [(k, ct.c_uint8 * 32) for k in ("algorithm_sha256", "configuration_sha256")]
        + [(k, ct.c_uint32) for k in ("flags", "legacy_bytes", "result_count")]
        + [("legacy_metadata", ct.c_void_p), ("results", Record * 4)]
    )


@pytest.fixture(scope="module")
def codec(tmp_path_factory):
    output = tmp_path_factory.mktemp("glrt-codec") / "codec.so"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(ROOT / "src/leo/scanner/native_presence/frame_codec.c"),
            "-lm",
            "-o",
            str(output),
        ],
        check=True,
    )
    lib = ct.CDLL(str(output))
    lib.leo_glrt_frame_encode.argtypes = [
        ct.POINTER(Frame),
        ct.c_void_p,
        ct.c_size_t,
        ct.POINTER(ct.c_size_t),
    ]
    lib.leo_glrt_frame_decode.argtypes = [ct.POINTER(Frame), ct.c_void_p, ct.c_size_t]
    lib.leo_glrt_frame_legacy_view.argtypes = [
        ct.c_void_p,
        ct.c_size_t,
        ct.POINTER(ct.c_void_p),
        ct.POINTER(ct.c_size_t),
    ]
    return lib


def packet(count=1, rate=5000000, flags=0):
    start = 10**16 + 37
    record = ScannerGlrtClassificationV1(
        sequence=0,
        visit=7,
        valid_start=start,
        valid_end=start + rate * 120 // 1000,
        search_start=start,
        search_end=start + rate // 50,
        confirmation_start=start,
        confirmation_end=start + rate // 50,
        rate_hz=rate,
        channel=3,
        edge="lower",
        rx=1,
        verdict="starlink",
        reason="complete",
        search_window_mask=1,
        exact_score=0.25,
        control_score=0.125,
        margin=0.125,
        cfo_hz=123456.25,
        epoch_sample_counter=start + 43,
        fractional_offset_samples=-0.375,
        cpu_ms=80.125,
        wall_ms=95.25,
    )
    return encode_frame(
        ScannerGlrtFrameV1(
            session=10**16 + 11,
            generation=1,
            frame_sequence=23,
            result_sequence_limit=count,
            dropped_results=0,
            algorithm_sha256="12" * 32,
            configuration_sha256="34" * 32,
            flags=flags,
            legacy_metadata=b"" if flags & DRAIN else b"\x00\xffopaqueABI3+HOPS\x80",
            results=tuple(
                record.model_copy(update={"sequence": i, "visit": 7 + i}) for i in range(count)
            ),
        )
    )


@pytest.mark.parametrize("rate", [2500000, 5000000, 25000000, 60000000])
@pytest.mark.parametrize("count", [0, 1, 4])
@pytest.mark.parametrize("flags", [0, DRAIN, DRAIN | FINAL])
def test_c_python_roundtrip_is_byte_exact(codec, rate, count, flags):
    raw = packet(count, rate, flags)
    frame = Frame()
    assert codec.leo_glrt_frame_decode(ct.byref(frame), raw, len(raw)) == 0
    output = ct.create_string_buffer(len(raw))
    written = ct.c_size_t()
    assert codec.leo_glrt_frame_encode(ct.byref(frame), output, len(raw), ct.byref(written)) == 0
    assert output.raw == raw and written.value == len(raw)
    assert encode_frame(decode_frame(output.raw)) == raw
    if count:
        assert frame.results[0].epoch_sample_counter == 10**16 + 80
        assert frame.results[0].fractional_offset_samples == -0.375


def test_c_rejects_partial_negative_and_leaves_outputs_untouched(codec):
    raw = packet()
    frame = Frame()
    assert codec.leo_glrt_frame_decode(ct.byref(frame), raw, len(raw)) == 0
    frame.results[0].verdict = 2
    output = ct.create_string_buffer(b"x" * len(raw), len(raw))
    written = ct.c_size_t(17)
    assert codec.leo_glrt_frame_encode(ct.byref(frame), output, len(raw), ct.byref(written)) == -1
    assert output.raw == b"x" * len(raw) and written.value == 17


def test_malformed_packets_agree_across_languages(codec):
    raw = packet()
    rng = random.Random(208)
    cases = [raw[:n] for n in range(len(raw))]
    for _ in range(1000):
        changed = bytearray(raw)
        changed[rng.randrange(len(raw))] ^= rng.randrange(1, 256)
        cases.append(bytes(changed))
    cases.extend((raw + b"x", bytes(65537)))
    for changed in cases:
        output = Frame()
        ct.memset(ct.byref(output), 0xAA, ct.sizeof(output))
        before = bytes(output)
        try:
            decoded = decode_frame(changed)
        except ValueError:
            assert codec.leo_glrt_frame_decode(ct.byref(output), changed, len(changed)) == -1
            assert bytes(output) == before
        else:
            assert codec.leo_glrt_frame_decode(ct.byref(output), changed, len(changed)) == 0
            encoded = ct.create_string_buffer(len(changed))
            written = ct.c_size_t()
            assert (
                codec.leo_glrt_frame_encode(
                    ct.byref(output), encoded, len(changed), ct.byref(written)
                )
                == 0
            )
            assert encoded.raw == encode_frame(decoded)


def test_bad_classification_does_not_hide_legacy_recording_metadata(codec):
    raw = bytearray(packet())
    legacy = extract_legacy_metadata(bytes(raw))
    struct.pack_into("<d", raw, HEADER_BYTES + len(legacy) + 96, float("nan"))
    raw = bytes(raw)
    pointer, size = ct.c_void_p(), ct.c_size_t()
    assert codec.leo_glrt_frame_legacy_view(raw, len(raw), ct.byref(pointer), ct.byref(size)) == 0
    assert ct.string_at(pointer, size.value) == legacy
    assert codec.leo_glrt_frame_decode(ct.byref(Frame()), raw, len(raw)) == -1
