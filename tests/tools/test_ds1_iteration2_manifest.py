from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BUILDER = ROOT / "reports/2026_09_24_ds1_iteration2/build_manifest.py"
BENCHMARK = ROOT / "reports/2026_09_24_ds1_train_full/benchmark.py"
TIMING_RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_timing/run.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("ds1_iteration2_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_benchmark():
    spec = importlib.util.spec_from_file_location("ds1_iteration2_benchmark", BENCHMARK)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_timing_runner():
    spec = importlib.util.spec_from_file_location("ds1_iteration2_timing", TIMING_RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seal(path: Path) -> None:
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def source_task(case_id: str, group_id: str, count: int, prior: str) -> dict:
    sessions = [f"{group_id}-scan-{item}" for item in range(count)]
    task_id = f"one-hour--{case_id}--{prior}--global_time"
    return {
        "schema": "ds1-train-full-inference-task/v1",
        "task_id": task_id,
        "partition": "train",
        "group_id": group_id,
        "case_id": case_id,
        "selection_kinds": ["fixed"],
        "session_ids": sessions,
        "scan_count": count,
        "prior": {"name": prior, "latitude_deg": 1.0, "longitude_deg": 2.0, "radius_km": 250.0},
        "method": "global_time",
        "input_scans": [
            {
                "session_id": session,
                "group_id": group_id,
                "causal_state_cache_root": f"/cache/{group_id}",
            }
            for session in sessions
        ],
        "output_path": f"artifacts/one-hour/global_time/{task_id}.json",
    }


def write_stage1(tmp_path: Path) -> Path:
    root = tmp_path / "stage1"
    fixed = {
        "train-20260921_00--first-singleton": ("20260921_00", 1),
        "train-20260921_00--prefix-6": ("20260921_00", 6),
        "train-20260921_16--first-singleton": ("20260921_16", 1),
        "train-20260921_16--prefix-6": ("20260921_16", 6),
    }
    cases, tasks = [], []
    for case_id, (group_id, count) in fixed.items():
        sessions = [f"{group_id}-scan-{item}" for item in range(count)]
        cases.append(
            {"case_id": case_id, "group_id": group_id, "scan_count": count, "session_ids": sessions}
        )
        for prior in ("sacramento", "reno"):
            task = source_task(case_id, group_id, count, prior)
            tasks.append(task)
            artifact = root / task["output_path"]
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(
                json.dumps(
                    {
                        "schema": "ds1-train-full-inference-result/v1",
                        "complete": True,
                        "task_id": task["task_id"],
                        "partition": "train",
                        "reference_used_for_fit": False,
                        "observation_use": {
                            "policy": "all_qualified_observations",
                            "heldout_observation_count": 0,
                        },
                        "estimated_position": {
                            "latitude_deg": 37.0 + len(tasks) / 100,
                            "longitude_deg": -122.0,
                        },
                        "fitted_parameters": {"timing": {"global_tau_s": -1.0}},
                        "rf_objective": {"selection_value": 0.1},
                    }
                )
            )
            seal(artifact)
    manifest = {
        "schema": "ds1-train-one-hour-benchmark-manifest/v1",
        "partitions_permitted": ["train"],
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "post_seal_external_only",
        "cases": cases,
        "tasks": tasks,
    }
    path = root / "one-hour-inference-manifest.json"
    path.write_text(json.dumps(manifest))
    seal(path)
    return path


def test_iteration2_manifest_binds_only_sealed_global_time_winners(tmp_path: Path) -> None:
    builder = load_builder()
    manifest = builder.build_manifest(write_stage1(tmp_path))
    benchmark = load_benchmark()
    timing = load_timing_runner()
    benchmark.TRAIN_CACHE_ROOTS.update(
        {"20260921_00": "/cache/20260921_00", "20260921_16": "/cache/20260921_16"}
    )
    timing.CACHE_ROOTS.update(
        {"20260921_00": Path("/cache/20260921_00"), "20260921_16": Path("/cache/20260921_16")}
    )

    assert manifest["schema"] == "ds1-iteration2-local-refinement-manifest/v1"
    assert manifest["task_count"] == 16
    assert len({task["task_id"] for task in manifest["tasks"]}) == 16
    assert {task["method"] for task in manifest["tasks"]} == {"global_time", "per_scan_time"}
    assert all(task["schema"] == "ds1-train-full-inference-task/v1" for task in manifest["tasks"])
    assert all(task["tier"] == "extended" for task in manifest["tasks"])
    assert all(task["partition"] == "train" for task in manifest["tasks"])
    assert all(
        task["options"]["observation_policy"] == "all_qualified_observations"
        for task in manifest["tasks"]
    )
    assert all(task["options"]["within_track_holdout"] == "forbidden" for task in manifest["tasks"])
    assert all(task["options"]["local_radius_km"] == 25.0 for task in manifest["tasks"])
    assert all(
        task["options"]["geographic_levels_km"] == [6.25, 3.125, 1.5625, 0.78125, 0.390625]
        for task in manifest["tasks"]
    )
    assert all(
        task["options"]["tau_grid_s"] == [-1.25, -1.0, -0.75, 0.0] for task in manifest["tasks"]
    )
    assert all(
        task["initial_geographic_seed"]["selection"] == "sealed_stage1_global_time_rf_winner"
        for task in manifest["tasks"]
    )
    assert all("reference" not in json.dumps(task).lower() for task in manifest["tasks"])
    for task in manifest["tasks"]:
        benchmark.validate_task(task, tmp_path)
        normalized = timing.validate_task({**task, "output_path": str(tmp_path / "result.json")})
        assert normalized["prior"]["radius_km"] == 25.0
        assert normalized["options"]["geographic_levels_km"] == (
            6.25,
            3.125,
            1.5625,
            0.78125,
            0.390625,
        )


def test_iteration2_builder_rejects_tampered_or_reference_contaminated_stage1(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    manifest_path = write_stage1(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    artifact = manifest_path.parent / manifest["tasks"][0]["output_path"]
    result = json.loads(artifact.read_text())
    result["reference_error_km"] = 1.0
    artifact.write_text(json.dumps(result))
    seal(artifact)
    with pytest.raises(ValueError, match="reference data"):
        builder.build_manifest(manifest_path)
    artifact.write_text(json.dumps({"tampered": True}))
    with pytest.raises(ValueError, match="input seal mismatch"):
        builder.build_manifest(manifest_path)
