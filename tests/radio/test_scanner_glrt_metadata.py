"""Hardware-free tests using public PPU contracts and the actual host session."""

import dataclasses
import errno
from types import SimpleNamespace

import numpy as np
import pytest
from pluto_plus.persistent_hop import (
    PERSISTENT_HOP_NONE_PROFILE,
    PersistentHopClient,
    PersistentHopEventFlag,
    PersistentHopEventKind,
    PersistentHopEventV1,
    PersistentHopEvidenceV1,
    PersistentHopPlanV1,
    PersistentHopProfileV1,
    PersistentHopSession,
    PersistentHopSessionState,
    PersistentHopStatusFlag,
    PersistentHopStatusV1,
    PersistentHopTerminalReason,
    PersistentHopWireBlock,
)
from pluto_plus.tandem import TandemMode, TandemSessionRequestV1

from leo.contracts.scanner_glrt_frame import (
    DRAIN,
    FINAL,
    ScannerGlrtClassificationV1,
    ScannerGlrtFrameV1,
    encode_frame,
)
from leo.contracts.scanner_glrt_request import decode_request
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.radio.scanner_glrt_metadata import ScannerGlrtMetadataExtension, ScannerGlrtOptions
from leo.scanner.models import scheduled_low_band_targets

ALG, CONFIG = "12" * 32, "34" * 32
START, SESSION, GENERATION = 10**16 + 37, 71, 2


def plan(rate):
    return PersistentHopPlanV1(
        nominal_duration_seconds=300,
        valid_visit_ms=120,
        sample_rate_hz=rate,
        rf_bandwidth_hz=rate,
        transition_guard_samples=2500,
        samples_per_block=32768,
        kernel_buffers=8,
        minimum_valid_duty_ppm=900000,
        manual_gain_db=40.0,
        profiles=tuple(
            PersistentHopProfileV1(
                target_index=i,
                fastlock_profile_index=i,
                center_hz=t.if_center_hz,
                lo_hz=t.if_center_hz,
                profile_crc32=i + 1,
            )
            for i, t in enumerate(scheduled_low_band_targets(bandwidth_hz=rate))
        ),
    )


def request(rate=5000000):
    hop = plan(rate).request(session_id=SESSION)
    return dataclasses.replace(hop, dwell_count=2, capture_span_samples=2 * hop.dwell_samples)


def raw_request(hop):
    return hop.append_to_tandem_request(
        TandemSessionRequestV1(mode=TandemMode.HOLD), 32768, retention_frames=3
    )


def capabilities():
    return {
        "iio,buffer-scanner-glrt": "1",
        "iio,buffer-metadata-drain": "1",
        "iio,buffer-scanner-glrt-mode": "unqualified-evidence",
        "iio,buffer-scanner-glrt-algorithm-sha256": ALG,
        "iio,buffer-scanner-glrt-configuration-sha256": CONFIG,
    }


@pytest.mark.parametrize("mode", ["unqualified-evidence", "positive-only-v1"])
def test_decision_mode_must_match_the_attested_provider(mode):
    port = ScannerGlrtMetadataExtension(ScannerGlrtOptions(ALG, CONFIG, mode=mode), session=SESSION)
    attributes = capabilities() | {
        "iio,buffer-scanner-glrt-mode": (
            "positive-only-v1" if mode == "unqualified-evidence" else "unqualified-evidence"
        )
    }
    raw = raw_request(request())
    assert port.negotiate(raw, attributes, drain_supported=True) == raw
    assert not port.snapshot().negotiated


def test_positive_only_mode_delivers_positive_and_unknown_but_not_absence():
    hop = request()
    options = ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1")
    port = ScannerGlrtMetadataExtension(options, session=SESSION, generation=GENERATION)
    raw = raw_request(hop)
    attrs = capabilities() | {"iio,buffer-scanner-glrt-mode": "positive-only-v1"}
    assert decode_request(port.negotiate(raw, attrs, drain_supported=True)).legacy_request == raw
    rows = (
        result(hop, 0, verdict="starlink", reason="complete"),
        result(hop, 1, reason="incomplete_search"),
    )
    for i in range(2):
        source = evidence(hop, i)
        port.consume(frame(i, (rows[i],)), b"iq", evidence=source)
    port.finish(terminal(hop), lambda _: frame(2, flags=DRAIN | FINAL))
    saved = port.snapshot()
    assert saved.mode == "positive-only-v1" and saved.delivery_complete
    assert not saved.classification_complete and saved.results == rows
    assert ScannerGlrtSessionEvidenceV1.model_validate_json(saved.model_dump_json()) == saved

    port = ScannerGlrtMetadataExtension(options, session=SESSION, generation=GENERATION)
    port.negotiate(raw, attrs, drain_supported=True)
    port.consume(
        frame(0, (result(hop, 0, verdict="no_signal", reason="complete"),)),
        b"iq",
        evidence=evidence(hop, 0),
    )
    assert "asserted signal absence" in port.snapshot().error


