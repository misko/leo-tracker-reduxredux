from __future__ import annotations

import hashlib
import json
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


def _published(
    tmp_path: Path, *, revision: str = REVISION, uv_bytes: bytes = b"uv-binary"
) -> tuple[Path, Path]:
    root = tmp_path / "leo-tracker"
    release = root / "releases" / revision
    metadata = root / "release-metadata" / f"{revision}.txt"
    tooling = release / ".release-tools/uv"
    python = tmp_path / "system-bin/python3.14"
    (release / "web").mkdir(parents=True)
    metadata.parent.mkdir()
    tooling.parent.mkdir()
    python.parent.mkdir()
    tooling.write_bytes(uv_bytes)
    python.write_text("#!/bin/sh\nprintf '3.14\\n'\n")
    python.chmod(0o755)
    (release / "uv.lock").write_text("python-lock\n")
    (release / "web/package-lock.json").write_text("node-lock\n")
    native = release / ".venv/lib/libiio.so.0.25"
    binding = release / ".venv/lib/python3.14/site-packages/iio.py"
    receipt = release / ".venv/share/pluto-plus-utils/metadata-runtime.json"
    native.parent.mkdir(parents=True)
    binding.parent.mkdir(parents=True)
    receipt.parent.mkdir(parents=True)
    native.write_bytes(b"metadata libiio ABI 3")
    binding.write_text("# patched pylibiio\n")
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata_abi": 3,
                "source_commit": "1e5002702f3033f5bc741da315dfe5d5558ef394",
                "native_libiio_path": str(native),
                "pylibiio_path": str(binding),
            }
        )
    )
    paths = (
        python,
        tooling,
        release / "uv.lock",
        release / "web/package-lock.json",
        receipt,
        native,
        binding,
    )
    metadata.write_text(
        f"revision={revision}\n"
        f"python={python}\n"
        "python_version=3.14\n" + "".join(f"{_sha256(path)}  {path}\n" for path in paths)
    )
    metadata.chmod(0o440)
    for path in (release, *release.rglob("*")):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o022)
    return release, metadata


def _validate(release: Path, metadata: Path, *, revision: str = REVISION, **kwargs: object) -> None:
    GLOBALS["validate"](
        release,
        metadata,
        revision,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        expected_python_prefix=release.parents[2] / "system-bin",
        expected_python_uid=os.getuid(),
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


def test_metadata_native_runtime_tamper_fails(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    native = release / ".venv/lib/libiio.so.0.25"
    native.chmod(0o640)
    native.write_bytes(b"changed metadata runtime")
    native.chmod(0o440)
    with pytest.raises(ValueError, match="digest does not verify"):
        _validate(release, metadata)


def test_pre_ring_runtime_identity_is_rejected_even_with_matching_file_hashes(tmp_path):
    release, metadata = _published(tmp_path)
    receipt = release / ".venv/share/pluto-plus-utils/metadata-runtime.json"
    document = json.loads(receipt.read_text())
    document["source_commit"] = "f72a72602e4ac0173bc7dd5842d831007baa3582"
    receipt.chmod(0o640)
    receipt.write_text(json.dumps(document))
    receipt.chmod(0o440)
    with pytest.raises(ValueError, match="production ABI 3 runtime"):
        _validate(release, metadata)


def test_metadata_python_version_mismatch_fails(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    metadata.chmod(0o640)
    metadata.write_text(metadata.read_text().replace("python_version=3.14", "python_version=3.12"))
    metadata.chmod(0o440)

    with pytest.raises(ValueError, match="path and observed version"):
        _validate(release, metadata)


def test_metadata_python_executable_replacement_fails(tmp_path: Path) -> None:
    release, metadata = _published(tmp_path)
    python = release.parents[2] / "system-bin/python3.14"
    python.write_text("#!/bin/sh\nprintf '3.14\\n'\n# replacement\n")

    with pytest.raises(ValueError, match="digest does not verify"):
        _validate(release, metadata)


def test_later_stage_with_different_uv_does_not_invalidate_older_release(
    tmp_path: Path,
) -> None:
    revision_a = "a" * 40
    revision_b = "b" * 40
    release_a, metadata_a = _published(tmp_path / "a", revision=revision_a, uv_bytes=b"uv-a")
    release_b, metadata_b = _published(tmp_path / "b", revision=revision_b, uv_bytes=b"uv-b")

    _validate(release_b, metadata_b, revision=revision_b)
    _validate(release_a, metadata_a, revision=revision_a)


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
