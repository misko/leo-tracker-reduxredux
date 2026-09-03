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
