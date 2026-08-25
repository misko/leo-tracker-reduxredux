from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.scientific import TrustedNativeReleaseEvidenceV2
from leo.qualification import native_release
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
    (source / "tools").mkdir()
    (source / "tools/native_evidence_worker.py").write_text("# sealed worker\n")
    _run("git", "add", "tracked.txt", "tools/native_evidence_worker.py", cwd=source)
    _run("git", "commit", "-qm", "fixture", cwd=source)
    revision = _run("git", "rev-parse", "HEAD", cwd=source)
    deployment = tmp_path / "deployment"
    release = deployment / "releases" / revision
    release.parent.mkdir(parents=True)
    source.rename(release)
    interpreter = release / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\n")
    package = release / ".venv/lib/python3.12/site-packages/leo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("# sealed installed package\n")
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


def test_selected_current_revision_is_a_bounded_no_validator_read(tmp_path: Path) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)

    assert (
        native_release.selected_current_revision(
            current_link=deployment / "current",
            deployment_root=deployment,
        )
        == revision
    )

    replacement = "f" * 40
    (deployment / "releases" / replacement).mkdir()
    (deployment / "current").unlink()
    (deployment / "current").symlink_to(deployment / "releases" / replacement)
    assert (
        native_release.selected_current_revision(
            current_link=deployment / "current",
            deployment_root=deployment,
        )
        == replacement
    )


def test_in_process_revalidation_detects_runtime_mutation(tmp_path: Path) -> None:
    deployment, _metadata, _revision = _published_fixture(tmp_path)
    evidence = load_trusted_current_release(
        pipeline_release="science-release",
        current_link=deployment / "current",
        deployment_root=deployment,
        validator=lambda _release, _revision: None,
    )

    native_release.assert_trusted_current_release_unchanged(
        evidence,
        current_link=deployment / "current",
        deployment_root=deployment,
    )
    worker = Path(evidence.release_path) / "tools/native_evidence_worker.py"
    worker.write_text("# mutated worker\n")
    with pytest.raises(ValueError, match="worker_digest"):
        native_release.assert_trusted_current_release_unchanged(
            evidence,
            current_link=deployment / "current",
            deployment_root=deployment,
        )


def test_release_git_reads_use_exact_safe_directory_without_index_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def execute(argv, **kwargs):  # noqa: ANN001, ANN003, ANN202
        observed["argv"] = argv
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, stdout="revision\n")

    monkeypatch.setattr(native_release.subprocess, "run", execute)
    root = Path("/opt/leo-tracker/releases/" + "a" * 40)
    assert native_release._git(root, "rev-parse", "HEAD") == "revision"
    assert observed["argv"] == (
        "/usr/bin/git",
        "-c",
        f"safe.directory={root}",
        "-C",
        str(root),
        "rev-parse",
        "HEAD",
    )
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"


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
    with pytest.raises(ValueError, match="no-follow directory"):
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


@pytest.mark.parametrize(
    "root",
    (
        Path("/tmp/../mnt/qnap01/must-not-open"),
        Path("//mnt/qnap01"),
        Path("//mnt/qnap01/must-not-open"),
    ),
)
def test_qnap_alias_is_rejected_before_any_filesystem_call(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> None:
    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("QNAP traversal reached a filesystem syscall")

    monkeypatch.setattr(native_release.os, "open", forbidden_open)
    with pytest.raises(ValueError, match="QNAP|double slash"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=root / "current",
            deployment_root=root,
        )


def test_alternate_release_root_requires_explicit_validator(tmp_path: Path) -> None:
    deployment, _metadata, _revision = _published_fixture(tmp_path)
    with pytest.raises(ValueError, match="explicit release validator"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
        )


@pytest.mark.parametrize(
    "component",
    ("releases", "release-metadata", "revision", "metadata", "current"),
)
def test_current_release_loader_rejects_symlinked_or_nonlink_components(
    tmp_path: Path,
    component: str,
) -> None:
    deployment, metadata, revision = _published_fixture(tmp_path)
    if component == "current":
        (deployment / "current").unlink()
        (deployment / "current").write_text(str(deployment / "releases" / revision))
    elif component == "metadata":
        external = tmp_path / "external-metadata.txt"
        metadata.rename(external)
        metadata.symlink_to(external)
    else:
        target = (
            deployment / component
            if component in {"releases", "release-metadata"}
            else deployment / "releases" / revision
        )
        external = tmp_path / f"external-{component}"
        target.rename(external)
        target.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink|no-follow|selector|component|metadata"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=lambda _release, _revision: None,
        )


