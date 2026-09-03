"""Lifecycle-safe orchestration for one persistent hopping session."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event

from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopSessionReceiptV1,
    PersistentHopUtcTimingAuthorityV1,
)
from leo.scanner.persistent_hop_ports import (
    PersistentHopRadio,
    PersistentHopSession,
    PersistentHopVisitBlock,
)


class PersistentHopCaptureError(RuntimeError):
    """Capture failed after preserving every terminal receipt still obtainable."""

    def __init__(
        self,
        message: str,
        *,
        terminal_receipt: PersistentHopSessionReceiptV1 | None = None,
        recovery_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.terminal_receipt = terminal_receipt
        self.recovery_error = recovery_error
        self.close_error = close_error


def capture_persistent_hop_session(
    radio: PersistentHopRadio,
    plan: PersistentHopPlanV1,
    *,
    session_id: str,
    visit_sink: Callable[[PersistentHopVisitBlock], None],
    cancel: Event,
    timing_sink: Callable[[PersistentHopUtcTimingAuthorityV1], None] | None = None,
    realtime_ns: Callable[[], int] = time.time_ns,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> PersistentHopSessionReceiptV1:
    """Drain valid visits and return only a server-attested terminal receipt.

    Storage is a narrow callback so the scanner domain never imports a concrete
    store. A queued sink can return quickly while compression and fsync proceed
    on a separate thread.
    """

    if cancel.is_set():
        raise PersistentHopCaptureError("persistent-hop capture was cancelled before open")

    session: PersistentHopSession | None = None
    receipt: PersistentHopSessionReceiptV1 | None = None
    primary_error: Exception | None = None
    recovery_error: Exception | None = None
    close_error: Exception | None = None
    opened = False
    begin_before_realtime_ns: int | None = None
    begin_before_monotonic_ns: int | None = None
    begin_after_realtime_ns: int | None = None
    begin_after_monotonic_ns: int | None = None
    terminal_realtime_ns: int | None = None
    terminal_monotonic_ns: int | None = None
    identity = radio.identity
    try:
        identity = radio.open()
        opened = True
        begin_before_monotonic_ns = monotonic_ns()
        begin_before_realtime_ns = realtime_ns()
        session = radio.begin_session(plan, session_id=session_id)
        begin_after_realtime_ns = realtime_ns()
        begin_after_monotonic_ns = monotonic_ns()
        cancel_requested = False
        while not session.complete:
            if cancel.is_set() and not cancel_requested:
                session.request_cancel()
                cancel_requested = True
            try:
                block = session.read_visit()
            except StopIteration:
                if not session.complete:
                    raise RuntimeError(
                        "persistent-hop session ended iteration without terminal status"
                    ) from None
                break
            visit_sink(block)
        receipt = session.finish()
        terminal_realtime_ns = realtime_ns()
        terminal_monotonic_ns = monotonic_ns()
        if (
            receipt.session_id != session_id
            or receipt.plan != plan
            or receipt.radio_id != identity.radio_id
            or receipt.radio_serial != identity.serial
            or receipt.radio_uri != identity.uri
        ):
            raise RuntimeError("persistent-hop terminal receipt disagrees with opened session")
    except Exception as error:
        primary_error = error
        if session is not None and receipt is None:
            try:
                if not session.complete:
                    session.request_cancel()
                receipt = session.finish()
            except Exception as recovery:
                recovery_error = recovery
    finally:
        if opened:
            try:
                radio.close()
            except Exception as error:
                close_error = error

    if primary_error is not None or close_error is not None:
        details = []
        if primary_error is not None:
            details.append(f"capture={type(primary_error).__name__}: {primary_error}")
        if recovery_error is not None:
            details.append(f"recovery={type(recovery_error).__name__}: {recovery_error}")
        if close_error is not None:
            details.append(f"close={type(close_error).__name__}: {close_error}")
        failure = PersistentHopCaptureError(
            "; ".join(details),
            terminal_receipt=receipt,
            recovery_error=recovery_error,
            close_error=close_error,
        )
        if primary_error is not None:
            raise failure from primary_error
        raise failure from close_error
    assert receipt is not None
    if timing_sink is not None:
        if None in (
            begin_before_realtime_ns,
            begin_before_monotonic_ns,
            begin_after_realtime_ns,
            begin_after_monotonic_ns,
            terminal_realtime_ns,
            terminal_monotonic_ns,
        ):
            raise PersistentHopCaptureError(
                "persistent-hop capture completed without a full host timing bracket",
                terminal_receipt=receipt,
            )
        assert begin_before_realtime_ns is not None
        assert begin_before_monotonic_ns is not None
        assert begin_after_realtime_ns is not None
        assert begin_after_monotonic_ns is not None
        assert terminal_realtime_ns is not None
        assert terminal_monotonic_ns is not None
        timing_sink(
            PersistentHopUtcTimingAuthorityV1.from_host_bracket(
                session_id=session_id,
                session_start_device_sample_counter=(
                    receipt.session_start_device_sample_counter
                ),
                sample_rate_hz=plan.sample_rate_hz,
                begin_before_realtime_ns=begin_before_realtime_ns,
                begin_before_monotonic_ns=begin_before_monotonic_ns,
                begin_after_realtime_ns=begin_after_realtime_ns,
                begin_after_monotonic_ns=begin_after_monotonic_ns,
                terminal_realtime_ns=terminal_realtime_ns,
                terminal_monotonic_ns=terminal_monotonic_ns,
            )
        )
    return receipt
