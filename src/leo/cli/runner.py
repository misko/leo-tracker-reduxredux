"""One foreground supervisor for scheduled recording and scanner capture."""

from __future__ import annotations

import logging
import signal
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, current_thread, main_thread
from time import monotonic
from types import FrameType
from typing import Any, cast

from leo.acquisition import (
    AcquisitionBackpressureController,
    AcquisitionQueuePressurePort,
    CaptureTaskKind,
)
from leo.cli.backend import (
    AcquisitionCliBackend,
    CliBackendError,
    ScheduledScannerPort,
)
from leo.cli.models import CaptureDataV1, ExitCode, RunDataV1
from leo.contracts.capture_control import (
    CaptureControlStateV1,
    CaptureDesiredState,
    CaptureObservedState,
)
from leo.contracts.states import CaptureState
from leo.scanner import ScannerReport

logger = logging.getLogger(__name__)

_RUNNING_CONTROL = CaptureControlStateV1(
    generation=0,
    desired_state=CaptureDesiredState.RUNNING,
    observed_state=CaptureObservedState.RUNNING,
    changed_utc_ns=0,
    operator_id="in-process",
    reason="backend has no durable capture authority",
)


class ContinuousAcquisitionRunner:
    """Schedule all radio work through one pause-aware supervisor."""

    def __init__(
        self,
        backend: AcquisitionCliBackend,
        *,
        queue_pressure: AcquisitionQueuePressurePort | None = None,
        backpressure: AcquisitionBackpressureController | None = None,
        clock=monotonic,
        zero_interval_backpressure_poll_seconds: float = 1.0,
        capture_control_poll_seconds: float = 0.25,
        radio_busy_retry_seconds: float = 1.0,
    ) -> None:
        if zero_interval_backpressure_poll_seconds <= 0:
            raise ValueError("backpressure poll interval must be positive")
        if capture_control_poll_seconds <= 0 or radio_busy_retry_seconds <= 0:
            raise ValueError("capture supervisor poll intervals must be positive")
        self.backend = backend
        self.queue_pressure = backend if queue_pressure is None else queue_pressure
        self.backpressure = backpressure or AcquisitionBackpressureController()
        self._clock = clock
        self._zero_interval_backpressure_poll_seconds = zero_interval_backpressure_poll_seconds
        self._capture_control_poll_seconds = capture_control_poll_seconds
        self._radio_busy_retry_seconds = radio_busy_retry_seconds

    def run(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
    ) -> RunDataV1:
        if interval_seconds < 0:
            raise ValueError("capture interval cannot be negative")
        if maximum_captures is not None and maximum_captures <= 0:
            raise ValueError("maximum captures must be positive")
        scanner = _scheduled_scanner(self.backend)
        control_reader = getattr(self.backend, "capture_control_snapshot", None)
        if scanner is None and not callable(control_reader):
            return self._run_capture_only(
                profile_name,
                radio_ids=radio_ids,
                extra_tags=extra_tags,
                interval_seconds=interval_seconds,
                maximum_captures=maximum_captures,
                cancel=cancel,
            )
        return self._run_supervised(
            profile_name,
            radio_ids=radio_ids,
            extra_tags=extra_tags,
            interval_seconds=interval_seconds,
            maximum_captures=maximum_captures,
            cancel=cancel,
            scanner=scanner,
        )

    def _run_capture_only(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
    ) -> RunDataV1:
        """Compatibility path for small fakes without capture-control ports."""

        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        with cancellation_signals(cancel):
            while not cancel.is_set():
                if not self._admit_scheduled_dwell():
                    delay = (
                        interval_seconds
                        if interval_seconds > 0
                        else self._zero_interval_backpressure_poll_seconds
                    )
                    if cancel.wait(delay):
                        break
                    continue
                capture_started = self._clock()
                try:
                    last = self.backend.capture_once(
                        profile_name,
                        radio_ids=radio_ids,
                        session_id=None,
                        extra_tags=extra_tags,
                        cancel=cancel,
                        task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                    )
                except KeyboardInterrupt:
                    cancel.set()
                    break
                count, committed, degraded, failed = _record_capture_result(
                    last,
                    count=count,
                    committed=committed,
                    degraded=degraded,
                    failed=failed,
                )
                if maximum_captures is not None and count >= maximum_captures:
                    return _run_result(
                        profile_name,
                        "maximum_captures",
                        count,
                        committed,
                        degraded,
                        failed,
                        last,
                    )
                remaining = max(0.0, interval_seconds - (self._clock() - capture_started))
                if remaining and cancel.wait(remaining):
                    break
        return _run_result(
            profile_name,
            "cancelled",
            count,
            committed,
            degraded,
            failed,
            last,
        )

    def _run_supervised(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
        scanner: ScheduledScannerPort | None,
    ) -> RunDataV1:
        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        now = self._clock()
        next_capture_due = now
        scanner_configuration = scanner.scanner_schedule() if scanner is not None else None
        next_scanner_due = (
            None
            if scanner_configuration is None
            else now + scanner_configuration.interval_seconds
        )
        pause_observed = False
        analysis: Future[ScannerReport] | None = None

        with cancellation_signals(cancel), ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="leo-scanner-analysis",
        ) as analysis_pool:
            while not cancel.is_set():
                analysis = _reap_scanner_analysis(analysis)
                control = self._capture_control_snapshot()
                if control is None or control.desired_state is CaptureDesiredState.PAUSED:
                    pause_observed = True
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue

                now = self._clock()
                if pause_observed:
                    next_capture_due = now
                    next_scanner_due = (
                        None
                        if scanner_configuration is None
                        else now + scanner_configuration.interval_seconds
                    )
                    pause_observed = False

                if now >= next_capture_due:
                    if not self._admit_scheduled_dwell():
                        delay = (
                            interval_seconds
                            if interval_seconds > 0
                            else self._zero_interval_backpressure_poll_seconds
                        )
                        next_capture_due = now + delay
                        continue
                    capture_started = now
                    try:
                        last = self.backend.capture_once(
                            profile_name,
                            radio_ids=radio_ids,
                            session_id=None,
                            extra_tags=extra_tags,
                            cancel=cancel,
                            task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                        )
                    except CliBackendError as error:
                        if error.exit_code == ExitCode.CONFLICT:
                            logger.info("scheduled_capture_deferred reason=%s", error)
                            next_capture_due = self._clock() + self._radio_busy_retry_seconds
                            continue
                        return _run_result(
                            profile_name,
                            "error",
                            count,
                            committed,
                            degraded,
                            failed,
                            last,
                            error=str(error),
                        )
                    count, committed, degraded, failed = _record_capture_result(
                        last,
                        count=count,
                        committed=committed,
                        degraded=degraded,
                        failed=failed,
                    )
                    if maximum_captures is not None and count >= maximum_captures:
                        return _run_result(
                            profile_name,
                            "maximum_captures",
                            count,
                            committed,
                            degraded,
                            failed,
                            last,
                        )
                    next_capture_due = (
                        capture_started + interval_seconds
                        if interval_seconds > 0
                        else self._clock()
                    )
                    continue

                if (
                    scanner is not None
                    and scanner_configuration is not None
                    and next_scanner_due is not None
                    and now >= next_scanner_due
                ):
                    scheduled_due = next_scanner_due
                    while next_scanner_due <= now:
                        next_scanner_due += scanner_configuration.interval_seconds
                    lateness = now - scheduled_due
                    if lateness > scanner_configuration.maximum_lateness_seconds:
                        logger.info(
                            "scheduled_scanner_skipped reason=late lateness_seconds=%.3f",
                            lateness,
                        )
                    elif analysis is not None:
                        logger.info("scheduled_scanner_skipped reason=analysis_busy")
                    else:
                        try:
                            captured = scanner.capture_scheduled_scanner()
                        except CliBackendError as error:
                            level = (
                                logging.INFO
                                if error.exit_code == ExitCode.CONFLICT
                                else logging.ERROR
                            )
                            logger.log(level, "scheduled_scanner_not_started reason=%s", error)
                        else:
                            analysis = analysis_pool.submit(
                                scanner.analyze_scheduled_scanner,
                                captured,
                            )
                    continue

                due = [next_capture_due]
                if next_scanner_due is not None:
                    due.append(next_scanner_due)
                delay = max(0.0, min(due) - now)
                if delay and cancel.wait(delay):
                    break

        return _run_result(
            profile_name,
            "cancelled",
            count,
            committed,
            degraded,
            failed,
            last,
        )

    def _capture_control_snapshot(self) -> CaptureControlStateV1 | None:
        reader = getattr(self.backend, "capture_control_snapshot", None)
        if not callable(reader):
            return _RUNNING_CONTROL
        try:
            return cast(CaptureControlStateV1, reader())
        except Exception as error:
            logger.error(
                "capture_control_unavailable suppressed=true error_type=%s error=%s",
                type(error).__name__,
                error,
            )
            return None

    def _admit_scheduled_dwell(self) -> bool:
        try:
            pressure = self.queue_pressure.acquisition_queue_pressure()
        except Exception as error:
            decision = self.backpressure.unavailable()
            logger.warning(
                "acquisition_backpressure queued=unknown running=unknown "
                "suppressed=true transition=%s enter_above=%d exit_below=%d "
                "error_type=%s error=%s",
                decision.transition,
                self.backpressure.enter_above,
                self.backpressure.exit_below,
                type(error).__name__,
                error,
            )
            return False
        decision = self.backpressure.observe(pressure)
        logger.info(
            "acquisition_backpressure queued=%d running=%d suppressed=%s transition=%s "
            "enter_above=%d exit_below=%d",
            pressure.queued,
            pressure.running,
            str(decision.suppressed).lower(),
            decision.transition,
            self.backpressure.enter_above,
            self.backpressure.exit_below,
        )
        return decision.admitted


