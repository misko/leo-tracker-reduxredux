from __future__ import annotations

from threading import Event

import pytest

from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.scanner.persistent_hop_application import (
    PersistentHopCaptureError,
    capture_persistent_hop_session,
)


def test_persistent_hop_application_drains_complete_300_second_session() -> None:
    radio = FakePersistentHopRadio(transition_invalid_ms=12)
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    visits = []

    receipt = capture_persistent_hop_session(
        radio,
        plan,
        session_id="hop-complete",
        visit_sink=lambda block: visits.append(block.evidence),
        cancel=Event(),
    )

    assert receipt.capture_outcome == "complete"
    assert receipt.qualified
    assert receipt.duty_denominator_sample_count >= plan.nominal_device_sample_count
    assert receipt.valid_duty_ppm == 909_090
    assert receipt.visits == tuple(visits)
    assert len(receipt.visits) < plan.maximum_visit_count
    assert radio.lifecycle[-2:] == ["finish_session:restored", "close"]


def test_persistent_hop_application_cancels_in_band_after_sink_requests_stop() -> None:
    radio = FakePersistentHopRadio()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=2)
    cancel = Event()
    visits = []

    def retain_three(block) -> None:
        visits.append(block.evidence)
        if len(visits) == 3:
            cancel.set()

    receipt = capture_persistent_hop_session(
        radio,
        plan,
        session_id="hop-cancel",
        visit_sink=retain_three,
        cancel=cancel,
    )

    assert receipt.capture_outcome == "cancelled"
    assert receipt.visits == tuple(visits)
    assert len(receipt.visits) == 3
    assert receipt.restoration.status == "restored"


def test_persistent_hop_application_emits_qualified_utc_timing_authority() -> None:
    radio = FakePersistentHopRadio()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    cancel = Event()
    timings = []
    realtime_values = iter((1_000_000_000_000, 1_000_002_000_000, 1_300_000_000_000))
    monotonic_values = iter((100_000_000_000, 100_002_000_000, 400_000_000_000))

    def retain_one(_block) -> None:
        cancel.set()

    receipt = capture_persistent_hop_session(
        radio,
        plan,
        session_id="hop-timed",
        visit_sink=retain_one,
        cancel=cancel,
        timing_sink=timings.append,
        realtime_ns=lambda: next(realtime_values),
        monotonic_ns=lambda: next(monotonic_values),
    )

    assert receipt.capture_outcome == "cancelled"
    assert len(timings) == 1
    timing = timings[0]
    assert timing.qualified is True
    assert timing.maximum_realtime_monotonic_offset_spread_ns == 0
    assert timing.first_sample_bracket_width_ns == 2_000_000
    assert timing.first_sample_earliest_utc_ns == 1_000_000_000_000
    assert timing.first_sample_latest_utc_ns == 1_000_002_000_000
    assert timing.first_sample_estimate_utc_ns == 1_000_001_000_000


def test_persistent_hop_utc_authority_detects_wall_clock_step() -> None:
    from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1

    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id="hop-clock-step",
        session_start_device_sample_counter=10,
        sample_rate_hz=5_000_000,
        begin_before_realtime_ns=1_000_000_000_000,
        begin_before_monotonic_ns=100_000_000_000,
        begin_after_realtime_ns=1_000_001_000_000,
        begin_after_monotonic_ns=100_001_000_000,
        terminal_realtime_ns=1_300_101_000_000,
        terminal_monotonic_ns=400_001_000_000,
        qualification_limit_ns=50_000_000,
    )

    assert timing.qualified is False
    assert timing.maximum_realtime_monotonic_offset_spread_ns == 100_000_000
    assert "must abstain" in timing.reason


def test_persistent_hop_utc_authority_rejects_a_wide_begin_bracket() -> None:
    from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1

    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id="hop-slow-begin",
        session_start_device_sample_counter=10,
        sample_rate_hz=5_000_000,
        begin_before_realtime_ns=1_000_000_000_000,
        begin_before_monotonic_ns=100_000_000_000,
        begin_after_realtime_ns=1_000_100_000_000,
        begin_after_monotonic_ns=100_100_000_000,
        terminal_realtime_ns=1_300_100_000_000,
        terminal_monotonic_ns=400_100_000_000,
        qualification_limit_ns=50_000_000,
    )

    assert timing.maximum_realtime_monotonic_offset_spread_ns == 0
    assert timing.first_sample_bracket_width_ns == 100_000_000
    assert timing.qualified is False


def test_persistent_hop_application_preserves_cancel_receipt_after_sink_failure() -> None:
    radio = FakePersistentHopRadio()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)

    def fail(_block) -> None:
        raise OSError("injected sink failure")

    with pytest.raises(PersistentHopCaptureError, match="injected sink failure") as caught:
        capture_persistent_hop_session(
            radio,
            plan,
            session_id="hop-sink-failure",
            visit_sink=fail,
            cancel=Event(),
        )

    assert caught.value.terminal_receipt is not None
    assert caught.value.terminal_receipt.capture_outcome == "cancelled"
    assert caught.value.terminal_receipt.restoration.status == "restored"
    assert radio.lifecycle[-1] == "close"


def test_persistent_hop_application_never_opens_after_precancel() -> None:
    radio = FakePersistentHopRadio()
    cancel = Event()
    cancel.set()

    with pytest.raises(PersistentHopCaptureError, match="before open"):
        capture_persistent_hop_session(
            radio,
            compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000),
            session_id="hop-precancel",
            visit_sink=lambda _block: None,
            cancel=cancel,
        )

    assert radio.lifecycle == []


def test_persistent_hop_application_does_not_invent_receipt_after_transport_loss() -> None:
    radio = FakePersistentHopRadio(transport_loss_before_visit=1)

    with pytest.raises(PersistentHopCaptureError, match="transport loss") as caught:
        capture_persistent_hop_session(
            radio,
            compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000),
            session_id="hop-transport-loss",
            visit_sink=lambda _block: None,
            cancel=Event(),
        )

    assert caught.value.terminal_receipt is None
    assert caught.value.recovery_error is not None
    assert caught.value.close_error is not None
