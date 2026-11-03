"""Detached standalone power controls and durable host restoration snapshots."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from leo.acquisition.power_scanner_ppu import power_measurements
from leo.contracts.power_scanner import StandalonePowerCheckpointV1
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import run_path
from leo.storage.power_scanner import (
    power_control_lock,
    read_power_checkpoint,
    write_power_checkpoint,
)


def start_power(
    *,
    root: Path,
    host: str,
    serial: str,
    frequencies_hz: tuple[int, ...],
    gain_db: float = 40,
    threshold_dbfs: float = -38,
    guard_samples: int = 50_000,
    adc12_qualified: bool = False,
    run_id: str | None = None,
    dry_run: bool = False,
    ssh_known_hosts: Path | None = None,
    ssh_password_file: Path | None = None,
) -> dict[str, Any]:
    from pluto_plus.continuous_scan import build_continuous_setup
    from pluto_plus.standalone_power import StandalonePowerClient, threshold_energy
    from pluto_plus.standalone_power_radio import StandalonePowerRadioOwner, preparation_snapshot

    if not serial or len(frequencies_hz) != 8 or not 2500 <= guard_samples <= 250_000:
        raise ValueError("standalone power requires serial, eight IF targets and valid guard")
    credentials = {}
    if ssh_known_hosts is not None:
        credentials["known_hosts_file"] = ssh_known_hosts
    if ssh_password_file is not None:
        credentials["password_file"] = ssh_password_file
    client = StandalonePowerClient(host.removeprefix("ip:"),**credentials)
    session, generation = secrets.randbits(32) or 1, secrets.randbits(32) or 1
    setup = build_continuous_setup(
        session=session,
        generation=generation,
        seed=secrets.randbits(32) or 1,
        frequencies_hz=frequencies_hz,
        analysis_digest=hashlib.sha256(b"leo-standalone-power-pwr1-v1").digest(),
    )
    threshold = threshold_energy(threshold_dbfs)
    identifier = run_id or f"power-{uuid.uuid4().hex}"
    path = run_path(root, identifier)
    if ssh_password_file and path in ssh_password_file.resolve().parents:
        raise ValueError("SSH password file must remain outside the power archive")
    if dry_run:
        return {
            "kind": "standalone_power_preview",
            "run_id": identifier,
            "frequencies_hz": frequencies_hz,
            "threshold_energy": [threshold, threshold],
            "guard_samples": guard_samples,
            "guard_identity": "post-recall-guard-v1",
            "adc12_qualified": adc12_qualified,
            "iq_dma": False,
        }
    path.mkdir(parents=True, exist_ok=False)
    checkpoint: StandalonePowerCheckpointV1 | None = None

    def prepared(preparation, request):
        nonlocal checkpoint
        request_metadata = json_metadata(asdict(request))
        request_metadata["ssh_known_hosts_sha256"] = getattr(
            getattr(client,"credentials",None),"known_hosts_sha256",None)
        checkpoint = StandalonePowerCheckpointV1(
            run_id=identifier,
            host=host,
            serial=serial,
            session=session,
            generation=generation,
            state="prepared",
            preparation=json_metadata(preparation_snapshot(preparation)),
            request=request_metadata,
            updated_utc_ns=time.time_ns(),
        )
        write_power_checkpoint(path, checkpoint)

    try:
        owner = StandalonePowerRadioOwner.start(
            host if host.startswith("ip:") else f"ip:{host}",
            serial,
            setup,
            client=client,
            gain_db=gain_db,
            guard_samples=guard_samples,
            threshold_energy=(threshold, threshold),
            adc12_qualified=adc12_qualified,
            on_prepared=prepared,
        )
    except BaseException as error:
        if checkpoint is not None:
            restoration = getattr(error, "power_host_restoration", None)
            write_power_checkpoint(
                path,
                checkpoint.model_copy(
                    update={
                        "state": "failed" if restoration is not None else "recovery_required",
                        "host_restoration": json_metadata(asdict(restoration))
                        if restoration
                        else None,
                        "fault": f"{type(error).__name__}: {error}",
                        "updated_utc_ns": time.time_ns(),
                    }
                ),
            )
        raise
    assert checkpoint is not None
    checkpoint = checkpoint.model_copy(
        update={"state": "running", "device_status": owner.status, "updated_utc_ns": time.time_ns()}
    )
    write_power_checkpoint(path, checkpoint)
    return checkpoint.model_dump(mode="json")


def control_power(
    root: Path,
    run_id: str,
    *,
    stop: bool = False,
    after_cursor: int = 0,
    timeout_seconds: float = 30,
    ssh_known_hosts: Path | None = None,
    ssh_password_file: Path | None = None,
) -> dict[str, Any]:
    with power_control_lock(run_path(root, run_id)):
        return _control_power(
            root, run_id, stop=stop, after_cursor=after_cursor, timeout_seconds=timeout_seconds,
            ssh_known_hosts=ssh_known_hosts,ssh_password_file=ssh_password_file,
        )


def _control_power(
    root: Path, run_id: str, *, stop: bool, after_cursor: int, timeout_seconds: float,
    ssh_known_hosts: Path | None, ssh_password_file: Path | None,
) -> dict[str, Any]:
    from pluto_plus.adaptive_scan_radio import restore_adaptive_scan_radio
    from pluto_plus.standalone_power import StandalonePowerClient
    from pluto_plus.standalone_power_radio import preparation_from_snapshot, stop_and_drain

    if not 0 <= after_cursor < 1 << 64 or timeout_seconds <= 0:
        raise ValueError("standalone power cursor/shutdown bound is invalid")

    checkpoint = read_power_checkpoint(root, run_id)
    if checkpoint.state == "stopped" or (
        checkpoint.state == "failed" and checkpoint.host_restoration
    ):
        return checkpoint.model_dump(mode="json")
    credentials = {}
    if ssh_known_hosts is not None:
        credentials["known_hosts_file"] = ssh_known_hosts
    if ssh_password_file is not None:
        credentials["password_file"] = ssh_password_file
    client = StandalonePowerClient(checkpoint.host.removeprefix("ip:"),**credentials)
    pinned_hash = checkpoint.request.get("ssh_known_hosts_sha256")
    if pinned_hash is not None and client.credentials.known_hosts_sha256 != pinned_hash:
        raise ValueError("power control host-key pin differs from persisted START")
    if not stop:
        status = client.status(checkpoint.session, checkpoint.generation, after_cursor)
        _bind_status(checkpoint, status)
        return {
            "run_id": run_id,
            "device_status": status,
            "latest": power_measurements(status, "latest"),
            "history": power_measurements(status, "history"),
            "host_restoration": checkpoint.host_restoration,
        }
    try:
        status = stop_and_drain(
            client, checkpoint.session, checkpoint.generation, timeout_seconds=timeout_seconds
        )
        _bind_status(checkpoint, status)
        restoration = restore_adaptive_scan_radio(preparation_from_snapshot(checkpoint.preparation))
        final = checkpoint.model_copy(
            update={
                "state": "stopped",
                "device_status": status,
                "host_restoration": json_metadata(asdict(restoration)),
                "fault": None,
                "updated_utc_ns": time.time_ns(),
            }
        )
    except BaseException as error:
        write_power_checkpoint(
            run_path(root, run_id),
            checkpoint.model_copy(
                update={
                    "state": "recovery_required",
                    "fault": f"{type(error).__name__}: {error}",
                    "updated_utc_ns": time.time_ns(),
                }
            ),
        )
        raise
    write_power_checkpoint(run_path(root, run_id), final)
    return final.model_dump(mode="json")


def _bind_status(checkpoint: StandalonePowerCheckpointV1, status: dict[str, Any]) -> None:
    request = checkpoint.request
    table = "".join(
        f"{target['profile']} {target['frequency_hz']} {target['profile_crc32']}\n"
        for target in request["targets"]
    )
    digest = hashlib.sha256(table.encode("ascii")).hexdigest()
    if (
        status["table_sha256"] != digest
        or status["guard_samples"] != request["guard_samples"]
        or status["adc12_qualified"] != request["adc12_qualified"]
        or tuple(status["threshold_energy"]) != tuple(request["threshold_energy"])
    ):
        raise ValueError("standalone power status differs from persisted preparation configuration")


def register_power_scanner_commands(scanner: typer.Typer) -> None:
    @scanner.command("power-start")
    def start_command(
        host: Annotated[str, typer.Option("--host")],
        serial: Annotated[str, typer.Option("--serial")],
        if_hz: Annotated[list[int], typer.Option("--if-hz")],
        output_root: Annotated[Path, typer.Option("--output-root")],
        gain_db: Annotated[float, typer.Option("--gain-db")] = 40,
        threshold_dbfs: Annotated[float, typer.Option("--threshold-dbfs")] = -38,
        guard_samples: Annotated[int, typer.Option("--guard-samples")] = 50_000,
        adc12_qualified: Annotated[bool, typer.Option("--adc12-qualified")] = False,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
        ssh_known_hosts: Annotated[Path | None, typer.Option("--ssh-known-hosts")] = None,
        ssh_password_file: Annotated[Path | None, typer.Option("--ssh-password-file")] = None,
    ):
        print(
            json.dumps(
                start_power(
                    root=output_root,
                    host=host,
                    serial=serial,
                    frequencies_hz=tuple(if_hz),
                    gain_db=gain_db,
                    threshold_dbfs=threshold_dbfs,
                    guard_samples=guard_samples,
                    adc12_qualified=adc12_qualified,
                    dry_run=dry_run,
                    ssh_known_hosts=ssh_known_hosts,ssh_password_file=ssh_password_file,
                )
            )
        )

    @scanner.command("power-status")
    def status_command(
        run_id: str,
        output_root: Annotated[Path, typer.Option("--output-root")],
        after_cursor: Annotated[int, typer.Option("--after-cursor")] = 0,
        ssh_known_hosts: Annotated[Path | None, typer.Option("--ssh-known-hosts")] = None,
        ssh_password_file: Annotated[Path | None, typer.Option("--ssh-password-file")] = None,
    ):
        print(json.dumps(control_power(output_root, run_id, after_cursor=after_cursor,
            ssh_known_hosts=ssh_known_hosts,ssh_password_file=ssh_password_file)))

    @scanner.command("power-stop")
    def stop_command(
        run_id: str,
        output_root: Annotated[Path, typer.Option("--output-root")],
        wait_seconds: Annotated[float, typer.Option("--wait-seconds")] = 30,
        ssh_known_hosts: Annotated[Path | None, typer.Option("--ssh-known-hosts")] = None,
        ssh_password_file: Annotated[Path | None, typer.Option("--ssh-password-file")] = None,
    ):
        print(
            json.dumps(control_power(output_root, run_id, stop=True, timeout_seconds=wait_seconds,
                ssh_known_hosts=ssh_known_hosts,ssh_password_file=ssh_password_file))
        )
