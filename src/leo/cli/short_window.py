"""Explicit, bounded short-window recording command composition."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Annotated, Any

import typer

from leo.scanner.short_window import (
    RfMappingAuthority,
    ShortWindowConfiguration,
    ShortWindowSource,
    ShortWindowTarget,
)
from leo.scanner.short_window_recording import json_metadata, run_short_window_recording

SourceFactory = Callable[..., ShortWindowSource]


def default_source_factory(*, host: str, serial: str, provider: str) -> ShortWindowSource:
    if provider == "ppu":
        from leo.acquisition.short_window_ppu import PpuShortWindowSource

        return PpuShortWindowSource(host, expected_serial=serial)
    if provider == "iio":
        from leo.acquisition.short_window_iio import IioShortWindowSource

        uri = host if host.startswith(("ip:", "usb:")) else f"ip:{host}"
        return IioShortWindowSource(uri=uri, expected_serial=serial)
    raise ValueError("provider must be ppu or iio")


def run_short_window_command(
    *,
    host: str,
    serial: str,
    if_centers_hz: tuple[int, ...],
    output_root: Path,
    duration_seconds: float = 120.0,
    max_visits: int = 90_000,
    gain_db: float = 40.0,
    threshold_dbfs: float = -38.0,
    transition_budget_ms: int = 100,
    receiver_ids: tuple[int, ...] = (0, 1),
    lnb_lo_hz: int | None = None,
    rf_mapping_authority: str = "unknown",
    provider: str = "ppu",
    dry_run: bool = False,
    session_id: str | None = None,
    queue_windows: int = 32,
    queue_bytes: int = 12_800_000,
    chunk_windows: int = 64,
    source_factory: SourceFactory | None = None,
    cancellation: Event | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not host.strip() or not serial.strip():
        raise ValueError("explicit radio host and expected serial are required")
    if provider not in {"ppu", "iio"}:
        raise ValueError("provider must be ppu or iio")
    if len(receiver_ids) not in (1, 2) or any(receiver not in (0, 1) for receiver in receiver_ids):
        raise ValueError("recording requires software receiver 0 and/or 1")
    config = ShortWindowConfiguration(
        targets=tuple(
            ShortWindowTarget(
                target_id=f"if-{index + 1:02d}",
                if_center_hz=center,
                rf_center_hz=None if lnb_lo_hz is None else center + lnb_lo_hz,
                lnb_lo_hz=lnb_lo_hz,
                rf_mapping_authority=RfMappingAuthority(rf_mapping_authority),
                profile_id=str(index + (1 if provider == "ppu" and len(if_centers_hz) < 8 else 0)),
            )
            for index, center in enumerate(if_centers_hz)
        ),
        duration_seconds=duration_seconds,
        max_visits=max_visits,
        gain_db=gain_db,
        threshold_dbfs=threshold_dbfs,
        transition_budget_ms=transition_budget_ms,
        receiver_ids=receiver_ids,
        scheduling_receiver_id=receiver_ids[0],
        physical_receiver_labels=tuple(f"RX{receiver + 1}" for receiver in receiver_ids),
        policy_id=(
            "firmware-weighted-20ms-v1" if provider == "ppu" else "fixed-round-robin-20ms-v1"
        ),
    )
    if provider == "ppu" and duration_seconds > 300:
        raise ValueError("initial PPU captures are bounded to at most 300 seconds")
    root = output_root.resolve()
    if root == Path("/mnt/qnap01") or Path("/mnt/qnap01") in root.parents:
        raise ValueError("recordings cannot be written beneath QNAP")
    if queue_windows < 1 or queue_bytes < config.window_bytes or not 1 <= chunk_windows <= 256:
        raise ValueError("queue and chunk bounds must accommodate complete windows")
    window_ceiling = min(max_visits, math.ceil(duration_seconds / 0.020))
    preview = {
        "kind": "short_window_capture_preview",
        "configuration": json_metadata(asdict(config)),
        "radio": {"host": host, "serial": serial, "provider": provider},
        "output_root": str(root),
        "window_samples": config.window_samples,
        "window_bytes": config.window_bytes,
        "maximum_windows_at_zero_gap": window_ceiling,
        "maximum_payload_bytes_at_zero_gap": window_ceiling * config.window_bytes,
        "assumed_uniform_gap_ms": transition_budget_ms,
        "estimated_windows_with_uniform_gap": min(
            max_visits, math.floor(duration_seconds / ((20 + transition_budget_ms) / 1000))
        ),
        "queue_windows": queue_windows,
        "queue_bytes": queue_bytes,
        "chunk_windows": chunk_windows,
        "rf_mapping_authority": rf_mapping_authority,
        "timing_authority": "provider receipt required; host arrival is separate",
    }
    if dry_run:
        return {"status": "dry_run", **preview}
    # The dry-run path above cannot instantiate hardware, storage, or a backend.
    from leo.cli.runner import cancellation_signals
    from leo.storage.short_window import ShortWindowWriter

    sink = ShortWindowWriter(
        root,
        session_id or f"short-window-{uuid.uuid4().hex[:20]}",
        configuration=json_metadata(asdict(config)),
        radio=preview["radio"],
        receiver_ids=receiver_ids,
        chunk_windows=chunk_windows,
    )
    try:
        source = (source_factory or default_source_factory)(
            host=host, serial=serial, provider=provider
        )
    except Exception as error:
        try:
            sink.finish(
                stop_reason="source_factory_failure", failure=f"{type(error).__name__}: {error}"
            )
        except Exception as publication_error:
            sink.abort()
            raise RuntimeError(
                f"source creation: {error}; failure publication: {publication_error}"
            ) from error
        raise
    cancel = cancellation if cancellation is not None else Event()
    with cancellation_signals(cancel):
        result = run_short_window_recording(
            source,
            config,
            sink,
            cancellation=cancel,
            on_progress=on_progress,
            queue_windows=queue_windows,
            queue_bytes=queue_bytes,
        )
    payload = asdict(result)
    payload["publication"] = None if result.publication is None else str(result.publication)
    return {"kind": "short_window_capture_result", **payload}


def register_short_window_commands(scanner: typer.Typer) -> None:
    from leo.cli.continuous_window import register_continuous_window_commands

    register_continuous_window_commands(scanner)

    @scanner.command("windows")
    def capture_windows(
        host: Annotated[str, typer.Option("--host", help="Explicit radio host.")],
        serial: Annotated[str, typer.Option("--serial", help="Required expected radio serial.")],
        if_hz: Annotated[list[int], typer.Option("--if-hz", help="Repeat for each requested IF.")],
        output_root: Annotated[Path, typer.Option("--output-root", file_okay=False)],
        duration_seconds: Annotated[
            float, typer.Option("--duration-seconds", min=0.001, max=1800)
        ] = 120,
        max_visits: Annotated[int, typer.Option("--max-visits", min=1)] = 90_000,
        gain_db: Annotated[float, typer.Option("--gain-db")] = 40,
        threshold_dbfs: Annotated[float, typer.Option("--threshold-dbfs")] = -38,
        transition_budget_ms: Annotated[
            int,
            typer.Option(
                "--transition-budget-ms",
                min=1,
                max=100,
                help="100 ms conservative default; 20 ms is an experimental transition profile.",
            ),
        ] = 100,
        receiver: Annotated[list[int] | None, typer.Option("--receiver", min=0, max=1)] = None,
        lnb_lo_hz: Annotated[int | None, typer.Option("--lnb-lo-hz", min=1)] = None,
        rf_mapping_authority: Annotated[str, typer.Option("--rf-mapping-authority")] = "unknown",
        provider: Annotated[str, typer.Option("--provider", help="ppu or diagnostic iio.")] = "ppu",
        queue_windows: Annotated[int, typer.Option("--queue-windows", min=1)] = 32,
        queue_bytes: Annotated[int, typer.Option("--queue-bytes", min=1)] = 12_800_000,
        chunk_windows: Annotated[int, typer.Option("--chunk-windows", min=1, max=256)] = 64,
        session_id: Annotated[str | None, typer.Option("--session-id")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        def progress(update: dict[str, Any]) -> None:
            # Live status is on stderr; stdout remains one machine-readable result.
            typer.echo(json.dumps(update, allow_nan=False), err=True)

        try:
            payload = run_short_window_command(
                host=host,
                serial=serial,
                if_centers_hz=tuple(if_hz),
                output_root=output_root,
                duration_seconds=duration_seconds,
                max_visits=max_visits,
                gain_db=gain_db,
                threshold_dbfs=threshold_dbfs,
                transition_budget_ms=transition_budget_ms,
                receiver_ids=tuple(receiver or (0, 1)),
                lnb_lo_hz=lnb_lo_hz,
                rf_mapping_authority=rf_mapping_authority,
                provider=provider,
                queue_windows=queue_windows,
                queue_bytes=queue_bytes,
                chunk_windows=chunk_windows,
                session_id=session_id,
                dry_run=dry_run,
                on_progress=progress,
            )
        except Exception as error:
            typer.echo(json.dumps({"status": "error", "failure": str(error)}), err=True)
            raise typer.Exit(code=2) from error
        if json_output or dry_run:
            typer.echo(json.dumps(payload, allow_nan=False))
        else:
            typer.echo(
                f"Short-window capture {payload['status']}: {payload['stop_reason']}; "
                f"{payload['written_windows']} windows; {payload['publication']}"
            )
        if payload["status"] == "incomplete":
            raise typer.Exit(code=22)
