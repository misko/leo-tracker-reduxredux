"""Acquisition port with the real isolated worker; synthetic IQ, no IIO/RF."""

import ctypes as ct
import errno
import os
import signal
import time
from pathlib import Path

import numpy as np
import pytest

from leo.contracts.scanner_glrt_frame import DRAIN, FINAL, decode_frame
from tests.scanner.test_native_presence_dwell_worker import artifacts as artifacts
from tools.native_presence import build_scanner_glrt_port, write_templates
from tools.presence_dwell import NativeDwell
from tools.qualify_presence_dwell_controls import generate


class Config(ct.Structure):
    _fields_ = (
        [(name, ct.c_uint64) for name in ("session", "generation")]
        + [
            (name, ct.c_uint32)
            for name in ("rate_hz", "rx", "maximum_visits", "maximum_block_samples")
        ]
        + [(name, ct.c_uint8 * 32) for name in ("algorithm_sha256", "configuration_sha256")]
    )


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    binary = build_scanner_glrt_port(tmp_path_factory.mktemp("glrt-port") / "port.so")
    return load_port(binary)


def load_port(binary):
    lib = ct.CDLL(str(binary))
    lib.leo_scanner_glrt_open.argtypes = [
        ct.POINTER(ct.c_void_p),
        ct.POINTER(Config),
        ct.c_char_p,
        ct.c_char_p,
    ]
    lib.leo_scanner_glrt_visit.argtypes = [
        ct.c_void_p,
        ct.c_uint64,
        ct.c_uint64,
        ct.c_uint64,
        ct.c_uint32,
        ct.c_uint32,
    ]
    lib.leo_scanner_glrt_block.argtypes = [
        ct.c_void_p,
        ct.c_uint64,
        ct.c_void_p,
        ct.c_size_t,
        ct.c_size_t,
        ct.c_size_t,
    ]
    lib.leo_scanner_glrt_finish.argtypes = [ct.c_void_p, ct.c_int]
    lib.leo_scanner_glrt_frame.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_size_t,
        ct.c_void_p,
        ct.c_size_t,
    ]
    lib.leo_scanner_glrt_frame.restype = ct.c_ssize_t
    lib.leo_scanner_glrt_drain.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t]
    lib.leo_scanner_glrt_drain.restype = ct.c_ssize_t
    lib.leo_scanner_glrt_fail.argtypes = [ct.c_void_p]
    lib.leo_scanner_glrt_close.argtypes = [ct.c_void_p]
    return lib


