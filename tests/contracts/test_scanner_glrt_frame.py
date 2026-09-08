import json
import struct

import pytest

from leo.contracts.scanner_glrt_frame import (
    DRAIN,
    FINAL,
    HEADER_BYTES,
    MAX_METADATA_BYTES,
    RECORD_BYTES,
    ScannerGlrtClassificationV1,
    ScannerGlrtFrameV1,
    decode_frame,
    encode_frame,
    extract_legacy_metadata,
)


def classification(rate=5000000, **updates):
    start = 10**16 + 37
    return ScannerGlrtClassificationV1.model_validate(
        {
            "sequence": 0,
            "visit": 83,
            "valid_start": start,
            "valid_end": start + rate * 120 // 1000,
            "search_start": start,
            "search_end": start + rate // 50,
            "confirmation_start": start,
            "confirmation_end": start + rate // 50,
            "rate_hz": rate,
            "channel": 4,
            "edge": "upper",
            "rx": 1,
            "verdict": "starlink",
            "reason": "complete",
            "search_window_mask": 1,
            "exact_score": 0.25,
            "control_score": 0.0625,
            "margin": 0.1875,
            "cfo_hz": -123456.125,
            "epoch_sample_counter": start + 47,
            "fractional_offset_samples": -0.375,
            "cpu_ms": 87.25,
            "wall_ms": 96.75,
            **updates,
        }
    )


def frame(result=None, **updates):
    return ScannerGlrtFrameV1.model_validate(
        {
            "session": 10**16 + 9,
            "generation": 2,
            "frame_sequence": 19,
            "result_sequence_limit": 1,
            "dropped_results": 0,
            "algorithm_sha256": "12" * 32,
            "configuration_sha256": "34" * 32,
            "legacy_metadata": b"\x00\xffABI3+HOPS\x80",
            "results": (result or classification(),),
            **updates,
        }
    )


@pytest.mark.parametrize("rate", [2500000, 5000000, 25000000, 60000000])
def test_wire_and_json_roundtrip_preserve_counter_and_fraction_separately(rate):
    original = frame(classification(rate))
    raw = encode_frame(original)
    assert len(raw) == HEADER_BYTES + len(original.legacy_metadata) + RECORD_BYTES
    assert raw[:8] == b"LGC1\x01\x00\x80\x00"
    assert struct.unpack_from("<Q", raw, 24)[0] == original.session
    assert extract_legacy_metadata(raw) == original.legacy_metadata
    assert decode_frame(raw) == original
    serialized = original.model_dump_json()
    data = json.loads(serialized)
    assert data["session"] == str(10**16 + 9)
    assert data["results"][0]["valid_start"] == str(10**16 + 37)
    assert data["legacy_metadata"] == original.legacy_metadata.hex()
    assert ScannerGlrtFrameV1.model_validate_json(serialized) == original


def test_partial_search_cannot_be_a_negative_dwell_classification():
    with pytest.raises(ValueError, match="partial temporal"):
        classification(verdict="no_signal")
    negative = classification(
        verdict="no_signal", search_window_mask=63, search_end=10**16 + 37 + 600000
    )
    assert decode_frame(encode_frame(frame(negative))).results[0].verdict == "no_signal"
    unknown = classification(verdict="unavailable", reason="incomplete_search")
    assert unknown.verdict == "unavailable"


@pytest.mark.parametrize(
    "updates",
    [
        {"search_window_mask": 63},
        {"search_start": 10**16 + 38},
        {"verdict": "unavailable"},
        {"reason": "worker_failed"},
        {"margin": 0.3},
        {"cfo_hz": float("nan")},
        {"cpu_ms": -1},
        {"fractional_offset_samples": 2.1},
        {"epoch_sample_counter": 0},
        {"rx": True},
        {"valid_start": float(10**16 + 37)},
        {"valid_start": "010000000000000037"},
    ],
)
def test_invalid_classification_is_rejected(updates):
    with pytest.raises(ValueError):
        classification(**updates)


@pytest.mark.parametrize("flags", [DRAIN, DRAIN | FINAL])
def test_metadata_only_drain_and_final_frames(flags):
    message = frame(flags=flags, legacy_metadata=b"")
    assert decode_frame(encode_frame(message)) == message
    with pytest.raises(ValueError):
        frame(flags=FINAL)


def test_legacy_metadata_can_be_recovered_when_only_classification_is_bad():
    original = frame()
    raw = bytearray(encode_frame(original))
    struct.pack_into("<d", raw, HEADER_BYTES + len(original.legacy_metadata) + 96, float("nan"))
    assert extract_legacy_metadata(bytes(raw)) == original.legacy_metadata
    with pytest.raises(ValueError):
        decode_frame(bytes(raw))


def test_bounds_order_and_fail_closed_versioning():
    original = frame()
    raw = encode_frame(original)
    for bad in (
        b"HOPS" + raw[4:],
        raw[:4] + b"\x02" + raw[5:],
        raw[:-1],
        raw + b"x",
        bytes(MAX_METADATA_BYTES + 1),
    ):
        with pytest.raises(ValueError):
            decode_frame(bad)
        with pytest.raises(ValueError):
            extract_legacy_metadata(bad)
    for updates in (
        {"results": (classification(),) * 5},
        {"results": (classification(),) * 2},
        {"result_sequence_limit": 0},
        {"dropped_results": 2},
        {"legacy_metadata": bytes(MAX_METADATA_BYTES)},
        {"algorithm_sha256": "0" * 64},
        {"generation": 0},
        {"flags": 8},
    ):
        with pytest.raises(ValueError):
            frame(**updates)
    # model_copy bypasses model validators; encoding must revalidate anyway.
    with pytest.raises(ValueError):
        encode_frame(original.model_copy(update={"flags": 8}))
