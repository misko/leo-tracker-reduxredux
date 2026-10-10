"""Supervised continuous recording commands; per-visit control remains on device."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.scanner.continuous_recording import run_continuous_recording
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import ShortWindowTarget
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import (
    ContinuousWindowWriter,
    read_checkpoint,
    run_path,
    write_checkpoint,
    write_publication_failure,
)


def _configuration(value: dict[str, Any]) -> ContinuousWindowConfiguration:
    fields = dict(value)
    fields["targets"] = tuple(ShortWindowTarget(**target) for target in fields["targets"])
    fields["receiver_ids"] = tuple(fields["receiver_ids"])
    return ContinuousWindowConfiguration(**fields)


def _supervise(root: Path, run_id: str) -> None:
    from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource

    path = run_path(root, run_id)
    checkpoint = read_checkpoint(root, run_id)
    configuration = _configuration(checkpoint.configuration)
    launch = json.loads((path / "worker.json").read_bytes())
    state = checkpoint.model_dump(mode="json")
    state["process_id"] = os.getpid()
    lock = threading.Lock()
    dirty = threading.Event()
    complete = threading.Event()
    finalizing = threading.Event()
    stop = threading.Event()
    publisher_error: str | None = None

    def progress(event: dict[str, Any]) -> None:
        with lock:
            if finalizing.is_set():
                return
            stage = event["state"]
            if stage in {"running", "stop_requested"}:
                state["state"] = stage
            for key in (
                "device_session",
                "generation",
                "captured_windows",
                "durable_windows",
                "sealed_segments",
                "latest_segment_id",
                "writer_backlog_windows",
                "writer_backlog_bytes",
            ):
                if key in event:
                    state[key] = event[key]
            if stage == "capture_complete":
                state["latest_targets"][event["target_id"]] = json_metadata(
                    {
                        "acquisition": event["acquisition"],
                        "powers": event["powers"],
                        "host_delivery_utc_ns": time.time_ns(),
                    }
                )
            state["updated_utc_ns"] = time.time_ns()
            dirty.set()

    def publish() -> None:
        nonlocal publisher_error
        try:
            while True:
                final = complete.wait(0.25)
                if (path / "stop.request").exists():
                    stop.set()
                if dirty.is_set() or final:
                    with lock:
                        snapshot = dict(state)
                        snapshot["latest_targets"] = dict(state["latest_targets"])
                        dirty.clear()
                    write_checkpoint(path, ContinuousRunCheckpointV1(**snapshot))
                if final:
                    return
        except Exception as error:
            publisher_error = f"continuous checkpoint failure: {error}"
            stop.set()

    def cancelled(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    if (path / "stop.request").exists():
        stop.set()
    write_checkpoint(path, ContinuousRunCheckpointV1(**state))
    publisher = threading.Thread(target=publish, name="continuous-checkpoint", daemon=True)
    source = PpuContinuousWindowSource(checkpoint.host, expected_serial=checkpoint.serial)
    writer = ContinuousWindowWriter(
        path,
        run_id,
        configuration,
        radio={
            "provider": "ppu-continuous-v5",
            "serial": checkpoint.serial,
            "host": checkpoint.host,
        },
    )
    publisher.start()
    try:
        result = run_continuous_recording(
            source,
            configuration,
            writer,
            stop=stop,
            stop_after_seconds=launch.get("stop_after_seconds"),
            queue_windows=launch["queue_windows"],
            queue_bytes=launch["queue_bytes"],
            on_progress=progress,
        )
        with lock:
            finalizing.set()
            state.update(
                state="failed" if result.fault or publisher_error else "stopped",
                fault=result.fault or publisher_error,
                captured_windows=result.captured_windows,
                durable_windows=writer.durable_windows,
                sealed_segments=writer.segment_index,
                latest_segment_id=writer.latest_segment_id,
                device_terminal=json_metadata(asdict(result.terminal)) if result.terminal else None,
                host_restoration=json_metadata(asdict(result.restoration))
                if result.restoration
                else None,
                updated_utc_ns=time.time_ns(),
            )
    except BaseException as error:
        with lock:
            finalizing.set()
            state.update(
                state="failed",
                fault=f"{type(error).__name__}: {error}",
                updated_utc_ns=time.time_ns(),
            )
        raise
    finally:
        complete.set()
        publisher.join(timeout=2)
        with lock:
            if publisher.is_alive():
                state.update(
                    state="failed", fault="continuous checkpoint publication remains unattested"
                )
                write_publication_failure(path, ContinuousRunCheckpointV1(**state))
            elif publisher_error:
                state.update(state="failed", fault=publisher_error)
                write_checkpoint(path, ContinuousRunCheckpointV1(**state))


def supervise(root: Path, run_id: str) -> None:
    """Publish initialization failures as well as failures after activation."""
    try:
        _supervise(root, run_id)
    except BaseException as error:
        checkpoint = read_checkpoint(root, run_id)
        write_checkpoint(
            run_path(root, run_id),
            checkpoint.model_copy(
                update={
                    "state": "failed",
                    "fault": f"{type(error).__name__}: {error}",
                    "updated_utc_ns": time.time_ns(),
                }
            ),
        )
        raise


def start_continuous(
    *,
    root: Path,
    host: str,
    serial: str,
    configuration: ContinuousWindowConfiguration,
    run_id: str | None = None,
    dry_run: bool = False,
    stop_after_seconds: float | None = None,
    queue_windows: int = 32,
    queue_bytes: int = 12_800_000,
    startup_timeout_seconds: float = 120,
) -> dict[str, Any]:
    if not serial or not host or queue_windows < 1 or queue_bytes < configuration.window_bytes:
        raise ValueError("continuous identity and writer admission bounds are required")
    if stop_after_seconds is not None and not 0 < stop_after_seconds <= 1800:
        raise ValueError("development bound must be positive and at most 30 minutes")
    identifier = run_id or f"continuous-{uuid.uuid4().hex}"
    from pydantic import TypeAdapter

    from leo.contracts.recording import Identifier

    TypeAdapter(Identifier).validate_python(f"{identifier}-segment-00000000")
    path = run_path(root, identifier)
    config = json_metadata(asdict(configuration))
    preview = {
        "run_id": identifier,
        "configuration": config,
        "configuration_sha256": canonical_digest(config),
        "device_policy": "ordered-v5-until-stop",
        "segment_uncompressed_bytes": configuration.segment_windows * configuration.window_bytes,
        "stop_after_seconds": stop_after_seconds,
    }
    if dry_run:
        return {"kind": "continuous_scan_preview", **preview}
    path.mkdir(parents=True, exist_ok=False)
    checkpoint = ContinuousRunCheckpointV1(
        run_id=identifier,
        configuration=config,
        configuration_sha256=canonical_digest(config),
        host=host,
        serial=serial,
        state="starting",
        updated_utc_ns=time.time_ns(),
    )
    write_checkpoint(path, checkpoint)
    with (path / "worker.json").open("xb") as stream:
        stream.write(
            canonical_json_bytes(
                {
                    "queue_windows": queue_windows,
                    "queue_bytes": queue_bytes,
                    "stop_after_seconds": stop_after_seconds,
                }
            )
        )
    try:
        with (path / "worker.log").open("xb") as log:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "leo.cli.continuous_window",
                    "--supervise",
                    str(root.resolve()),
                    identifier,
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
    except BaseException as error:
        write_checkpoint(
            path,
            checkpoint.model_copy(
                update={
                    "state": "failed",
                    "fault": f"worker launch failed: {error}",
                    "updated_utc_ns": time.time_ns(),
                }
            ),
        )
        raise
    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() < deadline:
        current = read_checkpoint(root, identifier)
        if current.state != "starting":
            return {"kind": "continuous_scan_start", **current.model_dump(mode="json")}
        time.sleep(0.05)
    raise TimeoutError(
        f"continuous run {identifier} preparation exceeded its startup bound; inspect status"
    )


def control_continuous(
    root: Path, run_id: str, *, stop: bool = False, forced: bool = False, wait_seconds: float = 0
) -> dict[str, Any]:
    checkpoint = read_checkpoint(root, run_id)
    result = checkpoint.model_dump(mode="json")
    if checkpoint.state in {"stopped", "failed"}:
        return result
    if checkpoint.device_session:
        from pluto_plus.continuous_scan import ContinuousClient, ContinuousControl

        host = checkpoint.host.removeprefix("ip:")
        client = ContinuousClient(host)
        try:
            response = client.control(
                "cf-ad9361-lpc",
                ContinuousControl(
                    secrets.randbits(63) or 1,
                    checkpoint.device_session,
                    checkpoint.generation,
                    forced,
                ),
                stop=stop,
            )
        except Exception as error:
            if getattr(error, "errno", None) != 61:
                raise
            # A consumed terminal can release device ownership before its local
            # checkpoint is published. ENODATA alone proves no restoration.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                final = read_checkpoint(root, run_id)
                if (final.device_session, final.generation) == (
                    checkpoint.device_session,
                    checkpoint.generation,
                ) and final.state in {"stopped", "failed"}:
                    return {
                        **final.model_dump(mode="json"),
                        "terminal_received": final.device_terminal is not None,
                    }
                time.sleep(0.05)
            raise
        result["device_status"] = json_metadata(asdict(response))
        result["stop_acknowledged"] = stop
    elif stop:
        # Persist cancellation under the validated run identity. Never signal a
        # PID read from a checkpoint: it may already have been reused.
        path = run_path(root, run_id)
        request = path / "stop.request"
        if request.is_symlink():
            raise ValueError("continuous stop request cannot be a symlink")
        with request.open("ab") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        result["stop_acknowledged"] = True
    deadline = time.monotonic() + wait_seconds
    while stop and wait_seconds > 0 and time.monotonic() < deadline:
        final = read_checkpoint(root, run_id)
        if final.state in {"stopped", "failed"}:
            return {
                **final.model_dump(mode="json"),
                "stop_acknowledged": True,
                "terminal_received": final.device_terminal is not None,
            }
        time.sleep(0.05)
    return {**result, "terminal_received": checkpoint.device_terminal is not None}


def register_continuous_window_commands(scanner: typer.Typer) -> None:
    @scanner.command("continuous-start")
    def start_command(
        host: Annotated[str, typer.Option("--host")],
        serial: Annotated[str, typer.Option("--serial")],
        if_hz: Annotated[list[int], typer.Option("--if-hz")],
        output_root: Annotated[Path, typer.Option("--output-root")],
        gain_db: Annotated[float, typer.Option("--gain-db")] = 40,
        threshold_dbfs: Annotated[float, typer.Option("--threshold-dbfs")] = -38,
        transition_budget_ms: Annotated[int, typer.Option("--transition-budget-ms")] = 20,
        segment_windows: Annotated[int, typer.Option("--segment-windows")] = 512,
        stop_after_seconds: Annotated[float | None, typer.Option("--stop-after-seconds")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    ) -> None:
        config = ContinuousWindowConfiguration(
            targets=tuple(ShortWindowTarget(f"if-{frequency}", frequency) for frequency in if_hz),
            gain_db=gain_db,
            threshold_dbfs=threshold_dbfs,
            transition_budget_ms=transition_budget_ms,
            segment_windows=segment_windows,
        )
        print(
            json.dumps(
                start_continuous(
                    root=output_root,
                    host=host,
                    serial=serial,
                    configuration=config,
                    dry_run=dry_run,
                    stop_after_seconds=stop_after_seconds,
                )
            )
        )

    @scanner.command("continuous-status")
    def status_command(
        run_id: str, output_root: Annotated[Path, typer.Option("--output-root")]
    ) -> None:
        print(json.dumps(control_continuous(output_root, run_id)))

    @scanner.command("continuous-stop")
    def stop_command(
        run_id: str,
        output_root: Annotated[Path, typer.Option("--output-root")],
        forced: Annotated[bool, typer.Option("--forced")] = False,
        wait_seconds: Annotated[float, typer.Option("--wait-seconds")] = 30,
    ) -> None:
        print(
            json.dumps(
                control_continuous(
                    output_root, run_id, stop=True, forced=forced, wait_seconds=wait_seconds
                )
            )
        )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--supervise":
        supervise(Path(sys.argv[2]), sys.argv[3])
    else:
        raise SystemExit("this module is the continuous scanner supervisor")
