"""Real SDK/worker with an exact test-only monotonic clock; no RF or hardware."""

import ctypes as ct
import errno
import os
import signal
from pathlib import Path

import numpy as np
import pytest

from leo.contracts.scanner_glrt_frame import DETECTOR_FAILED, FINAL
from tests.scanner.test_adaptive_scan import Observation, Scan
from tests.scanner.test_adaptive_scan import policy as policy
from tests.scanner.test_scanner_glrt_port import Config, Session, load_port
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_positive import PositivePolicy, feedback, supply_pilot
from tools.native_presence import build_scanner_glrt_port


class Protection(ct.Structure):
    _fields_ = [
        (name, ct.c_uint32)
        for name in (
            "max_occupied_slots",
            "admission_age_ms",
            "worker_timeout_ms",
            "recovery_blocks",
        )
    ]


class Stats(ct.Structure):
    _fields_ = [
        (name, ct.c_uint64)
        for name in (
            "backlog_skips",
            "pressure_skips",
            "history_blocks_skipped",
            "pressure_entries",
            "resumptions",
            "watchdog_trips",
            "clock_faults",
        )
    ] + [
        (name, ct.c_uint32)
        for name in ("enabled", "suspended", "disabled", "occupied_slots", "peak_occupied_slots")
    ]


@pytest.fixture(scope="module")
def protected_port(tmp_path_factory):
    wrapper = Path(__file__).parent / "native/protection_clock.c"
    p = load_port(
        build_scanner_glrt_port(
            tmp_path_factory.mktemp("protected-glrt") / "port.so",
            cflags=("-Wl,--wrap=clock_gettime", str(wrapper)),
        )
    )
    p.leo_scanner_glrt_open_positive.argtypes = [
        ct.POINTER(ct.c_void_p),
        ct.POINTER(Config),
        ct.c_char_p,
        ct.c_char_p,
        ct.POINTER(PositivePolicy),
    ]
    p.leo_scanner_glrt_observation.argtypes = [ct.c_void_p, ct.POINTER(Observation)]
    p.leo_scanner_glrt_enable_protection.argtypes = [ct.c_void_p, ct.POINTER(Protection)]
    p.leo_scanner_glrt_protection_stats.argtypes = [ct.c_void_p, ct.POINTER(Stats)]
    p.leo_scanner_glrt_capture_pressure.argtypes = [ct.c_void_p, ct.c_int]
    p.leo_test_clock.argtypes = [ct.c_uint64, ct.c_int]
    return p


@pytest.fixture(params=[2500000, 5000000])
def protected(protected_port, artifacts, tmp_path, request):
    p = protected_port
    s = Session(
        p, artifacts[0], tmp_path, request.param, positive_policy=PositivePolicy(0.175, 0.025)
    )
    p.leo_test_clock(1_000_000_000, 1)
    assert p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(2, 250, 500, 4))) == 0
    try:
        yield s
    finally:
        s.close()
        p.leo_test_clock(0, 0)


def stats(s):
    out = Stats()
    assert s.port.leo_scanner_glrt_protection_stats(s.ptr, ct.byref(out)) == 0
    return out


def pressure(s, busy):
    assert s.port.leo_scanner_glrt_capture_pressure(s.ptr, busy) == 0


