from pathlib import Path
from types import SimpleNamespace

import held_shrink_0019_ram as ram
import pytest


def test_command_exposes_only_explicit_inputs_and_private_outputs():
    path = Path("/dev/shm/enrolled/authority.json")
    cmd = ram.command(((path,), (Path("/usr"),)), "sandbox-worker")
    assert "/srv/bulk" not in cmd and "/mnt/qnap01" not in cmd
    assert all(flag in cmd for flag in ("--unshare-all", "--disable-userns", "--clearenv"))
    i = cmd.index(str(path))
    assert cmd[i - 1:i + 2] == ["--ro-bind", str(path), str(path)]
    for name in ram.ARTIFACTS:
        i = cmd.index(str(ram.OUTPUT/name))
        assert cmd[i-1:i+2] == ["--ro-bind", str(ram.OUTPUT/name), str(ram.saved.ROOT/name)]


def test_tmpfs_headroom_is_checked_before_admission(monkeypatch):
    monkeypatch.setattr(ram.os, "statvfs", lambda _: SimpleNamespace(f_bavail=1, f_frsize=4096))
    with pytest.raises(ValueError, match="tmpfs output headroom"):
        ram.headroom()
