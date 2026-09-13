"""Lifecycle-safe adaptive capture; persistence is a narrow visit callback."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopReceiptV1, AdaptiveHopVisitV1
from leo.scanner.adaptive_hop_ports import (
    AdaptiveHopRadio,
    AdaptiveHopVisitBlock,
)
from leo.scanner.host_adaptive import HostAdaptiveHopPlanV2, HostAdaptiveHopReceiptV2
from leo.scanner.host_adaptive_ports import HostAdaptiveHopRadio, HostAdaptiveHopVisitBlock
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1
from leo.scanner.ports import ScanRadioIdentity
from leo.scanner.single_rx import SingleRxHopTimingV2


@dataclass(frozen=True, slots=True)
class CapturedAdaptiveHopSession:
    receipt: AdaptiveHopReceiptV1
    timing: PersistentHopUtcTimingAuthorityV1 | None


@dataclass(frozen=True, slots=True)
class CapturedHostAdaptiveHopSession:
    receipt: HostAdaptiveHopReceiptV2
    timing: SingleRxHopTimingV2 | None


class _CaptureSession[P: AdaptiveHopPlanV1, R: AdaptiveHopReceiptV1, B](Protocol):
    @property
    def plan(self) -> P: ...
    @property
    def complete(self) -> bool: ...
    @property
    def start_clock_bracket(self) -> PersistentHopStartClockBracketV1 | None: ...
    def read_visit(self) -> B: ...
    def request_cancel(self) -> None: ...
    def finish(self) -> R: ...


class _CaptureRadio[P: AdaptiveHopPlanV1, R: AdaptiveHopReceiptV1, B](Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...
    def open(self) -> ScanRadioIdentity: ...
    def begin_session(self, plan: P, *, session_id: str) -> _CaptureSession[P, R, B]: ...
    def close(self) -> None: ...


class AdaptiveHopCaptureError(RuntimeError):
    def __init__(self, message: str, *, terminal_receipt: AdaptiveHopReceiptV1 | None = None):
        super().__init__(message)
        self.terminal_receipt = terminal_receipt


def capture_adaptive_hop_session(
    radio: AdaptiveHopRadio,
    plan: AdaptiveHopPlanV1,
    *,
    session_id: str,
    visit_sink: Callable[[AdaptiveHopVisitBlock], None],
    cancel: Event,
    realtime_ns: Callable[[], int] = time.time_ns,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> CapturedAdaptiveHopSession:
    receipt, timing = _capture(
        radio,
        plan,
        session_id=session_id,
        visit_sink=visit_sink,
        cancel=cancel,
        realtime_ns=realtime_ns,
        monotonic_ns=monotonic_ns,
        plan_model=AdaptiveHopPlanV1,
        receipt_model=AdaptiveHopReceiptV1,
        timing_model=PersistentHopUtcTimingAuthorityV1,
    )
    return CapturedAdaptiveHopSession(receipt, timing)


def capture_host_adaptive_hop_session(
    radio: HostAdaptiveHopRadio,
    plan: HostAdaptiveHopPlanV2,
    *,
    session_id: str,
    visit_sink: Callable[[HostAdaptiveHopVisitBlock], None],
    cancel: Event,
    realtime_ns: Callable[[], int] = time.time_ns,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> CapturedHostAdaptiveHopSession:
    receipt, timing = _capture(
        radio,
        plan,
        session_id=session_id,
        visit_sink=visit_sink,
        cancel=cancel,
        realtime_ns=realtime_ns,
        monotonic_ns=monotonic_ns,
        plan_model=HostAdaptiveHopPlanV2,
        receipt_model=HostAdaptiveHopReceiptV2,
        timing_model=SingleRxHopTimingV2,
    )
    return CapturedHostAdaptiveHopSession(receipt, timing)


def _capture[
    P: AdaptiveHopPlanV1,
    R: AdaptiveHopReceiptV1,
    T: PersistentHopUtcTimingAuthorityV1,
    B: (AdaptiveHopVisitBlock, HostAdaptiveHopVisitBlock),
](
    radio: _CaptureRadio[P, R, B],
    plan: P,
    *,
    session_id: str,
    visit_sink: Callable[[B], None],
    cancel: Event,
    realtime_ns: Callable[[], int],
    monotonic_ns: Callable[[], int],
    plan_model: type[P],
    receipt_model: type[R],
    timing_model: type[T],
) -> tuple[R, T | None]:
    """Shared lifecycle; each public entry point admits one closed major."""
    plan = plan_model.model_validate(plan)
    if cancel.is_set():
        raise AdaptiveHopCaptureError("adaptive capture cancelled before open")
    session: _CaptureSession[P, R, B] | None = None
    receipt: R | None = None
    primary: BaseException | None = None
    opened = False
    timing = None
    visits: list[AdaptiveHopVisitV1] = []
    try:
        expected_identity = radio.identity
        identity = radio.open()
        opened = True
        if identity != expected_identity:
            raise ValueError("adaptive radio identity changed on open")
        before_mono = monotonic_ns()
        before_real = realtime_ns()
        session = radio.begin_session(plan, session_id=session_id)
        after_real = realtime_ns()
        after_mono = monotonic_ns()
        if session.plan != plan:
            raise ValueError("adaptive opened session changed the requested plan")
        cancelled = False
        while not session.complete:
            if cancel.is_set() and not cancelled:
                session.request_cancel()
                cancelled = True
            try:
                block = session.read_visit()
            except StopIteration:
                if not session.complete:
                    raise ValueError("adaptive stream ended without terminal status") from None
                break
            evidence = AdaptiveHopVisitV1.model_validate(block.evidence)
            if evidence.event.visit_index != len(visits):
                raise ValueError("adaptive capture visits arrived out of order")
            visit_sink(block)
            visits.append(evidence)
        receipt = receipt_model.model_validate(session.finish())
        terminal_real = realtime_ns()
        terminal_mono = monotonic_ns()
        if (
            receipt.session_id != session_id
            or receipt.plan != plan
            or receipt.radio_id != identity.radio_id
            or receipt.radio_serial != identity.serial
            or receipt.radio_uri != identity.uri
            or receipt.visits != tuple(visits)
        ):
            raise ValueError("adaptive terminal identity or IQ visit inventory changed")
        if receipt.events:
            precise = session.start_clock_bracket or PersistentHopStartClockBracketV1(
                before_realtime_ns=before_real,
                before_monotonic_ns=before_mono,
                after_realtime_ns=after_real,
                after_monotonic_ns=after_mono,
            )
            timing = timing_model.model_validate(
                timing_model.from_host_bracket(
                    session_id=session_id,
                    session_start_device_sample_counter=receipt.terminal.first_counter,
                    sample_rate_hz=plan.geometry.sample_rate_hz,
                    begin_before_realtime_ns=precise.before_realtime_ns,
                    begin_before_monotonic_ns=precise.before_monotonic_ns,
                    begin_after_realtime_ns=precise.after_realtime_ns,
                    begin_after_monotonic_ns=precise.after_monotonic_ns,
                    terminal_realtime_ns=terminal_real,
                    terminal_monotonic_ns=terminal_mono,
                )
            )
    except BaseException as error:
        primary = error
        if session is not None and receipt is None:
            try:
                if not session.complete:
                    session.request_cancel()
                receipt = receipt_model.model_validate(session.finish())
            except BaseException as recovery:
                primary.add_note(f"adaptive terminal recovery also failed: {recovery!r}")
    finally:
        if opened:
            try:
                radio.close()
            except BaseException as close:
                if primary is None:
                    primary = close
                else:
                    primary.add_note(f"adaptive radio close also failed: {close!r}")
    if primary is not None:
        if not isinstance(primary, Exception):
            raise primary
        raise AdaptiveHopCaptureError(
            f"adaptive capture failed: {primary}",
            terminal_receipt=receipt,
        ) from primary
    assert receipt is not None
    return receipt, timing
