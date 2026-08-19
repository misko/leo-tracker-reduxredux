from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from leo.contracts.digests import sha256_digest
from leo.qualification.native_release import load_trusted_current_release


def _run(*argv: str, cwd: Path) -> str:
    return subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _published_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _run("git", "init", "-q", cwd=source)
    _run("git", "config", "user.email", "science@example.invalid", cwd=source)
    _run("git", "config", "user.name", "Science Test", cwd=source)
    (source / "tracked.txt").write_text("sealed source\n")
    _run("git", "add", "tracked.txt", cwd=source)
    _run("git", "commit", "-qm", "fixture", cwd=source)
    revision = _run("git", "rev-parse", "HEAD", cwd=source)
    deployment = tmp_path / "deployment"
    release = deployment / "releases" / revision
    release.parent.mkdir(parents=True)
    source.rename(release)
    metadata = deployment / "release-metadata" / f"{revision}.txt"
    metadata.parent.mkdir()
    metadata.write_text(f"revision={revision}\nsealed fixture\n")
    (deployment / "current").symlink_to(release)
    return deployment, metadata, revision


def test_current_release_loader_derives_exact_validated_identities(tmp_path: Path) -> None:
    deployment, metadata, revision = _published_fixture(tmp_path)
    observed: list[tuple[Path, str]] = []

    def validator(release: Path, selected_revision: str) -> None:
        observed.append((release, selected_revision))
        assert metadata.read_text().splitlines()[0] == f"revision={selected_revision}"

    evidence = load_trusted_current_release(
        pipeline_release="science-release",
        current_link=deployment / "current",
        deployment_root=deployment,
        validator=validator,
    )

    assert observed == [(deployment / "releases" / revision, revision)]
    assert evidence.source_revision == revision
    assert evidence.git_tree == _run(
        "git",
        "rev-parse",
        "HEAD^{tree}",
        cwd=deployment / "releases" / revision,
    )
    assert evidence.release_metadata_digest == sha256_digest(metadata.read_bytes())
    assert evidence.source_tree_digest.startswith("sha256:")
    assert evidence.release_path == str(deployment / "releases" / revision)


def test_current_release_loader_rejects_forged_metadata_and_revision(tmp_path: Path) -> None:
    deployment, metadata, revision = _published_fixture(tmp_path)

    def validator(_release: Path, selected_revision: str) -> None:
        if metadata.read_text().splitlines()[0] != f"revision={selected_revision}":
            raise ValueError("metadata revision mismatch")

    metadata.write_text("revision=" + "0" * 40 + "\nforged\n")
    with pytest.raises(ValueError, match="metadata revision mismatch"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=validator,
        )

    metadata.write_text(f"revision={revision}\nrestored\n")
    _run("git", "checkout", "--detach", "HEAD~0", cwd=deployment / "releases" / revision)
    wrong = deployment / "releases" / ("f" * 40)
    (deployment / "current").unlink()
    (deployment / "current").symlink_to(wrong)
    with pytest.raises(FileNotFoundError):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=validator,
        )


def test_current_release_loader_rejects_qnap_without_access() -> None:
    with pytest.raises(ValueError, match="QNAP"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=Path("/mnt/qnap01/must-not-open/current"),
            deployment_root=Path("/mnt/qnap01/must-not-open"),
        )


def test_current_release_loader_rejects_parent_symlink_before_following_qnap(
    tmp_path: Path,
) -> None:
    deployment = tmp_path / "deployment-alias"
    deployment.symlink_to("/mnt/qnap01/must-not-open")
    with pytest.raises(ValueError, match="symlink"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
        )
