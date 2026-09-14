"""Execute the restart helper's control boundary without systemd or a radio."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("command", ["status", "pause", "resume", "run"])
def test_restart_control_commands_ignore_scanner_admission_only_in_child(tmp_path, command):
    script = (ROOT / "deploy/scripts/restart-current-acquisition").read_text()
    function = script.split("run_leo() {", 1)[1].split("\n}", 1)[0]
    environment = tmp_path / "leo.env"
    component = tmp_path / "acquisition.env"
    environment.write_text("LEO_RADIO_BACKEND=pluto\nLEO_SCANNER_ENABLED=true\n")
    component.write_text("LEO_SCANNER_CAPTURE_MODE=persistent_hop\nLEO_SCANNER_ENABLED=true\n")
    release = tmp_path / "release"
    executable = release / ".venv/bin/leo"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from leo.cli.composition import CliSettings\n"
        "settings=CliSettings.from_environ(os.environ)\n"
        "print(json.dumps({'scanner_enabled':settings.scanner_enabled,'argv':sys.argv[1:]}))\n"
    )
    executable.chmod(0o700)
    # Replace only the OS user/credential-file adapters with fixture resources.
    function = function.replace("/usr/sbin/runuser -u leo -- ", "")
    function = function.replace("/etc/leo/leo.env", shlex.quote(str(environment)))
    function = function.replace("/etc/leo/acquisition.env", shlex.quote(str(component)))
    program = (
        f"release={shlex.quote(str(release))}\nrun_leo() {{{function}\n}}\n"
        f"run_leo acquire {command} --json\n"
    )
    child_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("LEO_")
    }
    child_environment.pop("CREDENTIALS_DIRECTORY", None)
    child_environment["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        ["bash", "-c", program],
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if command == "run":
        assert result.returncode == 64
        assert "only capture-authority" in result.stderr
        assert not result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "scanner_enabled": False,
            "argv": ["acquire", command, "--json"],
        }
    assert "LEO_SCANNER_ENABLED=true" in component.read_text()
