"""Trusted current-release evidence for scientific native execution."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.scientific import TrustedNativeReleaseEvidenceV2
from leo.qualification.release import _validate_deployed_release

ReleaseValidator = Callable[[Path, str], None]
_QNAP = Path("/mnt/qnap01")


def load_trusted_current_release(
    *,
    pipeline_release: str,
    current_link: Path = Path("/opt/leo-tracker/current"),
    deployment_root: Path = Path("/opt/leo-tracker"),
    validator: ReleaseValidator | None = None,
) -> TrustedNativeReleaseEvidenceV2:
    """Validate the selected release and derive immutable Git/metadata identities."""

    if not current_link.is_absolute() or not deployment_root.is_absolute():
        raise ValueError("release selector and deployment root must be absolute")
    if _beneath_qnap(current_link) or _beneath_qnap(deployment_root):
        raise ValueError("native release evidence cannot access QNAP")
    if current_link != deployment_root / "current":
        raise ValueError("current release selector is outside its deployment root")
    if deployment_root != Path("/opt/leo-tracker") and validator is None:
        raise ValueError("alternate deployment roots require an explicit release validator")
    root_fd = _open_absolute_directory(deployment_root)
    releases_fd: int | None = None
    metadata_root_fd: int | None = None
    release_fd: int | None = None
    metadata_fd: int | None = None
    try:
        releases_fd = _open_directory_at(root_fd, "releases")
        metadata_root_fd = _open_directory_at(root_fd, "release-metadata")
        try:
            target_text = os.readlink("current", dir_fd=root_fd)
        except OSError as error:
            raise ValueError("current release selector is not a readable symlink") from error
        target = Path(target_text)
        candidate = target if target.is_absolute() else deployment_root / target
        release = Path(os.path.abspath(candidate))
        if _beneath_qnap(release) or release.parent != deployment_root / "releases":
            raise ValueError("selected native release is outside the canonical release root")
        revision = release.name
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise ValueError("current release is not a full lowercase Git revision")
        release_fd = _open_directory_at(releases_fd, revision)
        metadata_name = f"{revision}.txt"
        try:
            metadata_fd = os.open(
                metadata_name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=metadata_root_fd,
            )
        except OSError as error:
            raise ValueError("release metadata is not a readable no-follow file") from error
        if not stat.S_ISREG(os.fstat(metadata_fd).st_mode):
            raise ValueError("release metadata is not a regular no-follow file")
        release_identity = os.fstat(release_fd)
        metadata_identity = os.fstat(metadata_fd)
        metadata_digest = _descriptor_digest(metadata_fd)
    finally:
        for descriptor in (metadata_fd, release_fd, metadata_root_fd, releases_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)

    (validator or _validate_deployed_release)(release, revision)
    observed_release, observed_metadata = _reopen_identities(
        deployment_root,
        revision,
        metadata_name,
    )
    if (
        observed_release != (release_identity.st_dev, release_identity.st_ino)
        or observed_metadata != (metadata_identity.st_dev, metadata_identity.st_ino)
    ):
        raise ValueError("release or metadata identity changed during validation")
    observed_revision = _git(release, "rev-parse", "HEAD")
    if observed_revision != revision:
        raise ValueError("validated release checkout differs from selected revision")
    git_tree = _git(release, "rev-parse", "HEAD^{tree}")
    if re.fullmatch(r"[0-9a-f]{40}", git_tree) is None:
        raise ValueError("validated release has an invalid Git tree identity")
    tree_inventory = _git(release, "ls-tree", "-r", "--full-tree", "HEAD")
    source_tree_digest = sha256_digest(tree_inventory.encode("utf-8"))
    worker = release / "tools/native_evidence_worker.py"
    interpreter = release / ".venv/bin/python"
    worker_digest = _file_digest(worker)
    interpreter_target = interpreter.resolve(strict=True)
    if _beneath_qnap(interpreter_target):
        raise ValueError("validated release interpreter resolves beneath QNAP")
    interpreter_digest = _file_digest(interpreter_target)
    values = {
        "schema_version": 2,
        "kind": "validated-current-native-release",
        "pipeline_release": pipeline_release,
        "source_revision": revision,
        "git_tree": git_tree,
        "source_tree_digest": source_tree_digest,
        "release_metadata_digest": metadata_digest,
        "worker_digest": worker_digest,
        "interpreter_digest": interpreter_digest,
        "release_path": str(release),
        "validator": "deployed-release-validators-v1",
    }
    return TrustedNativeReleaseEvidenceV2.model_validate(
        {**values, "evidence_digest": canonical_digest(values)}
    )


def _beneath_qnap(path: Path) -> bool:
    return path == _QNAP or _QNAP in path.parents


def _open_absolute_directory(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise ValueError(
                    f"deployment root contains an inaccessible or symlink component: {component}"
                ) from error
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        raise ValueError(f"release path component is not a no-follow directory: {name}") from error


def _reopen_identities(
    deployment_root: Path,
    revision: str,
    metadata_name: str,
) -> tuple[tuple[int, int], tuple[int, int]]:
    root_fd = _open_absolute_directory(deployment_root)
    releases_fd: int | None = None
    metadata_root_fd: int | None = None
    release_fd: int | None = None
    metadata_fd: int | None = None
    try:
        releases_fd = _open_directory_at(root_fd, "releases")
        metadata_root_fd = _open_directory_at(root_fd, "release-metadata")
        release_fd = _open_directory_at(releases_fd, revision)
        try:
            metadata_fd = os.open(
                metadata_name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=metadata_root_fd,
            )
        except OSError as error:
            raise ValueError("release metadata changed to an unsafe path") from error
        release_identity = os.fstat(release_fd)
        metadata_identity = os.fstat(metadata_fd)
        if not stat.S_ISREG(metadata_identity.st_mode):
            raise ValueError("release metadata changed to a non-regular file")
        return (
            (release_identity.st_dev, release_identity.st_ino),
            (metadata_identity.st_dev, metadata_identity.st_ino),
        )
    finally:
        for descriptor in (metadata_fd, release_fd, metadata_root_fd, releases_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("/usr/bin/git", "-C", str(root), *arguments),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    return result.stdout.strip()


def _file_digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        return _descriptor_digest(descriptor)
    finally:
        os.close(descriptor)


def _descriptor_digest(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()
