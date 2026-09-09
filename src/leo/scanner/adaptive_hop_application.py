"""Lifecycle-safe adaptive capture; persistence is a narrow visit callback."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopReceiptV1, AdaptiveHopVisitV1
from leo.scanner.adaptive_hop_ports import (
    AdaptiveHopRadio,
    AdaptiveHopSession,
    AdaptiveHopVisitBlock,
)
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1


@dataclass(frozen=True, slots=True)
class CapturedAdaptiveHopSession:
    receipt: AdaptiveHopReceiptV1
    timing: PersistentHopUtcTimingAuthorityV1 | None


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
    plan = AdaptiveHopPlanV1.model_validate(plan)
    if cancel.is_set():
        raise AdaptiveHopCaptureError("adaptive capture cancelled before open")
    session: AdaptiveHopSession | None = None
    receipt: AdaptiveHopReceiptV1 | None = None
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
        receipt = AdaptiveHopReceiptV1.model_validate(session.finish())
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
            timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
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
    except BaseException as error:
        primary = error
        if session is not None and receipt is None:
            try:
                if not session.complete:
                    session.request_cancel()
                receipt = AdaptiveHopReceiptV1.model_validate(session.finish())
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
    return CapturedAdaptiveHopSession(receipt, timing)
