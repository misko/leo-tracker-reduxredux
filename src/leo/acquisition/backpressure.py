"""Pure queue-pressure admission policy for scheduled acquisition dwells."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class AcquisitionQueuePressure:
    """Authoritative point-in-time processing pressure seen before one dwell."""

    queued: int
    running: int

    def __post_init__(self) -> None:
        if self.queued < 0 or self.running < 0:
            raise ValueError("acquisition queue pressure counts cannot be negative")


class AcquisitionQueuePressurePort(Protocol):
    """Narrow read-only port; implementations return authoritative queue counts."""

    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure: ...


BackpressureTransition = Literal[
    "none",
    "entered_high_watermark",
    "entered_unavailable",
    "exited_low_watermark",
]


@dataclass(frozen=True, slots=True)
class AcquisitionAdmissionDecision:
    admitted: bool
    suppressed: bool
    transition: BackpressureTransition
    reason: str


class AcquisitionBackpressureController:
    """Deterministic 20/10 queue hysteresis with fail-closed observations."""

    def __init__(self, *, enter_above: int = 20, exit_below: int = 10) -> None:
        if enter_above < 0 or exit_below < 0:
            raise ValueError("acquisition backpressure thresholds cannot be negative")
        if exit_below >= enter_above:
            raise ValueError("exit threshold must be below the entry threshold")
        self.enter_above = enter_above
        self.exit_below = exit_below
        self._suppressed: bool | None = None

    @property
    def suppressed(self) -> bool | None:
        """Return ``None`` until the first authoritative observation or failure."""

        return self._suppressed

    def observe(self, pressure: AcquisitionQueuePressure) -> AcquisitionAdmissionDecision:
        transition: BackpressureTransition = "none"
        if self._suppressed is None:
            if pressure.queued > self.enter_above:
                self._suppressed = True
                transition = "entered_high_watermark"
            else:
                # Controller state is deliberately not persisted alongside raw
                # acquisition. Every restart begins active and applies the same
                # entry boundary to the first authoritative observation.
                self._suppressed = False
        elif not self._suppressed and pressure.queued > self.enter_above:
            self._suppressed = True
            transition = "entered_high_watermark"
        elif self._suppressed and pressure.queued < self.exit_below:
            self._suppressed = False
            transition = "exited_low_watermark"
        return AcquisitionAdmissionDecision(
            admitted=not self._suppressed,
            suppressed=self._suppressed,
            transition=transition,
            reason=(
                "queued processing work is within the acquisition admission band"
                if not self._suppressed
                else "scheduled acquisition is suppressed by processing queue pressure"
            ),
        )

    def unavailable(self) -> AcquisitionAdmissionDecision:
        transition: BackpressureTransition = "none"
        if self._suppressed is not True:
            transition = "entered_unavailable"
        self._suppressed = True
        return AcquisitionAdmissionDecision(
            admitted=False,
            suppressed=True,
            transition=transition,
            reason="scheduled acquisition is suppressed because queue pressure is unavailable",
        )
