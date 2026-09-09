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
@pytest.mark.parametrize("complete", [False, True, None])
def test_adaptive_tcp_to_application_mapping_and_durable_iq(
    native_server,
    tmp_path,
    rate,
    mode,
    complete,
    record_property,
):
    """Actual TCP/client to new application contracts/store; synthetic IQ only."""
    from leo.radio.adaptive_hop_mapping import map_adaptive_capture, map_adaptive_sampled_visit
    from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopPolicyV1
    from leo.scanner.persistent_hop import (
        PersistentHopUtcTimingAuthorityV1,
        compile_persistent_hop_plan_v1,
        persistent_hop_wire_session_id,
    )
    from leo.scanner.ports import ScanRadioIdentity
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    _, iio = native_server
    session_id = "adaptive-tcp-storage-fixture"
    wire_id = persistent_hop_wire_session_id(session_id)
    application_plan = AdaptiveHopPlanV1(
        geometry=compile_persistent_hop_plan_v1(
            sample_rate_hz=rate,
            transition_guard_us=1000,
            kernel_buffers=2,
        ),
        policy=AdaptiveHopPolicyV1(mode=mode.name.lower(), generation=9),
    )
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(session_id, application_plan)
    with loopback_server(native_server, rate, 0, "normal") as (context, _stats):
        uri, serial = "ip:192.168.1.14", "loopback-fixture-only"
        radio = LoopbackRadio(uri, serial, context, iio)
        host = ScannerAdaptiveGlrtMetadataExtension(
            ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1"),
            session=wire_id,
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
            session_id=wire_id,
            tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
        )
        if complete is None:
            session.request_cancel()
        visits = []
        try:
            for sampled in session.visits():
                block = map_adaptive_sampled_visit(sampled, application_plan)
                writer.append(block)
                visits.append(block.evidence)
                if not complete and len(visits) == 30:
                    session.request_cancel()
            upstream = session.receipt
            mapped = map_adaptive_capture(
                upstream,
                plan=application_plan,
                identity=ScanRadioIdentity("loopback", serial, uri),
                session_id=session_id,
            )
            assert mapped.visits == tuple(visits)
            assert mapped.terminal.state == ("completed" if complete else "cancelled")
            if complete:
                assert mapped.duty_denominator_sample_count >= 300 * rate
                assert mapped.complete_visit_count > 2400
                assert mapped.unclassified_sample_count == 0
            assert not mapped.events or mapped.terminal.first_counter > 2**53
            assert radio.closed
            assert host.snapshot().delivery_complete
            precise = upstream.start_clock_bracket
            timing = (
                None
                if not mapped.events
                else PersistentHopUtcTimingAuthorityV1.from_host_bracket(
                    session_id=session_id,
                    session_start_device_sample_counter=mapped.terminal.first_counter,
                    sample_rate_hz=rate,
                    begin_before_realtime_ns=precise.before_realtime_ns,
                    begin_before_monotonic_ns=precise.before_monotonic_ns,
                    begin_after_realtime_ns=precise.after_realtime_ns,
                    begin_after_monotonic_ns=precise.after_monotonic_ns,
                    terminal_realtime_ns=time.time_ns(),
                    terminal_monotonic_ns=time.monotonic_ns(),
                )
            )
            published = writer.finish(mapped, timing=timing)
        finally:
            session.close()
            backend.close()
            writer.abort()
            store.close()
    # The server is stopped before offline readback; its unchanged 90-second
    # watchdog guards capture/cleanup, not disk re-analysis after radio close.
    read_store = AdaptiveHopIqStore(tmp_path, read_only=True)
    try:
        assert read_store.verify(session_id) == published
        if complete is not None:
            evidence, values = read_store.read_visit_ci16(published, 25)
            assert evidence == visits[25]
            assert values[0].tolist() == [[30000, -20000], [0, 0]]
            assert not values.flags.writeable
        else:
            assert mapped.complete_visit_count == 0
            assert not mapped.source_span_attested
            assert mapped.duty_denominator_sample_count == 0
            assert mapped.unclassified_sample_count == mapped.unreceived_tail_sample_count == 0
            assert (
                mapped.terminal.final_counter > 2**53
            )  # raw evidence is retained, not elapsed time
        record_property("complete", complete)
        record_property("rate", rate)
        record_property("mode", mode.name)
        record_property("persisted_visits", mapped.complete_visit_count)
        record_property("source_span_samples", mapped.duty_denominator_sample_count)
        record_property("source_span_attested", mapped.source_span_attested)
        record_property("verified_iq_bytes", published.manifest.uncompressed_bytes)
        for corrupted in (
            dataclasses.replace(upstream, host_lifecycle=None),
            dataclasses.replace(upstream, radio_serial="wrong-radio"),
            dataclasses.replace(upstream, kernel_buffers_readback=3),
            dataclasses.replace(
                upstream,
                stream=dataclasses.replace(
                    upstream.stream,
                    valid_sample_count=upstream.stream.valid_sample_count + 1,
                ),
            ),
        ):
            with pytest.raises(ValueError):
                map_adaptive_capture(
                    corrupted,
                    plan=application_plan,
                    identity=ScanRadioIdentity("loopback", serial, uri),
                    session_id=session_id,
                )
    finally:
        read_store.close()


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
