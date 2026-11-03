"""Atomic local recovery snapshots for detached standalone power ownership."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from leo.contracts.digests import canonical_json_bytes
from leo.contracts.power_scanner import StandalonePowerCheckpointV1
from leo.storage.continuous_window import run_path
from leo.storage.scanner import ScannerIqStore
from leo.storage.writer import _fsync_directory


@contextmanager
def power_control_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(path / "control.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def read_power_checkpoint(root: Path, run_id: str) -> StandalonePowerCheckpointV1:
    payload = ScannerIqStore._read_regular(run_path(root, run_id) / "power.json", 256 * 1024)
    value = StandalonePowerCheckpointV1.model_validate_json(payload)
    if value.run_id != run_id:
        raise ValueError("standalone power checkpoint identity changed")
    return value


def write_power_checkpoint(path: Path, value: StandalonePowerCheckpointV1) -> None:
    partial = path / "power.json.partial"
    if partial.is_symlink():
        raise ValueError("standalone power checkpoint partial cannot be a symlink")
    with partial.open("wb") as stream:
        stream.write(canonical_json_bytes(value.model_dump(mode="json")))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path / "power.json")
    _fsync_directory(path)
