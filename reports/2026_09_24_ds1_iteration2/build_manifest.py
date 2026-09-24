#!/usr/bin/env python3
"""Seal the DS1 iteration-2 local-refinement task manifest.

Iteration 2 consumes only the sealed stage-1 one-hour manifest and its sealed
``global_time`` results. It never loads a reference coordinate or evaluation.
Each local geographic seed is the stage-1 RF objective's winner coordinate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STAGE1_ROOT = HERE.parent / "2026_09_24_ds1_train_full"
DEFAULT_STAGE1_MANIFEST = STAGE1_ROOT / "one-hour-inference-manifest.json"
SCHEMA = "ds1-iteration2-local-refinement-manifest/v1"
# The existing scheduler and timing runner own this task/result contract.  The
# iteration marker and stage-1 provenance below add semantics without changing
# their public task schema.
TASK_SCHEMA = "ds1-train-full-inference-task/v1"
STAGE1_SCHEMA = "ds1-train-one-hour-benchmark-manifest/v1"
STAGE1_RESULT_SCHEMA = "ds1-train-full-inference-result/v1"
FIXED_CASES = {
    "train-20260921_00--first-singleton": ("20260921_00", 1),
    "train-20260921_00--prefix-6": ("20260921_00", 6),
    "train-20260921_16--first-singleton": ("20260921_16", 1),
    "train-20260921_16--prefix-6": ("20260921_16", 6),
}
PRIORS = ("sacramento", "reno")
METHODS = ("global_time", "per_scan_time")
GEOGRAPHIC_LEVELS_KM = (6.25, 3.125, 1.5625, 0.78125, 0.390625)
LOCAL_RADIUS_KM = 25.0
TAU_LOCAL_STEP_S = 0.25
FORBIDDEN_REFERENCE_KEYS = frozenset(
    {
        "reference_coordinate",
        "truth_coordinate",
        "ground_truth_coordinate",
        "reference_error_km",
        "horizontal_error_km",
        "horizontal_error_m",
    }
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sealed_json(path: Path) -> tuple[dict[str, Any], str]:
    """Return a JSON object only when its sibling SHA-256 seal matches."""
    path = path.resolve()
    seal = path.with_suffix(".sha256")
    _require(path.is_file(), f"missing sealed input: {path}")
    _require(seal.is_file(), f"missing input seal: {path}")
    digest = sha256_file(path)
    recorded = seal.read_text().strip().split(maxsplit=1)[0].removeprefix("sha256:")
    _require(recorded == digest.removeprefix("sha256:"), f"input seal mismatch: {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid sealed JSON: {path}") from exc
    _require(isinstance(payload, dict), f"sealed JSON object required: {path}")
    return payload, digest


def _contains_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_REFERENCE_KEYS.intersection(value)) or any(
            _contains_reference(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_reference(item) for item in value)
    return False


def _coordinate(result: dict[str, Any], artifact: Path) -> dict[str, float]:
    estimate = result.get("estimated_position")
    _require(isinstance(estimate, dict), f"stage-1 result lacks position: {artifact}")
    latitude, longitude = estimate.get("latitude_deg"), estimate.get("longitude_deg")
    _require(
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and math.isfinite(latitude)
        and -90.0 <= latitude <= 90.0,
        f"invalid stage-1 latitude: {artifact}",
    )
    _require(
        isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(longitude)
        and -180.0 <= longitude <= 180.0,
        f"invalid stage-1 longitude: {artifact}",
    )
    return {"latitude_deg": float(latitude), "longitude_deg": float(longitude), "altitude_m": 0.0}


def validate_stage1_result(task: dict[str, Any], result: dict[str, Any], artifact: Path) -> None:
    _require(result.get("schema") == STAGE1_RESULT_SCHEMA, "unexpected stage-1 result schema")
    _require(result.get("complete") is True, f"stage-1 result is incomplete: {artifact}")
    _require(result.get("task_id") == task["task_id"], f"stage-1 task ID mismatch: {artifact}")
    _require(result.get("partition") == "train", f"non-TRAIN stage-1 result: {artifact}")
    _require(
        result.get("reference_used_for_fit") is False, f"stage-1 result used reference: {artifact}"
    )
    _require(not _contains_reference(result), f"stage-1 result includes reference data: {artifact}")
    use = result.get("observation_use")
    _require(
        isinstance(use, dict)
        and use.get("policy") == "all_qualified_observations"
        and use.get("heldout_observation_count") == 0,
        f"stage-1 result is not full-observation: {artifact}",
    )
    objective = result.get("rf_objective")
    _require(isinstance(objective, dict), f"stage-1 result lacks RF objective: {artifact}")
    value = objective.get("selection_value")
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        f"stage-1 result lacks finite RF selection value: {artifact}",
    )
    _coordinate(result, artifact)


def load_stage1(stage1_manifest: Path) -> tuple[dict[str, Any], str, Path]:
    manifest_path = stage1_manifest.resolve()
    manifest, digest = sealed_json(manifest_path)
    _require(manifest.get("schema") == STAGE1_SCHEMA, "unexpected stage-1 manifest schema")
    _require(
        manifest.get("partitions_permitted") == ["train"], "stage-1 manifest is not TRAIN-only"
    )
    _require(
        manifest.get("reference_coordinate_in_manifest") is False, "stage-1 manifest has reference"
    )
    _require(
        manifest.get("position_evaluation") == "post_seal_external_only",
        "bad stage-1 evaluation policy",
    )
    cases = manifest.get("cases")
    _require(
        isinstance(cases, list) and len(cases) == len(FIXED_CASES), "stage-1 fixed views changed"
    )
    seen_cases = set()
    for case in cases:
        _require(isinstance(case, dict), "invalid stage-1 case")
        case_id = case.get("case_id")
        _require(case_id in FIXED_CASES, "unexpected stage-1 case")
        group_id, count = FIXED_CASES[case_id]
        _require(
            case.get("group_id") == group_id
            and case.get("scan_count") == count
            and isinstance(case.get("session_ids"), list)
            and len(case["session_ids"]) == count,
            f"stage-1 case membership changed: {case_id}",
        )
        seen_cases.add(case_id)
    _require(seen_cases == set(FIXED_CASES), "stage-1 fixed views missing")
    return manifest, digest, manifest_path.parent


def _seed_tasks(
    stage1_task: dict[str, Any], result: dict[str, Any], artifact: Path, digest: str
) -> list[dict[str, Any]]:
    coordinate = _coordinate(result, artifact)
    source_prior = stage1_task["prior"]
    timing = result.get("fitted_parameters", {}).get("timing", {})
    selected_tau = timing.get("global_tau_s")
    _require(
        isinstance(selected_tau, (int, float))
        and not isinstance(selected_tau, bool)
        and math.isfinite(selected_tau),
        f"stage-1 result lacks a finite global tau: {artifact}",
    )
    tau_grid = sorted(
        {
            0.0,
            max(-5.0, float(selected_tau) - TAU_LOCAL_STEP_S),
            float(selected_tau),
            min(5.0, float(selected_tau) + TAU_LOCAL_STEP_S),
        }
    )
    seed = {
        **coordinate,
        "selection": "sealed_stage1_global_time_rf_winner",
        "stage1_task_id": stage1_task["task_id"],
        "stage1_artifact_sha256": digest,
        "stage1_global_tau_s": float(selected_tau),
    }
    tasks = []
    for method in METHODS:
        task_id = f"iteration2--{stage1_task['case_id']}--{source_prior['name']}--{method}"
        tasks.append(
            {
                "schema": TASK_SCHEMA,
                "task_id": task_id,
                "iteration": 2,
                "partition": "train",
                # ``extended`` is accepted by the existing bounded scheduler.
                "tier": "extended",
                "stage": "stage2_local_geographic_refinement",
                "group_id": stage1_task["group_id"],
                "case_id": stage1_task["case_id"],
                "selection_kinds": stage1_task["selection_kinds"],
                "session_ids": stage1_task["session_ids"],
                "scan_count": stage1_task["scan_count"],
                # The stage-1 prior name preserves the paired arm identity;
                # its centre is deliberately replaced by the RF-selected seed
                # so the existing timing runner starts its local grid here.
                "prior": {"name": source_prior["name"], **coordinate, "radius_km": LOCAL_RADIUS_KM},
                "stage1_prior": source_prior,
                "method": method,
                "initial_geographic_seed": seed,
                "stage1_source": {
                    "task_id": stage1_task["task_id"],
                    "artifact_path": str(artifact),
                    "artifact_sha256": digest,
                    "selection": "stage1_global_time_rf_objective_winner",
                },
                "options": {
                    "observation_policy": "all_qualified_observations",
                    "within_track_holdout": "forbidden",
                    "frequency_loss_cap_hz": 800.0,
                    "minimum_track_duration_s": 3.0,
                    "altitude_m": 0.0,
                    "local_radius_km": LOCAL_RADIUS_KM,
                    "geographic_levels_km": list(GEOGRAPHIC_LEVELS_KM),
                    "search_levels_km": list(GEOGRAPHIC_LEVELS_KM),
                    "geographic_seed_policy": "sealed_stage1_global_time_rf_winner",
                    "tau_grid_s": tau_grid,
                    "timing_grid_policy": "tau zero plus sealed winner +/-0.25 seconds",
                    "causal_cache_validation": {
                        "require_cache_receipt": True,
                        "require_session_id_match": True,
                        "require_receipt_cache_digest_match": True,
                    },
                },
                "input_scans": stage1_task["input_scans"],
                "estimated_cost": {
                    "work_units": round(
                        stage1_task["scan_count"] * (1.25 if method == "global_time" else 1.8), 3
                    ),
                    "relative_per_scan": 1.25 if method == "global_time" else 1.8,
                },
                "output_path": f"artifacts/iteration2/{method}/{task_id}.json",
            }
        )
    return tasks


def build_manifest(stage1_manifest: Path = DEFAULT_STAGE1_MANIFEST) -> dict[str, Any]:
    manifest, manifest_digest, stage1_root = load_stage1(stage1_manifest)
    sessions_by_case = {case["case_id"]: case["session_ids"] for case in manifest["cases"]}
    selected = []
    for task in manifest.get("tasks", []):
        if not isinstance(task, dict) or task.get("method") != "global_time":
            continue
        case_id, prior = task.get("case_id"), task.get("prior", {}).get("name")
        if case_id not in FIXED_CASES or prior not in PRIORS:
            continue
        _require(task.get("partition") == "train", "non-TRAIN stage-1 task")
        _require(task.get("scan_count") == FIXED_CASES[case_id][1], "stage-1 scan count drift")
        _require(
            task.get("session_ids") == sessions_by_case[case_id], "stage-1 task/session mismatch"
        )
        selected.append(task)
    _require(len(selected) == 8, "expected exactly eight sealed global-time stage-1 arms")
    _require(
        len({(task["case_id"], task["prior"]["name"]) for task in selected}) == 8,
        "duplicate stage-1 global-time arm",
    )
    tasks, source_artifacts = [], []
    for task in sorted(selected, key=lambda row: row["task_id"]):
        relative = task.get("output_path")
        _require(isinstance(relative, str), "stage-1 output path missing")
        artifact = (stage1_root / relative).resolve()
        _require(artifact.is_relative_to(stage1_root), "stage-1 output escapes report")
        result, artifact_digest = sealed_json(artifact)
        validate_stage1_result(task, result, artifact)
        tasks.extend(_seed_tasks(task, result, artifact, artifact_digest))
        source_artifacts.append(
            {"task_id": task["task_id"], "path": str(artifact), "sha256": artifact_digest}
        )
    _require(len(tasks) == 16, "expected 16 iteration-2 tasks")
    _require(
        len({task["task_id"] for task in tasks}) == len(tasks), "duplicate iteration-2 task ID"
    )
    return {
        "schema": SCHEMA,
        "name": "DS1 iteration-2 sealed local geographic refinement",
        "version": 1,
        "iteration": 2,
        "partitions_permitted": ["train"],
        "position_evaluation": "post_seal_external_only",
        "reference_coordinate_in_manifest": False,
        "observation_policy": "all_qualified_observations",
        "within_track_holdout": "forbidden",
        "stage1": {
            "manifest_path": str(stage1_manifest.resolve()),
            "manifest_sha256": manifest_digest,
            "method": "global_time",
            "selection": "sealed_rf_objective_winner_coordinate",
            "artifacts": source_artifacts,
        },
        "views": sorted(FIXED_CASES),
        "priors": list(PRIORS),
        "methods": {
            "global_time": "shared global timing nuisance on the local grid",
            "per_scan_time": "regularized per-scan timing nuisance on the same local grid",
        },
        "local_search": {
            "radius_km": LOCAL_RADIUS_KM,
            "levels_km": list(GEOGRAPHIC_LEVELS_KM),
            "timing_policy": "tau zero plus each sealed stage-1 winner +/-0.25 seconds",
        },
        "task_count": len(tasks),
        "tasks": sorted(tasks, key=lambda row: row["task_id"]),
    }


def write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1-manifest", type=Path, default=DEFAULT_STAGE1_MANIFEST)
    parser.add_argument("--output", type=Path, default=HERE / "iteration2-inference-manifest.json")
    args = parser.parse_args()
    manifest = build_manifest(args.stage1_manifest)
    write_atomic(args.output, canonical_json(manifest))
    write_atomic(args.output.with_suffix(".sha256"), sha256_file(args.output) + "\n")
    print(
        json.dumps(
            {"tasks": manifest["task_count"], "stage1_arms": len(manifest["stage1"]["artifacts"])}
        )
    )


if __name__ == "__main__":
    main()
