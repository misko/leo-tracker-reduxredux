from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


benchmark = load("benchmark", "benchmark.py")
scheduler = load("train_full_scheduler", "run_scheduler.py")


def dataset():
    return {
        "schema": "ds1-benchmark/v1",
        "groups": [
            {
                "group_id": "20260921_00",
                "partition": "train",
                "session_ids": [f"a{i}" for i in range(32)],
            },
            {
                "group_id": "20260921_16",
                "partition": "train",
                "session_ids": [f"b{i}" for i in range(32)],
            },
            {"group_id": "ignored", "partition": "validation", "session_ids": ["v0"]},
            {"group_id": "ignored-test", "partition": "test", "session_ids": ["t0"]},
        ],
    }


def result_for(task):
    return {
        "schema": benchmark.RESULT_SCHEMA,
        "task_id": task["task_id"],
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_use": {"policy": "all_qualified_observations", "heldout_observation_count": 0},
        "estimated_position": {"latitude_deg": 38.0, "longitude_deg": -121.0},
        "fitted_parameters": {},
        "rf_objective": {},
    }


def test_manifest_is_train_only_and_tiered():
    manifest = benchmark.build_manifest(dataset(), "sha256:test", singleton_bins=8)
    assert manifest["partitions_permitted"] == ["train"]
    assert manifest["reference_coordinate_in_manifest"] is False
    assert all(task["partition"] == "train" for task in manifest["tasks"])
    assert all(
        "v0" not in task["session_ids"] and "t0" not in task["session_ids"]
        for task in manifest["tasks"]
    )
    core = [task for task in manifest["tasks"] if task["tier"] == "core"]
    assert {task["method"] for task in core} == {"baseline", "global_time"}
    assert len([task for task in core if task["scan_count"] == 1]) == 64 * 2 * 2
    extended = [
        task for task in manifest["tasks"] if task["tier"] == "extended" and task["scan_count"] == 1
    ]
    assert (
        len({task["session_ids"][0] for task in extended if task["group_id"] == "20260921_00"}) == 8
    )
    assert any(
        "nested_prefix" in task["selection_kinds"] and "disjoint_block" in task["selection_kinds"]
        for task in manifest["tasks"]
    )
    assert not manifest["expansion_included"]
    assert not any(task["tier"] == "expansion" for task in manifest["tasks"])
    assert not any(
        task["method"] == "soft_association_plus_global_time_orbit_rate"
        for task in manifest["tasks"]
    )
    assert manifest["methods"]["soft_association_plus_global_time_orbit_rate"]["supported"] is False


def test_task_rejects_non_train_and_escape(tmp_path):
    task = benchmark.build_manifest(dataset(), "sha256:test")["tasks"][0]
    benchmark.validate_task(task, tmp_path)
    task["partition"] = "validation"
    with pytest.raises(ValueError, match="TRAIN"):
        benchmark.validate_task(task, tmp_path)
    task["partition"] = "train"
    task["output_path"] = "../escaped.json"
    with pytest.raises(ValueError, match="artifacts"):
        benchmark.validate_task(task, tmp_path)


def test_result_rejects_holdout_and_reference_data():
    task = benchmark.build_manifest(dataset(), "sha256:test")["tasks"][0]
    result = result_for(task)
    benchmark.validate_result(task, result)
    result["observation_use"]["heldout_observation_count"] = 1
    with pytest.raises(ValueError, match="held-out"):
        benchmark.validate_result(task, result)
    result["observation_use"]["heldout_observation_count"] = 0
    result["reference_error_km"] = 3.0
    with pytest.raises(ValueError, match="reference"):
        benchmark.validate_result(task, result)


def test_sealed_artifact_is_resumable(tmp_path):
    task = benchmark.build_manifest(dataset(), "sha256:test")["tasks"][0]
    artifact = tmp_path / "artifacts" / "baseline" / "row.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(benchmark.canonical_json(result_for(task)))
    artifact.with_suffix(".sha256").write_text(
        hashlib.sha256(artifact.read_bytes()).hexdigest() + "\n"
    )
    assert scheduler.sealed_artifact(artifact, task)
    artifact.with_suffix(".sha256").write_text("bad\n")
    assert not scheduler.sealed_artifact(artifact, task)


def test_scheduler_runs_and_seals_an_atomic_artifact(tmp_path):
    task = next(
        task
        for task in benchmark.build_manifest(dataset(), "sha256:test")["tasks"]
        if task["method"] == "baseline"
    )
    runner = tmp_path / "runner.py"
    runner.write_text(
        """import json
import os
import sys
from pathlib import Path

task = json.loads(Path(sys.argv[1]).read_text())
assert os.environ['OPENBLAS_NUM_THREADS'] == '1'
result = {
    'schema': 'ds1-train-full-inference-result/v1',
    'task_id': task['task_id'],
    'partition': 'train',
    'reference_used_for_fit': False,
    'observation_use': {'policy': 'all_qualified_observations', 'heldout_observation_count': 0},
    'estimated_position': {'latitude_deg': 38.0, 'longitude_deg': -121.0},
    'fitted_parameters': {},
    'rf_objective': {},
}
Path(task['output_path']).write_text(json.dumps(result))
"""
    )
    registry = {
        "baseline": {
            "command": [sys.executable, str(runner), "{task}"],
            "max_concurrency": None,
            "geographic_shards": 1,
        }
    }
    row = scheduler.run_one(task, registry, tmp_path)
    artifact = tmp_path / task["output_path"]
    assert row["status"] == "completed"
    assert scheduler.sealed_artifact(artifact, task)
    assert scheduler.run_one(task, registry, tmp_path)["status"] == "skipped"


def test_registry_requires_placeholders_and_accepts_caps(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema": "ds1-train-full-runner-registry/v1",
                "methods": {"baseline": {"command": ["runner"], "max_concurrency": 8}},
            }
        )
    )
    with pytest.raises(ValueError, match="task"):
        scheduler.load_registry(path)
    path.write_text(
        json.dumps(
            {
                "schema": "ds1-train-full-runner-registry/v1",
                "methods": {
                    "baseline": {
                        "command": ["runner", "{task}"],
                        "max_concurrency": 8,
                        "geographic_shards": 4,
                    }
                },
            }
        )
    )
    assert scheduler.load_registry(path)["baseline"]["max_concurrency"] == 8
