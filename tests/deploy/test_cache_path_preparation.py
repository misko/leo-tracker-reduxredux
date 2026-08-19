from __future__ import annotations

import os
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
HELPER = PROJECT_ROOT / "deploy" / "scripts" / "prepare-leo-cache"
GLOBALS = runpy.run_path(str(HELPER))


def _prepare(root: Path) -> Path:
    return GLOBALS["prepare"](
        root,
        leo_uid=os.getuid(),
        leo_gid=os.getgid(),
        system_uid=os.getuid(),
        system_gid=os.getgid(),
    )


def _parents(root: Path) -> None:
    (root / "var/lib").mkdir(parents=True)
    (root / "var").chmod(0o755)
    (root / "var/lib").chmod(0o755)


def test_cache_tree_is_created_with_exact_modes_and_is_idempotent(tmp_path: Path) -> None:
    _parents(tmp_path)

    cache = _prepare(tmp_path)
    _prepare(tmp_path)

    assert cache.stat().st_mode & 0o777 == 0o750
    assert (cache / "uv").stat().st_mode & 0o777 == 0o750
    assert (cache / "ms-playwright").stat().st_mode & 0o777 == 0o750


def test_cache_component_qnap_symlink_is_rejected_without_target_access(
    tmp_path: Path,
) -> None:
    (tmp_path / "var").mkdir(mode=0o755)
    (tmp_path / "var/lib").symlink_to("/mnt/qnap01/must-not-be-opened")

    with pytest.raises(ValueError, match="not a real directory"):
        _prepare(tmp_path)


def test_existing_cache_mode_mismatch_fails_closed(tmp_path: Path) -> None:
    _parents(tmp_path)
    cache = _prepare(tmp_path)
    cache.chmod(0o770)

    with pytest.raises(ValueError, match="mode is not 0750"):
        _prepare(tmp_path)
