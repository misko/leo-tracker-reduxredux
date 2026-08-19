"""Injectable time boundary for deterministic synchronization tests."""

from __future__ import annotations

import time
from threading import Event
from typing import Protocol

from leo.acquisition.errors import AcquisitionCancelled


class AcquisitionClock(Protocol):
    def utc_ns(self) -> int: ...

    def monotonic_ns(self) -> int: ...

    def sleep(self, seconds: float, cancel: Event) -> None: ...

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int: ...


class SystemAcquisitionClock:
    """Wall/monotonic clock with cancellation-aware bounded waits."""

    def utc_ns(self) -> int:
        return time.time_ns()

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def sleep(self, seconds: float, cancel: Event) -> None:
        if seconds < 0:
            raise ValueError("sleep duration cannot be negative")
        deadline = self.monotonic_ns() + round(seconds * 1_000_000_000)
        self.wait_until(deadline, cancel)

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int:
        if target_monotonic_ns < 0:
            raise ValueError("monotonic target cannot be negative")
        while True:
            if cancel.is_set():
                raise AcquisitionCancelled("capture cancelled")
            remaining_ns = target_monotonic_ns - self.monotonic_ns()
            if remaining_ns <= 0:
                return self.monotonic_ns()
            cancel.wait(min(remaining_ns / 1_000_000_000, 0.05))
