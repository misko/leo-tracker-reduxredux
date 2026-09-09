"""Actual SPF provider/iiOD/parser/TCP/libiio/raw reader/session/GLRT adapter.

Only the server's radio operations and pyadi layout priming are substituted.
This short accelerated sample-clock fixture is not original-arrival replay,
ARM performance qualification, RF, or proof of unchanged live duty.
The native dependency is explicit; missing builds fail rather than skip.
"""

import dataclasses
import json
import os
import selectors
import signal
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pluto_plus.hardware.iio_metadata import IioRawSidecarCaptureSession
from pluto_plus.hardware.iio_persistent_hop import IioPersistentHopBackend
from pluto_plus.persistent_hop import (
    PERSISTENT_HOP_STATUS_BYTES,
    PersistentHopClient,
    PersistentHopEvidenceV1,
    PersistentHopSession,
    PersistentHopSessionState,
    PersistentHopStatusV1,
    PersistentHopWireBlock,
)
from pluto_plus.tandem import RadioMetadataV6, TandemMode, TandemSessionRequestV1

from leo.radio.scanner_glrt_metadata import ScannerGlrtMetadataExtension, ScannerGlrtOptions
from tests.radio.scanner_glrt_loopback_radio import LoopbackRadio, PrimingSdr
from tests.radio.test_scanner_glrt_metadata import ALG, CONFIG, SESSION, plan

pytestmark = pytest.mark.libiio_integration
FIRST = (1 << 53) + 10000
DECISION_MODE = os.environ.get("SCANNER_GLRT_TEST_MODE", "unqualified-evidence")


@pytest.fixture(scope="module")
def native_server():
    assert DECISION_MODE in ("unqualified-evidence", "positive-only-v1")
    path = os.environ.get("SCANNER_GLRT_NETWORK_SERVER")
    assert path and Path(path).is_file(), "set SCANNER_GLRT_NETWORK_SERVER to the built fixture"
    import iio

    assert hasattr(iio.MetadataBuffer, "metadata_status_raw"), "select the new Python binding"
    assert hasattr(iio.MetadataBuffer, "drain_metadata"), "select the new Python binding"
    return path, iio


@contextmanager
def loopback_server(native_server, rate, delay, mode):
    binary, iio = native_server
    server_environment = os.environ.copy()
    server_library_path = os.environ.get("SCANNER_GLRT_SERVER_LIBRARY_PATH")
    if server_library_path:
        assert Path(server_library_path).is_dir()
        server_environment["LD_LIBRARY_PATH"] = server_library_path
    with tempfile.TemporaryFile(mode="w+") as errors:
        process = subprocess.Popen(
            [binary, str(rate), str(delay), mode],
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            env=server_environment,
        )
        context = None
        stats = {"server_pid": process.pid}
        try:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(5), "loopback server did not become ready"
                line = process.stdout.readline().strip()
            assert line.isdecimal(), f"server failed before opening loopback: {line!r}"
            # This is the only network context opened. Never resolves a radio.
            context = iio.Context(f"ip:127.0.0.1:{int(line)}")
            context.set_timeout(2000)
            assert context.attrs["hw_serial"] == "loopback-fixture-only"
            yield context, stats
        finally:
            if context is not None:
                context.close()
            process.terminate()
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=5)
                pytest.fail(f"owned loopback server did not stop: {output}")
            errors.seek(0)
            diagnostics = errors.read()
            assert process.returncode == 0, diagnostics
            lines = output.splitlines()
            assert lines, diagnostics
            stats.update(json.loads(lines[-1]))
            assert stats["opens"] == stats["destroys"] == 1


class LoopbackCapturePort:
    """Public host ports around the actual raw metadata capture, no fake bytes."""

    def __init__(self, raw, extension):
        self.raw = raw
        self.metadata_extension = extension
        self.closed = False
        self.frames = []

    def blocks(self):
        while True:
            raw = self.raw.read_block()
            hop = PersistentHopEvidenceV1.unpack(raw.sidecar)
            base = RadioMetadataV6.unpack(raw.metadata_header).base
            assert (base.buffer_sequence, base.first_sample_sequence, base.samples_per_channel) == (
                hop.buffer_sequence,
                hop.block_first_counter,
                hop.block_end_counter_exclusive - hop.block_first_counter,
            )
            self.frames.append(raw)
            yield PersistentHopWireBlock(
                raw.sidecar, raw.iq_payload, base.stream_id, raw.extension_metadata
            )
            if hop.state in {
                PersistentHopSessionState.COMPLETED,
                PersistentHopSessionState.CANCELLED,
                PersistentHopSessionState.FAILED,
            }:
                return

    def read_status(self):
        return self.raw.read_status()

    def drain_metadata(self, capacity):
        assert not self.closed
        return self.raw.drain_metadata(capacity)

    def cancel(self):
        self.raw.request_cancel()

    def close(self):
        self.raw.close()
        self.closed = True


