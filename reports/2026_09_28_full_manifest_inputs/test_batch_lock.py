"""Actual OS-lock compatibility checks; no scientific jobs are started."""

import fcntl

import pytest
from batch_lock import acquire_locks


def test_distinct_datasets_coexist_but_duplicates_and_serial_do_not(tmp_path):
    with acquire_locks(tmp_path, "DS8"), acquire_locks(tmp_path, "DS9"):
        for dataset in ("DS8", "DS9"):
            with pytest.raises(BlockingIOError):
                acquire_locks(tmp_path, dataset)
        with (
            (tmp_path / ".worker.lock").open("a") as serial,
            pytest.raises(BlockingIOError),
        ):
            fcntl.flock(serial, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (tmp_path / ".worker.lock").open("a") as serial:
        fcntl.flock(serial, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_serial_blocks_parallel_and_failed_acquisition_releases_handles(tmp_path):
    with (tmp_path / ".worker.lock").open("a") as serial:
        fcntl.flock(serial, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            acquire_locks(tmp_path, "DS8")
    with acquire_locks(tmp_path, "DS8"):
        pass
    with pytest.raises(ValueError):
        acquire_locks(tmp_path, "DS7")