@pytest.mark.parametrize(
    "unsafe",
    (
        "/mnt/qnap01",
        "/mnt/qnap01/science",
        "/tmp/../mnt/qnap01/science",
        "//mnt/qnap01",
        "//mnt/qnap01/science",
    ),
)
def test_native_release_contract_rejects_noncanonical_or_qnap_root(
    tmp_path: Path,
    unsafe: str,
) -> None:
    deployment, _metadata, _revision = _published_fixture(tmp_path)
    evidence = load_trusted_current_release(
        pipeline_release="science-release",
        current_link=deployment / "current",
        deployment_root=deployment,
        validator=lambda _release, _revision: None,
    )
    values = evidence.model_dump(mode="python", exclude={"evidence_digest"})
    values["release_path"] = unsafe
    with pytest.raises(ValueError, match="unsafe"):
        TrustedNativeReleaseEvidenceV2(
            **values,
            evidence_digest=canonical_digest(values),
        )


def test_interpreter_qnap_symlink_is_rejected_without_target_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    interpreter = deployment / "releases" / revision / ".venv/bin/python"
    interpreter.unlink()
    interpreter.symlink_to("/mnt/qnap01/must-not-open/python")
    opened: list[Path] = []
    original = native_release._open_absolute_directory

    def observed(path: Path) -> int:
        opened.append(path)
        assert not native_release._beneath_qnap(path)
        return original(path)

    monkeypatch.setattr(native_release, "_open_absolute_directory", observed)
    validator_called = False

    def validator(_release: Path, _revision: str) -> None:
        nonlocal validator_called
        validator_called = True

    with pytest.raises(ValueError, match="QNAP"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=validator,
        )
    assert opened
    assert validator_called is False


def test_release_evidence_attests_installed_leo_package_tree(tmp_path: Path) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    arguments = {
        "pipeline_release": "science-release",
        "current_link": deployment / "current",
        "deployment_root": deployment,
        "validator": lambda _release, _revision: None,
    }
    before = load_trusted_current_release(**arguments)
    package = deployment / "releases" / revision / ".venv/lib/python3.12/site-packages/leo"
    (package / "numerical.py").write_text("VALUE = 1\n")
    after = load_trusted_current_release(**arguments)
    assert after.runtime_package_tree_digest != before.runtime_package_tree_digest


def test_checked_hash_bytecode_is_stable_across_writable_runtime_imports(
    tmp_path: Path,
) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    release = deployment / "releases" / revision
    site_packages = release / ".venv/lib/python3.12/site-packages"
    package = site_packages / "leo"
    subprocess.run(
        (
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "-f",
            "--invalidation-mode",
            "checked-hash",
            str(site_packages),
        ),
        check=True,
    )
    bytecode = tuple(sorted(package.rglob("*.pyc")))
    assert bytecode
    before = native_release._runtime_package_tree_digest(release)
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment["PYTHONPATH"] = str(site_packages)

    for _ in range(2):
        subprocess.run(
            (sys.executable, "-c", "import leo"),
            cwd=tmp_path,
            env=environment,
            check=True,
        )

    assert tuple(sorted(package.rglob("*.pyc"))) == bytecode
    assert native_release._runtime_package_tree_digest(release) == before


def test_release_evidence_does_not_exempt_python_bytecode(tmp_path: Path) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    evidence = load_trusted_current_release(
        pipeline_release="science-release",
        current_link=deployment / "current",
        deployment_root=deployment,
        validator=lambda _release, _revision: None,
    )
    package = deployment / "releases" / revision / ".venv/lib/python3.12/site-packages/leo"
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-312.pyc").write_bytes(b"new executable bytecode")

    with pytest.raises(ValueError, match="runtime_package_tree_digest"):
        native_release.assert_trusted_current_release_unchanged(
            evidence,
            current_link=deployment / "current",
            deployment_root=deployment,
        )


def test_runtime_mutation_during_release_validation_is_rejected(tmp_path: Path) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    package = deployment / "releases" / revision / ".venv/lib/python3.12/site-packages/leo"

    def mutate(_release: Path, _revision: str) -> None:
        (package / "__init__.py").write_text("mutated during validation\n")

    with pytest.raises(ValueError, match="runtime"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=mutate,
        )


def test_installed_package_symlink_is_rejected_without_target_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment, _metadata, revision = _published_fixture(tmp_path)
    package = deployment / "releases" / revision / ".venv/lib/python3.12/site-packages/leo"
    for child in package.iterdir():
        child.unlink()
    package.rmdir()
    package.symlink_to("/mnt/qnap01/must-not-open/leo", target_is_directory=True)
    original = native_release._open_absolute_directory

    def observed(path: Path) -> int:
        assert not native_release._beneath_qnap(path)
        return original(path)

    monkeypatch.setattr(native_release, "_open_absolute_directory", observed)
    with pytest.raises(ValueError, match="no-follow directory|exactly one"):
        load_trusted_current_release(
            pipeline_release="science-release",
            current_link=deployment / "current",
            deployment_root=deployment,
            validator=lambda _release, _revision: None,
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
            validator=lambda _release, _revision: None,
        )