@contextmanager
def capture(native_server, rate, delay=0, mode="normal", enabled=True, count=8):
    _, iio = native_server
    with loopback_server(native_server, rate, delay, mode) as (context, stats):
        device = context.find_device("dev0")
        for channel in device.channels:
            channel.enabled = True
        device.set_kernel_buffers_count(2)
        settings = dataclasses.replace(plan(rate), samples_per_block=131072, kernel_buffers=2)
        hop = settings.request(session_id=SESSION)
        hop = dataclasses.replace(
            hop, dwell_count=count, capture_span_samples=count * hop.dwell_samples
        )
        request = hop.append_to_tandem_request(
            TandemSessionRequestV1(mode=TandemMode.HOLD),
            settings.samples_per_block,
            retention_frames=3,
        )
        extension = None
        if enabled:
            extension = ScannerGlrtMetadataExtension(
                ScannerGlrtOptions(ALG, CONFIG, mode=DECISION_MODE), session=SESSION, generation=9
            )
            request = extension.negotiate(request, context.attrs, drain_supported=True)
            assert request.startswith(b"LGO1"), extension.error
        raw = IioRawSidecarCaptureSession(
            PrimingSdr(device),
            iio.MetadataBuffer,
            request=request,
            samples_per_channel=settings.samples_per_block,
            kernel_buffers=2,
            metadata_status_reader=lambda buffer, capacity: buffer.metadata_status_raw(capacity),
            metadata_canceller=lambda buffer: buffer.cancel_metadata_session(),
            status_capacity=PERSISTENT_HOP_STATUS_BYTES,
            metadata_unwrapper=extension.unwrap if extension else None,
        )
        raw.open()
        backend = LoopbackCapturePort(raw, extension)
        # No connection is opened by this owner: its backend factory is the
        # explicit loopback port. Production LAN/serial gates are not changed.
        owner = PersistentHopClient(
            "ip:192.168.1.18",
            expected_serial="loopback-fixture-only",
            backend_factory=lambda _: backend,
        )
        try:
            status = PersistentHopStatusV1.unpack(raw.read_status())
            session = PersistentHopSession(owner, backend, settings, hop, status)
            yield SimpleNamespace(
                session=session, host=extension, backend=backend, hop=hop, stats=stats
            )
        finally:
            backend.close()


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("delay", [0, 2])
def test_actual_provider_network_and_host_complete_all_edges(native_server, rate, delay):
    with capture(native_server, rate, delay) as run:
        visits = list(run.session.visits())
        assert len(visits) == 8
        assert all(np.all(v.samples[0] == 30000 - 20000j) for v in visits)
        assert all(np.count_nonzero(v.samples[1]) == 0 for v in visits)
        evidence = run.host.snapshot()
        assert evidence.delivery_complete, evidence
        assert not evidence.classification_complete
        assert evidence.expected_results == len(evidence.results) == 8
        expected_reason = (
            "incomplete_search" if DECISION_MODE == "positive-only-v1" else "unqualified_classifier"
        )
        assert evidence.mode == DECISION_MODE
        assert all(r.rx == 1 and r.reason == expected_reason for r in evidence.results)
        for result in evidence.results:
            assert result.channel == result.visit % 4 + 1
            assert result.edge == ("lower" if result.visit % 8 < 4 else "upper")
            assert result.valid_start == (
                FIRST + result.visit * (run.hop.dwell_samples + 2507) + 2507
            )
            assert result.valid_end - result.valid_start == run.hop.dwell_samples
        assert run.session.receipt.valid_sample_count == 8 * run.hop.dwell_samples
        assert run.session.receipt.missing_sample_count == 0
        assert run.backend.closed
    assert run.stats["drains"] > 0


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("mode", ["normal", "worker-failure", "missing-final"])
def test_enabled_and_faulted_capture_preserve_exact_legacy_iq(native_server, rate, mode):
    with capture(native_server, rate, enabled=False) as baseline:
        list(baseline.session.visits())
        original = baseline.backend.frames
    assert baseline.stats["drains"] == 0
    with capture(native_server, rate, mode=mode) as run:
        visits = list(run.session.visits())
        assert len(visits) == 8 and run.session.receipt.capture_outcome == "complete"
        frames = run.backend.frames
        assert len(frames) == len(original)
        for old, new in zip(original, frames, strict=True):
            assert new.metadata_header == old.metadata_header
            assert new.sidecar == old.sidecar
            assert new.iq_payload == old.iq_payload
        evidence = run.host.snapshot()
        assert evidence.delivery_complete == (mode == "normal")
        assert not evidence.classification_complete
        assert all(result.verdict == "unavailable" for result in evidence.results)
        if mode == "missing-final":
            assert not evidence.final_received and "drain failed" in evidence.error
        elif mode == "worker-failure":
            assert evidence.error is not None
        assert run.backend.closed
    assert run.stats["refills"] == baseline.stats["refills"]


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_actual_owned_worker_death_does_not_stop_iq(native_server, rate):
    with capture(native_server, rate) as run:
        parent = run.stats["server_pid"]
        children = {
            int(pid)
            for path in Path(f"/proc/{parent}/task").glob("*/children")
            for pid in path.read_text().split()
        }
        assert len(children) == 1, "fixture must own exactly one isolated numerical worker"
        child = children.pop()
        status = Path(f"/proc/{child}/status").read_text().splitlines()
        assert f"PPid:\t{parent}" in status
        # Signal only the explicitly discovered child of our fresh Popen server.
        os.kill(child, signal.SIGKILL)
        visits = list(run.session.visits())
        assert len(visits) == 8 and run.session.receipt.capture_outcome == "complete"
        assert run.session.receipt.missing_sample_count == 0
        evidence = run.host.snapshot()
        assert not evidence.classification_complete and evidence.error is not None
        assert all(result.verdict == "unavailable" for result in evidence.results)
    assert not Path(f"/proc/{child}").exists(), "fixture did not reap its worker"


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_partial_dwell_cancel_drains_without_extra_iq(native_server, rate):
    with capture(native_server, rate) as run:
        blocks = run.session.blocks()
        next(blocks)
        receipt = run.session.cancel()
        assert receipt.visits_started == 1
        assert run.session.receipt.capture_outcome == "cancelled"
        assert run.session.receipt.valid_sample_count == 0
        evidence = run.host.snapshot()
        assert evidence.delivery_complete, evidence
        assert evidence.expected_results == len(evidence.results) == 1
        assert evidence.results[0].verdict == "unavailable"
        assert evidence.results[0].reason == "cancelled"
        assert run.backend.closed
        blocks.close()
    assert run.stats["refills"] == 1 and run.stats["drains"] > 0


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_full_300s_virtual_span_through_concrete_backend(native_server, rate, record_property):
    """Full production request and backend, accelerated counters, not 300 s RF."""
    _, iio = native_server
    with loopback_server(native_server, rate, 2, "normal") as (context, stats):
        uri, serial = "ip:192.168.1.18", "loopback-fixture-only"
        radio = LoopbackRadio(uri, serial, context, iio)
        host = ScannerGlrtMetadataExtension(
            ScannerGlrtOptions(ALG, CONFIG, mode=DECISION_MODE), session=SESSION, generation=9
        )
        backend = IioPersistentHopBackend(
            uri,
            expected_serial=serial,
            iio_module=iio,
            radio_factory=lambda _uri, _serial: radio,
            metadata_extension=host,
        )
        client = PersistentHopClient(uri, expected_serial=serial, backend_factory=lambda _: backend)
        settings = dataclasses.replace(
            plan(rate),
            samples_per_block=131072,
            transition_guard_samples=rate // 1000,
        )
        session = client.start(
            settings,
            session_id=SESSION,
            tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
        )
        try:
            visits = 0
            # Consume and discard IQ incrementally: never retain a 300 s array.
            for visit in session.visits():
                assert np.all(visit.samples[0] == 30000 - 20000j)
                assert np.count_nonzero(visit.samples[1]) == 0
                visits += 1
            evidence = host.snapshot()
            assert evidence.delivery_complete, evidence
            assert not evidence.classification_complete
            assert evidence.expected_results == len(evidence.results) == visits
            assert 2400 < visits <= 2500
            assert session.receipt.duty_denominator_sample_count >= rate * 300
            assert session.receipt.valid_sample_count == visits * rate * 120 // 1000
            assert session.receipt.missing_sample_count == 0
            assert session.receipt.host_lifecycle.receive_buffer_closed
            assert radio.closed and not radio.capture.is_open
            record_property("visits", visits)
            record_property("source_span_samples", session.receipt.duty_denominator_sample_count)
            record_property("source_rate_hz", rate)
            record_property("delivery_complete", evidence.delivery_complete)
            record_property("result_reasons", sorted({r.reason for r in evidence.results}))
        finally:
            session.close()
            backend.close()
    assert stats["drains"] > 0
