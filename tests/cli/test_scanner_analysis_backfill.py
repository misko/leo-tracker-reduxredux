import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

import leo.cli.scanner_analysis_backfill as cli


def test_adaptive_sessions_execute_concurrently(monkeypatch, tmp_path):
    barrier = threading.Barrier(2, timeout=2)
    overlapped = []

    def run(command, **_kwargs):
        if command[2] == "leo.cli.adaptive_hop_analysis":
            barrier.wait()
            overlapped.append(command[command.index("--session-id") + 1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli, "_pending_adaptive_sessions", lambda *a, **k: ("new", "old"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill", "--bulk-root", str(tmp_path), "--site", "spinnaker-sausalito"],
    )
    cli.main()
    assert set(overlapped) == {"new", "old"}


@pytest.mark.parametrize(
    "module, option",
    [
        ("leo.cli.adaptive_hop_analysis", "--pending"),
        ("leo.cli.persistent_hop_analysis", "--maximum-tracking-groups"),
        ("leo.cli.scanner_analysis_backfill", "--site"),
        ("leo.cli.scanner_refinement", "--session-id"),
        ("leo.cli.scanner_tracking", "--session-id"),
    ],
)
def test_child_module_entrypoints_actually_execute(module, option):
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout and option in result.stdout


@pytest.mark.parametrize("failure", [None, "refinement", "adaptive-new", "fixed", "spawn"])
def test_two_adaptive_lanes_run_and_shared_publication_continues_after_failure(
    monkeypatch, tmp_path, capsys, failure
):
    commands = []

    def run(command, *, check):
        assert check is False
        commands.append(command)
        session_id = (
            command[command.index("--session-id") + 1] if "--session-id" in command else None
        )
        if session_id == "new" and failure == "spawn":
            raise OSError("injected spawn failure")
        failed = command[2] == {
            "refinement": "leo.cli.scanner_refinement",
            "fixed": "leo.cli.persistent_hop_analysis",
        }.get(failure) or (failure == "adaptive-new" and session_id == "new")
        return SimpleNamespace(returncode=int(failed))

    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli, "_pending_adaptive_sessions", lambda *a, **k: ("new", "old"))
    monkeypatch.setattr(
        sys, "argv", ["backfill", "--bulk-root", str(tmp_path), "--site", "spinnaker-sausalito"]
    )
    if failure:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
        assert json.loads(capsys.readouterr().err)["state"] == "failed"
    else:
        cli.main()
    assert len(commands) == 5
    tracking = commands.pop()
    assert tracking[2] == "leo.cli.scanner_tracking"
    assert "--maximum-workers" not in tracking
    assert tracking[-4:] == ["--maximum-seconds", "180", "--maximum-sessions", "2"]
    assert commands.pop() == [
        sys.executable,
        "-m",
        "leo.cli.scanner_refinement",
        "--bulk-root",
        str(tmp_path),
        "--maximum-seconds",
        "180",
    ]
    fixed = commands.pop()
    assert fixed[:3] == [sys.executable, "-m", "leo.cli.persistent_hop_analysis"]
    assert fixed[3:9] == [
        "--bulk-root",
        str(tmp_path),
        "--maximum-workers",
        "2",
        "--probe-stride-ms",
        "120",
    ]
    assert fixed[9:] == [
        "--maximum-sessions",
        "1",
        "--site",
        "spinnaker-sausalito",
        "--maximum-tracking-groups",
        "4",
        "--json",
    ]
    assert {command[command.index("--session-id") + 1] for command in commands} == {
        "new",
        "old",
    }
    for command in commands:
        assert command[:3] == [sys.executable, "-m", "leo.cli.adaptive_hop_analysis"]
        assert command[3:9] == [
            "--bulk-root",
            str(tmp_path),
            "--maximum-workers",
            "2",
            "--probe-stride-ms",
            "120",
        ]
        assert command[9] == "--session-id"
        assert command[11:] == ["--maximum-visits", "2500", "--maximum-seconds", "580"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("workers", [3, 4])
def test_explicit_worker_setting_only_changes_fixed_analysis(monkeypatch, workers):
    commands = []
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, **kw: commands.append(command) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(cli, "_pending_adaptive_sessions", lambda *a, **k: ("adaptive",))
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill", "--site", "spinnaker-sausalito", "--fixed-maximum-workers", str(workers)],
    )
    cli.main()
    adaptive, fixed = commands[:2]
    assert adaptive[adaptive.index("--maximum-workers") + 1] == "2"
    assert fixed[fixed.index("--maximum-workers") + 1] == str(workers)


@pytest.mark.parametrize("count", ["0", "5", "true"])
def test_backfill_rejects_unbounded_worker_settings_before_starting_jobs(monkeypatch, count):
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected job"))
    monkeypatch.setattr(
        sys, "argv", ["backfill", "--site", "spinnaker-sausalito", "--fixed-maximum-workers", count]
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2
