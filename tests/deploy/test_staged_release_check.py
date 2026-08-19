from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
CHECKER = PROJECT_ROOT / "deploy" / "scripts" / "check-staged-release"


def _run(*command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _committed_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "release"
    repository.mkdir()
    assert _run("git", "init", "--quiet", cwd=repository).returncode == 0
    assert _run("git", "config", "user.name", "Deployment Test", cwd=repository).returncode == 0
    assert (
        _run(
            "git", "config", "user.email", "deployment-test@example.invalid", cwd=repository
        ).returncode
        == 0
    )
    (repository / "tracked.txt").write_text("sealed\n")
    assert _run("git", "add", "tracked.txt", cwd=repository).returncode == 0
    assert _run("git", "commit", "--quiet", "-m", "fixture", cwd=repository).returncode == 0
    revision = _run("git", "rev-parse", "HEAD", cwd=repository).stdout.strip()
    return repository, revision


def test_checker_accepts_exact_clean_tracked_checkout(tmp_path: Path) -> None:
    repository, revision = _committed_repository(tmp_path)
    result = _run(str(CHECKER), str(repository), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 0, result.stderr
    assert f"verified clean staged release {revision}" in result.stdout


def test_checker_rejects_modified_tracked_checkout(tmp_path: Path) -> None:
    repository, revision = _committed_repository(tmp_path)
    (repository / "tracked.txt").write_text("modified\n")
    result = _run(str(CHECKER), str(repository), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "staged release has modified tracked files" in result.stderr
    assert "tracked.txt" in result.stderr


def test_checker_propagates_git_failure_instead_of_treating_output_as_clean(
    tmp_path: Path,
) -> None:
    not_a_repository = tmp_path / "not-a-repository"
    not_a_repository.mkdir()
    result = _run(str(CHECKER), str(not_a_repository), "0" * 40, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "cannot resolve staged release HEAD" in result.stderr
    assert "verified clean" not in result.stdout


def test_checker_propagates_status_failure_after_revision_succeeds(tmp_path: Path) -> None:
    revision = "c" * 40
    release = tmp_path / "release"
    release.mkdir()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == *'rev-parse --verify HEAD'* ]]; then\n"
        f"  echo {revision}\n"
        "  exit 0\n"
        "fi\n"
        "echo 'simulated status failure' >&2\n"
        "exit 128\n"
    )
    fake_git.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    result = subprocess.run(
        (str(CHECKER), str(release), revision),
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 65
    assert "simulated status failure" in result.stderr
    assert "cannot inspect staged release tracked-file cleanliness" in result.stderr
    assert "verified clean" not in result.stdout


def test_nonblocking_publication_lock_rejects_concurrent_holder(tmp_path: Path) -> None:
    lock = tmp_path / "publisher.lock"
    holder = subprocess.Popen(
        ("flock", "-x", str(lock), "sh", "-c", "echo locked; cat >/dev/null"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        contender = subprocess.run(
            ("flock", "-n", str(lock), "true"),
            text=True,
            capture_output=True,
            check=False,
        )
        assert contender.returncode != 0
    finally:
        if holder.stdin is not None:
            holder.stdin.close()
        holder.wait(timeout=5)
