"""Real opt-in SDK/pool/worker with exact owner clock; synthetic IQ, no RF."""

import ctypes as ct
import errno
import os
import signal

import numpy as np
import pytest

from tests.scanner.test_scanner_glrt_port import Session
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_positive import PositivePolicy, feedback
from tests.scanner.test_scanner_glrt_protection import Protection, pressure, stats
from tests.scanner.test_scanner_glrt_protection import protected_port as protected_port


class Admission(ct.Structure):
    _fields_ = [("maximum_pending_age_ms", ct.c_uint32), ("freshness_trigger_ms", ct.c_uint32)]


class AdmissionStats(ct.Structure):
    _fields_ = [
        (name, ct.c_uint64)
        for name in ("dispatched", "replacements", "expired", "freshness_skips", "pressure_drops")
    ] + [(name, ct.c_uint32) for name in ("enabled", "pending", "running")]


@pytest.fixture(params=[(rate, age) for rate in (2500000, 5000000) for age in (120, 240)])
def fair(protected_port, artifacts, tmp_path, request):
    p = protected_port
    rate, pending_age = request.param
    p.leo_scanner_glrt_enable_fair_admission.argtypes = [ct.c_void_p, ct.POINTER(Admission)]
    p.leo_scanner_glrt_admission_stats.argtypes = [ct.c_void_p, ct.POINTER(AdmissionStats)]
    s = Session(p, artifacts[0], tmp_path, rate, positive_policy=PositivePolicy(0.175, 0.025))
    s.pending_age_ms = pending_age
    p.leo_test_clock(1_000_000_000, 1)
    assert (
        p.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(Admission(120, 2500)))
        == -errno.ENOTSUP
    )
    assert p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(3, 450, 500, 4))) == 0
    assert p.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == 0
    assert (
        p.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(Admission(pending_age, 2500))) == 0
    )
    try:
        yield s
    finally:
        s.close()
        p.leo_test_clock(0, 0)


def admission_stats(s):
    result = AdmissionStats()
    assert s.port.leo_scanner_glrt_admission_stats(s.ptr, ct.byref(result)) == 0
    return result


