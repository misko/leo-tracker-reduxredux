from __future__ import annotations

from collections.abc import Iterable
from threading import Event
from typing import cast

from leo.acquisition import AcquisitionQueuePressure
from leo.cli.backend import AcquisitionCliBackend
from leo.cli.models import CaptureDataV1
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.contracts.states import CaptureState


class _PressurePort:
    def __init__(self, queued: Iterable[int]) -> None:
        self._queued = iter(queued)
        self.observations: list[int] = []

    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
        queued = next(self._queued)
        self.observations.append(queued)
        return AcquisitionQueuePressure(queued=queued, running=999)


class _CatalogFailurePort:
    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
        raise RuntimeError("catalog unavailable")


class _CancelOnWait:
    def __init__(self) -> None:
        self.cancelled = False

    def is_set(self) -> bool:
        return self.cancelled

    def wait(self, _timeout: float) -> bool:
        self.cancelled = True
        return True

    def set(self) -> None:
        self.cancelled = True


class _CaptureBackend:
    def __init__(self, *, on_capture=None) -> None:
        self.session_ids: list[str] = []
        self.on_capture = on_capture

    def capture_once(self, profile_name: str, **_kwargs) -> CaptureDataV1:
        if self.on_capture is not None:
            self.on_capture()
        session_id = f"capture-{len(self.session_ids) + 1}"
        self.session_ids.append(session_id)
        return CaptureDataV1(
            session_id=session_id,
            state=CaptureState.COMMITTED,
            radio_ids=("radio-a",),
            profile_name=profile_name,
            raw_iq_bytes=32,
            required_free_bytes=32,
            available_free_bytes=1024,
        )


def _run(
    backend: _CaptureBackend,
    pressure,
    *,
    maximum_captures: int,
    cancel: Event | None = None,
):
    return ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        queue_pressure=pressure,
        zero_interval_backpressure_poll_seconds=0.001,
    ).run(
        "tiny-test",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=0,
        maximum_captures=maximum_captures,
        cancel=cancel or Event(),
    )


def test_suppression_creates_no_capture_session_or_spool_placeholder() -> None:
    backend = _CaptureBackend()
    cancel = cast(Event, _CancelOnWait())

    summary = _run(backend, _PressurePort((21,)), maximum_captures=1, cancel=cancel)

    assert summary.capture_count == 0
    assert backend.session_ids == []


def test_suppression_then_recovery_admits_oldest_schedule_without_phantom_capture() -> None:
    backend = _CaptureBackend()
    pressure = _PressurePort((0, 21, 10, 9))

    summary = _run(backend, pressure, maximum_captures=2)

    assert pressure.observations == [0, 21, 10, 9]
    assert backend.session_ids == ["capture-1", "capture-2"]
    assert summary.capture_count == 2
    assert summary.committed_count == 2


def test_catalog_failure_is_fail_closed_and_structurally_logged(caplog) -> None:
    backend = _CaptureBackend()

    summary = _run(
        backend,
        _CatalogFailurePort(),
        maximum_captures=1,
        cancel=cast(Event, _CancelOnWait()),
    )

    assert summary.capture_count == 0
    assert backend.session_ids == []
    assert "queued=unknown running=unknown suppressed=true" in caplog.text
    assert "enter_above=20 exit_below=10" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


def test_pressure_change_during_active_dwell_never_interrupts_publication() -> None:
    pressure = _PressurePort((0, 21, 9))
    dwell_completed = False

    def complete_dwell() -> None:
        nonlocal dwell_completed
        # The next catalog observation is already overloaded, but the admitted
        # capture publishes before the runner asks for that observation.
        dwell_completed = True

    backend = _CaptureBackend(on_capture=complete_dwell)

    summary = _run(backend, pressure, maximum_captures=2)

    assert dwell_completed is True
    assert backend.session_ids == ["capture-1", "capture-2"]
    assert pressure.observations == [0, 21, 9]
    assert summary.committed_count == 2


def test_point_in_time_admission_race_is_bounded_to_one_dwell() -> None:
    pressure = _PressurePort((20, 21, 9))
    backend = _CaptureBackend()

    summary = _run(backend, pressure, maximum_captures=2)

    # Twenty admits exactly one dwell. The next authoritative observation at
    # 21 suppresses; no speculative second session is created before recovery.
    assert pressure.observations == [20, 21, 9]
    assert backend.session_ids == ["capture-1", "capture-2"]
    assert summary.capture_count == 2
