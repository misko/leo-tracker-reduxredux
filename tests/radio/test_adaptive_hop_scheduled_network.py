"""Scheduled application -> real native TCP transport -> sealed IQ and GLRT.

All sockets target localhost. Physical identities and radio controls are
substituted fixtures, with constant RX0/zero RX1 and accelerated source time.
This is not live RF, ARM performance or detector sensitivity qualification.
"""

import json
from datetime import UTC, datetime, timedelta
from threading import Event

import numpy as np
import pytest
from pluto_plus.adaptive_hop_client import AdaptiveHopClient
from pluto_plus.hardware.iio_adaptive_hop import IioAdaptiveHopBackend

from leo.cli.backend import ScheduledAdaptiveHopRun
from leo.cli.composition import CompositionHooks, LocalAcquisitionBackend, RadioConfigurationV1
from leo.radio.pluto_adaptive_hop import PlutoAdaptiveHopRadio
from leo.radio.scanner_glrt_metadata import ScannerGlrtOptions
from leo.scanner import canonical_scheduled_scanner_operation_key
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_glrt import ScannerGlrtStore
from tests.cli.test_persistent_hop_schedule import _Lifecycle, _RecordingAuthority, _settings
from tests.radio.scanner_glrt_loopback_radio import LoopbackRadio
from tests.radio.test_scanner_glrt_metadata import ALG, CONFIG
from tests.radio.test_scanner_glrt_network import loopback_server
from tests.radio.test_scanner_glrt_network import native_server as native_server

