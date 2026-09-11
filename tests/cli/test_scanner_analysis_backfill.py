import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import leo.cli.scanner_analysis_backfill as cli


@pytest.mark.parametrize(
    "module, option",
    [
        ("leo.cli.adaptive_hop_analysis", "--pending"),
        ("leo.cli.persistent_hop_analysis", "--maximum-tracking-groups"),
        ("leo.cli.scanner_analysis_backfill", "--site"),
        ("leo.cli.scanner_refinement", "--session-id"),
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


@pytest.mark.parametrize("failure", [None, "refinement", "adaptive", "fixed", "spawn"])
def test_both_publication_paths_run_sequentially_even_after_failure(
    monkeypatch, tmp_path, capsys, failure
):
    commands = []

    def run(command, *, check):
        assert check is False
        commands.append(command)
        if len(commands) == 1 and failure == "spawn":
            raise OSError("injected spawn failure")
        failed = command[2] == {
            "refinement": "leo.cli.scanner_refinement",
            "adaptive": "leo.cli.adaptive_hop_analysis",
            "fixed": "leo.cli.persistent_hop_analysis",
        }.get(failure)
        return SimpleNamespace(returncode=int(failed))

    monkeypatch.setattr(cli.subprocess, "run", run)
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
    assert len(commands) == 3
    assert commands.pop(0) == [
        sys.executable,
        "-m",
        "leo.cli.scanner_refinement",
        "--bulk-root",
        str(tmp_path),
        "--maximum-seconds",
        "180",
    ]
    assert commands[0][:3] == [sys.executable, "-m", "leo.cli.adaptive_hop_analysis"]
    assert commands[1][:3] == [sys.executable, "-m", "leo.cli.persistent_hop_analysis"]
    for command in commands:
        assert command[3:9] == [
            "--bulk-root",
            str(tmp_path),
            "--maximum-workers",
            "2",
            "--probe-stride-ms",
            "120",
        ]
    assert commands[0][9:] == ["--pending", "--maximum-visits", "2500", "--maximum-seconds", "300"]
    assert commands[1][9:] == [
        "--maximum-sessions",
        "1",
        "--site",
        "spinnaker-sausalito",
        "--maximum-tracking-groups",
        "4",
        "--json",
    ]
    assert list(tmp_path.iterdir()) == []
