"""Synthetic execution tests; never touch recording inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "controller106", Path(__file__).with_name("controller.py")
)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def setup(tmp_path):
    (tmp_path / "protocol.json").write_text(json.dumps(dict(labels=["A", "B", "C", "D"], shards=2)))
    (tmp_path / "results").mkdir()
    return hashlib.sha256((tmp_path / "protocol.json").read_bytes()).hexdigest()


def test_disjoint_shards_resume_without_duplicate_fits(tmp_path):
    digest = setup(tmp_path)
    calls = []

    def invoke(command, **kwargs):
        label = command[-1]
        calls.append(label)
        (tmp_path / "results" / f"{label}.json").write_text(
            json.dumps(dict(status="complete", protocol_sha256=digest))
        )
        return SimpleNamespace(returncode=0)

    controller.launch(0, 1, here=tmp_path, invoke=invoke)
    controller.launch(0, 1, here=tmp_path, invoke=invoke)
    controller.launch(1, 2, here=tmp_path, invoke=invoke)
    assert calls == ["A", "C", "B", "D"]
    assert controller.launch(0, 1, here=tmp_path, invoke=invoke)["launched"] == 0


def test_crashed_launch_is_not_implicitly_retried(tmp_path):
    setup(tmp_path)
    with pytest.raises(RuntimeError, match="child exited"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(FileExistsError):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **k: pytest.fail("No retry allowed"))


def test_stale_result_rejected(tmp_path):
    setup(tmp_path)
    (tmp_path / "results/A.json").write_text(
        json.dumps(dict(status="complete", protocol_sha256="wrong"))
    )
    with pytest.raises(ValueError, match="another protocol"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **k: pytest.fail("No fit expected"))


def test_missing_terminal_stops_and_records_exit(tmp_path):
    setup(tmp_path)
    with pytest.raises(RuntimeError, match="no terminal receipt"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **k: SimpleNamespace(returncode=0))
    assert (tmp_path / "controller-claims/A.exit.json").exists()
