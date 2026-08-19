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

    current_link = _canonical_absolute(current_link, "release selector")
    deployment_root = _canonical_absolute(deployment_root, "deployment root")
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
        release = _normalized_absolute(candidate, "selected native release")
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

    worker = release / "tools/native_evidence_worker.py"
    interpreter = release / ".venv/bin/python"
    worker_digest = _file_digest(worker)
    interpreter_target = _resolve_regular_file(interpreter)
    interpreter_digest = _file_digest(interpreter_target)
    runtime_package_tree_digest = _runtime_package_tree_digest(release)
    (validator or _validate_deployed_release)(release, revision)
    observed_release, observed_metadata = _reopen_identities(
        deployment_root,
        revision,
        metadata_name,
    )
    if (
        observed_release != (release_identity.st_dev, release_identity.st_ino)
        or observed_metadata != (metadata_identity.st_dev, metadata_identity.st_ino)
        or _file_digest(worker) != worker_digest
        or _file_digest(_resolve_regular_file(interpreter)) != interpreter_digest
        or _runtime_package_tree_digest(release) != runtime_package_tree_digest
    ):
        raise ValueError("release, runtime, or metadata changed during validation")
    observed_revision = _git(release, "rev-parse", "HEAD")
    if observed_revision != revision:
        raise ValueError("validated release checkout differs from selected revision")
    git_tree = _git(release, "rev-parse", "HEAD^{tree}")
    if re.fullmatch(r"[0-9a-f]{40}", git_tree) is None:
        raise ValueError("validated release has an invalid Git tree identity")
    tree_inventory = _git(release, "ls-tree", "-r", "--full-tree", "HEAD")
    source_tree_digest = sha256_digest(tree_inventory.encode("utf-8"))
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
        "runtime_package_tree_digest": runtime_package_tree_digest,
        "release_path": str(release),
        "validator": "deployed-release-validators-v1",
    }
    return TrustedNativeReleaseEvidenceV2.model_validate(
        {**values, "evidence_digest": canonical_digest(values)}
    )


def _beneath_qnap(path: Path) -> bool:
    normalized = Path(os.path.normpath(os.fspath(path)))
    return normalized == _QNAP or _QNAP in normalized.parents


def _normalized_absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    if os.fspath(path).startswith("//"):
        raise ValueError(f"{label} must not begin with a double slash")
    normalized = Path(os.path.normpath(os.fspath(path)))
    if _beneath_qnap(normalized):
        raise ValueError(f"{label} cannot access QNAP")
    return normalized


def _canonical_absolute(path: Path, label: str) -> Path:
    normalized = _normalized_absolute(path, label)
    if normalized != path:
        raise ValueError(f"{label} must be a canonical absolute path")
    return normalized


def _open_absolute_directory(path: Path) -> int:
    path = _canonical_absolute(path, "directory")
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
    path = _canonical_absolute(path, "file")
    parent_fd = _open_absolute_directory(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError(f"file is not a readable no-follow regular file: {path.name}") from error
    finally:
        os.close(parent_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("file digest input is not regular")
        return _descriptor_digest(descriptor)
    finally:
        os.close(descriptor)


def _resolve_regular_file(path: Path) -> Path:
    candidate = _normalized_absolute(path, "runtime executable")
    for _ in range(16):
        parent_fd = _open_absolute_directory(candidate.parent)
        try:
            info = os.stat(candidate.name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                return candidate
            if not stat.S_ISLNK(info.st_mode):
                raise ValueError("runtime executable is neither regular nor a symlink")
            target_text = os.readlink(candidate.name, dir_fd=parent_fd)
        except OSError as error:
            raise ValueError(
                "runtime executable is inaccessible without following links"
            ) from error
        finally:
            os.close(parent_fd)
        target = Path(target_text)
        candidate = _normalized_absolute(
            target if target.is_absolute() else candidate.parent / target,
            "runtime executable target",
        )
    raise ValueError("runtime executable contains too many symlink hops")


def _runtime_package_tree_digest(release: Path) -> str:
    library = _canonical_absolute(release / ".venv/lib", "runtime library")
    library_fd = _open_absolute_directory(library)
    package_fds: list[int] = []
    try:
        for python_name in sorted(os.listdir(library_fd)):
            if re.fullmatch(r"python\d+\.\d+", python_name) is None:
                continue
            python_fd = _open_directory_at(library_fd, python_name)
            site_fd: int | None = None
            try:
                site_fd = _open_directory_at(python_fd, "site-packages")
                package_fds.append(_open_directory_at(site_fd, "leo"))
            except ValueError:
                pass
            finally:
                if site_fd is not None:
                    os.close(site_fd)
                os.close(python_fd)
        if len(package_fds) != 1:
            raise ValueError("validated release must contain exactly one installed leo package")
        return _directory_tree_digest(package_fds[0])
    finally:
        for descriptor in package_fds:
            os.close(descriptor)
        os.close(library_fd)


def _directory_tree_digest(root_fd: int) -> str:
    inventory: list[dict[str, object]] = []

    def visit(directory_fd: int, prefix: str) -> None:
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child_fd = _open_directory_at(directory_fd, name)
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    inventory.append(
                        {
                            "path": relative,
                            "size": info.st_size,
                            "digest": _descriptor_digest(descriptor),
                        }
                    )
                finally:
                    os.close(descriptor)
            else:
                raise ValueError(f"runtime package contains an unsafe entry: {relative}")

    visit(root_fd, "")
    if not inventory:
        raise ValueError("installed leo runtime package is empty")
    return canonical_digest(inventory)


def _descriptor_digest(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()
