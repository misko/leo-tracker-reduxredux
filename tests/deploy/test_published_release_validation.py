from __future__ import annotations

import runpy
import stat
import subprocess
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-published-release"
GLOBALS = runpy.run_path(str(VALIDATOR))


def test_binary_scan_finds_reference_crossing_chunk_boundary(tmp_path: Path) -> None:
    forbidden = "/opt/leo-tracker/releases/.staging-deadbeef"
    prefix = b"x" * (1024 * 1024 - 7)
    artifact = tmp_path / "entrypoint"
    artifact.write_bytes(prefix + forbidden.encode() + b"\n")

    found = GLOBALS["find_forbidden_reference"](tmp_path, forbidden)
    assert found == artifact


def test_binary_scan_ignores_clean_tree_and_symlinks(tmp_path: Path) -> None:
    forbidden = "/opt/leo-tracker/releases/.staging-deadbeef"
    clean = tmp_path / "clean"
    clean.write_text("/opt/leo-tracker/releases/final\n")
    outside = tmp_path.parent / "outside-reference"
    outside.write_text(forbidden)
    (tmp_path / "ignored-link").symlink_to(outside)

    assert GLOBALS["find_forbidden_reference"](tmp_path, forbidden) is None


def test_release_symlink_to_qnap_is_rejected_without_target_access(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.symlink_to("/mnt/qnap01/must-not-be-opened")
    try:
        GLOBALS["_safe_absolute"](release, "release")
    except ValueError as error:
        assert "symlink components" in str(error)
    else:
        raise AssertionError("QNAP-targeting release symlink was accepted")


def test_each_release_runs_its_own_sealed_uv_after_a_later_stage(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    release_a = releases / ("a" * 40)
    release_b = releases / ("b" * 40)
    for release, version in ((release_a, "uv A"), (release_b, "uv B")):
        uv = release / ".release-tools/uv"
        uv.parent.mkdir(parents=True)
        uv.write_text(f"#!/bin/sh\nprintf '{version}\\n'\n")
        uv.chmod(uv.stat().st_mode | stat.S_IXUSR)

    assert GLOBALS["validate_release_uv"](release_b) == "uv B"
    assert GLOBALS["validate_release_uv"](release_a) == "uv A"


def test_runtime_validation_disables_bytecode_for_entrypoints(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    release = tmp_path / ("a" * 40)
    venv = release / ".venv"
    bin_root = venv / "bin"
    bin_root.mkdir(parents=True)
    python = bin_root / "python"
    python.write_text("#!/bin/sh\n")
    for name in ("leo", "leo-api", "leo-release-qualify"):
        entrypoint = bin_root / name
        entrypoint.write_text(f"#!{python}\n")
        entrypoint.chmod(0o755)
    uv = release / ".release-tools/uv"
    uv.parent.mkdir(parents=True)
    uv.write_text("#!/bin/sh\nprintf 'uv test\\n'\n")
    uv.chmod(0o755)
    observed: list[dict[str, str]] = []

    def execute(*_args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if "env" in kwargs:
            observed.append(kwargs["env"])
        return subprocess.CompletedProcess((), 0, stdout="uv test\n")

    monkeypatch.setattr(GLOBALS["subprocess"], "run", execute)

    # The current checkout's module identity is intentionally outside the fake
    # venv, so validation stops after exercising all three entrypoints.
    with suppress(AttributeError, ValueError):
        GLOBALS["validate"](release, "")
    assert observed
    assert all(item["PYTHONDONTWRITEBYTECODE"] == "1" for item in observed)
