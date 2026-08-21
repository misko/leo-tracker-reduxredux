from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from typing import cast

from leo.acquisition import AcquisitionQueuePressure
from leo.cli.backend import (
    AcquisitionCliBackend,
    ScheduledScannerCapture,
    ScheduledScannerConfiguration,
)
from leo.cli.models import CaptureDataV1
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.contracts.capture_control import (
    CaptureControlStateV1,
    CaptureDesiredState,
    CaptureObservedState,
)
from leo.contracts.states import CaptureState
from leo.scanner import ScannerReport


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _AdvancingCancel:
    def __init__(self, clock: _Clock, *, on_wait=None) -> None:
        self.clock = clock
        self.cancelled = False
        self.on_wait = on_wait

    def is_set(self) -> bool:
        return self.cancelled

    def wait(self, timeout: float) -> bool:
        self.clock.now += timeout
        if self.on_wait is not None:
            self.on_wait()
        return self.cancelled

    def set(self) -> None:
        self.cancelled = True


def _control(desired: CaptureDesiredState) -> CaptureControlStateV1:
    observed = (
        CaptureObservedState.RUNNING
        if desired is CaptureDesiredState.RUNNING
        else CaptureObservedState.PAUSED
    )
    return CaptureControlStateV1(
        generation=1,
        desired_state=desired,
        observed_state=observed,
        changed_utc_ns=1,
        operator_id="test",
        reason="test state",
    )


class _SupervisorBackend:
    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.control = _control(CaptureDesiredState.RUNNING)
        self.capture_times: list[float] = []
        self.scanner_capture_times: list[float] = []
        self.events: list[str] = []
        self.analyzed = Event()

    def reconcile_scanner_recordings(self) -> None:
        self.events.append("reconcile")

    def capture_control_snapshot(self) -> CaptureControlStateV1:
        return self.control

    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
        return AcquisitionQueuePressure(queued=0, running=0)

    def scanner_schedule(self) -> ScheduledScannerConfiguration:
        return ScheduledScannerConfiguration(
            interval_seconds=5.0,
            maximum_lateness_seconds=1.0,
        )

    def capture_once(self, profile_name: str, **_kwargs) -> CaptureDataV1:
        self.capture_times.append(self.clock())
        self.events.append("dwell")
        return CaptureDataV1(
            session_id=f"capture-{len(self.capture_times)}",
            state=CaptureState.COMMITTED,
            radio_ids=("radio-a",),
            profile_name=profile_name,
            raw_iq_bytes=32,
            required_free_bytes=32,
            available_free_bytes=1024,
        )

    def capture_scheduled_scanner(self) -> ScheduledScannerCapture:
        self.scanner_capture_times.append(self.clock())
        self.events.append("scan")
        return cast(ScheduledScannerCapture, SimpleNamespace())

    def analyze_scheduled_scanner(self, _capture: ScheduledScannerCapture) -> ScannerReport:
        assert self.analyzed.wait(timeout=2.0)
        return cast(
            ScannerReport,
            SimpleNamespace(scan_id="scan-1", active_edges=("ch1-lower",)),
        )


class _DurableSupervisorBackend(_SupervisorBackend):
    def __init__(self, clock: _Clock) -> None:
        super().__init__(clock)
        self.operations: list[SimpleNamespace] = []
        self.next_id = 1

    def enqueue_acquisition_operation(
        self,
        *,
        operation_key,
        kind,
        payload,
        scheduled_for,
        coalesce_pending_kind=False,
    ):
        existing = next(
            (item for item in self.operations if item.operation_key == operation_key),
            None,
        )
        if existing is not None:
            return existing
        if coalesce_pending_kind:
            for queued in self.operations:
                if queued.kind == kind and queued.state == "pending":
                    queued.state = "cancelled"
        item = SimpleNamespace(
            operation_id=self.next_id,
            operation_key=operation_key,
            kind=kind,
            payload=payload,
            scheduled_for=scheduled_for,
            state="pending",
            worker_id=None,
            attempt_count=0,
        )
        self.next_id += 1
        self.operations.append(item)
        return item

    def active_acquisition_operations(self, *, limit=200):
        active = tuple(item for item in self.operations if item.state in {"pending", "leased"})
        return active[:limit]

    def claim_acquisition_operation(self, *, worker_id, lease_for):
        if any(item.state == "leased" for item in self.operations):
            return None
        item = next((item for item in self.operations if item.state == "pending"), None)
        if item is None:
            return None
        item.state = "leased"
        item.worker_id = worker_id
        item.attempt_count += 1
        return SimpleNamespace(
            operation_id=item.operation_id,
            operation_key=item.operation_key,
            kind=item.kind,
            payload=item.payload,
            scheduled_for=item.scheduled_for,
        )

    def complete_acquisition_operation(self, *, operation_id, worker_id, outcome):
        item = next(item for item in self.operations if item.operation_id == operation_id)
        assert item.worker_id == worker_id
        item.state = "succeeded"
        item.worker_id = None

    def fail_acquisition_operation(
        self,
        *,
        operation_id,
        worker_id,
        error,
        retryable,
        retry_after=timedelta(0),
    ):
        item = next(item for item in self.operations if item.operation_id == operation_id)
        item.state = "pending" if retryable else "failed"
        item.worker_id = None
        return item.state

    def reclaim_expired_acquisition_operations(self):
        return ()


