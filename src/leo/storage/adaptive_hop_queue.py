"""Bounded asynchronous compression. Storage pressure is an explicit failure."""

from __future__ import annotations

import queue
import threading
import time
from contextlib import suppress

from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.storage.adaptive_hop import AdaptiveHopSessionWriter, PublishedAdaptiveHopIqSession
from leo.storage.errors import BundleStateError
from leo.storage.persistent_hop import PersistentHopQueueTelemetryV1

_POLL_SECONDS = 0.025
_JOIN_SECONDS = 15.0


class QueuedAdaptiveHopSessionWriter:
    """One append/finish owner; one worker owns the underlying writer until joined.

    A full queue never blocks acquisition or silently discards IQ. It poisons
    this recording and asks the caller to cancel and retain its unpublished
    evidence. Abort never closes a file still in use by the worker.
    """

    def __init__(self, writer: AdaptiveHopSessionWriter, *, capacity_visits: int) -> None:
        if type(capacity_visits) is not int or not 1 <= capacity_visits <= 64:
            raise ValueError("adaptive storage queue capacity must be within 1..64")
        self._writer = writer
        self._queue: queue.Queue[AdaptiveHopVisitBlock] = queue.Queue(capacity_visits)
        self._closing = threading.Event()
        self._abort = threading.Event()
        self._error: BaseException | None = None
        self._closed = False
        self._high_water = 0
        self._enqueue_failures = 0
        self._maximum_service_ns = 0
        self._thread = threading.Thread(
            target=self._run, name="leo-adaptive-iq-store", daemon=False
        )
        self._thread.start()

    @property
    def telemetry(self) -> PersistentHopQueueTelemetryV1:
        # Existing storage-owned queue metrics have no fixed-hop semantics.
        return PersistentHopQueueTelemetryV1(
            capacity_visits=self._queue.maxsize,
            high_water_visits=self._high_water,
            enqueue_failure_count=self._enqueue_failures,
            maximum_writer_service_ns=self._maximum_service_ns,
        )

    def _raise_error(self) -> None:
        if self._error is not None:
            raise BundleStateError(
                f"adaptive storage worker failed: {self._error}"
            ) from self._error

    def append(self, block: AdaptiveHopVisitBlock) -> None:
        self._raise_error()
        if self._closed or self._closing.is_set() or self._abort.is_set():
            raise BundleStateError("adaptive storage queue is closed or failed")
        try:
            self._queue.put_nowait(block)
        except queue.Full as error:
            self._enqueue_failures += 1
            self._abort.set()
            raise BundleStateError(
                "adaptive storage queue exhausted; recording must cancel"
            ) from error
        self._high_water = max(self._high_water, self._queue.qsize())
        self._raise_error()

    def _run(self) -> None:
        try:
            while not self._abort.is_set():
                try:
                    block = self._queue.get(timeout=_POLL_SECONDS)
                except queue.Empty:
                    if self._closing.is_set():
                        return
                    continue
                start = time.monotonic_ns()
                self._writer.append(block)
                self._maximum_service_ns = max(
                    self._maximum_service_ns, time.monotonic_ns() - start
                )
                del block
        except BaseException as error:
            self._error = error
            self._abort.set()
        finally:
            if self._abort.is_set():
                try:
                    self._writer.abort()
                except BaseException as error:
                    if self._error is None:
                        self._error = error
                    else:
                        self._error.add_note(f"adaptive writer abort also failed: {error!r}")
                while not self._queue.empty():
                    with suppress(queue.Empty):
                        self._queue.get_nowait()

    def _join(self) -> None:
        self._thread.join(timeout=_JOIN_SECONDS)
        if self._thread.is_alive():
            self._abort.set()
            raise BundleStateError("adaptive storage worker did not stop; publication refused")

    def finish(
        self, receipt: AdaptiveHopReceiptV1, *, timing: PersistentHopUtcTimingAuthorityV1 | None
    ) -> PublishedAdaptiveHopIqSession:
        if self._closed:
            raise BundleStateError("adaptive storage queue is closed")
        self._closing.set()
        self._join()
        self._raise_error()
        if self._abort.is_set():
            raise BundleStateError("adaptive storage queue failed; publication refused")
        try:
            return self._writer.finish(receipt, timing=timing, queue_telemetry=self.telemetry)
        finally:
            self._closed = True
            self._writer.abort()

    def abort(self) -> None:
        if self._closed:
            return
        self._abort.set()
        self._closing.set()
        self._join()
        self._closed = True
        self._writer.abort()
        self._raise_error()
