import json

from typer.testing import CliRunner

from leo.cli.app import create_cli


def test_offline_command_composes_explicit_mode_and_workers(monkeypatch, tmp_path):
    import leo.processing.fast_scan as processing

    calls = []

    def replay(recording, **kwargs):
        calls.append((recording, kwargs))
        return {"counts": {"processed": 2}, "points": [1]}

    monkeypatch.setattr(processing, "process_recording", replay)
    result = CliRunner().invoke(
        create_cli(),
        [
            "scan",
            "analyze-fast",
            str(tmp_path / "raw"),
            "--bulk-root",
            str(tmp_path / "bulk"),
            "--database-url",
            "postgresql:///test",
            "--workers",
            "8",
            "--mode",
            "shadow",
            "--export-tracking-input",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout) == {"counts": {"processed": 2}}
    assert calls[0][1]["workers"] == 8
    assert calls[0][1]["policy"].mode == "shadow"
    assert calls[0][1]["export_tracking_input"] is True


def test_invalid_mode_never_queues_work(monkeypatch, tmp_path):
    import leo.processing.fast_scan as processing

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid policy must not queue work")

    monkeypatch.setattr(processing, "process_recording", forbidden)
    result = CliRunner().invoke(
        create_cli(),
        [
            "scan",
            "analyze-fast",
            str(tmp_path),
            "--bulk-root",
            str(tmp_path),
            "--database-url",
            "postgresql:///test",
            "--mode",
            "invalid",
        ],
    )
    assert result.exit_code != 0
    assert not isinstance(result.exception, AssertionError)


def test_auto_discovery_waits_for_terminal_and_does_not_repeat_completion(tmp_path):
    from leo.cli.fast_scan import discover_automatic
    from leo.contracts.digests import canonical_digest
    from leo.storage.continuous_window import write_checkpoint
    from leo.storage.fast_scan import FastScanStore
    from tests.contracts.test_continuous_window_contracts import checkpoint

    raw = tmp_path / "raw"
    folder = raw / "run"
    folder.mkdir(parents=True)
    store = FastScanStore(tmp_path / "bulk")
    config = {"targets": [{"edge": "lower"}]}
    cp = checkpoint().model_copy(update={"configuration": config,
        "configuration_sha256": canonical_digest(config), "state": "running"})
    write_checkpoint(folder, cp)
    assert discover_automatic(raw, store) == []
    assert store.automatic_status("run")["state"] == "recording"
    cp = cp.model_copy(update={"state": "stopped", "captured_windows": 8,
        "durable_windows": 8, "device_terminal": {"state": 1, "error": 0},
        "host_restoration": {"fastlock_inactive": True}})
    write_checkpoint(folder, cp)
    assert discover_automatic(raw, store) == [folder]
    store.update_automatic("run", state="tracking")
    assert discover_automatic(raw, store) == [folder]
    store.update_automatic("run", state="complete")
    assert discover_automatic(raw, store) == []


def test_automatic_failure_never_reports_complete(monkeypatch, tmp_path):
    import threading

    import pytest

    import leo.processing.fast_scan as processing
    from leo.cli.fast_scan import process_automatic
    from leo.storage.fast_scan import FastScanStore

    def failed(*args, **kwargs):
        raise ValueError("broken IQ")
    monkeypatch.setattr(processing, "process_recording", failed)
    store = FastScanStore(tmp_path / "bulk")
    with pytest.raises(ValueError, match="broken IQ"):
        process_automatic(tmp_path / "recording", store=store, database_url="unused",
                          standard_command=[], glrt_lock=threading.Lock())
    assert store.automatic_status("recording")["state"] == "failed"


def test_automatic_resumes_standard_slices_without_recomputing_glrt(monkeypatch, tmp_path):
    import threading
    from types import SimpleNamespace

    import leo.cli.fast_scan as cli
    import leo.processing.fast_scan as processing
    from leo.storage.fast_scan import FastScanStore

    store = FastScanStore(tmp_path / "bulk")
    store.update_automatic("recording", state="tracking", run_id="run", session_id="session")
    def forbidden(*args, **kwargs):
        raise AssertionError("sealed GLRT must not be repeated")
    monkeypatch.setattr(processing, "process_recording", forbidden)
    calls = []
    def standard(command, **kwargs):
        calls.append(command)
        workspace = store.automatic_workspace("recording")
        (workspace / "adapter-receipt.json").write_text(json.dumps({
            "analysis_complete": len(calls) == 2, "standard_stages": {"regional": True}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cli.subprocess, "run", standard)
    result = cli.process_automatic(tmp_path / "recording", store=store, database_url="unused",
        standard_command=["python", "bridge"], glrt_lock=threading.Lock())
    assert len(calls) == 2
    assert "--full" in calls[0]
    assert result["state"] == "complete"
