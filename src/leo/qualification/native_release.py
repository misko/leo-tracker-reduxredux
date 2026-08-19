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
from leo.contracts.scientific import TrustedNativeReleaseEvidenceV1
from leo.qualification.release import _validate_deployed_release

ReleaseValidator = Callable[[Path, str], None]
_QNAP = Path("/mnt/qnap01")


def load_trusted_current_release(
    *,
    pipeline_release: str,
    current_link: Path = Path("/opt/leo-tracker/current"),
    deployment_root: Path = Path("/opt/leo-tracker"),
    validator: ReleaseValidator | None = None,
) -> TrustedNativeReleaseEvidenceV1:
    """Validate the selected release and derive immutable Git/metadata identities."""

    if not current_link.is_absolute() or not deployment_root.is_absolute():
        raise ValueError("release selector and deployment root must be absolute")
    if _beneath_qnap(current_link) or _beneath_qnap(deployment_root):
        raise ValueError("native release evidence cannot access QNAP")
    if current_link != deployment_root / "current":
        raise ValueError("current release selector is outside its deployment root")
    _require_real_directory_components(deployment_root)
    current_info = current_link.lstat()
    if not stat.S_ISLNK(current_info.st_mode):
        raise ValueError("current release selector must be a symlink")
    target_text = os.readlink(current_link)
    target = Path(target_text)
    candidate = target if target.is_absolute() else current_link.parent / target
    release = Path(os.path.abspath(candidate))
    if _beneath_qnap(release):
        raise ValueError("selected native release cannot be beneath QNAP")
    releases_root = deployment_root / "releases"
    release_info = release.lstat()
    if (
        release.parent != releases_root
        or stat.S_ISLNK(release_info.st_mode)
        or not stat.S_ISDIR(release_info.st_mode)
    ):
        raise ValueError("current release is outside the canonical releases directory")
    revision = release.name
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("current release is not a full lowercase Git revision")
    metadata = deployment_root / "release-metadata" / f"{revision}.txt"
    if metadata.is_symlink() or not metadata.is_file() or _beneath_qnap(metadata):
        raise ValueError("current release lacks canonical external metadata")

    (validator or _validate_deployed_release)(release, revision)
    observed_revision = _git(release, "rev-parse", "HEAD")
    if observed_revision != revision:
        raise ValueError("validated release checkout differs from selected revision")
    git_tree = _git(release, "rev-parse", "HEAD^{tree}")
    if re.fullmatch(r"[0-9a-f]{40}", git_tree) is None:
        raise ValueError("validated release has an invalid Git tree identity")
    tree_inventory = _git(release, "ls-tree", "-r", "--full-tree", "HEAD")
    source_tree_digest = sha256_digest(tree_inventory.encode("utf-8"))
    metadata_digest = _file_digest(metadata)
    values = {
        "schema_version": 1,
        "kind": "validated-current-native-release",
        "pipeline_release": pipeline_release,
        "source_revision": revision,
        "git_tree": git_tree,
        "source_tree_digest": source_tree_digest,
        "release_metadata_digest": metadata_digest,
        "release_path": str(release),
        "validator": "deployed-release-validators-v1",
    }
    return TrustedNativeReleaseEvidenceV1.model_validate(
        {**values, "evidence_digest": canonical_digest(values)}
    )


def _beneath_qnap(path: Path) -> bool:
    return path == _QNAP or _QNAP in path.parents


def _require_real_directory_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"deployment root contains a non-directory or symlink: {current}")


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
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()
