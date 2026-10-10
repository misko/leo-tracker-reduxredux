from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from leo.cli.continuous_window import control_continuous, start_continuous
from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_digest
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import read_checkpoint, run_path, write_checkpoint
from tests.scanner.test_continuous_recording import configuration


def test_continuous_dry_run_has_no_source_or_storage(tmp_path: Path):
    output = tmp_path / "absent"
    result = start_continuous(
        root=output, host="fixture", serial="serial", configuration=configuration(), dry_run=True
    )
    assert result["device_policy"] == "ordered-v5-until-stop"
    assert result["stop_after_seconds"] is None
    assert not output.exists()


def test_checkpoint_terminal_idempotence_and_qnap_guard(tmp_path: Path):
    config = json_metadata(asdict(configuration()))
    path = run_path(tmp_path, "run")
    path.mkdir()
    checkpoint = ContinuousRunCheckpointV1(
        run_id="run",
        configuration=config,
        configuration_sha256=canonical_digest(config),
        host="fixture",
        serial="serial",
        process_id=1,
        state="stopped",
        updated_utc_ns=time.time_ns(),
    )
    write_checkpoint(path, checkpoint)
    assert read_checkpoint(tmp_path, "run") == checkpoint
    assert control_continuous(tmp_path, "run", stop=True) == checkpoint.model_dump(mode="json")
    with pytest.raises(ValueError):
        run_path(Path("/mnt/qnap01/control"), "run")
    with pytest.raises(ValueError):
        run_path(tmp_path, "../escape")


def test_cli_registers_additive_sibling_controls():
    import typer

    from leo.cli.short_window import register_short_window_commands

    app = typer.Typer()
    register_short_window_commands(app)
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("windows", "continuous-start", "continuous-status", "continuous-stop"):
        assert name in result.stdout


def test_stop_before_activation_persists_request_without_signalling(tmp_path, monkeypatch):
    from leo.cli import continuous_window as cli

    config = json_metadata(asdict(configuration()))
    path = run_path(tmp_path, "starting")
    path.mkdir()
    checkpoint = ContinuousRunCheckpointV1(
        run_id="starting",
        configuration=config,
        configuration_sha256=canonical_digest(config),
        host="fixture",
        serial="serial",
        process_id=999999,
        state="starting",
        updated_utc_ns=time.time_ns(),
    )
    write_checkpoint(path, checkpoint)
    monkeypatch.setattr(cli.os, "kill", lambda *_: pytest.fail("must not signal stale PID"))
    assert cli.control_continuous(tmp_path, "starting", stop=True)["stop_acknowledged"]
    assert (path / "stop.request").is_file()


def test_supervisor_initialization_failure_is_terminal(tmp_path, monkeypatch):
    from leo.cli import continuous_window as cli

    config = json_metadata(asdict(configuration()))
    path = run_path(tmp_path, "failed")
    path.mkdir()
    write_checkpoint(
        path,
        ContinuousRunCheckpointV1(
            run_id="failed",
            configuration=config,
            configuration_sha256=canonical_digest(config),
            host="fixture",
            serial="serial",
            state="starting",
            updated_utc_ns=time.time_ns(),
        ),
    )

    def failed(*_):
        raise ValueError("initialization fixture")

    monkeypatch.setattr(cli, "_supervise", failed)
    with pytest.raises(ValueError, match="initialization fixture"):
        cli.supervise(tmp_path, "failed")
    checkpoint = read_checkpoint(tmp_path, "failed")
    assert checkpoint.state == "failed" and "initialization fixture" in checkpoint.fault


def test_supervisor_real_capture_progress_serializes_latest_and_actual_counts(
    tmp_path, monkeypatch
):
    from dataclasses import dataclass
    from enum import StrEnum

    from leo.acquisition import continuous_window_ppu as provider
    from leo.cli import continuous_window as cli
    from tests.scanner.test_continuous_recording import Source

    class State(StrEnum):
        COMPLETED = "completed"

    @dataclass
    class Terminal:
        state: State = State.COMPLETED
        error: int = 0

    @dataclass
    class Restoration:
        restored: bool = True

    @dataclass
    class Receipt:
        terminal: Terminal
        restoration: Restoration

    source = Source(count=19)
    source.close = lambda: Receipt(Terminal(), Restoration())
    monkeypatch.setattr(provider, "PpuContinuousWindowSource", lambda *_, **__: source)
    monkeypatch.setattr(cli.signal, "signal", lambda *_: None)
    config = json_metadata(asdict(configuration()))
    path = run_path(tmp_path, "supervised")
    path.mkdir()
    (path / "worker.json").write_text('{"queue_windows":32,"queue_bytes":12800000}')
    write_checkpoint(
        path,
        ContinuousRunCheckpointV1(
            run_id="supervised",
            configuration=config,
            configuration_sha256=canonical_digest(config),
            host="fixture",
            serial="serial",
            state="starting",
            updated_utc_ns=time.time_ns(),
        ),
    )
    cli.supervise(tmp_path, "supervised")
    result = read_checkpoint(tmp_path, "supervised")
    assert result.state == "stopped" and result.fault is None
    assert result.captured_windows == result.durable_windows == 19
    assert result.sealed_segments == 3 and len(result.latest_targets) == 8
    assert all(isinstance(value["powers"], list) for value in result.latest_targets.values())
