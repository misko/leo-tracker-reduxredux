from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
EVALUATOR = ROOT / "reports/2026_09_24_ds1_iteration2/evaluate_postseal.py"


def load_module():
    spec = importlib.util.spec_from_file_location("iteration2_postseal", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seal(path: Path) -> None:
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def write_stage1(root: Path) -> tuple[Path, Path, str]:
    artifact = root / "artifacts/one-hour/global_time/source.json"
    artifact.parent.mkdir(parents=True)
    payload = {
        "schema": "ds1-train-full-inference-result/v1",
        "complete": True,
        "task_id": "one-hour--source--reno--global_time",
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_use": {"policy": "all_qualified_observations", "heldout_observation_count": 0},
        "estimated_position": {"latitude_deg": 37.8, "longitude_deg": -122.4},
        "selected": {"parameters": {"global_tau_s": -1.5}},
        "rf_objective": {"selection_value": 1.0},
    }
    artifact.write_text(json.dumps(payload))
    seal(artifact)
    manifest = root / "one-hour-inference-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "ds1-train-one-hour-benchmark-manifest/v1",
                "reference_coordinate_in_manifest": False,
                "partitions_permitted": ["train"],
                "tasks": [
                    {
                        "task_id": "one-hour--source--reno--global_time",
                        "method": "global_time",
                        "partition": "train",
                        "case_id": "case-0",
                        "scan_count": 1,
                        "prior": {"name": "reno"},
                        "output_path": "artifacts/one-hour/global_time/source.json",
                    }
                ],
            }
        )
    )
    seal(manifest)
    return manifest, artifact, hashlib.sha256(artifact.read_bytes()).hexdigest()


def write_iteration2(root: Path, stage1_manifest: Path, source: Path, source_digest: str) -> Path:
    tasks = []
    for index in range(16):
        method = "global_time" if index % 2 == 0 else "per_scan_time"
        prior = "reno"
        task_id = f"iteration2--case-0--{prior}--{method}--{index}"
        tasks.append(
            {
                "task_id": task_id,
                "partition": "train",
                "method": method,
                "stage": "stage2_local_geographic_refinement",
                "case_id": "case-0",
                "group_id": "20260921_00",
                "scan_count": 1,
                "prior": {"name": prior},
                "initial_geographic_seed": {"latitude_deg": 37.8, "longitude_deg": -122.4},
                "stage1_source": {
                    "task_id": "one-hour--source--reno--global_time",
                    "artifact_path": str(source),
                    "artifact_sha256": f"sha256:{source_digest}",
                },
                "options": {
                    "observation_policy": "all_qualified_observations",
                    "within_track_holdout": "forbidden",
                    "geographic_levels_km": [6.25, 3.125, 1.5625, 0.78125, 0.390625],
                    "tau_grid_s": [-1.75, -1.5, -1.25, 0.0],
                },
                "output_path": f"artifacts/iteration2/{method}/{task_id}.json",
            }
        )
    payload = {
        "schema": "ds1-iteration2-local-refinement-manifest/v1",
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "post_seal_external_only",
        "partitions_permitted": ["train"],
        "local_search": {
            "radius_km": 25.0,
            "levels_km": [6.25, 3.125, 1.5625, 0.78125, 0.390625],
            "timing_policy": "tau zero plus each sealed stage-1 winner +/-0.25 seconds",
        },
        "task_count": len(tasks),
        "stage1": {
            "manifest_path": str(stage1_manifest),
            "manifest_sha256": f"sha256:{hashlib.sha256(stage1_manifest.read_bytes()).hexdigest()}",
            "artifacts": [
                {
                    "task_id": "one-hour--source--reno--global_time",
                    "path": str(source),
                    "sha256": f"sha256:{source_digest}",
                }
            ],
        },
        "tasks": tasks,
    }
    path = root / "iteration2-inference-manifest.json"
    path.write_text(json.dumps(payload))
    seal(path)
    return path


def write_result(root: Path, task: dict, *, contaminated: bool = False) -> None:
    payload = {
        "schema": "ds1-train-full-inference-result/v1",
        "complete": True,
        "task_id": task["task_id"],
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_use": {"policy": "all_qualified_observations", "heldout_observation_count": 0},
        "estimated_position": {
            "latitude_deg": 37.84903264307456,
            "longitude_deg": -122.4856541910174,
        },
        "rf_objective": {"selection_value": 0.5},
        "fitted_parameters": {"timing": {"global_tau_s": -1.75}},
        "selected": {"east_km": 25.0, "north_km": 0.0},
        "convergence": {"geographic_levels_km": [6.25, 3.125, 1.5625, 0.78125, 0.390625]},
        "elapsed_s": 12.0,
    }
    if contaminated:
        payload["reference_error_km"] = 1.0
    path = root / task["output_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    seal(path)


def test_iteration2_evaluator_releases_reference_only_after_full_matrix_validation(tmp_path: Path):
    evaluator = load_module()
    stage1_manifest, source, source_digest = write_stage1(tmp_path)
    manifest_path = write_iteration2(tmp_path, stage1_manifest, source, source_digest)
    manifest = json.loads(manifest_path.read_text())
    for task in manifest["tasks"]:
        write_result(tmp_path, task)

    evaluation = evaluator.evaluate(manifest_path, tmp_path)

    assert evaluation["completed_task_count"] == 16
    assert evaluation["reference_evaluation"]["introduced"] is True
    assert all(row["reference_error_km"] == 0.0 for row in evaluation["rows"])
    assert evaluation["rows"][0]["grid_diagnostics"]["geographic_boundary_hit"] is True
    assert evaluation["rows"][0]["grid_diagnostics"]["timing_boundary_hit"] is True
    output = tmp_path / "post-seal-evaluation"
    evaluator.write_outputs(evaluation, output)
    assert (output / "iteration2-post-seal-evaluation.json").is_file()
    assert (output / "iteration2-post-seal-evaluation.csv").is_file()
    assert (output / "iteration2-post-seal-evaluation.png").is_file()


def test_iteration2_evaluator_withholds_reference_for_missing_or_contaminated_result(
    tmp_path: Path,
):
    evaluator = load_module()
    stage1_manifest, source, source_digest = write_stage1(tmp_path)
    manifest_path = write_iteration2(tmp_path, stage1_manifest, source, source_digest)
    manifest = json.loads(manifest_path.read_text())
    write_result(tmp_path, manifest["tasks"][0], contaminated=True)

    evaluation = evaluator.evaluate(manifest_path, tmp_path)

    assert evaluation["reference_evaluation"]["introduced"] is False
    assert evaluation["status_counts"] == {"invalid_result": 1, "missing": 15}
    assert all(row["reference_error_km"] is None for row in evaluation["rows"])