def zeros(s, visit, *, late=False):
    start, count = 2**53 + 347 + visit * (s.rate // 50 * 6), s.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    iq[:, :2] = 30000
    before = iq.copy()
    if not late:
        assert s.visit(visit, start, visit % 4 + 1, (visit // 4) % 2) == 0
    for j in range(6):
        assert s.block(start + j * count, iq) == 0
    if late:
        assert s.visit(visit, start, visit % 4 + 1, (visit // 4) % 2) == 0
    np.testing.assert_array_equal(iq, before)


def test_early_queue_gate_leaves_a_spare_slot_and_keeps_order(protected):
    s = protected
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        for visit in range(4):
            zeros(s, visit)
        out = stats(s)
        assert (out.backlog_skips, out.occupied_slots, out.peak_occupied_slots) == (2, 2, 2)
        frame = s.frame(b"IQ carrier still passes")
        assert frame.legacy_metadata == b"IQ carrier still passes" and not frame.results
        assert frame.result_sequence_limit == 4
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    records = [r for f in s.drain() for r in f.results]
    assert [r.visit for r in records] == list(range(4))
    assert [r.reason for r in records[2:]] == ["worker_busy"] * 2
    assert all(r.search_window_mask == 0 and r.verdict == "unavailable" for r in records[2:])
    observations = [feedback(s) for _ in range(4)]
    assert [(o.outcome, o.healthy) for o in observations[2:]] == [(0, 0)] * 2


def test_age_gate_before_full_queue_and_exact_watchdog_boundary(protected):
    s = protected
    os.kill(s.worker_pid, signal.SIGSTOP)
    zeros(s, 0)
    s.port.leo_test_clock(1_250_000_000, 1)
    zeros(s, 1)
    assert (stats(s).backlog_skips, stats(s).occupied_slots) == (1, 1)
    s.port.leo_test_clock(1_499_999_999, 1)
    assert not s.frame().results
    assert stats(s).watchdog_trips == 0
    s.port.leo_test_clock(1_500_000_000, 1)
    frame = s.frame(b"no wait for stopped worker")
    assert frame.legacy_metadata == b"no wait for stopped worker"
    assert frame.flags & DETECTOR_FAILED
    assert [r.reason for r in frame.results] == ["worker_failed", "worker_busy"]
    assert (stats(s).watchdog_trips, stats(s).disabled) == (1, 1)
    observations = [feedback(s) for _ in range(2)]
    assert [(o.outcome, o.healthy) for o in observations] == [(0, 0)] * 2
    zeros(s, 2)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    tail = s.drain()
    assert tail[-1].flags & FINAL and tail[-1].result_sequence_limit == 3
    assert [r.reason for f in tail for r in f.results] == ["worker_failed"]
    assert stats(s).watchdog_trips == 1


def test_pressure_skips_history_unknown_then_hysteretic_recovery(protected):
    s = protected
    pressure(s, 1)
    zeros(s, 0, late=True)
    assert (stats(s).pressure_skips, stats(s).history_blocks_skipped) == (1, 6)
    r = s.frame().results[0]
    assert (r.reason, r.verdict, r.search_window_mask) == ("incomplete_search", "unavailable", 0)
    o = feedback(s)
    assert (o.visit, o.outcome, o.healthy) == (0, 0, 0)
    for _ in range(3):
        pressure(s, 0)
        assert stats(s).suspended
    pressure(s, 1)  # One more bad block resets the recovery streak.
    for _ in range(3):
        pressure(s, 0)
        assert stats(s).suspended
    pressure(s, 0)
    assert not stats(s).suspended
    assert (stats(s).pressure_entries, stats(s).resumptions) == (1, 1)
    zeros(s, 1)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    record = [r for f in s.drain() for r in f.results][0]
    assert record.visit == 1 and record.search_window_mask == 63
    assert stats(s).watchdog_trips == 0


def test_terminal_drain_trips_watchdog_without_any_more_iq(protected):
    s = protected
    os.kill(s.worker_pid, signal.SIGSTOP)
    zeros(s, 0)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    output = ct.create_string_buffer(65536)
    assert s.port.leo_scanner_glrt_drain(s.ptr, output, len(output)) == -errno.EAGAIN
    s.port.leo_test_clock(1_500_000_000, 1)
    tail = s.drain()
    assert tail[-1].flags & FINAL and tail[-1].flags & DETECTOR_FAILED
    assert [r.reason for f in tail for r in f.results] == ["worker_failed"]
    assert stats(s).watchdog_trips == 1


def test_real_skips_never_become_misses_and_recovery_does_not_unlatch_policy(protected, policy):
    s = protected
    scan = Scan(policy, rate=s.rate, start=2**53 + 347)
    try:
        pressure(s, 1)
        for visit in range(4):
            if visit == 3:
                for _ in range(4):
                    pressure(s, 0)
            choice = scan.choose()
            assert choice.reason == (4 if visit == 3 else 0)
            start, end = scan.now, scan.now + s.rate // 50 * 6
            assert policy.leo_adaptive_commit_actual(scan.ptr, visit, start, end) == 0
            scan.now = end
            zeros(s, visit)
            o = feedback(s)
            assert (o.visit, o.valid_start, o.valid_end) == (visit, start, end)
            if visit < 3:
                assert (o.outcome, o.healthy) == (0, 0)
            else:
                assert o.healthy == 1
            scan.observe(o)
            assert s.frame().legacy_metadata == b"legacy"
        assert scan.choose().reason == 4
        for target in range(3):
            assert scan.target(target).consecutive_misses == 0
            assert scan.target(target).last_detection_end == 0
            assert scan.target(target).has_detection == 0
        assert stats(s).pressure_skips == 3 and stats(s).resumptions == 1
    finally:
        scan.close()


def test_pressure_aborts_partial_collection_without_stale_iq_reuse(protected):
    s = protected
    start, count = 2**53 + 347, s.rate // 50
    iq = np.full((count, 4), 17000, dtype=np.int16)
    assert s.visit(0, start) == 0 and s.block(start, iq) == 0
    assert stats(s).occupied_slots == 1
    pressure(s, 1)
    assert s.block(start + count, iq) == 0
    assert stats(s).occupied_slots == 0
    for _ in range(4):
        pressure(s, 0)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    r = [r for f in s.drain() for r in f.results][0]
    assert r.reason == "incomplete_search" and r.search_window_mask == 0
    assert (feedback(s).outcome, stats(s).pressure_skips) == (0, 1)


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_protected_positive_still_has_full_fractional_coverage(protected, edge):
    s = protected
    supply_pilot(s, edge)
    r = [r for f in s.drain() for r in f.results][0]
    assert r.verdict == "starlink" and r.search_window_mask == 63
    assert r.fractional_offset_samples is not None
    o = feedback(s)
    assert (o.outcome, o.healthy) == (1, 1)
    assert stats(s).backlog_skips == stats(s).watchdog_trips == stats(s).pressure_skips == 0


@pytest.mark.parametrize("clock", [(999_999_999, 1), (0, -1)])
def test_bad_clock_disables_advisory_not_iq(protected, clock):
    s = protected
    os.kill(s.worker_pid, signal.SIGSTOP)
    zeros(s, 0)
    s.port.leo_test_clock(*clock)
    frame = s.frame(b"opaque legacy")
    assert frame.legacy_metadata == b"opaque legacy"
    assert frame.results[0].reason == "worker_failed"
    assert (stats(s).clock_faults, stats(s).disabled, stats(s).watchdog_trips) == (1, 1, 0)


def test_protection_is_explicit_validated_and_startup_only(protected_port, artifacts, tmp_path):
    p = protected_port
    s = Session(p, artifacts[0], tmp_path, 2500000)
    try:
        assert stats(s).enabled == 0
        assert p.leo_scanner_glrt_capture_pressure(s.ptr, 1) == -errno.ENOTSUP
        for values in (
            (0, 250, 500, 4),
            (4, 250, 500, 4),
            (2, 0, 500, 4),
            (2, 500, 500, 4),
            (2, 500, 1001, 4),
            (2, 250, 500, 0),
        ):
            assert (
                p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(*values)))
                == -errno.EINVAL
            )
        assert s.visit(0, 100) == 0
        assert (
            p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(2, 250, 500, 4)))
            == -errno.EBUSY
        )
    finally:
        s.close()
