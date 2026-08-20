"""Foreground continuous acquisition with graceful Unix cancellation."""

from __future__ import annotations

import signal
from collections.abc import Sequence
from contextlib import contextmanager
from threading import Event, current_thread, main_thread
from time import monotonic
from types import FrameType
from typing import Any

from leo.cli.backend import AcquisitionCliBackend
from leo.cli.models import CaptureDataV1, RunDataV1
from leo.contracts.states import CaptureState


class ContinuousAcquisitionRunner:
    def __init__(self, backend: AcquisitionCliBackend, *, clock=monotonic) -> None:
        self.backend = backend
        self._clock = clock

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
