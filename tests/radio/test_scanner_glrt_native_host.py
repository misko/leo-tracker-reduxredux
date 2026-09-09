"""Real C SDK/worker envelopes through actual PPU session; fake IIO, no RF."""

import ctypes as ct
from types import SimpleNamespace

import numpy as np
import pytest
from pluto_plus.persistent_hop import (
    PersistentHopClient,
    PersistentHopSession,
    PersistentHopWireBlock,
)

from leo.radio.scanner_glrt_metadata import ScannerGlrtMetadataExtension, ScannerGlrtOptions
from tests.radio.test_scanner_glrt_metadata import (
    ALG,
    CONFIG,
    SESSION,
    capabilities,
    event,
    evidence,
    plan,
    raw_request,
    request,
    terminal,
)
from tests.scanner.test_scanner_glrt_port import Session
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_port import port as port
from tests.scanner.test_scanner_glrt_positive import PositivePolicy
from tests.scanner.test_scanner_glrt_positive import positive_port as positive_port
from tools.qualify_presence_dwell_controls import generate


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("positive", [False, True])
def test_native_worker_frames_and_terminal_drain_reach_attested_host(
    positive_port, artifacts, tmp_path, rate, positive
):
    port = positive_port
    native = Session(
        port,
        artifacts[0],
        tmp_path,
        rate,
        positive_policy=PositivePolicy(0.175, 0.025) if positive else None,
    )
    hop = request(rate)
    mode = "positive-only-v1" if positive else "unqualified-evidence"
    host = ScannerGlrtMetadataExtension(
        ScannerGlrtOptions(ALG, CONFIG, mode=mode), session=SESSION, generation=9
    )
    host.negotiate(
        raw_request(hop),
        capabilities() | {"iio,buffer-scanner-glrt-mode": mode},
        drain_supported=True,
    )
    backend = SimpleNamespace(metadata_extension=host, closed=False)
    expected_iq = []

    def blocks():
        for index in range(2):
            ev = event(hop, index)
            assert native.visit(index, ev.invalid_end_counter_exclusive, index + 1) == 0
            source = evidence(hop, index)
            iq = np.zeros(
                (source.block_end_counter_exclusive - source.block_first_counter, 4), dtype="<i2"
            )
            iq[:, :2] = 30000
            guard = ev.invalid_end_counter_exclusive - source.block_first_counter
            if positive:
                selected, _ = generate(rate, "lower", 91, "pilot", 4)
                iq[guard:, 2:] = selected
            expected_iq.append(iq[guard:, 2] + 1j * iq[guard:, 3])
            # Feed at actual source counters, including the invalid guard,
            # in non-dividing chunks. The SDK must select RX1, not loud RX0.
            for first in range(
                source.block_first_counter, source.block_end_counter_exclusive, 8191
            ):
                count = min(8191, source.block_end_counter_exclusive - first)
                offset = first - source.block_first_counter
                assert native.block(first, iq[offset : offset + count]) == 0
            if index == 1:
                assert port.leo_scanner_glrt_finish(native.ptr, 0) == 0
            legacy = source.pack()
            buffer = ct.create_string_buffer(65536)
            n = port.leo_scanner_glrt_frame(native.ptr, legacy, len(legacy), buffer, len(buffer))
            assert n > 0
            raw = buffer.raw[:n]
            assert host.unwrap(raw) == legacy
            yield PersistentHopWireBlock(legacy, iq.tobytes(), 17, raw)

    def drain(capacity):
        assert not backend.closed and capacity == 65536
        buffer = ct.create_string_buffer(capacity)
        n = port.leo_scanner_glrt_drain(native.ptr, buffer, capacity)
        if n < 0:
            raise OSError(-n, "native drain")
        return buffer.raw[:n]

    def close():
        backend.closed = True
        native.close()

    backend.blocks = blocks
    backend.read_status = lambda: terminal(hop).pack()
    backend.drain_metadata = drain
    backend.cancel = lambda: port.leo_scanner_glrt_finish(native.ptr, 1)
    backend.close = close
    owner = PersistentHopClient(
        "ip:192.168.1.18", expected_serial="test-only", backend_factory=lambda _: backend
    )
    session = PersistentHopSession(owner, backend, plan(rate), hop, terminal(hop))
    try:
        visits = list(session.visits())
        assert len(visits) == 2
        assert all(np.all(v.samples[0] == 30000 + 30000j) for v in visits)
        for visit, expected in zip(visits, expected_iq, strict=True):
            np.testing.assert_array_equal(visit.samples[1], expected)
        snapshot = host.snapshot()
        assert snapshot.delivery_complete and snapshot.classification_complete == positive
        assert snapshot.expected_results == len(snapshot.results) == 2
        assert snapshot.mode == mode
        assert all(
            r.reason == ("complete" if positive else "unqualified_classifier") and r.rx == 1
            for r in snapshot.results
        )
        assert all(
            r.verdict == ("starlink" if positive else "unavailable") for r in snapshot.results
        )
        assert session.receipt.valid_sample_count == 2 * hop.dwell_samples
        assert session.receipt.missing_sample_count == 0 and backend.closed
    finally:
        native.close()
