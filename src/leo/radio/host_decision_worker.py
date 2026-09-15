"""Bounded host computation only; this worker never owns or calls an IIO object."""

from __future__ import annotations

import dataclasses
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt
from pluto_plus.host_adaptive_hop import HostDecisionOutcome, HostFeedbackV1

from leo.analysis.host_decision import HostDecisionEvidence


class HostDecisionEngine(Protocol):
    def run(
        self, iq: npt.NDArray[np.int16], *, edge: Literal["lower", "upper"]
    ) -> HostDecisionEvidence: ...
    def close(self) -> None: ...


@dataclasses.dataclass(frozen=True, slots=True)
class HostDecisionWorkResult:
    source: HostFeedbackV1
    evidence: HostDecisionEvidence | None
    failure: str | None
    submitted_ns: int
    started_ns: int
    completed_ns: int

    def feedback(self, now_ns: int) -> HostFeedbackV1:
        """Expired/failed work stays unknown; retain computed evidence separately."""
        evidence = self.evidence
        if evidence is None or not 0 <= now_ns - self.submitted_ns <= 1_000_000_000:
            return self.source
        return dataclasses.replace(
            self.source,
            outcome={
                "unknown": HostDecisionOutcome.UNKNOWN,
                "detected": HostDecisionOutcome.DETECTED,
                "not_detected": HostDecisionOutcome.NOT_DETECTED,
            }[evidence.outcome],
            healthy=1,
            screen_mask=evidence.screen_mask,
            confirmation_mask=evidence.confirmation_mask,
        )


class BoundedHostDecisionWorker:
    """At most two jobs, including the running job and completed unconsumed results.

    The acquisition owner submits/polls. Overflow raises before retaining IQ;
    callers must explicitly record degraded operation rather than skip a probe.
    """

    capacity = 2

    def __init__(
        self, factory: Callable[[], HostDecisionEngine], *, source_sample_count: int = 1_200_000
    ) -> None:
        if source_sample_count not in (1_200_000, 1_800_000, 2_400_000):
            raise ValueError("host decision source sample count is unsupported")
        self._factory = factory
        self._source_sample_count = source_sample_count
        self._engine: HostDecisionEngine | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="host-decision")
        self._pending: deque[Future[HostDecisionWorkResult]] = deque()
        self._closed = False
        self.high_watermark = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def submit(
        self,
        source: HostFeedbackV1,
        samples: npt.NDArray[np.complex64],
        *,
        edge: Literal["lower", "upper"],
    ) -> None:
        if self._closed:
            raise RuntimeError("host decision worker is closed")
        if len(self._pending) >= self.capacity:
            raise RuntimeError("host decision queue exceeded its bounded capacity")
        source.pack()
        if (
            source.outcome != HostDecisionOutcome.UNKNOWN
            or source.healthy
            or (source.screen_mask or source.confirmation_mask)
        ):
            raise ValueError("host decision source must start as unevaluated/unknown")
        submitted = time.monotonic_ns()
        if (
            not isinstance(samples, np.ndarray)
            or samples.dtype != np.complex64
            or samples.shape != (1, self._source_sample_count)
            or edge not in ("lower", "upper")
        ):
            raise ValueError("host decision input must be one complete native single-RX dwell")
        # Complex64 represents all CI16 integers exactly. Reject arbitrary floats
        # rather than rounding or clipping recording samples into new evidence.
        values = np.ascontiguousarray(samples).view(np.float32).reshape(-1, 2)
        if (
            not np.isfinite(values).all()
            or np.any(values < -32768)
            or np.any(values > 32767)
            or np.any(values != np.trunc(values))
        ):
            raise ValueError("host decision samples are not lossless CI16")
        iq = values.astype("<i2")
        iq.setflags(write=False)
        self._pending.append(self._executor.submit(self._run, source, iq, edge, submitted))
        self.high_watermark = max(self.high_watermark, len(self._pending))

    def _run(
        self,
        source: HostFeedbackV1,
        iq: npt.NDArray[np.int16],
        edge: Literal["lower", "upper"],
        submitted: int,
    ) -> HostDecisionWorkResult:
        started = time.monotonic_ns()
        evidence, failure = None, None
        try:
            if self._engine is None:
                self._engine = self._factory()
            evidence = self._engine.run(iq, edge=edge)
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
        return HostDecisionWorkResult(
            source,
            evidence,
            failure,
            submitted,
            started,
            time.monotonic_ns(),
        )

    def poll(self) -> tuple[HostDecisionWorkResult, ...]:
        output = []
        while self._pending and self._pending[0].done():
            output.append(self._pending.popleft().result())
        return tuple(output)

    def finish(self, *, timeout: float = 2.0) -> tuple[HostDecisionWorkResult, ...]:
        """Drain bounded outstanding work, then destroy its workspace on its owner."""
        if self._closed:
            return ()
        if not 0 < timeout <= 10:
            raise ValueError("host decision finish timeout must be within (0, 10]")
        deadline = time.monotonic() + timeout
        output = []
        # Queue cleanup behind accepted work even when a caller's bounded wait
        # expires. A late computation must still destroy its native workspace.
        destroyed = self._executor.submit(self._destroy)
        try:
            while self._pending:
                output.append(self._pending[0].result(timeout=max(0, deadline - time.monotonic())))
                self._pending.popleft()
            destroyed.result(timeout=max(0, deadline - time.monotonic()))
        finally:
            self._closed = True
            self._executor.shutdown(wait=False)
        return tuple(output)

    def drain(self, *, timeout: float = 2.0) -> tuple[HostDecisionWorkResult, ...]:
        """Finish submitted jobs before radio restoration, retaining the workspace."""
        if not 0 < timeout <= 10:
            raise ValueError("host decision drain timeout must be within (0, 10]")
        deadline = time.monotonic() + timeout
        output = []
        while self._pending:
            output.append(self._pending[0].result(timeout=max(0, deadline - time.monotonic())))
            self._pending.popleft()
        return tuple(output)

    def _destroy(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None
