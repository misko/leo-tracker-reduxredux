from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
EVALUATOR = ROOT / "reports/2026_09_24_ds1_train_full/evaluate_one_hour_postseal.py"


def load_module():
    spec = importlib.util.spec_from_file_location("one_hour_postseal", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seal(path: Path) -> None:
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def task(task_id: str, scan_count: int, method: str, prior: str) -> dict:
    return {
        "task_id": task_id,
        "partition": "train",
        "scan_count": scan_count,
        "method": method,
        "stage": "screening_comparison",
        "tier": "core",
        "group_id": "20260921_00",
        "case_id": f"case-{scan_count}",
        "prior": {"name": prior},
        "output_path": f"artifacts/one-hour/{method}/{task_id}.json",
        "options": {"geographic_levels_km": [100.0, 50.0, 25.0, 12.5]},
    }


def result(task_value: dict, latitude: float = 37.84903264307456) -> dict:
    return {
        "schema": "ds1-train-full-inference-result/v1",
        "complete": True,
        "task_id": task_value["task_id"],
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_use": {
            "policy": "all_qualified_observations",
            "heldout_observation_count": 0,
        },
        "estimated_position": {"latitude_deg": latitude, "longitude_deg": -122.4856541910174},
        "fitted_parameters": {"timing": {"global_tau_s": 0.5}},
        "rf_objective": {"selection_value": 0.125},
    }


def manifest(tasks: list[dict]) -> dict:
    return {
        "schema": "ds1-train-one-hour-benchmark-manifest/v1",
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "post_seal_external_only",
        "partitions_permitted": ["train"],
        "task_count": len(tasks),
        "tasks": tasks,
    }


def write_manifest(root: Path, payload: dict) -> Path:
    path = root / "one-hour-inference-manifest.json"
    path.write_text(json.dumps(payload))
    seal(path)
    return path


def test_postseal_evaluator_scores_only_valid_sealed_results_and_exports(tmp_path: Path):
    evaluator = load_module()
    completed = task("complete", 1, "baseline", "reno")
    missing = task("missing", 6, "global_time", "sacramento")
    artifact = tmp_path / completed["output_path"]
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(result(completed)))
    seal(artifact)
    manifest_path = write_manifest(tmp_path, manifest([completed, missing]))
    evaluation = evaluator.evaluate(manifest_path, tmp_path)

    assert evaluation["completed_task_count"] == 1
    assert evaluation["status_counts"] == {"completed": 1, "missing": 1}
    row = next(row for row in evaluation["rows"] if row["task_id"] == "complete")
    assert row["reference_error_km"] == 0.0
    assert row["timing_nuisance_median_s"] == 0.5
    assert "12.5 km" in evaluation["grid_screen_label"]

    output = tmp_path / "post-seal-output"
    evaluator.write_outputs(evaluation, output)
    assert (output / "one-hour-post-seal-evaluation.json").is_file()
    assert (output / "one-hour-post-seal-evaluation.csv").is_file()
    assert (output / "one-hour-post-seal-evaluation.png").is_file()
    json_path = output / "one-hour-post-seal-evaluation.json"
    assert (
        json_path.with_name(json_path.name + ".sha256").read_text().strip()
        == hashlib.sha256(json_path.read_bytes()).hexdigest()
    )


def test_postseal_evaluator_does_not_parse_badly_sealed_results(tmp_path: Path):
    evaluator = load_module()
    item = task("bad-seal", 1, "baseline", "reno")
    artifact = tmp_path / item["output_path"]
    artifact.parent.mkdir(parents=True)
    artifact.write_text("not JSON")
    artifact.with_suffix(".sha256").write_text("wrong\n")
    evaluation = evaluator.evaluate(write_manifest(tmp_path, manifest([item])), tmp_path)

    assert evaluation["rows"][0]["status"] == "invalid_seal"
    assert evaluation["rows"][0]["reference_error_km"] is None


def test_postseal_evaluator_rejects_reference_contaminated_result(tmp_path: Path):
    evaluator = load_module()
    item = task("contaminated", 6, "global_time", "sacramento")
    payload = result(item)
    payload["reference_error_km"] = 1.0
    artifact = tmp_path / item["output_path"]
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(payload))
    seal(artifact)

    evaluation = evaluator.evaluate(write_manifest(tmp_path, manifest([item])), tmp_path)
    assert evaluation["rows"][0]["status"] == "invalid_result"
    assert "reference" in evaluation["rows"][0]["status_reason"]