def feed(s, visit, target, *, offset_ms=None):
    start = 2**53 + 347 + (visit * 120 if offset_ms is None else offset_ms) * s.rate // 1000
    count = s.rate // 50
    iq = np.zeros((count, 4), dtype=np.int16)
    iq[:, :2] = 30000
    assert s.visit(visit, start, target % 4 + 1, target // 4) == 0
    for j in range(6):
        assert s.block(start + j * count, iq) == 0
    assert np.all(iq[:, :2] == 30000) and not np.any(iq[:, 2:])


def finish(s, cancelled=0):
    assert s.port.leo_scanner_glrt_finish(s.ptr, cancelled) == 0
    return [r for frame in s.drain() for r in frame.results]


def test_replacement_keeps_visit_order_and_terminal_pending_work(fair):
    s = fair
    feed(s, 0, 0)
    assert feedback(s).visit == 0
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        feed(s, 1, 0)  # Running target 0.
        feed(s, 2, 0)  # Pending target 0.
        feed(s, 3, 1)  # Previously unserved target replaces pending target 0.
        a = admission_stats(s)
        assert (a.replacements, a.pending, a.running) == (1, 1, 1)
        assert stats(s).occupied_slots == 2 and stats(s).peak_occupied_slots == 3
        assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    rows = [r for frame in s.drain() for r in frame.results]
    assert [r.visit for r in rows] == list(range(4))
    assert [r.search_window_mask for r in rows] == [63, 63, 0, 63]
    assert rows[2].reason == "worker_busy" and rows[2].verdict == "unavailable"
    observations = [feedback(s) for _ in range(3)]
    assert [(o.visit, o.healthy) for o in observations] == [(1, 1), (2, 1), (3, 1)]
    assert admission_stats(s).dispatched == 3 and not stats(s).disabled


@pytest.mark.parametrize("domain", ["host", "source"])
def test_pending_exact_age_boundary_and_expiry_are_unknown_not_fault(fair, domain):
    s = fair
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        feed(s, 0, 0)
        feed(s, 1, 1)
        if domain == "host":
            boundary = 1_000_000_000 + s.pending_age_ms * 1_000_000
            s.port.leo_test_clock(boundary, 1)
            assert not s.frame().results
            assert admission_stats(s).pending == 1
            s.port.leo_test_clock(boundary + 1, 1)
            s.frame()
        else:
            count = s.rate // 50
            start = 2**53 + 347 + s.rate * 240 // 1000
            iq = np.zeros((count, 4), dtype=np.int16)
            blocks = s.pending_age_ms // 20
            for j in range(blocks):
                assert s.block(start + j * count, iq) == 0
            assert admission_stats(s).pending == 1
            assert s.block(start + blocks * count, iq) == 0
        assert admission_stats(s).expired == 1 and admission_stats(s).pending == 0
        assert not stats(s).disabled
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    rows = finish(s)
    assert [r.visit for r in rows] == [0, 1]
    assert rows[1].search_window_mask == 0 and rows[1].reason == "worker_busy"
    assert [feedback(s).healthy for _ in range(2)] == [1, 1]


@pytest.mark.parametrize("reason", ["pressure", "cancel", "watchdog"])
def test_pending_lifecycle_distinguishes_intentional_skip_from_failure(fair, reason):
    s = fair
    os.kill(s.worker_pid, signal.SIGSTOP)
    feed(s, 0, 0)
    feed(s, 1, 1)
    if reason == "pressure":
        pressure(s, 1)
        assert admission_stats(s).pressure_drops == 1
    elif reason == "cancel":
        assert s.port.leo_scanner_glrt_finish(s.ptr, 1) == 0
    else:
        s.port.leo_test_clock(1_500_000_000, 1)
        # Do not consume results yet; this owner call checks the watchdog.
        pressure(s, 0)
        assert stats(s).watchdog_trips == 1
    if reason != "watchdog":
        os.kill(s.worker_pid, signal.SIGCONT)
    rows = finish(s, reason == "cancel")
    assert [r.visit for r in rows] == [0, 1]
    assert (
        rows[1].reason
        == {"pressure": "incomplete_search", "cancel": "cancelled", "watchdog": "worker_failed"}[
            reason
        ]
    )
    observations = [feedback(s) for _ in range(2)]
    assert observations[1].healthy == (reason == "pressure")
    assert not admission_stats(s).pending


def test_no_overload_checks_every_dwell_and_keeps_legacy_iq(fair):
    s = fair
    for visit in range(16):
        feed(s, visit, visit % 8)
        assert feedback(s).visit == visit
    rows = finish(s)
    assert [r.visit for r in rows] == list(range(16))
    assert all(r.search_window_mask == 63 for r in rows)
    a = admission_stats(s)
    assert a.dispatched == 16 and a.replacements == a.expired == a.freshness_skips == 0


def test_freshness_guard_preserves_service_for_overdue_target_after_pressure(fair):
    s = fair
    # Explicit synthetic source-time gap, not a live-stream timing claim.
    feed(s, 0, 0, offset_ms=0)
    assert feedback(s).visit == 0
    feed(s, 1, 1, offset_ms=2600)
    assert feedback(s).visit == 1  # No overload: do not shed this fresh-target check.
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        feed(s, 2, 1, offset_ms=2720)
        feed(s, 3, 1, offset_ms=2840)
        assert admission_stats(s).pending == 1
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    assert feedback(s).visit == 2
    skipped = feedback(s)
    assert (skipped.visit, skipped.outcome, skipped.healthy) == (3, 0, 1)
    assert admission_stats(s).freshness_skips == 1
    feed(s, 4, 0, offset_ms=2960)
    assert feedback(s).visit == 4
    rows = finish(s)
    assert [r.search_window_mask for r in rows] == [63, 63, 63, 0, 63]
    assert not stats(s).disabled


def test_startup_opt_in_is_one_shot_and_validated(fair):
    s = fair
    assert (
        s.port.leo_scanner_glrt_enable_fair_admission(None, ct.byref(Admission(120, 2500)))
        == -errno.EINVAL
    )
    assert s.port.leo_scanner_glrt_enable_fair_admission(s.ptr, None) == -errno.EINVAL
    for config in (Admission(0, 2500), Admission(241, 2500), Admission(120, 0)):
        assert (
            s.port.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(config)) == -errno.EINVAL
        )
    assert (
        s.port.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(Admission(120, 2500)))
        == -errno.EBUSY
    )


def test_pending_age_cannot_relax_the_separate_admission_guard(protected_port, artifacts, tmp_path):
    p = protected_port
    p.leo_scanner_glrt_enable_fair_admission.argtypes = [ct.c_void_p, ct.POINTER(Admission)]
    s = Session(p, artifacts[0], tmp_path, 5000000, positive_policy=PositivePolicy(0.175, 0.025))
    try:
        assert (
            p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(3, 200, 500, 4))) == 0
        )
        assert p.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == 0
        for age in (200, 240):
            assert (
                p.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(Admission(age, 2500)))
                == -errno.ENOTSUP
            )
        assert p.leo_scanner_glrt_enable_fair_admission(s.ptr, ct.byref(Admission(120, 2500))) == 0
    finally:
        s.close()
