"""Checks the actual candidate bytes without executing ARM code or contacting a radio."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATOR = PROJECT_ROOT / "deploy/scripts/validate-scanner-glrt-bundle"
FUNCTIONS = runpy.run_path(str(VALIDATOR))
NAMES = (
    "bundle.json",
    "algorithm.json",
    "configuration.json",
    "iiod",
    "worker",
    "libleo-scanner-glrt.so",
    "libfftw3.so.3",
    "libiio.so.0",
    "libxml2.so.2",
    "libz.so.1",
    "templates-2500000.bin",
    "templates-5000000.bin",
)


@pytest.fixture
def release(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    bundle = root / "runtime/scanner-glrt"
    shutil.copytree(PROJECT_ROOT / "runtime/scanner-glrt", bundle)
    bundle.chmod(0o750)
    for name in NAMES:
        (bundle / name).chmod(0o550 if name in ("iiod", "worker") else 0o440)
    return root


def validate(release: Path, **kwargs: object) -> tuple[Path, ...]:
    return FUNCTIONS["inventory"](
        release, expected_uid=os.geteuid(), expected_gid=os.getegid(), **kwargs
    )


def test_actual_bundle_has_exact_order_bytes_and_no_execution(release: Path) -> None:
    paths = validate(release)
    assert tuple(path.name for path in paths) == NAMES
    original = PROJECT_ROOT / "runtime/scanner-glrt"
    assert all(path.read_bytes() == (original / path.name).read_bytes() for path in paths)
    manifest = json.loads((original / "bundle.json").read_text())
    assert manifest["daemon_bytes"] + sum(item["bytes"] for item in manifest["files"]) == 3477064
    assert hashlib.sha256((original / "iiod").read_bytes()).hexdigest() == (
        "5d4cdce3f96d51e4fac38bbcc51a63a7123ff54abd710fc386e75fc89d681af1"
    )


def test_candidate_preserves_capture_guards_and_explicit_unknown_feedback(release: Path) -> None:
    validate(release)
    config = json.loads((release / "runtime/scanner-glrt/configuration.json").read_text())
    assert config["rx"] == 1 and config["rates_hz"] == [2500000, 5000000]
    assert config["valid_dwell_ms"] == 120 and config["maximum_capture_seconds"] == 300
    assert config["bandwidth_equals_rate"] is True
    assert config["positive_policy"] == {"minimum_exact_score": 0.175, "minimum_margin": 0.025}
    protection = config["capture_protection"]
    assert protection["max_occupied_slots"] == 3
    assert protection["admission_age_ms"] == 450 and protection["worker_timeout_ms"] == 500
    assert config["fair_admission"]["maximum_pending_age_ms"] == 240
    assert config["fair_admission"]["maximum_revisit_guaranteed"] is False
    assert config["cooperative_skips"]["provides_negative_evidence"] is False
    assert config["cooperative_skips"]["renews_activity_or_cooldown"] is False
    assert config["cooperative_skips"]["genuine_faults_remain_latched"] is True


def test_only_the_reviewed_sdk_shared_object_is_trackable() -> None:
    for name, expected in (
        ("runtime/scanner-glrt/libleo-scanner-glrt.so", 1),
        ("runtime/scanner-glrt/unreviewed.so", 0),
    ):
        result = subprocess.run(
            ("git", "check-ignore", "--no-index", "-q", name), cwd=PROJECT_ROOT, check=False
        )
        assert result.returncode == expected


@pytest.mark.parametrize("name", NAMES)
def test_every_candidate_file_is_digest_bound(release: Path, name: str) -> None:
    path = release / "runtime/scanner-glrt" / name
    raw = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(raw[:-1] + bytes((raw[-1] ^ 1,)))
    path.chmod(0o550 if name in ("iiod", "worker") else 0o440)
    with pytest.raises(ValueError, match="digest"):
        validate(release)


@pytest.mark.parametrize("name", NAMES)
def test_missing_file_never_becomes_an_optional_absent_bundle(release: Path, name: str) -> None:
    (release / "runtime/scanner-glrt" / name).unlink()
    with pytest.raises(ValueError, match="inventory"):
        validate(release)


def test_absent_bundle_preserves_legacy_release(tmp_path: Path) -> None:
    assert validate(tmp_path) == ()


def test_extra_input_is_rejected_without_being_read(release: Path) -> None:
    (release / "runtime/scanner-glrt/unexpected").symlink_to("/mnt/qnap01/must-not-open")
    with pytest.raises(ValueError, match="inventory"):
        validate(release)


def test_qnap_and_symlinked_directories_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside QNAP"):
        validate(Path("/mnt/qnap01/must-not-open"))
    (tmp_path / "runtime").symlink_to("/mnt/qnap01/must-not-open")
    with pytest.raises(ValueError, match="symlink"):
        validate(tmp_path)


@pytest.mark.parametrize("mutation", ("symlink", "hardlink", "fifo", "writable", "oversize"))
def test_untrusted_inputs_fail_before_use(release: Path, tmp_path: Path, mutation: str) -> None:
    worker = release / "runtime/scanner-glrt/worker"
    if mutation in ("symlink", "fifo"):
        worker.unlink()
        if mutation == "symlink":
            worker.symlink_to("/mnt/qnap01/must-not-open")
        else:
            os.mkfifo(worker, 0o550)
    elif mutation == "hardlink":
        os.link(worker, tmp_path / "peer")
    elif mutation == "writable":
        worker.chmod(0o570)
    else:
        worker.chmod(0o750)
        with worker.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        worker.chmod(0o550)
    with pytest.raises((ValueError, OSError)):
        validate(release)


def test_group_writable_directory_is_rejected(release: Path) -> None:
    (release / "runtime/scanner-glrt").chmod(0o770)
    with pytest.raises(ValueError, match="directory"):
        validate(release)


def test_preseal_mode_does_not_relax_final_release_modes(release: Path) -> None:
    (release / "runtime/scanner-glrt/worker").chmod(0o750)
    assert len(validate(release, staged=True)) == 12
    with pytest.raises(ValueError, match="trusted regular file"):
        validate(release)


def test_cli_emits_only_validated_inventory_in_paths_mode(release: Path) -> None:
    result = subprocess.run(
        (sys.executable, str(VALIDATOR), str(release), "--staged", "--paths"),
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.splitlines() == [
        str(release / "runtime/scanner-glrt" / name) for name in NAMES
    ]


def test_stager_verifies_before_modes_and_seals_all_optional_files() -> None:
    script = (PROJECT_ROOT / "deploy/scripts/stage-production-release").read_text()
    assert script.index(
        '"$staging_dir/deploy/scripts/validate-scanner-glrt-bundle"'
    ) < script.index('chmod 0440 "${scanner_bundle_paths[@]}"')
    assert 'paths.extend(bundle_validator["inventory"](release))' in script
    assert script.index('paths.extend(bundle_validator["inventory"](release))') < script.index(
        '"${metadata_runtime_paths[@]}"'
    )
    assert "if bundle_root.exists() or bundle_root.is_symlink():" in script


def test_git_archive_permissions_override_ambient_config(release: Path, tmp_path: Path) -> None:
    subprocess.run(("git", "-C", str(release), "init", "-q"), check=True)
    subprocess.run(("git", "-C", str(release), "add", "runtime/scanner-glrt"), check=True)
    tree = subprocess.check_output(("git", "-C", str(release), "write-tree"), text=True).strip()
    subprocess.run(("git", "-C", str(release), "config", "tar.umask", "0000"), check=True)
    for corrected in (False, True):
        options = ("-c", "tar.umask=0027") if corrected else ()
        archive = subprocess.check_output(
            ("git", "-C", str(release), *options, "archive", "--format=tar", tree)
        )
        export = tmp_path / f"export-{corrected}"
        export.mkdir()
        # Match root tar's preserve-permissions behavior without requiring root.
        subprocess.run(
            ("tar", "-x", "--same-permissions", "--no-same-owner", "-C", str(export)),
            input=archive,
            check=True,
        )
        if corrected:
            assert len(validate(export, staged=True)) == 12
            assert (export / "runtime/scanner-glrt").stat().st_mode & 0o777 == 0o750
            assert (export / "runtime/scanner-glrt/algorithm.json").stat().st_mode & 0o777 == 0o640
        else:
            with pytest.raises(ValueError, match="directory is not trusted"):
                validate(export, staged=True)
