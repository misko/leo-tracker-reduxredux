"""Capture-first recording through narrow source and sink ports.

The recording thread owns append/finalization. Its byte and window admission
bounds include an in-flight write. A terminal event uses no payload capacity.
Sources must bound their calls; a source with ``cancel()`` additionally gets a
deadline/cancellation watchdog to interrupt blocking hardware reads.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Protocol

import numpy as np

from leo.scanner.short_window import (
    RoundRobinScheduler,
    ShortWindowAcquisition,
    ShortWindowConfiguration,
    ShortWindowSource,
    classify_window,
)


class ShortWindowSink(Protocol):
    def append(
        self,
        *,
        sequence: int,
        target_id: str,
        samples: np.ndarray,
        acquisition: dict[str, Any],
        powers: tuple[dict[str, Any], ...],
    ) -> None: ...

    def finish(self, *, stop_reason: str, failure: str | None = None) -> Any: ...

    def abort(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ShortWindowRecordingResult:
    status: str
    stop_reason: str
    failure: str | None
    captured_windows: int
    accepted_windows: int
    written_windows: int
    queued_peak_windows: int
    queued_peak_bytes: int
    elapsed_seconds: float
    publication: Any = None


@dataclass(frozen=True, slots=True)
class _PendingWindow:
    sequence: int
    target_id: str
    samples: np.ndarray
    acquisition: dict[str, Any]
    powers: tuple[dict[str, Any], ...]


def json_metadata(value: Any) -> Any:
    """Convert tuple metadata to JSON arrays required by persisted envelopes."""
    if isinstance(value, dict):
        return {key: json_metadata(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_metadata(item) for item in value]
    return value


def acquisition_metadata(acquisition: ShortWindowAcquisition) -> dict[str, Any]:
    """Avoid dataclasses.asdict copying the IQ payload on the capture path."""
    result = {
        field.name: getattr(acquisition, field.name)
        for field in fields(acquisition)
        if field.name != "samples"
    }
    result.update(
        sample_count=acquisition.sample_count,
        sample_end=acquisition.sample_end,
        complete=acquisition.complete,
    )
    return json_metadata(result)


def run_short_window_recording(
    source: ShortWindowSource,
    configuration: ShortWindowConfiguration,
    sink: ShortWindowSink,
    *,
    cancellation: Event | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    queue_windows: int = 32,
    queue_bytes: int = 12_800_000,
    shutdown_timeout_seconds: float = 10.0,
    provider_duration_grace_seconds: float = 10.0,
) -> ShortWindowRecordingResult:
    if queue_windows < 1 or queue_bytes < configuration.window_bytes:
        raise ValueError("writer bounds must accommodate at least one complete window")
    if not math.isfinite(shutdown_timeout_seconds) or shutdown_timeout_seconds <= 0:
        raise ValueError("writer shutdown timeout must be finite and positive")
    if not math.isfinite(provider_duration_grace_seconds) or provider_duration_grace_seconds < 0:
        raise ValueError("provider duration grace must be finite and nonnegative")
    cancel = cancellation if cancellation is not None else Event()
    queue: Queue[_PendingWindow] = Queue(maxsize=queue_windows)
    lock = Lock()
    terminal = Event()
    writer_done = Event()
    writer_failed = Event()
    watchdog_done = Event()
    deadline_interrupt = Event()
    scheduler = RoundRobinScheduler(configuration)
    started = time.monotonic()
    capture_started: float | None = None
    provider_owned = callable(getattr(source, "next_capture", None))
    captured = accepted = written = outstanding_windows = outstanding_bytes = 0
    peak_windows = peak_bytes = 0
    failure: str | None = None
    writer_error: str | None = None
    watchdog_error: str | None = None
    publication: Any = None

    def error_text(error: BaseException) -> str:
        return f"{type(error).__name__}: {error}"

    def add_failure(message: str) -> None:
        nonlocal failure
        failure = message if failure is None else f"{failure}; {message}"

    def emit(payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(payload)

    def writer() -> None:
        nonlocal written, outstanding_windows, outstanding_bytes, writer_error, publication
        try:
            while not terminal.is_set() or not queue.empty():
                try:
                    window = queue.get(timeout=min(0.01, shutdown_timeout_seconds / 2))
                except Empty:
                    continue
                try:
                    if writer_error is None:
                        sink.append(
                            sequence=window.sequence,
                            target_id=window.target_id,
                            samples=window.samples,
                            acquisition=window.acquisition,
                            powers=window.powers,
                        )
                        written += 1
                except Exception as error:
                    writer_error = error_text(error)
                    writer_failed.set()
                finally:
                    with lock:
                        outstanding_windows -= 1
                        outstanding_bytes -= window.samples.nbytes
                    queue.task_done()
            final_failure = failure
            if writer_error is not None:
                if scheduler.stop_reason in {None, "duration", "max_visits", "provider_complete"}:
                    scheduler.stop_reason = "writer_failure"
                final_failure = (
                    writer_error if final_failure is None else f"{final_failure}; {writer_error}"
                )
            publication = sink.finish(
                stop_reason=scheduler.stop_reason or "writer_failure",
                failure=final_failure,
            )
        except Exception as error:
            writer_error = (
                error_text(error)
                if writer_error is None
                else (f"{writer_error}; finalization: {error_text(error)}")
            )
            writer_failed.set()
            try:
                sink.abort()
            except Exception as abort_error:
                writer_error = f"{writer_error}; abort: {error_text(abort_error)}"
        finally:
            writer_done.set()

    def watchdog() -> None:
        nonlocal watchdog_error
        while not watchdog_done.wait(0.01):
            deadline = configuration.duration_seconds + (
                provider_duration_grace_seconds if provider_owned else 0
            )
            expired = capture_started is not None and time.monotonic() - capture_started >= deadline
            if cancel.is_set() or expired:
                if expired:
                    deadline_interrupt.set()
                interrupt = getattr(source, "cancel", None)
                if callable(interrupt):
                    try:
                        interrupt()
                    except Exception as error:
                        watchdog_error = error_text(error)
                return

    worker = Thread(target=writer, name="leo-short-window-writer", daemon=True)
    monitor = Thread(target=watchdog, name="leo-short-window-deadline", daemon=True)
    worker.start()
    monitor.start()
    try:
        if cancel.is_set():
            scheduler.stop("cancelled")
            add_failure("capture cancelled before configuration")
        else:
            source.configure_once(configuration)
            capture_started = time.monotonic()
        while scheduler.stop_reason is None:
            if cancel.is_set():
                scheduler.stop("cancelled")
                add_failure("capture cancelled")
                break
            if writer_failed.is_set():
                scheduler.stop("writer_failure")
                break
            if deadline_interrupt.is_set():
                scheduler.stop("source_deadline_failure")
                add_failure("provider exceeded its capture duration and delivery grace")
                break
            elapsed_capture = 0 if capture_started is None else time.monotonic() - capture_started
            target = scheduler.next_target(0 if provider_owned else elapsed_capture)
            if target is None:
                break
            scheduled_capture = getattr(source, "next_capture", None)
            if callable(scheduled_capture):
                try:
                    target, acquisition = scheduled_capture()
                except StopIteration:
                    if cancel.is_set() or deadline_interrupt.is_set():
                        scheduler.stop(
                            "cancelled" if cancel.is_set() else "source_deadline_failure"
                        )
                        add_failure("provider interrupted before its terminal receipt")
                    else:
                        scheduler.stop("provider_complete")
                    break
                if target not in configuration.targets:
                    raise ValueError("provider scheduled a target outside the configured table")
            else:
                acquisition = source.capture(target, configuration.window_samples)
            if acquisition.requested_if_center_hz != target.if_center_hz:
                raise ValueError("source requested IF disagrees with admitted target")
            classification_started = time.monotonic_ns()
            powers = tuple(
                json_metadata(asdict(power))
                for power in classify_window(acquisition, configuration)
            )
            classified_at = time.monotonic_ns()
            metadata = acquisition_metadata(acquisition)
            metadata.update(
                target_id=target.target_id,
                classification_elapsed_ns=classified_at - classification_started,
                classification_after_final_delivery_ns=(
                    max(0, classified_at - acquisition.host_final_sample_monotonic_ns)
                    if acquisition.host_final_sample_monotonic_ns
                    else None
                ),
            )
            captured += 1
            emit(
                {
                    "state": "capture_complete",
                    "sequence": accepted,
                    "target_id": target.target_id,
                    "acquisition": metadata,
                    "powers": powers,
                }
            )
            window = _PendingWindow(
                accepted, target.target_id, acquisition.samples, metadata, powers
            )
            with lock:
                overloaded = (
                    outstanding_windows >= queue_windows
                    or outstanding_bytes + acquisition.samples.nbytes > queue_bytes
                )
                if not overloaded:
                    outstanding_windows += 1
                    outstanding_bytes += acquisition.samples.nbytes
                    peak_windows = max(peak_windows, outstanding_windows)
                    peak_bytes = max(peak_bytes, outstanding_bytes)
                    queue.put_nowait(window)
                    accepted += 1
            if overloaded:
                scheduler.stop("writer_overload")
                add_failure(f"writer admission rejected captured window {accepted}")
                break
            emit(
                {
                    "state": "writer_accepted",
                    "sequence": accepted - 1,
                    "target_id": target.target_id,
                }
            )
            integrity_flags = {
                "overflow",
                "sample_discontinuity",
                "generation_changed",
                "stale_samples",
                "gap",
                "retune_failure",
                "cancelled",
            }.intersection(acquisition.quality_flags)
            integrity_flags.update(
                flag for flag in acquisition.quality_flags if flag.startswith("provider_")
            )
            if not acquisition.complete or integrity_flags:
                scheduler.stop("capture_integrity_failure")
                add_failure(
                    f"window {accepted - 1} has {acquisition.sample_count} samples; "
                    f"quality={','.join(acquisition.quality_flags)}"
                )
                break
    except KeyboardInterrupt:
        cancel.set()
        scheduler.stop("cancelled")
        add_failure("capture interrupted")
    except Exception as error:
        scheduler.stop(
            "cancelled"
            if cancel.is_set()
            else ("source_deadline_failure" if deadline_interrupt.is_set() else "source_failure")
        )
        add_failure(error_text(error))
    finally:
        watchdog_done.set()
        monitor.join(timeout=shutdown_timeout_seconds)
        if monitor.is_alive():
            add_failure("source cancellation watchdog failed to shut down")
        if watchdog_error is not None:
            add_failure(f"source cancellation: {watchdog_error}")
        close_done = Event()
        close_error: str | None = None

        def close_source() -> None:
            nonlocal close_error
            try:
                source.close()
            except Exception as error:
                close_error = error_text(error)
            finally:
                close_done.set()

        Thread(target=close_source, name="leo-short-window-close", daemon=True).start()
        if not close_done.wait(shutdown_timeout_seconds):
            scheduler.stop_reason = "source_close_timeout"
            add_failure("source close/restoration did not complete within the shutdown bound")
        elif close_error is not None:
            scheduler.stop_reason = "source_close_failure"
            add_failure(f"source close: {close_error}")
        if writer_failed.is_set() and scheduler.stop_reason in {"duration", "max_visits"}:
            scheduler.stop_reason = "writer_failure"
        terminal.set()
        if not writer_done.wait(shutdown_timeout_seconds):
            scheduler.stop_reason = "writer_shutdown_timeout"
            add_failure("writer did not drain/finalize within the shutdown bound")
        if writer_error is not None:
            add_failure(f"writer: {writer_error}")
    return ShortWindowRecordingResult(
        status="complete" if failure is None and not writer_failed.is_set() else "incomplete",
        stop_reason=scheduler.stop_reason or "source_failure",
        failure=failure,
        captured_windows=captured,
        accepted_windows=accepted,
        written_windows=written,
        queued_peak_windows=peak_windows,
        queued_peak_bytes=peak_bytes,
        elapsed_seconds=time.monotonic() - started,
        publication=publication,
    )
