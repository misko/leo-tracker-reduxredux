from __future__ import annotations

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

    def analyze_scheduled_scanner(
        self, _capture: ScheduledScannerCapture
    ) -> ScannerReport:
        assert self.analyzed.wait(timeout=2.0)
        return cast(
            ScannerReport,
            SimpleNamespace(scan_id="scan-1", active_edges=("ch1-lower",)),
        )


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
    assert backend.events == ["dwell", "scan", "dwell"]


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
    assert backend.events == ["dwell", "scan", "dwell", "scan", "dwell"]


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