def test_unknown_decision_profile_is_rejected():
    with pytest.raises(ValueError, match="decision profile"):
        ScannerGlrtOptions(ALG, CONFIG, mode="anything")


def event(hop, index):
    start = START + index * (hop.dwell_samples + hop.transition_guard_samples + 1)
    target = index % 8
    return PersistentHopEventV1(
        event_sequence=index,
        dwell_index=index,
        transition_before_counter=start,
        transition_after_counter=start + 1,
        invalid_start_counter=start,
        invalid_end_counter_exclusive=start + 1 + hop.transition_guard_samples,
        from_profile_index=PERSISTENT_HOP_NONE_PROFILE if not index else (target - 1) % 8,
        to_profile_index=target,
        fastlock_slot=target,
        kind=PersistentHopEventKind.RETUNE if index else PersistentHopEventKind.STARTUP,
        flags=PersistentHopEventFlag.COUNTER_BOUNDS_ATTESTED | PersistentHopEventFlag.LO_ATTESTED,
        actual_lo_frequency_hz=hop.profiles[target].lo_hz,
        actual_if_offset_hz=0,
        device_event_id=index + 1,
    )


def result(hop, index, **updates):
    start = event(hop, index).invalid_end_counter_exclusive
    confirm = start + hop.dwell_samples * 5 // 6
    return ScannerGlrtClassificationV1.model_validate(
        dict(
            sequence=index,
            visit=index,
            valid_start=start,
            valid_end=start + hop.dwell_samples,
            search_start=start,
            search_end=start + hop.dwell_samples,
            confirmation_start=confirm,
            confirmation_end=start + hop.dwell_samples,
            rate_hz=hop.sample_rate_hz,
            channel=index % 4 + 1,
            edge="lower" if index % 8 < 4 else "upper",
            rx=1,
            verdict="unavailable",
            reason="unqualified_classifier",
            search_window_mask=63,
            exact_score=0.25,
            control_score=0.125,
            margin=0.125,
            cfo_hz=-12345.25,
            epoch_sample_counter=confirm + 43,
            fractional_offset_samples=0.375,
        )
        | updates
    )


def frame(sequence, results=(), *, flags=0, legacy=b"legacy", limit=2, **updates):
    return encode_frame(
        ScannerGlrtFrameV1.model_validate(
            dict(
                session=SESSION,
                generation=GENERATION,
                frame_sequence=sequence,
                result_sequence_limit=limit,
                dropped_results=0,
                algorithm_sha256=ALG,
                configuration_sha256=CONFIG,
                flags=flags,
                legacy_metadata=b"" if flags & DRAIN else legacy,
                results=results,
            )
            | updates
        )
    )


def extension(hop, **options):
    port = ScannerGlrtMetadataExtension(
        ScannerGlrtOptions(ALG, CONFIG, **options), session=SESSION, generation=GENERATION
    )
    raw = raw_request(hop)
    wrapped = port.negotiate(raw, capabilities(), drain_supported=True)
    assert decode_request(wrapped).legacy_request == raw
    return port


def evidence(hop, index):
    ev = event(hop, index)
    return PersistentHopEvidenceV1(
        flags=PersistentHopStatusFlag.RESTORE_REQUIRED,
        session_id=SESSION,
        buffer_sequence=index,
        block_first_counter=ev.invalid_start_counter,
        block_end_counter_exclusive=ev.invalid_end_counter_exclusive + hop.dwell_samples,
        state=PersistentHopSessionState.RUNNING,
        reason=PersistentHopTerminalReason.NONE,
        error_code=0,
        events=(ev,),
    )