def test_supervisor_releases_scanner_path_for_ordinary_capture_during_analysis() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)

    original_capture = backend.capture_once

    def capture_and_release_analysis(profile_name: str, **kwargs) -> CaptureDataV1:
        result = original_capture(profile_name, **kwargs)
        if len(backend.capture_times) == 2:
            backend.analyzed.set()
        return result

    backend.capture_once = capture_and_release_analysis  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=2,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 2
    assert backend.capture_times == [0.0, 10.0]
    assert backend.scanner_capture_times == [0.0]
    assert backend.events == ["reconcile", "dwell", "scan", "dwell"]


def test_supervisor_runs_one_scan_after_each_eligible_dwell() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)
    backend.analyzed.set()
    analyses = 0

    def analyze(_capture: ScheduledScannerCapture) -> ScannerReport:
        nonlocal analyses
        analyses += 1
        return cast(
            ScannerReport,
            SimpleNamespace(scan_id=f"scan-{analyses}", active_edges=()),
        )

    backend.analyze_scheduled_scanner = analyze  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=3,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 3
    assert backend.events == ["reconcile", "dwell", "scan", "dwell", "scan", "dwell"]


def test_durable_supervisor_persists_and_alternates_dwell_scan_operations() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=3,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 3
    assert backend.events == ["reconcile", "dwell", "scan", "dwell", "scan", "dwell"]
    assert [item.kind for item in backend.operations] == [
        "scheduled_recording",
        "scanner_sweep",
        "scheduled_recording",
        "scanner_sweep",
        "scheduled_recording",
        "scanner_sweep",
    ]


def test_backpressure_retains_due_dwell_until_admission_recovers() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    observations = 0
    pending_seen = False

    def pressure() -> AcquisitionQueuePressure:
        nonlocal observations, pending_seen
        observations += 1
        pending_seen = pending_seen or any(
            item.kind == "scheduled_recording" and item.state == "pending"
            for item in backend.operations
        )
        return AcquisitionQueuePressure(queued=31 if observations == 1 else 0, running=0)

    backend.acquisition_queue_pressure = pressure  # type: ignore[method-assign]
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert pending_seen
    assert observations >= 2
    assert summary.capture_count == 1
    assert backend.events == ["reconcile", "dwell"]


def test_durable_supervisor_coalesces_missed_cadence_slots() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    backend.control = _control(CaptureDesiredState.PAUSED)

    polls = 0

    def advance_while_paused() -> None:
        nonlocal polls
        polls += 1
        clock.now += 10.0
        if polls == 4:
            backend.control = _control(CaptureDesiredState.RUNNING)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
        capture_control_poll_seconds=0.25,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock, on_wait=advance_while_paused)),
    )

    queued_dwells = [
        item
        for item in backend.operations
        if item.kind == "scheduled_recording" and item.state == "pending"
    ]
    assert summary.capture_count == 1
    assert len(queued_dwells) <= 1


def test_pause_fences_both_schedules_and_resume_starts_fresh_cadence() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)
    backend.control = _control(CaptureDesiredState.PAUSED)

    def resume_after_poll() -> None:
        backend.control = _control(CaptureDesiredState.RUNNING)

    cancel = _AdvancingCancel(clock, on_wait=resume_after_poll)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        capture_control_poll_seconds=0.25,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, cancel),
    )

    assert summary.capture_count == 1
    assert backend.capture_times == [0.25]
    assert backend.scanner_capture_times == []


def test_durable_pause_preserves_due_operation_until_resume() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.control = _control(CaptureDesiredState.PAUSED)
    pending_while_paused = False

    def resume_after_observing_pending() -> None:
        nonlocal pending_while_paused
        pending_while_paused = any(
            item.kind == "scheduled_recording"
            and item.state == "pending"
            and item.attempt_count == 0
            for item in backend.operations
        )
        backend.control = _control(CaptureDesiredState.RUNNING)

    cancel = _AdvancingCancel(clock, on_wait=resume_after_observing_pending)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        capture_control_poll_seconds=0.25,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, cancel),
    )

    assert pending_while_paused
    assert summary.capture_count == 1
    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert dwell.state == "succeeded"
    assert dwell.attempt_count == 1
