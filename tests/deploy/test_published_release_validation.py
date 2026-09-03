from __future__ import annotations

import json
import runpy
import stat
import subprocess
import tomllib
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-published-release"
GLOBALS = runpy.run_path(str(VALIDATOR))


def test_ppu_pin_is_one_exact_dependency_authority() -> None:
    expected = "e7990eb3b7adfdb9a20d92bf2945c890727d2979"
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)
    provenance = json.loads((PROJECT_ROOT / "docs/dependencies/pluto-plus-utils.json").read_text())
    lock = (PROJECT_ROOT / "uv.lock").read_text()

    assert project["tool"]["uv"]["sources"]["pluto-plus-utils"]["rev"] == expected
    assert provenance["revision"] == expected
    assert f"#{expected}" in lock


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


def test_metadata_runtime_validation_scrubs_ambient_loader_state(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    python = tmp_path / "release/.venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    observed: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def execute(command, **kwargs):  # noqa: ANN001, ANN003, ANN202
        observed.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("LD_LIBRARY_PATH", "/ambient")
    monkeypatch.setenv("PYTHONPATH", "/ambient-python")
    monkeypatch.setenv("PLUTO_LIBIIO_LIBRARY", "/ambient/libiio.so")
    monkeypatch.setattr(GLOBALS["subprocess"], "run", execute)

    GLOBALS["validate_metadata_runtime"](python)

    command, environment = observed[0]
    assert command[:4] == (str(python), "-I", "-B", "-c")
    assert "expected_abi=3" in command[4]
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "LD_LIBRARY_PATH" not in environment
    assert "PYTHONPATH" not in environment
    assert "PLUTO_LIBIIO_LIBRARY" not in environment


def test_published_release_closes_installed_ppu_against_exact_uv_revision(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    expected = "e7990eb3b7adfdb9a20d92bf2945c890727d2979"
    release = tmp_path / "release"
    release.mkdir()
    (release / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        f'pluto-plus-utils = {{ git = "https://example.test/ppu", rev = "{expected}" }}\n'
    )

    class Distribution:
        @staticmethod
        def read_text(name):  # noqa: ANN001, ANN205
            assert name == "direct_url.json"
            return json.dumps(
                {
                    "url": "https://example.test/ppu",
                    "vcs_info": {"vcs": "git", "commit_id": expected},
                }
            )

    monkeypatch.setattr(
        GLOBALS["importlib"].metadata,
        "distribution",
        lambda name: Distribution() if name == "pluto-plus-utils" else None,
    )

    assert GLOBALS["validate_pluto_plus_utils_revision"](release) == expected

    bad = Distribution()
    monkeypatch.setattr(
        bad,
        "read_text",
        lambda _name: json.dumps({"vcs_info": {"vcs": "git", "commit_id": "0" * 40}}),
    )
    monkeypatch.setattr(GLOBALS["importlib"].metadata, "distribution", lambda _name: bad)
    try:
        GLOBALS["validate_pluto_plus_utils_revision"](release)
    except ValueError as error:
        assert "differs from uv authority" in str(error)
    else:
        raise AssertionError("a mismatched installed pluto-plus-utils revision was accepted")
