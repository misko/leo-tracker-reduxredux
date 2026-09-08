import struct

import pytest

from leo.contracts.scanner_glrt_frame import (
    DETECTOR_FAILED,
    DRAIN,
    FINAL,
    HEADER_BYTES,
    ScannerGlrtClassificationV1,
    ScannerGlrtFrameV1,
    encode_frame,
)
from leo.radio.scanner_glrt_frames import GlrtVisitGeometry, ScannerGlrtFrameReader

START = 10**16 + 37
ALG, CONFIG = "12" * 32, "34" * 32


def geometry(visit):
    if visit not in (83, 84, 85):
        return None
    first = START + (visit - 83) * 630000
    return GlrtVisitGeometry(first, first + 600000, 5000000, 1, "lower", 1)


def result(sequence, verdict="starlink"):
    g = geometry(83 + sequence)
    return ScannerGlrtClassificationV1(
        sequence=sequence,
        visit=83 + sequence,
        valid_start=g.valid_start,
        valid_end=g.valid_end,
        search_start=g.valid_start,
        search_end=g.valid_end,
        confirmation_start=g.valid_start,
        confirmation_end=g.valid_start + 100000,
        rate_hz=g.rate_hz,
        channel=g.channel,
        edge=g.edge,
        rx=g.rx,
        verdict=verdict,
        reason="worker_busy" if verdict == "unavailable" else "complete",
        search_window_mask=63,
        exact_score=0.25,
        control_score=0.125,
        margin=0.125,
        epoch_sample_counter=g.valid_start + 43,
        fractional_offset_samples=0.375,
    )


def frame(sequence, results=(), limit=0, flags=0, **updates):
    return encode_frame(
        ScannerGlrtFrameV1.model_validate(
            {
                "session": 71,
                "generation": 2,
                "frame_sequence": sequence,
                "result_sequence_limit": limit,
                "dropped_results": 0,
                "flags": flags,
                "algorithm_sha256": ALG,
                "configuration_sha256": CONFIG,
                "legacy_metadata": b"" if flags & DRAIN else b"opaque legacy HOPS",
                "results": results,
                **updates,
            }
        )
    )


def reader(**updates):
    return ScannerGlrtFrameReader(
        **{
            "negotiated": True,
            "session": 71,
            "generation": 2,
            "algorithm_sha256": ALG,
            "configuration_sha256": CONFIG,
            "maximum_results": 3,
            "visit_geometry": geometry,
            **updates,
        }
    )


def test_late_results_bind_to_original_dwells_without_retaining_or_copying_iq():
    consumer = reader()
    iq = memoryview(b"unchanged IQ")
    early = consumer.consume(frame(0), iq)
    assert early.iq is iq and early.results == () and early.classification_error is None
    late = consumer.consume(frame(1, (result(0),), 1), iq)
    assert late.iq is iq and late.results[0].valid_start == START
    assert not consumer.summary(2)["complete"]
    final = consumer.consume(frame(2, (result(1, "no_signal"),), 2, DRAIN | FINAL), b"")
    assert final.final and final.legacy_metadata == b"" and final.iq == b""
    assert consumer.summary(2) == {
        "complete": True,
        "expected": 2,
        "received": 2,
        "dropped": 0,
        "starlink": 1,
        "no_signal": 1,
        "unavailable": 0,
        "error": None,
    }
    assert all(value is not iq for value in vars(consumer).values())


def test_multiple_drain_frames_and_explicit_loss_never_count_as_complete():
    consumer = reader()
    consumer.consume(frame(0, (result(0),), 3, dropped_results=1), b"IQ")
    consumer.consume(frame(1, (), 3, DRAIN, dropped_results=1), b"")
    consumer.consume(frame(2, (result(2),), 3, DRAIN | FINAL, dropped_results=1), b"")
    summary = consumer.summary(3)
    assert summary["received"] == 2 and summary["dropped"] == 1 and not summary["complete"]


@pytest.mark.parametrize(
    "updates",
    [
        {"session": 72},
        {"generation": 3},
        {"algorithm_sha256": "ab" * 32},
        {"configuration_sha256": "cd" * 32},
        {"frame_sequence": 3},
    ],
)
def test_wrong_identity_disables_classification_but_preserves_recording(updates):
    consumer = reader()
    iq = b"unchanged IQ"
    bad = consumer.consume(frame(0, (result(0),), 1, **updates), iq)
    assert bad.iq is iq and bad.legacy_metadata == b"opaque legacy HOPS"
    assert bad.results == () and bad.classification_error
    # Recovery requires a new session/generation, never an implicit reset.
    later = consumer.consume(frame(1, (result(1),), 2), iq)
    assert later.results == () and later.classification_error == bad.classification_error


def test_invalid_score_does_not_discard_iq_or_make_a_negative():
    consumer = reader()
    raw = bytearray(frame(0, (result(0),), 1))
    struct.pack_into("<d", raw, HEADER_BYTES + len(b"opaque legacy HOPS") + 96, float("nan"))
    got = consumer.consume(bytes(raw), b"IQ")
    assert got.legacy_metadata == b"opaque legacy HOPS" and got.iq == b"IQ"
    assert not got.results and got.classification_error
    assert consumer.summary(1)["no_signal"] == 0


@pytest.mark.parametrize("lookup", [lambda visit: None, lambda visit: {}[visit]])
def test_unattested_visit_never_attaches_to_current_dwell(lookup):
    consumer = reader(visit_geometry=lookup)
    got = consumer.consume(frame(0, (result(0),), 1), b"IQ")
    assert got.iq == b"IQ" and not got.results and got.classification_error


def test_duplicate_results_and_unaccounted_gaps_are_classification_faults():
    for bad in (frame(1, (result(0),), 1), frame(1, (result(2),), 3)):
        consumer = reader()
        consumer.consume(frame(0, (result(0),), 1), b"IQ")
        got = consumer.consume(bad, b"more IQ")
        assert not got.results and got.classification_error and got.iq == b"more IQ"
        assert consumer.summary(3)["received"] == 1


def test_unavailable_failed_or_missing_final_never_pass_completion():
    consumer = reader()
    consumer.consume(frame(0, (result(0, "unavailable"),), 1), b"IQ")
    assert not consumer.summary(1)["complete"]
    consumer.consume(frame(1, (), 1, DRAIN | FINAL | DETECTOR_FAILED), b"")
    assert consumer.summary(1)["unavailable"] == 1
    assert consumer.summary(1)["no_signal"] == 0
    assert not consumer.summary(1)["complete"]


def test_unnegotiated_legacy_path_is_unchanged():
    consumer = reader(negotiated=False)
    metadata, iq = b"ABI3 and HOPS", b"original IQ"
    got = consumer.consume(metadata, iq)
    assert got.legacy_metadata is metadata and got.iq is iq
    assert got.results == () and got.classification_error == "unsupported"


def test_iq_and_drain_must_not_be_misframed():
    consumer = reader()
    with pytest.raises(ValueError, match="framing"):
        consumer.consume(frame(0, (), 0, DRAIN), b"IQ")
    consumer.consume(frame(0, (), 0, DRAIN), b"")
    with pytest.raises(ValueError, match="framing"):
        consumer.consume(frame(1), b"IQ")
