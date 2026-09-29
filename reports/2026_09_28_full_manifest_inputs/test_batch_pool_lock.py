"""Exercise OS locks, slot cleanup and cross-process compatibility."""

import fcntl
import subprocess
import sys
from contextlib import ExitStack

import pytest
from batch_lock import acquire_locks as acquire_old
from batch_pool_lock import acquire_locks


def test_four_distinct_batches_and_slot_release(tmp_path):
    with ExitStack() as stack:
        for dataset, batch in (("DS8", 4), ("DS8", 5), ("DS9", 4), ("DS9", 5)):
            stack.enter_context(acquire_locks(tmp_path, dataset, batch))
        with pytest.raises(BlockingIOError):
            acquire_locks(tmp_path, "DS9", 6)
    with acquire_locks(tmp_path, "DS9", 6):
        pass


def test_duplicate_batch_and_invalid_arguments(tmp_path):
    with acquire_locks(tmp_path, "DS8", 4), pytest.raises(BlockingIOError):
        acquire_locks(tmp_path, "DS8", 4)
    for dataset, batch in (("DS7", 4), ("DS8", -1), ("DS8", "4"), ("DS9", True)):
        with pytest.raises(ValueError):
            acquire_locks(tmp_path, dataset, batch)


@pytest.mark.parametrize("dataset", ["DS8", "DS9"])
def test_older_parallel_launcher_excluded_in_both_directions(tmp_path, dataset):
    with acquire_old(tmp_path, dataset), pytest.raises(BlockingIOError):
        acquire_locks(tmp_path, "DS8", 4)
    with acquire_locks(tmp_path, "DS9", 4), pytest.raises(BlockingIOError):
        acquire_old(tmp_path, dataset)


def test_serial_excluded_in_both_directions(tmp_path):
    with (tmp_path / ".worker.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            acquire_locks(tmp_path, "DS8", 4)
    with (
        acquire_locks(tmp_path, "DS8", 4),
        (tmp_path / ".worker.lock").open("a") as handle,
        pytest.raises(BlockingIOError),
    ):
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_child_process_conflict_then_release(tmp_path):
    code = """
import sys
from pathlib import Path
from batch_pool_lock import acquire_locks
try:
    with acquire_locks(Path(sys.argv[1]), 'DS8', 4):
        pass
except BlockingIOError:
    sys.exit(23)
"""
    command = [sys.executable, "-c", code, str(tmp_path)]
    with acquire_locks(tmp_path, "DS8", 4):
        assert subprocess.run(command, check=False).returncode == 23
    assert subprocess.run(command, check=False).returncode == 0
