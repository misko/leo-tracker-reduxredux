"""Runtime overlays must not redirect scientific imports into changed adapters."""

import sys

import pytest

from leo.cli.fast_graph_worker_command import worker_command


def test_default_launch_matches_existing_release_layout(tmp_path):
    module = tmp_path / "src/leo/cli/watch.py"
    assert worker_command(module, "worker.py", tmp_path / "bulk") == [
        sys.executable,
        "-B",
        str(tmp_path / "tools/worker.py"),
        "--bulk-root",
        str(tmp_path / "bulk"),
    ]


def test_frozen_worker_resets_pythonpath_and_uses_frozen_script(tmp_path):
    frozen = tmp_path / "frozen"
    (frozen / "src").mkdir(parents=True)
    (frozen / "tools").mkdir()
    (frozen / "tools/worker.py").write_text("pass\n")
    command = worker_command(
        tmp_path / "overlay/src/leo/cli/watch.py",
        "worker.py",
        tmp_path / "bulk",
        worker_root=frozen,
    )
    assert command[:2] == ["/usr/bin/env", f"PYTHONPATH={frozen}/src:{frozen}/tools"]
    assert command[4] == str(frozen / "tools/worker.py")


def test_incomplete_frozen_release_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Worker release"):
        worker_command(__file__, "worker.py", tmp_path, worker_root=tmp_path)
