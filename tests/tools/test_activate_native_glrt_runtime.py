"""A native drain starts only at the tested main-thread boundary."""

from pathlib import Path

import activate_native_glrt_runtime as handoff
import pytest


def trace(source, *, line=171, name="watch_automatic", tid=42):
    return dict(os_thread_id=tid, pid=42, frames=[dict(name=name, line=line,
        filename=str(source / "src/leo/cli/fast_scan.py"))])


def test_main_sleep_point_is_distinct_from_a_waiting_worker():
    source = Path("/opt/example")
    assert handoff.main_sleeping([trace(source)], 42, source)
    assert not handoff.main_sleeping([trace(source, tid=43)], 42, source)
    assert not handoff.main_sleeping([trace(source, name="process_automatic")], 42, source)
    assert not handoff.main_sleeping([trace(source, line=155)], 42, source)
    assert not handoff.main_sleeping([], 42, source)


def test_configuration_preserves_worker_count_and_all_start_arguments():
    old = ("[Service]\nEnvironment=PYTHONPATH=/opt/old/src\nExecStart=\n"
           "ExecStart=/opt/python -m leo.cli.fast_scan --glrt-workers 16 --standard-mode algo07\n")
    base, new = handoff.configuration(old, Path("/opt/new"), "/opt/python", "a" * 64)
    assert base == Path("/opt/old")
    assert "Environment=PYTHONPATH=/opt/new/src" in new
    assert [s for s in new.splitlines() if s.startswith("ExecStart=")] == [
        s for s in old.splitlines() if s.startswith("ExecStart=")]
    assert "ExecStartPre=/opt/python -B /opt/new/tools/stage_native_glrt_runtime.py verify" in new
    assert "--pin " + "a" * 64 in new


@pytest.mark.parametrize("old", ["[Service]\n", "[Unit]\nEnvironment=PYTHONPATH=/opt/old/src\n",
    "[Service]\nEnvironment=PYTHONPATH=/opt/old/src:/opt/other\n"])
def test_ambiguous_override_is_rejected(old):
    with pytest.raises(ValueError):
        handoff.configuration(old, Path("/opt/new"), "/opt/python", "a" * 64)