def terminal(hop):
    end = event(hop, 1).invalid_end_counter_exclusive + hop.dwell_samples
    return PersistentHopStatusV1(
        state=PersistentHopSessionState.COMPLETED,
        reason=PersistentHopTerminalReason.PLAN_COMPLETE,
        error_code=0,
        flags=(
            PersistentHopStatusFlag.TERMINAL
            | PersistentHopStatusFlag.RESTORE_ATTEMPTED
            | PersistentHopStatusFlag.RESTORE_SUCCEEDED
            | PersistentHopStatusFlag.RESTORE_REQUIRED
        ),
        session_id=SESSION,
        planned_dwells=2,
        visits_started=2,
        events_emitted=2,
        next_event_sequence=2,
        last_block_sequence=1,
        last_block_end_counter=end,
        first_counter=START,
        final_counter=end,
        restore_before_counter=end,
        restore_after_counter=end + 1,
        restored_lo_frequency_hz=915000000,
        restore_error_code=0,
        active_profile_index=255,
        restored_profile_index=255,
        startup_invalid_start_counter=START,
        startup_invalid_end_counter_exclusive=event(hop, 0).invalid_end_counter_exclusive,
        device_dropped_events=0,
    )


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_actual_ppu_session_consumes_late_results_and_drains_before_close(rate):
    hop = request(rate)
    port = extension(hop)
    wires = []
    for i in range(2):
        ev = evidence(hop, i)
        iq = bytes((ev.block_end_counter_exclusive - ev.block_first_counter) * 8)
        metadata = frame(i, (result(hop, 0),) if i else (), legacy=ev.pack())
        assert port.unwrap(metadata) == ev.pack()
        wires.append(PersistentHopWireBlock(ev.pack(), iq, 17, metadata))
    backend = SimpleNamespace(
        metadata_extension=port,
        blocks=lambda: iter(wires),
        read_status=lambda: terminal(hop).pack(),
        closed=False,
    )

    def drain(capacity):
        assert capacity == 65536 and not backend.closed
        return frame(2, (result(hop, 1),), flags=DRAIN | FINAL)

    backend.drain_metadata = drain
    backend.close = lambda: setattr(backend, "closed", True)
    backend.cancel = lambda: pytest.fail("valid capture must not be cancelled")
    owner = PersistentHopClient(
        "ip:192.168.1.18", expected_serial="test-only-serial", backend_factory=lambda _: backend
    )
    session = PersistentHopSession(owner, backend, plan(rate), hop, terminal(hop))
    visits = list(session.visits())
    assert len(visits) == 2 and all(np.count_nonzero(v.samples) == 0 for v in visits)
    assert session.receipt.valid_sample_count == 2 * hop.dwell_samples
    assert session.receipt.missing_sample_count == 0 and backend.closed
    snapshot = port.snapshot()
    assert snapshot.delivery_complete and not snapshot.classification_complete
    assert snapshot.results == (result(hop, 0), result(hop, 1))
    assert snapshot.results[0].valid_start > 2**53
    assert snapshot.results[0].fractional_offset_samples == 0.375
    assert ScannerGlrtSessionEvidenceV1.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert not any(isinstance(v, (bytes, memoryview, np.ndarray)) for v in vars(port).values())


@pytest.mark.parametrize("missing", [*capabilities(), "binding"])
def test_missing_or_mismatched_capability_preserves_exact_request(missing):
    port = ScannerGlrtMetadataExtension(ScannerGlrtOptions(ALG, CONFIG), session=SESSION)
    attributes = capabilities()
    if missing != "binding":
        attributes[missing] = "unsupported"
    raw = raw_request(request())
    assert port.negotiate(raw, attributes, drain_supported=missing != "binding") == raw
    assert port.unwrap(b"legacy") == b"legacy"
    port.finish(terminal(request()), lambda _: pytest.fail("unsupported peer must not drain"))
    got = port.snapshot()
    assert not got.negotiated and not got.delivery_complete and got.expected_results == 2


@pytest.mark.parametrize("change", ["rate", "bandwidth", "center", "duration"])
def test_unsupported_geometry_does_not_wrap_open(change):
    hop = request()
    if change == "rate":
        hop = dataclasses.replace(hop, sample_rate_hz=6000000)
    elif change == "bandwidth":
        hop = dataclasses.replace(hop, rf_bandwidth_hz=2500000)
    elif change == "duration":
        hop = dataclasses.replace(
            hop, dwell_count=2600, capture_span_samples=hop.sample_rate_hz * 301
        )
    else:
        hop = dataclasses.replace(
            hop,
            profiles=tuple(
                dataclasses.replace(p, center_hz=p.center_hz + 10, lo_hz=p.lo_hz + 10)
                for p in hop.profiles
            ),
        )
    port = ScannerGlrtMetadataExtension(ScannerGlrtOptions(ALG, CONFIG), session=SESSION)
    raw = raw_request(hop)
    assert port.negotiate(raw, capabilities(), drain_supported=True) == raw
    assert port.snapshot().error == "unsupported_classifier_geometry"


