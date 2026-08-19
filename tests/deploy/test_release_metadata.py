from __future__ import annotations

import hashlib
import os
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATOR = PROJECT_ROOT / "deploy" / "scripts" / "validate-release-metadata"
GLOBALS = runpy.run_path(str(VALIDATOR))
REVISION = "f" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _published(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "leo-tracker"
    release = root / "releases" / REVISION
    metadata = root / "release-metadata" / f"{REVISION}.txt"
    tooling = root / "tooling/uv"
    (release / "web").mkdir(parents=True)
    metadata.parent.mkdir()
    tooling.parent.mkdir()
    tooling.write_bytes(b"uv-binary")
    (release / "uv.lock").write_text("python-lock\n")
    (release / "web/package-lock.json").write_text("node-lock\n")
    paths = (tooling, release / "uv.lock", release / "web/package-lock.json")
    metadata.write_text(
        f"revision={REVISION}\n" + "".join(f"{_sha256(path)}  {path}\n" for path in paths)
    )
    metadata.chmod(0o440)
    for path in (release, *release.rglob("*")):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o022)
    return release, metadata


def _validate(release: Path, metadata: Path, **kwargs: object) -> None:
    GLOBALS["validate"](
        release,
        metadata,
        REVISION,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        **kwargs,
    )


def test_external_metadata_seals_exact_immutable_tree(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    _validate(release, metadata)


def test_metadata_digest_tamper_fails(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    (release / "uv.lock").chmod(0o640)
    (release / "uv.lock").write_text("changed\n")
    (release / "uv.lock").chmod(0o440)
    with pytest.raises(ValueError, match="digest does not verify"):
        _validate(release, metadata)


def test_incomplete_and_validation_failed_markers_fail_closed(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    incomplete = release / ".leo-release-incomplete"
    incomplete.write_text("")
    incomplete.chmod(0o440)
    with pytest.raises(ValueError, match="incomplete marker"):
        _validate(release, metadata)
    metadata_temp = metadata.parent / f".{REVISION}.fixture.tmp"
    metadata.rename(metadata_temp)
    _validate(release, metadata_temp, allow_incomplete=True)
    metadata_temp.rename(metadata)

    incomplete.unlink()
    failed = release / ".leo-release-validation-failed"
    failed.write_text("")
    failed.chmod(0o440)
    with pytest.raises(ValueError, match="validation-failed"):
        _validate(release, metadata)


def test_group_writable_release_entry_fails(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    artifact = release / "uv.lock"
    artifact.chmod(0o460)
    with pytest.raises(ValueError, match="group/other writable"):
        _validate(release, metadata)


def test_release_tree_qnap_symlink_fails_without_target_access(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    (release / "forbidden-link").symlink_to("/mnt/qnap01/must-not-be-opened")
    with pytest.raises(ValueError, match="beneath QNAP"):
        _validate(release, metadata)
