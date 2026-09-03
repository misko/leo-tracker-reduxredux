"""Lifecycle-safe orchestration for one persistent hopping session."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from leo.scanner.persistent_hop import PersistentHopPlanV1, PersistentHopSessionReceiptV1
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
    identity = radio.identity
    try:
        identity = radio.open()
        opened = True
        session = radio.begin_session(plan, session_id=session_id)
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
    return receipt
