"""Real native SDK, worker and policy; synthetic IQ, no radio access."""

import ctypes as ct
import errno
import os
import signal

import numpy as np
import pytest

from tests.scanner.test_adaptive_scan import Scan
from tests.scanner.test_adaptive_scan import policy as policy
from tests.scanner.test_scanner_glrt_port import Session
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_positive import PositivePolicy, feedback
from tests.scanner.test_scanner_glrt_protection import Protection, pressure, stats, zeros
from tests.scanner.test_scanner_glrt_protection import protected as protected
from tests.scanner.test_scanner_glrt_protection import protected_port as protected_port


@pytest.fixture
def cooperative(protected):
    assert protected.port.leo_scanner_glrt_enable_cooperative_skips(protected.ptr) == 0
    return protected


def commit_actual(scan, policy, visit):
    choice = scan.choose()
    start, end = scan.now, scan.now + scan.config.rate_hz // 50 * 6
    assert policy.leo_adaptive_commit_actual(scan.ptr, visit, start, end) == 0
    scan.now = end
    return choice


def test_explicit_pressure_skips_preserve_unknown_and_do_not_latch_fault(cooperative, policy):
    s = cooperative
    scan = Scan(policy, rate=s.rate, start=2**53 + 347)
    try:
        pressure(s, 1)
        for visit in range(4):
            if visit == 3:
                for _ in range(4):
                    pressure(s, 0)
            assert commit_actual(scan, policy, visit).reason != 4
            zeros(s, visit)
            observation = feedback(s)
            if visit < 3:
                assert (observation.outcome, observation.healthy) == (0, 1)
                assert observation.valid_end - observation.valid_start == s.rate * 120 // 1000
            scan.observe(observation)
            frame = s.frame(b"unaltered dual-RX carrier")
            assert frame.legacy_metadata == b"unaltered dual-RX carrier"
            record = frame.results[0]
            if visit < 3:
                assert record.verdict == "unavailable" and record.reason == "incomplete_search"
                assert record.search_window_mask == 0
                assert record.cpu_ms == record.wall_ms == 0
                assert record.confirmation_start == record.confirmation_end
        assert scan.choose().reason != 4
        for target in range(3):
            state = scan.target(target)
            assert state.consecutive_misses == state.has_detection == state.last_detection_end == 0
        assert stats(s).pressure_skips == 3 and stats(s).resumptions == 1
    finally:
        scan.close()


def test_explicit_backlog_shedding_is_unknown_not_an_error(cooperative):
    s = cooperative
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        for visit in range(5):
            zeros(s, visit)
        assert stats(s).backlog_skips == 3 and stats(s).occupied_slots == 2
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    rows = [r for frame in s.drain() for r in frame.results]
    observations = [feedback(s) for _ in range(5)]
    assert all(
        (r.verdict, r.reason, r.search_window_mask) == ("unavailable", "worker_busy", 0)
        for r in rows[2:]
    )
    assert [(o.outcome, o.healthy) for o in observations[2:]] == [(0, 1)] * 3


