"""Narrow operator application service for durable capture admission control."""

from __future__ import annotations

from typing import Protocol

from leo.contracts.capture_control import CaptureControlStateV1


class CaptureControlAuthorityPort(Protocol):
    """Typed authority needed by operator-facing presentation adapters."""

    def snapshot(self) -> CaptureControlStateV1: ...

    def pause(
        self,
        *,
        operator_id: str,
        reason: str,
        wait: bool = True,
        timeout_seconds: float = 90.0,
    ) -> CaptureControlStateV1: ...

    def resume(self, *, operator_id: str, reason: str) -> CaptureControlStateV1: ...


class OperatorCaptureControl:
    """Expose idempotent stop/start without coupling HTTP to host services."""

    def __init__(
        self,
        authority: CaptureControlAuthorityPort,
        *,
        operator_id: str = "web-ui",
    ) -> None:
        self._authority = authority
        self._operator_id = operator_id

    def status(self) -> CaptureControlStateV1:
        return self._authority.snapshot()

    def stop(self) -> CaptureControlStateV1:
        # Fence new claims immediately and return without waiting for an active
        # dwell to drain. Subsequent status reads reconcile pausing -> paused.
        return self._authority.pause(
            operator_id=self._operator_id,
            reason="operator stopped capture from web UI",
            wait=False,
        )

    def start(self) -> CaptureControlStateV1:
        return self._authority.resume(
            operator_id=self._operator_id,
            reason="operator started capture from web UI",
        )