pytestmark = pytest.mark.libiio_integration


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
@pytest.mark.parametrize("ending", ["complete", "cancel", "before_refill"])
def test_scheduled_full_300s_actual_tcp_recording_and_publication(
    native_server, tmp_path, rate, mode, ending, record_property
):
    _, iio = native_server
    events = []
    options = ScannerGlrtOptions(ALG, CONFIG, mode="positive-only-v1")
    settings = _settings(
        tmp_path,
        scanner_hop_policy=mode,
        scanner_glrt=options,
        scanner_persistent_kernel_buffers=2,
        scanner_persistent_queue_capacity_visits=64,
        radios=(
            RadioConfigurationV1(
                radio_id="radio-a", serial="loopback-fixture-only", host="192.168.1.14"
            ),
        ),
    )
    settings.bulk_root.mkdir()
    lifecycle = _Lifecycle(events)
    cancel = Event()

    class Store(AdaptiveHopIqStore):
        def begin_queued(self, *args, **kwargs):
            writer = super().begin_queued(*args, **kwargs)
            append = writer.append

            def observe(block):
                append(block)
                if ending == "cancel" and block.evidence.event.visit_index == 29:
                    cancel.set()

            writer.append = observe
            return writer

    with loopback_server(native_server, rate, 0, "normal") as (context, stats):

        def radio_factory(configuration):
            def client_factory(uri, serial, *, metadata_extension):
                radio = LoopbackRadio(uri, serial, context, iio)
                backend = IioAdaptiveHopBackend(
                    uri,
                    expected_serial=serial,
                    iio_module=iio,
                    radio_factory=lambda _uri, _serial: radio,
                    metadata_extension=metadata_extension,
                )
                client = AdaptiveHopClient(
                    uri, expected_serial=serial, backend_factory=lambda _: backend
                )
                if ending == "before_refill":
                    start = client.start

                    def cancelled_start(*args, **kwargs):
                        session = start(*args, **kwargs)
                        session.request_cancel()
                        return session

                    client.start = cancelled_start
                return client

            return PlutoAdaptiveHopRadio(
                configuration.host,
                expected_serial=configuration.serial,
                radio_id=configuration.radio_id,
                scanner_glrt=options,
                iiod_port=30432,
                client_factory=client_factory,
            )

        application = LocalAcquisitionBackend(
            settings,
            CompositionHooks(
                adaptive_hop_radio_factory=radio_factory,
                persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
                adaptive_hop_store_factory=Store,
            ),
        )
        application._capture_authority = _RecordingAuthority(events)
        start = datetime(2026, 9, 9, 0, 0, tzinfo=UTC)
        intents = tuple(
            application.scheduled_scanner_intent(
                operation_key=canonical_scheduled_scanner_operation_key(
                    start + timedelta(minutes=20 * i)
                ),
                scheduled_for=start + timedelta(minutes=20 * i),
            )
            for i in range(4)
        )
        intent = next(i for i in intents if i.configuration.sample_rate_hz == rate)
        result = application.capture_scheduled_scanner(intent, cancel=cancel)
        assert isinstance(result, ScheduledAdaptiveHopRun)
        assert result.capture_qualified == (ending == "complete")
        assert result.classification_warning is None
        assert lifecycle.enter_count == lifecycle.exit_count == 1
        assert events == ["claim.enter", "lifecycle.enter", "lifecycle.exit", "claim.release"]
        receipt = result.published.manifest.receipt
        if ending == "complete":
            assert receipt.complete_visit_count == 2480
            assert receipt.source_span_attested
            assert receipt.duty_denominator_sample_count >= rate * 300
        elif ending == "cancel":
            assert 30 <= receipt.complete_visit_count < 50
            assert receipt.source_span_attested
            assert receipt.terminal.state == "cancelled"
            assert len(receipt.events) == receipt.complete_visit_count + 1
        else:
            assert not receipt.source_span_attested
            assert receipt.complete_visit_count == receipt.duty_denominator_sample_count == 0
            assert receipt.valid_duty_ppm == 0
            assert not receipt.events
            assert result.published.manifest.timing is None
        assert receipt.plan.policy.mode == mode
        assert receipt.restoration.receive_buffer_closed and receipt.restoration.fastlock_inactive
        assert result.published.manifest.queue_telemetry.enqueue_failure_count == 0
        evidence = ScannerGlrtStore(settings.bulk_root).read(result.published.session_id)
        assert evidence.error is None
        assert evidence.evidence.delivery_complete
        assert len(evidence.evidence.results) == len(receipt.events)
        assert evidence.evidence.generation == receipt.plan.policy.generation
        assert all(r.verdict == "unavailable" for r in evidence.evidence.results)
        assert receipt.radio_uri == "ip:192.168.1.14:30432"
    # End the unchanged native server watchdog before expensive offline readback.
    store = application._adaptive_hop_iq_store()
    assert store.verify(result.published.session_id) == result.published
    with store.reader(result.published.session_id) as reader:
        for index in (
            (0, 24, receipt.complete_visit_count - 1) if receipt.complete_visit_count else ()
        ):
            visit, values = reader.read_visit_ci16(index)
            assert visit == receipt.visits[index]
            assert values.shape == (rate * 120 // 1000, 2, 2)
            assert np.all(values[:, 0, 0] == 30000)
            assert np.all(values[:, 0, 1] == -20000)
            assert not np.any(values[:, 1])
    before = tuple(events)
    # Retrying after TCP server exit must return the immutable recording without
    # ever reopening its closed context or generating a new policy generation.
    assert application.capture_scheduled_scanner(intent, cancel=Event()) == result
    assert tuple(events) == before
    record_property("mode", mode)
    record_property("ending", ending)
    record_property("rate_hz", rate)
    record_property("complete_visits", receipt.complete_visit_count)
    record_property("source_span_samples", receipt.duty_denominator_sample_count)
    record_property("uncompressed_bytes", result.published.manifest.uncompressed_bytes)
    record_property(
        "queue_high_water_visits", result.published.manifest.queue_telemetry.high_water_visits
    )
    record_property("detector_results", len(evidence.evidence.results))
    record_property("network_fixture_stats", json.dumps(stats, sort_keys=True))
    store.close()
