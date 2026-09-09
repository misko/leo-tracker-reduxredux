"""Exercise runtime selection without root staging, services, or radio access."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
STAGER = PROJECT_ROOT / "deploy/scripts/stage-production-release"


@pytest.mark.parametrize("scanner_glrt", (False, True))
def test_real_argument_parser_forwards_only_explicit_installer_opt_in(scanner_glrt: bool) -> None:
    script = STAGER.read_text()
    # Execute the actual side-effect-free parser and installer command with
    # runuser replaced by an argv recorder. No installer or radio is run.
    parser = script.split('[[ -n "$source_dir"', 1)[0]
    command_start = script.rfind(
        "runuser -u leo -- env",
        0,
        script.index('"$release_dir/.venv/bin/pluto-install-metadata-runtime"'),
    )
    command_end = script.index('--prefix "$release_dir/.venv"', command_start)
    command_end += len('--prefix "$release_dir/.venv"')
    command = script[command_start:command_end]
    harness = (
        parser
        + "\n"
        + """
release_dir=/reviewed/release
release_uv=/reviewed/release/.release-tools/uv
metadata_abi=3
runuser() { printf '%s\\0' "$@"; }
"""
        + command
    )
    result = subprocess.run(
        ("bash", "-c", harness, "stager-test", *(("--scanner-glrt",) if scanner_glrt else ())),
        check=True,
        capture_output=True,
        env=dict(os.environ, scanner_glrt="true"),
    )
    arguments = result.stdout.decode().rstrip("\0").split("\0")
    assert arguments.count("--scanner-glrt") == int(scanner_glrt)
    assert "" not in arguments
    assert arguments[arguments.index("--metadata-abi") + 1] == "3"
    assert arguments[arguments.index("--prefix") + 1] == "/reviewed/release/.venv"
    assert "/reviewed/release/.venv/bin/pluto-install-metadata-runtime" in arguments


def _system_python() -> Path:
    choices = tuple(Path(f"/usr/bin/python3.{minor}") for minor in (14, 13, 12))
    for path in choices:
        if path.is_file() and not path.is_symlink():
            info = path.stat()
            if info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o022:
                return path
    pytest.fail("deployment dry-run requires a root-owned versioned /usr/bin/python3.12–3.14")


@pytest.mark.parametrize("scanner_glrt", (False, True))
def test_complete_stager_dry_run_is_non_mutating(tmp_path: Path, scanner_glrt: bool) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for arguments in (
        ("init", "-q"),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fixture",
        ),
    ):
        subprocess.run(("git", "-C", str(source), *arguments), check=True, capture_output=True)
    revision = subprocess.check_output(
        ("git", "-C", str(source), "rev-parse", "HEAD"), text=True
    ).strip()
    tooling = tmp_path / "uv"
    tooling.write_text("#!/bin/sh\nexit 99\n")
    tooling.chmod(0o500)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    result = subprocess.run(
        (
            str(STAGER),
            "--source",
            str(source),
            "--revision",
            revision,
            "--python-bin",
            str(_system_python()),
            "--uv-bin",
            str(tooling),
            *(("--scanner-glrt",) if scanner_glrt else ()),
        ),
        check=True,
        text=True,
        capture_output=True,
    )
    assert "without changing services, data, or PostgreSQL" in result.stdout
    assert "Re-run with --execute as root" in result.stdout
    assert ("GLRT-capable host runtime" in result.stdout) == scanner_glrt
    if scanner_glrt:
        assert "does not enable GLRT, change the ARM bundle, or authorize RF" in result.stdout
    else:
        assert "default host runtime" in result.stdout
    assert before == sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))


def test_requested_profile_is_checked_for_existing_and_new_releases() -> None:
    script = STAGER.read_text()
    assert script.count('"${runtime_verification_options[@]}"') == 2
    assert "runtime_verification_options=(--runtime-profile scanner-glrt)" in script
    assert script.index('"${runtime_verification_options[@]}"') < script.index(
        "release already staged"
    )
    assert script.rindex('"${runtime_verification_options[@]}"') < script.index(
        'mv -- "$metadata_temp" "$metadata"'
    )
    # Installing host capabilities alone must not mutate runtime enablement or
    # replace the existing fixed-hop ARM daemon and its strict provenance.
    assert "LEO_SCANNER_GLRT_MODE=" not in script
    assert "LEO_SCANNER_HOP_POLICY=" not in script
    assert "scanner_iiod=$staging_dir/runtime/scanner-iiod/iiod" in script
    subprocess.run(("bash", "-n", str(STAGER)), check=True)
