from __future__ import annotations

import json
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


def _staged_release(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "release"
    repository.mkdir()
    revision = "a" * 40
    tree = "b" * 40
    (repository / ".leo-release-source.json").write_text(
        json.dumps(
            {
                "schema": "org.leo.release-source/v1",
                "revision": revision,
                "tree": tree,
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    return repository, revision, tree


def test_checker_accepts_exact_git_free_source_identity(tmp_path: Path) -> None:
    repository, revision, tree = _staged_release(tmp_path)
    result = _run(str(CHECKER), str(repository), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 0, result.stderr
    assert f"revision={revision} tree={tree}" in result.stdout


def test_checker_rejects_mismatched_revision(tmp_path: Path) -> None:
    repository, revision, _tree = _staged_release(tmp_path)
    result = _run(str(CHECKER), str(repository), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 0

    result = _run(str(CHECKER), str(repository), "c" * 40, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "does not match requested revision" in result.stderr


def test_checker_rejects_missing_or_malformed_source_identity(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    result = _run(str(CHECKER), str(release), "0" * 40, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "source identity is absent" in result.stderr

    marker = release / ".leo-release-source.json"
    marker.write_text('{"schema":"org.leo.release-source/v1","revision":"bad"}\n')
    result = _run(str(CHECKER), str(release), "0" * 40, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "not canonical V1 JSON" in result.stderr


def test_checker_rejects_git_metadata_and_historical_reports(tmp_path: Path) -> None:
    release, revision, _tree = _staged_release(tmp_path)
    (release / ".git").mkdir()
    result = _run(str(CHECKER), str(release), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "contains Git metadata" in result.stderr

    (release / ".git").rmdir()
    (release / "reports").mkdir()
    result = _run(str(CHECKER), str(release), revision, cwd=PROJECT_ROOT)
    assert result.returncode == 65
    assert "contains historical reports" in result.stderr


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
