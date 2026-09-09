import os

import pytest

from leo.storage.analysis_worker_lock import analysis_worker_lock
from leo.storage.errors import BundleCorruptionError


def test_shared_lease_is_released_on_error_and_creates_only_existing_control_path(tmp_path):
    with pytest.raises(RuntimeError), analysis_worker_lock(tmp_path) as acquired:
        assert acquired
        with analysis_worker_lock(tmp_path) as second:
            assert not second
        raise RuntimeError("test owner failed")
    with analysis_worker_lock(tmp_path) as acquired:
        assert acquired
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == [
        "control",
        "control/persistent-hop-analysis",
        "control/persistent-hop-analysis/worker.lock",
    ]


@pytest.mark.parametrize(
    "fault", ["root", "control", "directory", "lock", "hardlink", "fifo", "nonempty"]
)
def test_shared_lease_refuses_symlink_and_nonregular_paths(tmp_path, fault):
    real = tmp_path / "real"
    real.mkdir()
    root = real
    if fault == "root":
        root = tmp_path / "alias"
        root.symlink_to(real, target_is_directory=True)
    elif fault in ("control", "directory"):
        parent = real if fault == "control" else real / "control"
        parent.mkdir(exist_ok=True)
        (parent / ("control" if fault == "control" else "persistent-hop-analysis")).symlink_to(
            tmp_path
        )
    else:
        directory = real / "control" / "persistent-hop-analysis"
        directory.mkdir(parents=True)
        lock = directory / "worker.lock"
        original = tmp_path / "unrelated"
        original.touch()
        if fault == "lock":
            lock.symlink_to(original)
        elif fault == "hardlink":
            os.link(original, lock)
        elif fault == "fifo":
            os.mkfifo(lock)
        else:
            lock.write_bytes(b"not-a-lease")
    with pytest.raises((ValueError, OSError, BundleCorruptionError)), analysis_worker_lock(root):
        pass