class Session:
    def __init__(self, port, worker, tmp_path, rate, *, positive_policy=None):
        self.port = port
        self.rate = rate
        self.ptr = ct.c_void_p()
        self.config = Config(71, 9, rate, 1, 2500, rate // 50)
        self.config.algorithm_sha256[:] = [18] * 32
        self.config.configuration_sha256[:] = [52] * 32
        self.template = tmp_path / f"templates-{rate}"
        write_templates(self.template, rate)
        self.template.chmod(0o600)
        worker.chmod(0o755)
        children_path = Path(f"/proc/self/task/{os.getpid()}/children")
        children_before = set(children_path.read_text().split())
        args = (
            ct.byref(self.ptr),
            ct.byref(self.config),
            os.fsencode(worker),
            os.fsencode(self.template),
        )
        status = (
            port.leo_scanner_glrt_open(*args)
            if positive_policy is None
            else port.leo_scanner_glrt_open_positive(*args, ct.byref(positive_policy))
        )
        assert status == 0
        children_after = set(children_path.read_text().split())
        created = children_after - children_before
        assert len(created) == 1
        self.worker_pid = int(created.pop())

    def visit(self, index, start, channel=1, edge=0):
        return self.port.leo_scanner_glrt_visit(
            self.ptr, index, start, start + self.rate // 50 * 6, channel, edge
        )

    def block(self, first, iq):
        assert iq.dtype == np.int16 and iq.flags.c_contiguous and iq.shape[1] == 4
        return self.port.leo_scanner_glrt_block(self.ptr, first, iq.ctypes.data, len(iq), 4, 2)

    def frame(self, legacy=b"legacy", capacity=65536):
        result = ct.create_string_buffer(capacity)
        n = self.port.leo_scanner_glrt_frame(self.ptr, legacy, len(legacy), result, capacity)
        return decode_frame(result.raw[:n]) if n > 0 else n

    def drain(self):
        output = ct.create_string_buffer(65536)
        until = time.monotonic() + 5
        frames = []
        while time.monotonic() < until:
            n = self.port.leo_scanner_glrt_drain(self.ptr, output, len(output))
            if n == -errno.EAGAIN:
                time.sleep(0.005)
                continue
            assert n > 0
            frame = decode_frame(output.raw[:n])
            frames.append(frame)
            if frame.flags & FINAL:
                assert (
                    self.port.leo_scanner_glrt_drain(self.ptr, output, len(output))
                    == -errno.ENODATA
                )
                return frames
        pytest.fail("bounded worker drain did not finish")

    def close(self):
        if self.ptr:
            self.port.leo_scanner_glrt_close(self.ptr)
            self.ptr = ct.c_void_p()


@pytest.fixture
def session(port, artifacts, tmp_path, request):
    value = Session(port, artifacts[0], tmp_path, getattr(request, "param", 2500000))
    yield value
    value.close()


@pytest.mark.parametrize("session", [2500000, 5000000], indirect=True)
@pytest.mark.parametrize("late", [False, True])
def test_real_worker_whole_dwell_late_hop_and_fractional_binding(session, late):
    start = 2**53 + 217
    count = session.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    iq[:, :2] = 30000  # RX0 is deliberately not detector input.
    original = iq.copy()
    if not late:
        assert session.visit(0, start, 2, 1) == 0
    for window in range(6):
        assert session.block(start + window * count, iq) == 0
        if late and window == 1:
            assert session.visit(0, start, 2, 1) == 0
    first = session.frame()
    assert first.legacy_metadata == b"legacy"
    assert first.frame_sequence == 0
    assert session.port.leo_scanner_glrt_finish(session.ptr, 0) == 0
    tail = session.drain()
    records = [*first.results, *(r for f in tail for r in f.results)]
    assert len(records) == 1
    record = records[0]
    assert record.sequence == record.visit == 0
    assert record.valid_start == start
    assert record.valid_end == start + count * 6
    assert record.rx == 1 and record.channel == 2 and record.edge == "upper"
    assert record.search_window_mask == 63
    assert record.verdict == "unavailable" and record.reason == "unqualified_classifier"
    assert tail[-1].flags == DRAIN | FINAL
    assert tail[-1].result_sequence_limit == 1
    np.testing.assert_array_equal(iq, original)


def test_partial_and_missing_history_are_not_negative(session):
    start, count = 10000, session.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    for i in range(10):
        assert session.block(start + i * count, iq) == 0
    assert session.visit(0, start) == 0  # Earlier than bounded retained history.
    assert session.visit(1, start + 10 * count) == 0
    assert session.block(start + 10 * count, iq) == 0  # Only 20ms of visit 1.
    assert session.port.leo_scanner_glrt_finish(session.ptr, 1) == 0
    records = [r for frame in session.drain() for r in frame.results]
    assert [r.reason for r in records] == ["invalid_input", "cancelled"]
    assert all(r.verdict == "unavailable" and r.search_window_mask == 0 for r in records)


def test_small_output_does_not_consume_results_or_sequence(session):
    assert session.visit(0, 100) == 0
    assert session.port.leo_scanner_glrt_finish(session.ptr, 1) == 0
    assert session.frame(capacity=128) == -errno.ENOSPC
    frame = session.frame()
    assert frame.frame_sequence == 0 and len(frame.results) == 1
    assert frame.results[0].reason == "cancelled"
    assert not session.drain()[-1].results


def test_failure_preserves_legacy_and_final_accounting(session):
    assert session.visit(0, 100) == 0
    session.port.leo_scanner_glrt_fail(session.ptr)
    assert session.visit(1, 100 + session.rate) == 0
    frame = session.frame(b"opaque-hop-metadata")
    assert frame.legacy_metadata == b"opaque-hop-metadata"
    assert [r.reason for r in frame.results] == ["worker_failed", "worker_failed"]
    assert session.port.leo_scanner_glrt_finish(session.ptr, 1) == 0
    tail = session.drain()
    assert tail[-1].flags & FINAL and tail[-1].result_sequence_limit == 2


def test_bad_geometry_and_active_drain_rejected(session):
    output = ct.create_string_buffer(65536)
    assert session.port.leo_scanner_glrt_drain(session.ptr, output, len(output)) == -errno.EBUSY
    assert session.visit(1, 100) == -errno.EINVAL
    assert session.visit(0, 2**64 - 1) == -errno.EINVAL
    assert session.visit(0, 100) == 0
    assert session.visit(1, 101) == -errno.EINVAL
    assert session.visit(0, 100) == -errno.EINVAL


def test_missing_or_writable_artifacts_do_not_publish_session(port, artifacts, tmp_path):
    config = Config(71, 9, 2500000, 1, 8, 50000)
    config.algorithm_sha256[:] = config.configuration_sha256[:] = [1] * 32
    output = ct.c_void_p(123)
    assert (
        port.leo_scanner_glrt_open(
            ct.byref(output), ct.byref(config), b"/nonexistent/worker", b"/nonexistent/templates"
        )
        == -errno.ENOENT
    )
    assert output.value == 123
    templates = tmp_path / "templates"
    write_templates(templates, 2500000)
    templates.chmod(0o666)
    artifacts[0].chmod(0o755)
    assert (
        port.leo_scanner_glrt_open(
            ct.byref(output), ct.byref(config), os.fsencode(artifacts[0]), os.fsencode(templates)
        )
        == -errno.EPERM
    )
    assert output.value == 123


@pytest.mark.parametrize("session", [2500000, 5000000], indirect=True)
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_late_split_pilot_matches_fractional_desktop_evidence(session, artifacts, edge):
    rate, start = session.rate, 2**53 + 347
    selected, _ = generate(rate, edge, 91, "pilot", 4)
    with NativeDwell(artifacts[1], rate, edge, 4096) as oracle:
        reference = oracle.run(selected, maximum=1, seeded=False)
    candidate = reference.confirmations[0].candidates[0]
    window = reference.rank.order[0]
    assert reference.confirmations[0].candidate_count == 1 and candidate.fractional_complete
    iq = np.empty((len(selected), 4), dtype=np.int16)
    iq[:, :2] = 30000
    iq[:, 2:] = selected
    original = iq.copy()
    # Non-dividing blocks force ring wrap and split the selected pilot interval.
    block_samples = rate // 50 - 17
    for index, offset in enumerate(range(0, len(iq), block_samples)):
        assert session.block(start + offset, iq[offset : offset + block_samples]) == 0
        if index == 1:
            assert session.visit(0, start, 4, int(edge == "upper")) == 0
    assert session.port.leo_scanner_glrt_finish(session.ptr, 0) == 0
    records = [r for frame in session.drain() for r in frame.results]
    assert len(records) == 1
    record = records[0]
    assert record.channel == 4 and record.edge == edge and record.search_window_mask == 63
    assert record.confirmation_start == start + window * (rate // 50)
    assert record.epoch_sample_counter == record.confirmation_start + candidate.epoch
    for field, expected in (
        ("fractional_offset_samples", candidate.fractional_offset_samples),
        ("cfo_hz", candidate.tracking_cfo_hz),
        ("exact_score", candidate.exact_score),
        ("control_score", candidate.control_score),
        ("margin", candidate.margin),
    ):
        assert getattr(record, field) == pytest.approx(expected, rel=1e-9, abs=1e-10)
    assert record.reason == "unqualified_classifier"
    np.testing.assert_array_equal(iq, original)


def test_slow_worker_has_ordered_unknown_overflow_without_blocking_iq(session):
    os.kill(session.worker_pid, signal.SIGSTOP)
    start, count = 10000, session.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    try:
        for visit in range(4):
            beginning = start + visit * count * 6
            assert session.visit(visit, beginning) == 0
            for window in range(6):
                assert session.block(beginning + window * count, iq) == 0
        frame = session.frame(b"still-forwarded")
        assert frame.legacy_metadata == b"still-forwarded" and not frame.results
        assert frame.result_sequence_limit == 4  # Busy result cannot overtake work 0..2.
        assert session.port.leo_scanner_glrt_finish(session.ptr, 0) == 0
    finally:
        os.kill(session.worker_pid, signal.SIGCONT)
    records = [r for frame in session.drain() for r in frame.results]
    assert [r.sequence for r in records] == [0, 1, 2, 3]
    assert [r.reason for r in records] == ["unqualified_classifier"] * 3 + ["worker_busy"]
    assert records[-1].search_window_mask == 0


def test_unexpected_worker_death_preserves_iq_and_reports_unknown(session):
    assert session.visit(0, 10000) == 0
    os.kill(session.worker_pid, signal.SIGKILL)
    deadline = time.monotonic() + 3
    records = []
    while time.monotonic() < deadline and not records:
        frame = session.frame(b"recording-continues")
        assert frame.legacy_metadata == b"recording-continues"
        records.extend(frame.results)
        if not records:
            time.sleep(0.005)
    assert len(records) == 1 and records[0].reason == "worker_failed"
    assert session.visit(1, 10000 + session.rate) == 0
    assert session.port.leo_scanner_glrt_finish(session.ptr, 1) == 0
    tail = session.drain()
    assert [r.reason for frame in tail for r in frame.results] == ["worker_failed"]
    assert tail[-1].result_sequence_limit == 2


def test_counter_gap_invalidates_partial_input_without_negative_claim(session):
    start, count = 10000, session.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    assert session.visit(0, start) == 0
    assert session.block(start, iq) == 0
    assert session.block(start + count + 1, iq) == 0
    assert session.port.leo_scanner_glrt_finish(session.ptr, 0) == 0
    records = [r for frame in session.drain() for r in frame.results]
    assert len(records) == 1 and records[0].reason == "invalid_input"
    assert records[0].search_window_mask == 0