@pytest.mark.parametrize("already_faulted", [False, True])
def test_skips_preserve_activity_history_and_cannot_clear_existing_fault(
    cooperative, policy, already_faulted
):
    s = cooperative
    scan = Scan(policy, rate=s.rate, start=2**53 + 347)
    try:
        # Explicit synthetic prehistory in the policy, separate from the SDK
        # under test. This is not a claimed detector result from zero IQ.
        choice = scan.choose()
        initial = scan.commit(choice)
        initial.outcome = 1
        scan.observe(initial)
        # Feedback is queued and applied at the next choose boundary.
        last_positive = initial.valid_end
        if already_faulted:
            policy.leo_adaptive_fallback(scan.ptr)
        pressure(s, 1)
        # Align the SDK with the already committed first visit; its skipped
        # observation is drained but is not applied a second time to the policy.
        zeros(s, 0)
        assert feedback(s).outcome == 0
        for visit in range(1, 9):
            choice = scan.choose()
            start, end = scan.now, scan.now + s.rate * 120 // 1000
            assert policy.leo_adaptive_commit_actual(scan.ptr, visit % 8, start, end) == 0
            scan.now = end
            zeros(s, visit)
            observation = feedback(s)
            assert (observation.outcome, observation.healthy) == (0, 1)
            scan.observe(observation)
            assert scan.target(0).last_detection_end == last_positive
            assert scan.target(0).has_detection == 1
            assert scan.target(0).consecutive_misses == 0
            assert (choice.reason == 4) == already_faulted
        # Target 0 has been revisited, without treating the unknown as another
        # detection or extending its cooldown. A previous fallback stays latched.
        assert scan.target(0).visits == 2
        assert (scan.choose().reason == 4) == already_faulted
    finally:
        scan.close()


def test_real_worker_timeout_still_latches_capture_long_fault(cooperative, policy):
    s = cooperative
    scan = Scan(policy, rate=s.rate, start=2**53 + 347)
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        for visit in range(3):
            commit_actual(scan, policy, visit)
            zeros(s, visit)
            if visit == 0:
                s.port.leo_test_clock(1_500_000_000, 1)
            row = s.frame(b"IQ continues").results[0]
            assert row.reason == "worker_failed"
            observation = feedback(s)
            assert (observation.outcome, observation.healthy) == (0, 0)
            scan.observe(observation)
        assert scan.choose().reason == 4
        assert stats(s).watchdog_trips == stats(s).disabled == 1
    finally:
        scan.close()


@pytest.mark.parametrize("failure", ["cancel", "invalid_input", "clock"])
def test_other_unavailability_is_not_reclassified_as_cooperative(cooperative, failure):
    s = cooperative
    start, count = 2**53 + 347, s.rate // 50
    assert s.visit(0, start) == 0
    if failure == "cancel":
        assert s.port.leo_scanner_glrt_finish(s.ptr, 1) == 0
    elif failure == "invalid_input":
        # The first required window is genuinely absent, not deliberately shed.
        assert s.block(start + count, np.zeros((count, 4), dtype=np.int16)) == 0
    else:
        s.port.leo_test_clock(0, -1)
    observation = feedback(s)
    assert (observation.outcome, observation.healthy) == (0, 0)
    # Read the observation independently of its wire result only once.
    row = s.frame().results[0]
    assert row.verdict == "unavailable" and row.search_window_mask == 0


def test_cooperative_skips_require_explicit_startup_opt_in(protected_port, artifacts, tmp_path):
    port = protected_port
    assert port.leo_scanner_glrt_enable_cooperative_skips(None) == -errno.EINVAL
    for positive in (False, True):
        directory = tmp_path / str(positive)
        directory.mkdir()
        s = Session(
            port,
            artifacts[0],
            directory,
            2500000,
            positive_policy=PositivePolicy(0.175, 0.025) if positive else None,
        )
        try:
            assert port.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == -errno.ENOTSUP
            assert (
                port.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(2, 250, 500, 4)))
                == 0
            )
            assert port.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == (
                0 if positive else -errno.ENOTSUP
            )
            if positive:
                assert port.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == -errno.EBUSY
        finally:
            s.close()


@pytest.mark.parametrize("started", ["visit", "history", "finished", "failed"])
def test_cooperative_policy_cannot_change_after_startup(protected, started):
    s = protected
    if started == "visit":
        assert s.visit(0, 100) == 0
    elif started == "history":
        assert s.block(100, np.zeros((1, 4), dtype=np.int16)) == 0
    elif started == "finished":
        assert s.port.leo_scanner_glrt_finish(s.ptr, 1) == 0
    else:
        s.port.leo_scanner_glrt_fail(s.ptr)
    assert s.port.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == -errno.EBUSY
