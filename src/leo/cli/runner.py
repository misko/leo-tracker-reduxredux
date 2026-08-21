"""Foreground continuous acquisition with graceful Unix cancellation."""

from __future__ import annotations

import logging
import signal
from collections.abc import Sequence
from contextlib import contextmanager
from threading import Event, current_thread, main_thread
from time import monotonic
from types import FrameType
from typing import Any

from leo.acquisition import AcquisitionBackpressureController, AcquisitionQueuePressurePort
from leo.cli.backend import AcquisitionCliBackend
from leo.cli.models import CaptureDataV1, RunDataV1
from leo.contracts.states import CaptureState

logger = logging.getLogger(__name__)


class ContinuousAcquisitionRunner:
    def __init__(
        self,
        backend: AcquisitionCliBackend,
        *,
        queue_pressure: AcquisitionQueuePressurePort | None = None,
        backpressure: AcquisitionBackpressureController | None = None,
        clock=monotonic,
        zero_interval_backpressure_poll_seconds: float = 1.0,
    ) -> None:
        if zero_interval_backpressure_poll_seconds <= 0:
            raise ValueError("backpressure poll interval must be positive")
        self.backend = backend
        self.queue_pressure = backend if queue_pressure is None else queue_pressure
        self.backpressure = backpressure or AcquisitionBackpressureController()
        self._clock = clock
        self._zero_interval_backpressure_poll_seconds = zero_interval_backpressure_poll_seconds

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
                    )
                except KeyboardInterrupt:
                    cancel.set()
                    break
                count += 1
                if last.state is CaptureState.COMMITTED:
                    committed += 1
                elif last.state is CaptureState.DEGRADED:
                    degraded += 1
                else:
                    failed += 1
                if maximum_captures is not None and count >= maximum_captures:
                    return RunDataV1(
                        profile_name=profile_name,
                        stopped_reason="maximum_captures",
                        capture_count=count,
                        committed_count=committed,
                        degraded_count=degraded,
                        failed_count=failed,
                        last_capture=last,
                    )
                remaining = max(0.0, interval_seconds - (self._clock() - capture_started))
                if remaining and cancel.wait(remaining):
                    break
        return RunDataV1(
            profile_name=profile_name,
            stopped_reason="cancelled",
            capture_count=count,
            committed_count=committed,
            degraded_count=degraded,
            failed_count=failed,
            last_capture=last,
        )

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
