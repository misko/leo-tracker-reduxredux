from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).with_name("resume_joint.py")
SPEC = importlib.util.spec_from_file_location("resume_joint", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _parent(tmp_path: Path) -> Path:
    source = tmp_path / "input"
    source.write_text("fixed")
    path = tmp_path / "parent.json"
    path.write_text(json.dumps({
        "schema": "fixed-height-joint-greedy/v1",
        "student_degrees_of_freedom": 4.0,
        "source_sha256": {str(source): _digest(source)},
        "inputs": {},
    }))
    path.with_suffix(".seal.json").write_text(json.dumps({"prediction_sha256": _digest(path)}))
    return path


def test_parent_seal_and_every_source_binding_are_verified(tmp_path: Path) -> None:
    path = _parent(tmp_path)
    MODULE._load_verified_parent(path)
    (tmp_path / "input").write_text("changed")
    with pytest.raises(ValueError, match="binding mismatch"):
        MODULE._load_verified_parent(path)


def test_best_includes_converged_and_unresolved_parent_or_resumed_fits() -> None:
    fits = [
        {"objectives": [4.0], "converged": True, "name": "parent"},
        {"objectives": [2.0], "converged": False, "name": "unresolved"},
        {"objectives": [3.0, 1.0], "converged": True, "name": "resumed"},
    ]
    assert MODULE._best(fits)["name"] == "resumed"


def test_reassociation_may_only_improve_resumed_initial_objective() -> None:
    assert MODULE._initial_objective_consistent(12.0, (11.5, 10.0))
    assert not MODULE._initial_objective_consistent(12.0, (12.01,))
    assert not MODULE._initial_objective_consistent(12.0, ())
