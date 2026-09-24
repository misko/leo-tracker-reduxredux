from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


benchmark = load("benchmark", "benchmark.py")
one_hour = load("one_hour_manifest", "build_one_hour_manifest.py")


def dataset():
    return {
        "schema": "ds1-benchmark/v1",
        "groups": [
            {
                "group_id": "20260921_00",
                "partition": "train",
                "session_ids": [f"a{index}" for index in range(72)],
            },
            {
                "group_id": "20260921_16",
                "partition": "train",
                "session_ids": [f"b{index}" for index in range(79)],
            },
            {"group_id": "validation", "partition": "validation", "session_ids": ["v0"]},
            {"group_id": "test", "partition": "test", "session_ids": ["t0"]},
        ],
    }


def test_one_hour_manifest_has_fixed_full_observation_comparison_matrix(tmp_path: Path):
    manifest = one_hour.build_manifest(dataset(), "sha256:test")

    assert manifest["case_count"] == 4
    assert manifest["task_count"] == 64
    assert len([task for task in manifest["tasks"] if task["tier"] == "core"]) == 48
    assert len([task for task in manifest["tasks"] if task["tier"] == "extended"]) == 16
    assert {task["scan_count"] for task in manifest["tasks"]} == {1, 6}
    assert {task["prior"]["name"] for task in manifest["tasks"]} == {"sacramento", "reno"}
    assert all(task["partition"] == "train" for task in manifest["tasks"])
    assert all(task["options"]["within_track_holdout"] == "forbidden" for task in manifest["tasks"])
    assert all(
        task["options"]["observation_policy"] == "all_qualified_observations"
        for task in manifest["tasks"]
    )
    assert all(
        "v0" not in task["session_ids"] and "t0" not in task["session_ids"]
        for task in manifest["tasks"]
    )
    assert all(task["output_path"].startswith("artifacts/") for task in manifest["tasks"])
    assert all("reference" not in task for task in manifest["tasks"])
    for task in manifest["tasks"]:
        benchmark.validate_task(task, tmp_path)


def test_one_hour_global_time_grid_and_orbit_budget_are_fixed():
    manifest = one_hour.build_manifest(dataset(), "sha256:test")
    by_method = {}
    for task in manifest["tasks"]:
        by_method.setdefault(task["method"], task)

    for method in ("global_time", "per_scan_time", "independent_per_track_time"):
        assert by_method[method]["options"]["tau_limit_s"] == 2.0
        assert by_method[method]["options"]["tau_step_s"] == 0.5
    for method in one_hour.ORBIT_METHODS:
        assert by_method[method]["options"]["exact_rate_finalists"] == 1
        assert by_method[method]["options"]["exact_rate_workers"] == 1
    assert by_method["global_time_plus_per_norad_orbit_rate"]["options"]["tau_grid_s"] == [
        -2.0,
        -1.5,
        -1.0,
        -0.5,
        0.0,
        0.5,
        1.0,
        1.5,
        2.0,
    ]
