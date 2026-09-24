from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load():
    path = HERE / "refine_joint.py"
    spec = importlib.util.spec_from_file_location("ds2_successor_refine_joint", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seal(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(content)
    sha = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(sha.removeprefix("sha256:") + "\n")
    return sha


def successor_parent(tmp_path: Path) -> tuple[Path, Path]:
    output_root = tmp_path / "output"
    cache_root = tmp_path / "cache"
    adapter = tmp_path / "fake_adapter.py"
    adapter.write_text(
        """import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--task', type=Path, required=True)
parser.add_argument('--cache-root', type=Path, required=True)
args = parser.parse_args()
task = json.loads(args.task.read_text())
out = Path(task['output_path'])
out.parent.mkdir(parents=True, exist_ok=True)
value = {
    'task_id': task['task_id'],
    'reference_coordinate_present': False,
    'estimated_position': {
        'latitude_deg': task['prior']['lat'],
        'longitude_deg': task['prior']['lon'],
    },
}
content = json.dumps(value, indent=2, sort_keys=True) + '\\n'
out.write_text(content)
out.with_suffix(out.suffix + '.sha256').write_text(
    hashlib.sha256(content.encode()).hexdigest() + '\\n'
)
"""
    )
    parent_output = output_root / "portable" / "inference" / "joint.json"
    task = {
        "task_id": "joint-all2__baseline",
        "session_ids": ["scan-a", "scan-b"],
        "prior": {"lat": 38.0, "lon": -121.0, "radius_km": 250.0},
        "options": {"geographic_levels_km": [100.0]},
        "output_path": str(parent_output.resolve()),
    }
    parent_sha = seal(
        parent_output,
        {
            "task_id": task["task_id"],
            "reference_coordinate_present": False,
            "estimated_position": {"latitude_deg": 38.0, "longitude_deg": -121.0},
        },
    )
    plan = {
        "schema": "ds2-successor-portable-plan/v1",
        "reference_coordinate_present": False,
        "joint_task_prefix": "joint-all2",
        "sessions": [{"session_id": "scan-a"}, {"session_id": "scan-b"}],
        "tasks": [task],
        "adapters": {"portable_evaluation": str(adapter.resolve())},
    }
    seal(output_root / "portable" / "plan.json", plan)
    seal(
        output_root / "portable" / "execution.json",
        {
            "schema": "ds2-successor-portable-execution/v1",
            "complete": True,
            "reference_coordinate_present": False,
            "rows": [{"task_id": task["task_id"], "state": "complete", "sha256": parent_sha}],
        },
    )
    return output_root, cache_root


def test_parent_context_derives_joint_prefix_from_sealed_successor(tmp_path: Path):
    runner = load()
    output_root, cache_root = successor_parent(tmp_path)
    parent = runner.parent_context(output_root, cache_root)
    assert parent.joint_prefix == "joint-all2"
    assert [task["task_id"] for task in parent.tasks] == ["joint-all2__baseline"]


def test_refinement_is_root_scoped_reference_free_and_resumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = load()
    output_root, cache_root = successor_parent(tmp_path)
    result = runner.run_refinement(output_root, cache_root, workers=1)
    assert len(result["stage_one"]["models"]) == 1
    assert len(result["fine"]["models"]) == 1
    for stage in ("stage-one", "fine"):
        index = output_root / "portable" / "refinement" / stage / "index.json"
        assert runner.sealed(index)
        document = json.loads(index.read_text())
        assert document["reference_coordinate_present"] is False
        task_path = next((index.parent / "tasks").glob("*.json"))
        assert task_path.is_relative_to(output_root)
        assert '"reference_coordinate":' not in task_path.read_text()

    monkeypatch.setattr(runner, "run_adapter", lambda *_args: pytest.fail("must resume"))
    resumed = runner.run_refinement(output_root, cache_root, workers=3)
    assert resumed["fine"]["complete"] is True


def test_refinement_rejects_incomplete_parent_and_bad_worker_count(tmp_path: Path):
    runner = load()
    output_root, cache_root = successor_parent(tmp_path)
    execution = output_root / "portable" / "execution.json"
    value = json.loads(execution.read_text())
    value["complete"] = False
    seal(execution, value)
    with pytest.raises(ValueError, match="reference-free completion"):
        runner.parent_context(output_root, cache_root)
    with pytest.raises(ValueError, match="workers"):
        runner.run_refinement(output_root, cache_root, workers=4)


def test_boundary_and_reusable_ladder_rules():
    runner = load()
    assert not runner.boundary_triggered(3.124, 4.6875, 1.5625)
    assert runner.boundary_triggered(3.125, 4.6875, 1.5625)
    assert runner.levels_for_radius(9.375, (1.5625, 0.78125, 0.390625)) == (
        3.125,
        1.5625,
        0.78125,
        0.390625,
    )
