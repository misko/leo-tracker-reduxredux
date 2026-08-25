"""Acquisition application errors."""

from __future__ import annotations

from threading import Thread


class AcquisitionError(RuntimeError):
    """Base error raised at the acquisition boundary."""


class AcquisitionCancelled(AcquisitionError):
    """Raised when a capture is cancelled at a safe refill boundary."""


class AdmissionRejected(AcquisitionError):
    """Raised when local storage cannot safely admit a capture plan."""


class AcquisitionSupervisorPoisoned(BaseException):
    """Force a live supervisor process to exit while storage work is still alive.

    This deliberately does not inherit from :class:`Exception`: the ordinary CLI
    and continuous-run recovery paths must not turn an unbounded live writer into
    another scheduled dwell in the same process.
    """

    def __init__(
        self,
        *,
        session_id: str,
        consumer_threads: tuple[Thread, ...],
        errors: tuple[str, ...],
    ) -> None:
        if not consumer_threads:
            raise ValueError("a poisoned supervisor requires timed-out consumer threads")
        self.session_id = session_id
        self.consumer_threads = consumer_threads
        self.errors = errors
        super().__init__(
            f"live storage consumer exceeded bounded shutdown for {session_id}; "
            "acquisition supervisor is poisoned"
        )
