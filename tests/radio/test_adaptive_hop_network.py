"""Actual iiOD/provider/TCP/libiio and PPU V2 codecs, no radio context.

Hardware receipts and IQ are synthetic. This checks transport, cross-block
actual-visit IQ reconstruction and terminal accounting, not durable publication
or RF quality.
"""

import dataclasses
import errno
import time

import numpy as np
import pytest
from pluto_plus.adaptive_hop import (
    AdaptiveHopEvidenceV2,
    AdaptiveHopMode,
    AdaptiveHopPolicyV2,
    AdaptiveHopRequestV2,
    AdaptiveHopStatusV2,
)
from pluto_plus.adaptive_hop_client import AdaptiveHopClient
from pluto_plus.adaptive_hop_stream import AdaptiveHopStreamV2
from pluto_plus.hardware.iio_adaptive_hop import IioAdaptiveHopBackend
from pluto_plus.hardware.iio_metadata import IioRawSidecarCaptureSession
from pluto_plus.persistent_hop import PersistentHopSessionState, PersistentHopWireBlock
from pluto_plus.tandem import RadioMetadataV6, TandemMode, TandemSessionRequestV1

from leo.contracts.scanner_glrt_frame import FINAL, decode_frame, extract_legacy_metadata
from leo.contracts.scanner_glrt_request import ScannerGlrtRequestV1, encode_request
from leo.radio.scanner_glrt_metadata import ScannerAdaptiveGlrtMetadataExtension, ScannerGlrtOptions
from tests.radio.scanner_glrt_loopback_radio import LoopbackRadio, PrimingSdr
from tests.radio.test_scanner_glrt_metadata import ALG, CONFIG, SESSION, plan
from tests.radio.test_scanner_glrt_network import loopback_server
from tests.radio.test_scanner_glrt_network import native_server as native_server