@contextmanager
def cancellation_signals(cancel: Event):
    """Translate SIGINT/SIGTERM into the same cooperative capture event."""

    if current_thread() is not main_thread():
        yield
        return
    previous: dict[signal.Signals, Any] = {}

    def handle(_signal: int, _frame: FrameType | None) -> None:
        cancel.set()

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handle)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _scheduled_scanner(backend: AcquisitionCliBackend) -> ScheduledScannerPort | None:
    required = (
        "scanner_schedule",
        "capture_scheduled_scanner",
        "analyze_scheduled_scanner",
    )
    if all(callable(getattr(backend, name, None)) for name in required):
        return cast(ScheduledScannerPort, backend)
    return None


def _reap_scanner_analysis(
    future: Future[ScannerReport] | None,
) -> Future[ScannerReport] | None:
    if future is None or not future.done():
        return future
    try:
        report = future.result()
    except Exception:
        logger.exception("scheduled_scanner_analysis_failed")
    else:
        logger.info(
            "scheduled_scanner_completed scan_id=%s active_edges=%d",
            report.scan_id,
            len(report.active_edges),
        )
    return None


def _record_capture_result(
    result: CaptureDataV1,
    *,
    count: int,
    committed: int,
    degraded: int,
    failed: int,
) -> tuple[int, int, int, int]:
    count += 1
    if result.state is CaptureState.COMMITTED:
        committed += 1
    elif result.state is CaptureState.DEGRADED:
        degraded += 1
    else:
        failed += 1
    return count, committed, degraded, failed


def _run_result(
    profile_name: str,
    reason: str,
    count: int,
    committed: int,
    degraded: int,
    failed: int,
    last: CaptureDataV1 | None,
    *,
    error: str | None = None,
) -> RunDataV1:
    return RunDataV1(
        profile_name=profile_name,
        stopped_reason=cast(Any, reason),
        capture_count=count,
        committed_count=committed,
        degraded_count=degraded,
        failed_count=failed,
        last_capture=last,
        error=error,
    )
