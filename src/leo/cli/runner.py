"""One foreground supervisor for scheduled recording and scanner capture."""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import socket
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
from leo.scanner import ScannerCaptureBurstReportLike

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
        utc_now=lambda: datetime.now(UTC),
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
        self._utc_now = utc_now

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
        if scanner is not None and _durable_acquisition_queue(self.backend):
            return self._run_durable_supervised(
                profile_name,
                radio_ids=radio_ids,
                extra_tags=extra_tags,
                interval_seconds=interval_seconds,
                maximum_captures=maximum_captures,
                cancel=cancel,
                scanner=scanner,
            )
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

    def _run_durable_supervised(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
        scanner: ScheduledScannerPort,
    ) -> RunDataV1:
        """Persist cadence ticks before admission and dispatch one global lease."""

        queue = cast(Any, self.backend)
        worker_id = f"capture-supervisor:{socket.gethostname()}:{os.getpid()}"
        lease_for = timedelta(minutes=10)
        scanner_configuration = scanner.scanner_schedule()
        if scanner_configuration is not None:
            scanner.reconcile_scanner_recordings()
        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        next_due = _cadence_floor(self._utc_now(), interval_seconds)

        queue.reclaim_expired_acquisition_operations()
        with cancellation_signals(cancel):
            while not cancel.is_set():
                now_utc = self._utc_now()
                if now_utc >= next_due:
                    key = _scheduled_dwell_key(profile_name, next_due, interval_seconds)
                    queue.enqueue_acquisition_operation(
                        operation_key=key,
                        kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                        payload={
                            "profile_name": profile_name,
                            "radio_ids": list(radio_ids),
                            "extra_tags": list(extra_tags),
                        },
                        scheduled_for=next_due,
                        coalesce_pending_kind=True,
                    )
                    next_due = (
                        next_due + timedelta(seconds=interval_seconds)
                        if interval_seconds > 0
                        else now_utc + timedelta(microseconds=1)
                    )

                control = self._capture_control_snapshot()
                if control is None or control.desired_state is CaptureDesiredState.PAUSED:
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue

                active = queue.active_acquisition_operations(limit=1)
                if not active:
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue
                head = active[0]
                if head.state == "leased":
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    queue.reclaim_expired_acquisition_operations()
                    continue
                if (
                    head.kind == CaptureTaskKind.SCHEDULED_RECORDING.value
                    and not self._admit_scheduled_dwell()
                ):
                    # Backpressure suppresses execution, not the durable intent.
                    if cancel.wait(self._zero_interval_backpressure_poll_seconds):
                        break
                    continue

                lease = queue.claim_acquisition_operation(worker_id=worker_id, lease_for=lease_for)
                if lease is None:
                    if cancel.wait(self._radio_busy_retry_seconds):
                        break
                    continue
                try:
                    if lease.kind == CaptureTaskKind.SCHEDULED_RECORDING.value:
                        payload = lease.payload
                        last = self.backend.capture_once(
                            str(payload["profile_name"]),
                            radio_ids=tuple(str(item) for item in payload["radio_ids"]),
                            session_id=None,
                            extra_tags=tuple(str(item) for item in payload["extra_tags"]),
                            cancel=cancel,
                            task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                        )
                        count, committed, degraded, failed = _record_capture_result(
                            last,
                            count=count,
                            committed=committed,
                            degraded=degraded,
                            failed=failed,
                        )
                        queue.complete_acquisition_operation(
                            operation_id=lease.operation_id,
                            worker_id=worker_id,
                            outcome=f"capture {last.session_id} {last.state.value}",
                        )
                        if scanner_configuration is not None and last.state in {
                            CaptureState.COMMITTED,
                            CaptureState.DEGRADED,
                        }:
                            queue.enqueue_acquisition_operation(
                                operation_key=f"scan-after:{lease.operation_key}",
                                kind=CaptureTaskKind.SCANNER_SWEEP.value,
                                payload={"after_operation_id": lease.operation_id},
                                # Place the scan immediately after its parent
                                # even when several overdue cadence slots were
                                # materialized during backpressure.
                                scheduled_for=lease.scheduled_for + timedelta(microseconds=1),
                                coalesce_pending_kind=True,
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
                    elif lease.kind == CaptureTaskKind.SCANNER_SWEEP.value:
                        captured = scanner.capture_scheduled_scanner()
                        burst = scanner.analyze_scheduled_scanner(captured)
                        queue.complete_acquisition_operation(
                            operation_id=lease.operation_id,
                            worker_id=worker_id,
                            outcome=(
                                f"scan burst {burst.burst_id} published; "
                                f"scans={len(burst.reports)}; "
                                f"active_edges={burst.active_edge_count}"
                            ),
                        )
                    else:
                        queue.fail_acquisition_operation(
                            operation_id=lease.operation_id,
                            worker_id=worker_id,
                            error=f"supervisor cannot dispatch kind {lease.kind}",
                            retryable=False,
                        )
                except CliBackendError as error:
                    retryable = error.exit_code == ExitCode.CONFLICT
                    queue.fail_acquisition_operation(
                        operation_id=lease.operation_id,
                        worker_id=worker_id,
                        error=str(error),
                        retryable=retryable,
                        retry_after=timedelta(seconds=self._radio_busy_retry_seconds),
                    )
                    if not retryable:
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
                except Exception as error:
                    queue.fail_acquisition_operation(
                        operation_id=lease.operation_id,
                        worker_id=worker_id,
                        error=f"{type(error).__name__}: {error}",
                        retryable=True,
                        retry_after=timedelta(seconds=self._radio_busy_retry_seconds),
                    )
                    logger.exception("durable_acquisition_operation_failed")

        return _run_result(profile_name, "cancelled", count, committed, degraded, failed, last)

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
        if scanner is not None and scanner_configuration is not None:
            scanner.reconcile_scanner_recordings()
        next_scanner_due: float | None = None
        last_scanner_capture: float | None = None
        pause_observed = False
        analysis: Future[ScannerCaptureBurstReportLike] | None = None

        with (
            cancellation_signals(cancel),
            ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="leo-scanner-analysis",
            ) as analysis_pool,
        ):
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
                    next_scanner_due = None
                    last_scanner_capture = None
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
                    if scanner_configuration is not None and last.state in {
                        CaptureState.COMMITTED,
                        CaptureState.DEGRADED,
                    }:
                        captured_at = self._clock()
                        next_scanner_due = (
                            captured_at
                            if last_scanner_capture is None
                            else max(
                                captured_at,
                                last_scanner_capture + scanner_configuration.interval_seconds,
                            )
                        )
                    continue

                if (
                    scanner is not None
                    and scanner_configuration is not None
                    and next_scanner_due is not None
                    and now >= next_scanner_due
                ):
                    lateness = now - next_scanner_due
                    if lateness > scanner_configuration.maximum_lateness_seconds:
                        logger.warning(
                            "scheduled_scanner_late lateness_seconds=%.3f",
                            lateness,
                        )
                    if analysis is not None:
                        next_scanner_due = now + self._radio_busy_retry_seconds
                        logger.info("scheduled_scanner_deferred reason=analysis_busy")
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
                            next_scanner_due = now + self._radio_busy_retry_seconds
                        else:
                            last_scanner_capture = now
                            next_scanner_due = None
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
        "reconcile_scanner_recordings",
        "scanner_schedule",
        "capture_scheduled_scanner",
        "analyze_scheduled_scanner",
    )
    if all(callable(getattr(backend, name, None)) for name in required):
        return cast(ScheduledScannerPort, backend)
    return None


