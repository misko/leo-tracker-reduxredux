from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
CLEANER = PROJECT_ROOT / "deploy" / "scripts" / "remove-unpublished-release"
REVISION = "d" * 40


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "leo-tracker"
    release = root / "releases" / REVISION
    metadata = root / "release-metadata" / f"{REVISION}.txt"
    current = root / "current"
    release.mkdir(parents=True)
    metadata.parent.mkdir()
    (release / "partial-build").write_text("recoverable\n")
    (release / ".leo-release-incomplete").write_text("build in progress\n")
    return release, metadata, current


def _clean(release: Path, metadata: Path, current: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(CLEANER), str(release), str(metadata), str(current), REVISION),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_exact_unpublished_unselected_release_is_removed(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    result = _clean(release, metadata, current)
    assert result.returncode == 0, result.stderr
    assert not release.exists()
    assert "removed unpublished release build" in result.stderr


def test_published_metadata_prevents_cleanup(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    metadata.write_text("revision=digest\n")
    result = _clean(release, metadata, current)
    assert result.returncode == 73
    assert release.is_dir()
    assert "published metadata" in result.stderr


def test_current_selection_prevents_cleanup(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    current.symlink_to(Path("releases") / REVISION)
    result = _clean(release, metadata, current)
    assert result.returncode == 73
    assert release.is_dir()
    assert "selected current release" in result.stderr


def test_cleanup_refuses_revision_path_mismatch(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    wrong = release.parent / ("e" * 40)
    release.rename(wrong)
    result = _clean(wrong, metadata, current)
    assert result.returncode == 65
    assert wrong.is_dir()
    assert "exact revision" in result.stderr


def test_cleanup_refuses_release_without_incomplete_marker(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    (release / ".leo-release-incomplete").unlink()
    result = _clean(release, metadata, current)
    assert result.returncode == 73
    assert release.is_dir()
    assert "incomplete marker" in result.stderr


def test_cleanup_rejects_qnap_current_target_without_target_access(tmp_path: Path) -> None:
    release, metadata, current = _paths(tmp_path)
    current.symlink_to("/mnt/qnap01/must-not-be-opened")
    result = _clean(release, metadata, current)
    assert result.returncode == 65
    assert release.is_dir()
    assert "must not target QNAP" in result.stderr