pytestmark = pytest.mark.libiio_integration


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("mode", list(AdaptiveHopMode))
@pytest.mark.parametrize("cancelled", [False, True])
def test_v2_actual_network_and_original_source_binding(native_server, rate, mode, cancelled):
    _, iio = native_server
    with loopback_server(native_server, rate, 0, "normal") as (context, stats):
        assert context.attrs["iio,buffer-adaptive-hop-request"] == "2"
        assert context.attrs["iio,buffer-adaptive-hop-policy"] == "three-miss-two-second-v1"
        assert context.attrs["iio,buffer-scanner-glrt-mode"] == "positive-only-v1"
        device = context.find_device("dev0")
        for channel in device.channels:
            channel.enabled = True
        device.set_kernel_buffers_count(2)
        settings = dataclasses.replace(plan(rate), samples_per_block=131072, kernel_buffers=2)
        geometry = dataclasses.replace(
            settings.request(session_id=SESSION), dwell_count=64, capture_span_samples=rate * 4
        )
        request = AdaptiveHopRequestV2(geometry, AdaptiveHopPolicyV2(9, mode))
        stream = AdaptiveHopStreamV2(request, samples_per_block=settings.samples_per_block)
        sampled_visits = []

        def accept_samples(samples):
            for sampled in samples:
                assert sampled.samples.shape == (2, geometry.dwell_samples)
                assert np.all(sampled.samples[0] == 30000 - 20000j)
                assert not np.any(sampled.samples[1])
                assert not hasattr(sampled.visit, "sweep_index")
                sampled_visits.append(sampled.visit)

        packet = encode_request(
            ScannerGlrtRequestV1(
                9,
                ALG,
                CONFIG,
                request.append_to_tandem_request(
                    TandemSessionRequestV1(mode=TandemMode.HOLD), settings.samples_per_block
                ),
            )
        )
        raw = IioRawSidecarCaptureSession(
            PrimingSdr(device),
            iio.MetadataBuffer,
            request=packet,
            samples_per_channel=settings.samples_per_block,
            kernel_buffers=2,
            metadata_status_reader=lambda buffer, capacity: buffer.metadata_status_raw(capacity),
            metadata_canceller=lambda buffer: buffer.cancel_metadata_session(),
            status_capacity=160,
            metadata_unwrapper=extract_legacy_metadata,
        )
        events, records = [], []
        previous_end = None
        frames = 0
        raw.open()
        try:
            assert AdaptiveHopStatusV2.unpack(raw.read_status()).geometry.session_id == SESSION
            for index in range(256):
                block = raw.read_block()
                hop = AdaptiveHopEvidenceV2.unpack(block.sidecar)
                hop.validate_binding(request)
                base = RadioMetadataV6.unpack(block.metadata_header).base
                accept_samples(
                    stream.feed(
                        PersistentHopWireBlock(
                            block.sidecar,
                            block.iq_payload,
                            base.stream_id,
                            block.extension_metadata,
                        )
                    )
                )
                assert base.buffer_sequence == index == hop.geometry.buffer_sequence
                assert base.first_sample_sequence == hop.geometry.block_first_counter
                if previous_end is not None:
                    assert hop.geometry.block_first_counter == previous_end
                previous_end = hop.geometry.block_end_counter_exclusive
                iq = np.frombuffer(block.iq_payload, dtype="<i2").reshape(-1, 4)
                assert np.all(iq[:, 0] == 30000) and np.all(iq[:, 1] == -20000)
                assert not np.any(iq[:, 2:])
                for event in hop.geometry.events:
                    assert event.dwell_index == len(events)
                    assert event.from_profile_index == (
                        events[-1].to_profile_index if events else 255
                    )
                    if events:
                        assert (
                            event.invalid_start_counter
                            == events[-1].invalid_end_counter_exclusive + geometry.dwell_samples
                        )
                    events.append(event)
                frame = decode_frame(block.extension_metadata)
                assert frame.frame_sequence == frames and not frame.dropped_results
                frames += 1
                records.extend(frame.results)
                if cancelled and index == 7:
                    raw.request_cancel()
                    break
                if hop.geometry.state == PersistentHopSessionState.COMPLETED:
                    break
            else:
                pytest.fail("finite adaptive capture did not terminate")
            final = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    packet = raw.drain_metadata()
                except OSError as error:
                    assert error.errno == errno.EAGAIN
                    time.sleep(0.002)
                    continue
                frame = decode_frame(packet)
                assert frame.frame_sequence == frames and not frame.dropped_results
                frames += 1
                records.extend(frame.results)
                if frame.flags & FINAL:
                    final = frame
                    break
            assert final is not None and final.result_sequence_limit == len(events) == len(records)
            for index, result in enumerate(records):
                event = events[index]
                assert result.sequence == result.visit == index
                assert result.channel == event.to_profile_index % 4 + 1
                assert result.edge == ("upper" if event.to_profile_index >= 4 else "lower")
                assert result.valid_start == event.invalid_end_counter_exclusive
                assert result.valid_end == result.valid_start + geometry.dwell_samples
                assert result.rx == 1 and result.verdict != "no_signal"
            final_status = AdaptiveHopStatusV2.unpack(raw.read_status())
            receipt, last_samples = stream.finish(final_status)
            accept_samples(last_samples)
            assert receipt.visits == tuple(sampled_visits)
            assert receipt.events == tuple(events)
            assert len(sampled_visits) == len(events) - (1 if cancelled else 0)
            assert receipt.valid_sample_count == len(sampled_visits) * geometry.dwell_samples
            assert (
                receipt.valid_sample_count
                + receipt.transition_invalid_sample_count
                + receipt.unclassified_sample_count
                == receipt.duty_denominator_sample_count
            )
            if not cancelled:
                assert receipt.duty_target_met and not receipt.unclassified_sample_count
            status = final_status.geometry
            assert status.visits_started == status.events_emitted == len(events)
            assert status.state == (
                PersistentHopSessionState.CANCELLED
                if cancelled
                else PersistentHopSessionState.COMPLETED
            )
        finally:
            raw.close()
    assert stats["opens"] == stats["destroys"] == 1 and stats["drains"] > 0


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("mode", list(AdaptiveHopMode))
@pytest.mark.parametrize("cancelled", [False, True])
def test_adaptive_full_client_backend_lifecycle_300s_or_cancel(
    native_server, rate, mode, cancelled, record_property
):
    """Full 300-second source span, accelerated synthetic IQ, not live RF/load."""
    _, iio = native_server
    with loopback_server(native_server, rate, 0, "normal") as (context, stats):
        uri, serial = "ip:192.168.1.14", "loopback-fixture-only"
        radio = LoopbackRadio(uri, serial, context, iio)
        host = ScannerAdaptiveGlrtMetadataExtension(
            ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1"),
            session=SESSION,
            generation=9,
        )
        backend = IioAdaptiveHopBackend(
            uri,
            expected_serial=serial,
            iio_module=iio,
            radio_factory=lambda _uri, _serial: radio,
            metadata_extension=host,
        )
        client = AdaptiveHopClient(uri, expected_serial=serial, backend_factory=lambda _: backend)
        settings = dataclasses.replace(
            plan(rate),
            samples_per_block=131072,
            kernel_buffers=2,
            transition_guard_samples=rate // 1000,
        )
        session = client.start(
            settings,
            policy=AdaptiveHopPolicyV2(9, mode),
            session_id=SESSION,
            tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
        )
        visits = 0
        try:
            for sampled in session.visits():
                assert np.all(sampled.samples[0] == 30000 - 20000j)
                assert not np.any(sampled.samples[1])
                visits += 1
                if cancelled and visits == 3:
                    session.request_cancel()
            receipt = session.receipt
            assert receipt.stream.valid_sample_count == visits * settings.dwell_samples
            assert len(receipt.stream.visits) == visits
            assert (
                receipt.host_lifecycle.receive_buffer_closed
                and receipt.host_lifecycle.fastlock_inactive
            )
            assert (
                receipt.host_lifecycle.original_settings == receipt.host_lifecycle.restored_settings
            )
            assert receipt.kernel_buffers_requested == receipt.kernel_buffers_readback == 2
            assert receipt.start_clock_bracket is not None
            assert not receipt.metadata_extension_error
            assert radio.closed and not radio.capture.is_open
            evidence = host.snapshot()
            assert evidence.delivery_complete, evidence
            assert evidence.expected_results == len(receipt.stream.events)
            assert all(r.rx == 1 and r.verdict != "no_signal" for r in evidence.results)
            for result, event in zip(evidence.results, receipt.stream.events, strict=True):
                assert result.valid_start == event.invalid_end_counter_exclusive
                assert result.channel == event.to_profile_index % 4 + 1
                assert result.edge == ("upper" if event.to_profile_index >= 4 else "lower")
            if not cancelled:
                assert 2400 < visits <= 2500
                assert receipt.stream.duty_denominator_sample_count >= rate * 300
                assert receipt.stream.duty_target_met
            else:
                assert receipt.stream.status.geometry.state == PersistentHopSessionState.CANCELLED
            record_property("visits", visits)
            record_property("mode", mode.name)
            record_property("source_span_samples", receipt.stream.duty_denominator_sample_count)
            record_property("source_rate_hz", rate)
            record_property("delivery_complete", evidence.delivery_complete)
        finally:
            session.close()
            backend.close()
    assert stats["drains"] > 0


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("fault", ["consume", "drain", "source"])
def test_adaptive_host_faults_preserve_iq_or_fail_closed_with_cleanup(native_server, rate, fault):
    _, iio = native_server
    with loopback_server(native_server, rate, 0, "normal") as (context, stats):
        uri, serial = "ip:192.168.1.14", "loopback-fixture-only"
        radio = LoopbackRadio(uri, serial, context, iio)
        host = ScannerAdaptiveGlrtMetadataExtension(
            ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1"),
            session=SESSION,
            generation=9,
        )

        def injected_failure(*_args, **_kwargs):
            raise ValueError("injected adaptive reporting fault")

        if fault == "consume":
            host.consume = injected_failure
        elif fault == "drain":
            host.finish = injected_failure
        backend = IioAdaptiveHopBackend(
            uri,
            expected_serial=serial,
            iio_module=iio,
            radio_factory=lambda *_: radio,
            metadata_extension=host,
        )
        original_blocks = backend.blocks

        def corrupt_blocks():
            for i, wire in enumerate(original_blocks()):
                if i == 3:
                    hop = AdaptiveHopEvidenceV2.unpack(wire.evidence)
                    wire = dataclasses.replace(
                        wire,
                        evidence=dataclasses.replace(
                            hop, geometry=dataclasses.replace(hop.geometry, buffer_sequence=i + 1)
                        ).pack(),
                    )
                yield wire

        if fault == "source":
            backend.blocks = corrupt_blocks
        client = AdaptiveHopClient(uri, expected_serial=serial, backend_factory=lambda _: backend)
        settings = dataclasses.replace(plan(rate), samples_per_block=131072, kernel_buffers=2)
        session = client.start(
            settings,
            policy=AdaptiveHopPolicyV2(9),
            session_id=SESSION,
            tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
        )
        try:
            if fault == "source":
                with pytest.raises(RuntimeError, match="sequence"):
                    list(session.visits())
                with pytest.raises(RuntimeError, match="no terminal receipt"):
                    _ = session.receipt
            else:
                visits = 0
                for sampled in session.visits():
                    assert np.all(sampled.samples[0] == 30000 - 20000j)
                    assert not np.any(sampled.samples[1])
                    visits += 1
                    if visits == 3:
                        session.request_cancel()
                assert session.receipt.stream.valid_sample_count == visits * settings.dwell_samples
                assert session.receipt.metadata_extension_error
                assert host.snapshot().error
                assert session.receipt.host_lifecycle.receive_buffer_closed
            assert radio.closed and not radio.capture.is_open
            assert radio.read_active_rx_fastlock_profile() is None
        finally:
            session.close()
            backend.close()