def _durable_acquisition_queue(backend: AcquisitionCliBackend) -> bool:
    required = (
        "enqueue_acquisition_operation",
        "active_acquisition_operations",
        "claim_acquisition_operation",
        "complete_acquisition_operation",
        "fail_acquisition_operation",
        "reclaim_expired_acquisition_operations",
    )
    return all(callable(getattr(backend, name, None)) for name in required)


def _cadence_floor(now: datetime, interval_seconds: float) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("acquisition scheduling clock must be timezone-aware")
    canonical = now.astimezone(UTC)
    if interval_seconds == 0:
        return canonical
    slot = int(canonical.timestamp() // interval_seconds)
    return datetime.fromtimestamp(slot * interval_seconds, tz=UTC)


def _scheduled_dwell_key(
    profile_name: str, scheduled_for: datetime, interval_seconds: float
) -> str:
    profile_digest = hashlib.sha256(profile_name.encode("utf-8")).hexdigest()[:16]
    if interval_seconds == 0:
        return (
            f"scheduled-dwell:{profile_digest}:{scheduled_for.isoformat(timespec='microseconds')}"
        )
    return f"scheduled-dwell:{profile_digest}:{scheduled_for.isoformat(timespec='seconds')}"


def _reap_scanner_analysis(
    future: Future[ScannerCaptureBurstReportLike] | None,
) -> Future[ScannerCaptureBurstReportLike] | None:
    if future is None or not future.done():
        return future
    try:
        burst = future.result()
    except Exception:
        logger.exception("scheduled_scanner_analysis_failed")
    else:
        logger.info(
            "scheduled_scanner_completed burst_id=%s scans=%d active_edges=%d",
            burst.burst_id,
            len(burst.reports),
            burst.active_edge_count,
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
