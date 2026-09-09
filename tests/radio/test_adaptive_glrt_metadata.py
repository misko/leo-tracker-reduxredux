"""Adaptive classifier admission uses V2; result/source numerics stay unchanged."""

import dataclasses as dc

import pytest
from pluto_plus.adaptive_hop import AdaptiveHopPolicyV2, AdaptiveHopRequestV2
from pluto_plus.persistent_hop import PersistentHopClientError
from pluto_plus.tandem import TandemMode, TandemSessionRequestV1

from leo.contracts.scanner_glrt_frame import DRAIN, FINAL
from leo.contracts.scanner_glrt_request import decode_request
from leo.radio.scanner_glrt_metadata import (
    ScannerAdaptiveGlrtMetadataExtension,
    ScannerGlrtMetadataExtension,
    ScannerGlrtOptions,
)
from tests.radio.test_scanner_glrt_metadata import (
    ALG,
    CONFIG,
    GENERATION,
    SESSION,
    capabilities,
    evidence,
    frame,
    plan,
    result,
    terminal,
)


def fixture(rate=2500000):
    geometry = dc.replace(
        plan(rate).request(session_id=SESSION), dwell_count=64, capture_span_samples=rate * 4
    )
    request = AdaptiveHopRequestV2(geometry, AdaptiveHopPolicyV2(GENERATION))
    packet = request.append_to_tandem_request(TandemSessionRequestV1(mode=TandemMode.HOLD), 131072)
    attrs = capabilities() | {
        "iio,buffer-adaptive-hop-request": "2",
        "iio,buffer-adaptive-hop-event": "2",
        "iio,buffer-adaptive-hop-status": "2",
        "iio,buffer-adaptive-hop-modes": "shadow,adaptive",
        "iio,buffer-adaptive-hop-policy": "three-miss-two-second-v1",
        "iio,buffer-scanner-glrt-mode": "positive-only-v1",
    }
    port = ScannerAdaptiveGlrtMetadataExtension(
        ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1"),
        session=SESSION,
        generation=GENERATION,
    )
    return request, packet, attrs, port


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_adaptive_negotiation_keeps_exact_request_and_fractional_result_fields(rate):
    request, packet, attrs, port = fixture(rate)
    assert (
        decode_request(port.negotiate(packet, attrs, drain_supported=True)).legacy_request == packet
    )
    # The separately tested V2 stream attests actual event geometry. The
    # classifier port must use that target, not infer target = visit % 8.
    source = evidence(request.geometry, 0)
    actual = dc.replace(
        source.events[0],
        to_profile_index=3,
        fastlock_slot=3,
        actual_lo_frequency_hz=request.geometry.profiles[3].lo_hz,
    )
    source = dc.replace(source, events=(actual,))
    row = result(request.geometry, 0, channel=4, verdict="starlink", reason="complete")
    port.consume(frame(0, (row,), limit=1), b"iq", evidence=source)
    status = dc.replace(
        terminal(request.geometry), visits_started=1, events_emitted=1, next_event_sequence=1
    )
    # Use a one-result exact final inventory, not the fixture's default limit.
    port.finish(status, lambda _: frame(1, flags=DRAIN | FINAL, limit=1))
    saved = port.snapshot()
    assert saved.results == (row,)
    assert saved.delivery_complete, saved
    assert saved.results[0].channel == 4 and saved.results[0].visit == 0
    with pytest.raises(ValueError, match="single-use"):
        port.negotiate(packet, attrs, drain_supported=True)


@pytest.mark.parametrize(
    "name",
    [
        "iio,buffer-adaptive-hop-request",
        "iio,buffer-adaptive-hop-event",
        "iio,buffer-adaptive-hop-status",
        "iio,buffer-adaptive-hop-modes",
        "iio,buffer-adaptive-hop-policy",
        "iio,buffer-scanner-glrt-mode",
        "iio,buffer-scanner-glrt-algorithm-sha256",
        "iio,buffer-scanner-glrt-configuration-sha256",
        "iio,buffer-metadata-drain",
    ],
)
def test_unsupported_peer_refuses_adaptive_instead_of_returning_fixed_request(name):
    _, packet, attrs, port = fixture()
    del attrs[name]
    with pytest.raises((ValueError, PersistentHopClientError)):
        port.negotiate(packet, attrs, drain_supported=True)
    assert not port.snapshot().negotiated


@pytest.mark.parametrize("change", ["session", "generation", "rate_geometry", "no_drain", "v1"])
def test_adaptive_source_binding_failure_never_admits_classifier(change):
    request, packet, attrs, port = fixture()
    if change == "session":
        request = dc.replace(request, geometry=dc.replace(request.geometry, session_id=72))
    elif change == "generation":
        request = dc.replace(request, policy=dc.replace(request.policy, generation=GENERATION + 1))
    elif change == "rate_geometry":
        request = dc.replace(
            request, geometry=dc.replace(request.geometry, rf_bandwidth_hz=1000000)
        )
    packet = request.append_to_tandem_request(TandemSessionRequestV1(mode=TandemMode.HOLD), 131072)
    if change == "v1":
        packet = request.geometry.append_to_tandem_request(
            TandemSessionRequestV1(mode=TandemMode.HOLD), 131072, retention_frames=3
        )
    with pytest.raises(ValueError):
        port.negotiate(packet, attrs, drain_supported=change != "no_drain")
    assert not port.snapshot().negotiated


def test_fixed_extension_cannot_silently_consume_v2_request():
    _, packet, attrs, _ = fixture()
    port = ScannerGlrtMetadataExtension(
        ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1"), session=SESSION
    )
    with pytest.raises(ValueError, match="existing tandem"):
        port.negotiate(packet, attrs, drain_supported=True)
