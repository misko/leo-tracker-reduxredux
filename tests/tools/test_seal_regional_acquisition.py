from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _subject():
    path = Path(__file__).parents[2] / "tools/research/seal_regional_acquisition.py"
    spec = importlib.util.spec_from_file_location("seal_regional_acquisition", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(path):
    path.mkdir()
    (path / "result.json").write_text(json.dumps({"complete": True, "position_truth_used": False}))
    (path / "history.json").write_text(json.dumps([{"session_id": "scan"}]))
    for name in ("configuration.json", "grid.npz", "accumulated.npz", "scan.npz"):
        (path / name).write_bytes(name.encode())


def test_seal_is_exactly_repeatable_and_detects_mutation(tmp_path):
    subject = _subject()
    run = tmp_path / "run"
    _run(run)
    first = subject.seal(run)
    assert subject.seal(run) == first
    (run / "scan.npz").write_bytes(b"changed")
    try:
        subject.seal(run)
    except ValueError as error:
        assert "changed after sealing" in str(error)
    else:
        raise AssertionError("mutation after acquisition seal was accepted")


def test_incomplete_or_truth_accessed_run_cannot_be_sealed(tmp_path):
    subject = _subject()
    run = tmp_path / "run"
    _run(run)
    (run / "result.json").write_text(json.dumps({"complete": True, "position_truth_used": True}))
    try:
        subject.seal(run)
    except ValueError as error:
        assert "truth-free" in str(error)
    else:
        raise AssertionError("truth-accessed acquisition was sealed")