@pytest.mark.parametrize("failure", ["wrong_session", "missing", "qualified", "future"])
def test_bad_result_evidence_cannot_become_a_complete_classification(failure):
    hop = request()
    port = extension(hop)
    first = result(hop, 0)
    updates = {"session": SESSION + 1} if failure == "wrong_session" else {}
    if failure == "qualified":
        first = result(hop, 0, verdict="starlink", reason="complete")
    ev = evidence(hop, 0)
    if failure == "future":
        ev = dataclasses.replace(ev, block_end_counter_exclusive=ev.block_first_counter + 10000)
    port.consume(frame(0, (first,), **updates), b"iq", evidence=ev)
    port.consume(frame(1), b"iq", evidence=evidence(hop, 1))
    port.finish(terminal(hop), lambda _: frame(2, flags=DRAIN | FINAL))
    got = port.snapshot()
    assert got.error and not got.delivery_complete and not got.classification_complete
    assert all(r.verdict == "unavailable" for r in got.results)


@pytest.mark.parametrize("end", ["final", "enodata", "disconnect", "timeout"])
def test_terminal_retry_errors_and_missing_final_are_explicit(monkeypatch, end):
    hop = request()
    port = extension(hop, drain_budget_seconds=0.02)
    port.consume(frame(0, (result(hop, 0),)), b"iq", evidence=evidence(hop, 0))
    port.consume(frame(1, (result(hop, 1),)), b"iq", evidence=evidence(hop, 1))
    now = [0.0]
    monkeypatch.setattr("leo.radio.scanner_glrt_metadata.time.monotonic", lambda: now[0])
    monkeypatch.setattr(
        "leo.radio.scanner_glrt_metadata.time.sleep", lambda s: now.__setitem__(0, now[0] + s)
    )
    attempts = []

    def drain(capacity):
        attempts.append(capacity)
        if len(attempts) <= 2 or end == "timeout":
            raise OSError(errno.EAGAIN, "pending")
        if end != "final":
            raise OSError(errno.ENODATA if end == "enodata" else errno.ECONNRESET, end)
        return frame(2, flags=DRAIN | FINAL)

    port.finish(terminal(hop), drain)
    got = port.snapshot()
    assert got.delivery_complete == (end == "final")
    assert got.final_received == (end == "final")
    assert bool(got.error) == (end != "final")
    assert 3 <= len(attempts) <= 5


def test_malformed_envelope_cannot_be_unwrapped_as_iq():
    port = extension(request())
    for packet in (b"truncated", frame(0, flags=DRAIN | FINAL)):
        with pytest.raises(ValueError):
            port.unwrap(packet)


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_all_eight_targets_keep_channel_edge_and_source_fractional_timing(rate):
    hop = request(rate)
    hop = dataclasses.replace(hop, dwell_count=8, capture_span_samples=8 * hop.dwell_samples)
    port = extension(hop)
    for index in range(8):
        port.consume(
            frame(index, (result(hop, index),), limit=index + 1),
            b"iq",
            evidence=evidence(hop, index),
        )
    end = event(hop, 7).invalid_end_counter_exclusive + hop.dwell_samples
    status = dataclasses.replace(
        terminal(hop),
        visits_started=8,
        planned_dwells=8,
        events_emitted=8,
        next_event_sequence=8,
        last_block_sequence=7,
        last_block_end_counter=end,
        final_counter=end,
        restore_before_counter=end,
        restore_after_counter=end + 1,
    )
    port.finish(status, lambda _: frame(8, flags=DRAIN | FINAL, limit=8))
    snapshot = port.snapshot()
    assert snapshot.delivery_complete
    assert [(r.channel, r.edge) for r in snapshot.results] == [
        (c, edge) for edge in ("lower", "upper") for c in range(1, 5)
    ]
    assert all(r.fractional_offset_samples == 0.375 for r in snapshot.results)


@pytest.mark.parametrize("budget", [True, 0, -1, float("inf"), float("nan"), 11])
def test_options_reject_unbounded_drain(budget):
    with pytest.raises(ValueError):
        ScannerGlrtOptions(ALG, CONFIG, budget)
