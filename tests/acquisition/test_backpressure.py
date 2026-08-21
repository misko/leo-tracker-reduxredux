from __future__ import annotations

import pytest

from leo.acquisition import AcquisitionBackpressureController, AcquisitionQueuePressure


def _pressure(queued: int, running: int = 0) -> AcquisitionQueuePressure:
    return AcquisitionQueuePressure(queued=queued, running=running)


def test_exact_entry_and_exit_boundaries() -> None:
    controller = AcquisitionBackpressureController()

    at_twenty = controller.observe(_pressure(20, running=400))
    above_twenty = controller.observe(_pressure(21, running=0))
    at_ten = controller.observe(_pressure(10, running=0))
    below_ten = controller.observe(_pressure(9, running=900))

    assert at_twenty.admitted is True
    assert above_twenty.admitted is False
    assert above_twenty.transition == "entered_high_watermark"
    assert at_ten.admitted is False
    assert below_ten.admitted is True
    assert below_ten.transition == "exited_low_watermark"


def test_running_jobs_are_reported_but_do_not_drive_suppression() -> None:
    controller = AcquisitionBackpressureController()

    assert controller.observe(_pressure(0, running=10_000)).admitted is True
    assert controller.observe(_pressure(20, running=10_000)).admitted is True


def test_oscillation_inside_hysteresis_band_does_not_flap() -> None:
    controller = AcquisitionBackpressureController()
    admitted = [
        controller.observe(_pressure(19)).admitted,
        controller.observe(_pressure(21)).admitted,
        controller.observe(_pressure(20)).admitted,
        controller.observe(_pressure(11)).admitted,
        controller.observe(_pressure(10)).admitted,
        controller.observe(_pressure(9)).admitted,
        controller.observe(_pressure(10)).admitted,
        controller.observe(_pressure(20)).admitted,
    ]

    assert admitted == [True, False, False, False, False, True, True, True]


@pytest.mark.parametrize(
    ("queued", "admitted"),
    ((9, True), (10, True), (20, True), (21, False)),
)
def test_restart_state_is_deterministic_from_first_authoritative_count(
    queued: int, admitted: bool
) -> None:
    first = AcquisitionBackpressureController().observe(_pressure(queued))
    restarted = AcquisitionBackpressureController().observe(_pressure(queued))

    assert first == restarted
    assert restarted.admitted is admitted


def test_catalog_failure_is_fail_closed_until_low_watermark_recovery() -> None:
    controller = AcquisitionBackpressureController()

    failure = controller.unavailable()
    still_suppressed = controller.observe(_pressure(10))
    recovered = controller.observe(_pressure(9))

    assert failure.admitted is False
    assert failure.transition == "entered_unavailable"
    assert still_suppressed.admitted is False
    assert recovered.admitted is True


def test_pressure_counts_and_thresholds_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        AcquisitionQueuePressure(queued=-1, running=0)
    with pytest.raises(ValueError, match="below the entry"):
        AcquisitionBackpressureController(enter_above=20, exit_below=20)
