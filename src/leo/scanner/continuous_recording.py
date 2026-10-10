"""Continuous IQ reader/writer composition with explicit stop and fault ownership."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any

from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import classify_window
from leo.scanner.short_window_recording import acquisition_metadata, json_metadata


@dataclass(frozen=True, slots=True)
class ContinuousRecordingResult:
    captured_windows: int
    accepted_windows: int
    written_windows: int
    fault: str | None
    terminal: Any
    restoration: Any
    publication: Any
    peak_queue_windows: int
    peak_queue_bytes: int


def run_continuous_recording(
    source: Any,
    configuration: ContinuousWindowConfiguration,
    sink: Any,
    *,
    stop: Event | None = None,
    stop_after_seconds: float | None = None,
    queue_windows: int = 32,
    queue_bytes: int = 12_800_000,
    shutdown_timeout_seconds: float = 30,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> ContinuousRecordingResult:
    if queue_windows < 1 or queue_bytes < configuration.window_bytes:
        raise ValueError("continuous writer bounds must admit a complete window")
    if shutdown_timeout_seconds <= 0:
        raise ValueError("continuous shutdown bound must be positive")
    if stop_after_seconds is not None and not 0 < stop_after_seconds <= 1800:
        raise ValueError("development capture bound must be positive and at most 30 minutes")
    stop = stop or Event()
    done = Event()
    terminal = Event()
    writer_done = Event()
    queue: Queue[Any] = Queue(queue_windows)
    lock = Lock()
    fault: str | None = None
    fault_messages: deque[str] = deque(maxlen=8)
    first_fault: str | None = None
    fault_count = 0
    outstanding = outstanding_bytes = peak = peak_bytes = 0
    captured = accepted = written = 0
    publication = receipt = None
    configured = Event()
    abort = Event()
    stop_started = Event()
    stop_deadline = 0.0
    stop_strengths: set[bool] = set()
    control_threads: list[Thread] = []
    started = 0.0
    expected_identity: tuple[int, int] | None = None
    power_config = configuration.power_configuration()

    def fail(error: object) -> None:
        nonlocal fault, fault_count, first_fault
        text = str(error)[:384]
        with lock:
            fault_count += 1
            if first_fault is None:
                first_fault = text
            if text not in fault_messages:
                fault_messages.append(text)
            messages = tuple(fault_messages)
            fault = "; ".join(messages if first_fault in messages else (first_fault, *messages))
            if fault_count > 1:
                fault += f"; [{fault_count - 1} additional errors]"

    def emit(record: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(record)

    def request_stop(*, forced: bool = False) -> None:
        nonlocal stop_deadline

        def control() -> None:
            try:
                ack = source.request_stop(forced=forced)
                if not done.is_set():
                    emit(
                        {
                            "state": "stop_requested",
                            "device_ack": json_metadata(asdict(ack)) if ack is not None else None,
                        }
                    )
            except Exception as error:
                if not done.is_set():
                    fail(f"device STOP request failed: {error}")

        with lock:
            if not stop_started.is_set():
                stop_deadline = time.monotonic() + shutdown_timeout_seconds
                stop_started.set()
            if forced in stop_strengths:
                return
            stop_strengths.add(forced)
            worker = Thread(target=control, name="continuous-stop-control", daemon=True)
            control_threads.append(worker)
            worker.start()

    def monitor() -> None:
        while not done.wait(0.05):
            if (
                configured.is_set()
                and not stop_started.is_set()
                and (
                    stop.is_set()
                    or (
                        stop_after_seconds is not None
                        and time.monotonic() - started >= stop_after_seconds
                    )
                )
            ):
                request_stop()
            if stop_started.is_set() and time.monotonic() >= stop_deadline:
                fail("continuous STOP did not reach terminal within its drain bound")
                abort.set()
                request_stop(forced=True)
                try:
                    source.abort_read()
                except Exception as error:
                    fail(f"continuous data cancellation failed: {error}")
                return

    def writer() -> None:
        nonlocal written, outstanding, outstanding_bytes, publication
        try:
            write_failed = False
            while not terminal.is_set() or not queue.empty():
                try:
                    window = queue.get(timeout=0.01)
                except Empty:
                    continue
                try:
                    if not write_failed:
                        sink.append(**window)
                        written += 1
                        emit(
                            {
                                "state": "writer_progress",
                                "written_windows": written,
                                "durable_windows": getattr(sink, "durable_windows", 0),
                                "sealed_segments": getattr(sink, "segment_index", 0),
                                "latest_segment_id": getattr(sink, "latest_segment_id", None),
                            }
                        )
                except Exception as error:
                    write_failed = True
                    fail(f"continuous writer failure: {error}")
                    request_stop(forced=True)
                finally:
                    with lock:
                        outstanding -= 1
                        outstanding_bytes -= window["samples"].nbytes
                        backlog = outstanding, outstanding_bytes
                    queue.task_done()
                    emit(
                        {
                            "state": "writer_backlog",
                            "writer_backlog_windows": backlog[0],
                            "writer_backlog_bytes": backlog[1],
                        }
                    )
            publication = sink.finish(
                stop_reason="fault" if fault else "explicit_stop", failure=fault
            )
        except Exception as error:
            fail(f"continuous finalization failure: {error}")
            sink.abort()
        finally:
            writer_done.set()

    worker = Thread(target=writer, name="continuous-iq-writer", daemon=True)
    watcher = Thread(target=monitor, name="continuous-iq-stop", daemon=True)
    worker.start()
    watcher.start()
    try:
        if stop.is_set():
            raise RuntimeError("continuous capture cancelled before preparation")
        source.configure_once(configuration)
        expected_identity = source.identity
        started = time.monotonic()
        configured.set()
        emit(
            {
                "state": "running",
                "device_session": expected_identity[0],
                "generation": expected_identity[1],
            }
        )
        while True:
            if abort.is_set():
                raise RuntimeError("continuous data drain cancelled after STOP deadline")
            try:
                window = source.next_window()
            except StopIteration:
                break
            if window.visit != captured or (window.session, window.generation) != expected_identity:
                raise ValueError("continuous source lost global visit or generation identity")
            if window.target != configuration.targets[window.target_index]:
                raise ValueError("continuous source target table changed")
            powers = tuple(
                json_metadata(asdict(power))
                for power in classify_window(window.acquisition, power_config)
            )
            metadata = acquisition_metadata(window.acquisition)
            metadata.update(
                device_session=window.session,
                global_visit=window.visit,
                sweep=window.sweep,
                target_index=window.target_index,
                policy_id=configuration.policy_id,
            )
            captured += 1
            emit(
                {
                    "state": "capture_complete",
                    "captured_windows": captured,
                    "target_id": window.target.target_id,
                    "powers": powers,
                    "acquisition": metadata,
                }
            )
            record = {
                "sequence": accepted,
                "target_id": window.target.target_id,
                "samples": window.acquisition.samples,
                "acquisition": metadata,
                "powers": powers,
            }
            with lock:
                overload = (
                    outstanding >= queue_windows
                    or outstanding_bytes + window.acquisition.samples.nbytes > queue_bytes
                )
                if not overload:
                    outstanding += 1
                    outstanding_bytes += window.acquisition.samples.nbytes
                    peak = max(peak, outstanding)
                    peak_bytes = max(peak_bytes, outstanding_bytes)
                    queue.put_nowait(record)
                    accepted += 1
                backlog = outstanding, outstanding_bytes
            emit(
                {
                    "state": "writer_backlog",
                    "writer_backlog_windows": backlog[0],
                    "writer_backlog_bytes": backlog[1],
                }
            )
            if overload:
                fail(f"continuous writer admission overflow at global visit {window.visit}")
                request_stop(forced=True)
                # Exhausted admission is a visible fault. Continue draining the
                # source's terminal accounting without claiming lost IQ durable.
            integrity_flags = tuple(
                flag for flag in window.acquisition.quality_flags if flag != "adc12_clipping"
            )
            if not window.acquisition.complete or integrity_flags:
                fail(f"continuous visit {window.visit} has invalid or partial support")
                request_stop(forced=True)
    except BaseException as error:
        fail(f"continuous capture failed: {type(error).__name__}: {error}")
        if configured.is_set():
            request_stop(forced=True)
    finally:
        done.set()
        watcher.join(timeout=shutdown_timeout_seconds)
        if watcher.is_alive():
            fail("continuous STOP control did not finish within its bound")
        control_deadline = time.monotonic() + shutdown_timeout_seconds
        with lock:
            controllers = tuple(control_threads)
        for controller in controllers:
            controller.join(timeout=max(0, control_deadline - time.monotonic()))
            if controller.is_alive():
                fail("continuous STOP RPC exceeded its control bound")
        closed = Event()

        def close_source() -> None:
            nonlocal receipt
            try:
                receipt = source.close()
                if receipt is None or receipt.terminal is None:
                    fail("continuous source closed without terminal drain/restoration receipt")
                elif receipt.terminal.state.name != "COMPLETED" or receipt.terminal.error:
                    fail(
                        f"continuous device terminal {receipt.terminal.state.name}: "
                        f"{receipt.terminal.error}"
                    )
            except Exception as error:
                fail(f"continuous restoration failure: {error}")
            finally:
                closed.set()

        Thread(target=close_source, name="continuous-source-close", daemon=True).start()
        if not closed.wait(shutdown_timeout_seconds):
            fail(
                "continuous source close exceeded its bound; "
                "device and host restoration remain unattested"
            )
        terminal.set()
        if not writer_done.wait(shutdown_timeout_seconds):
            fail("continuous writer drain/finalization exceeded its shutdown bound")
    return ContinuousRecordingResult(
        captured,
        accepted,
        written,
        fault,
        getattr(receipt, "terminal", None),
        getattr(receipt, "restoration", None),
        publication,
        peak,
        peak_bytes,
    )
