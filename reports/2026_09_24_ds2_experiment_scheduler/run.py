#!/usr/bin/env python3
# ruff: noqa: E501
"""Build and, when adapters are supplied, run a sealed DS2 experiment plan.

The scheduler deliberately keeps receiver-reference coordinates out of both the
manifest and every inference task.  It accepts whole recording sessions only;
evaluation is represented as a later, external task after an inference result
has been sealed.  Until the receipt-bound tracking products exist, the useful
output is a deterministic, machine-readable list of blocked work rather than a
partly executed experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA = "ds2-experiment-schedule/v1"
MANIFEST_SCHEMA = "ds2-position-manifest/v1"
RUNNER_SCHEMA = "ds2-runner-registry/v1"
FORBIDDEN_REFERENCE_KEYS = {
    "reference_coordinate",
    "reference_latitude_deg",
    "reference_longitude_deg",
    "truth",
    "truth_coordinate",
    "ground_truth",
    "ground_truth_coordinate",
}
COMPLETE_TRACKING_STATUSES = {"ready", "complete", "completed"}
PRIMARY = {
    "baseline_doppler",
    "shared_global_receive_time",
    "causal_per_norad_orbit_rate",
    "equal_weight_joint_multiscan_position",
}
CONDITIONAL = {
    "regularized_per_scan_time",
    "rate_aware_joint_geographic_screen",
    "consistent_cap800_joint_objective",
    "shared_norad_rate_joint",
    "regularized_common_plus_session_scale",
}
DIAGNOSTIC = {
    "independent_per_track_time",
    "soft_identity_mixture",
    "learned_pointing_cone_quantiles",
    "fixed_hard_cone_orientation",
    "staged_full_fov_cone_sweep",
    "local_fitted_full_fov_cone_position",
    "robust_residual_likelihood_rerank",
    "legacy_joint_session_scale_lbfgsb",
}
RUNTIME = {
    "screen": {
        "coarse_cell_km": 100.0,
        "refinement_cells_km": [25.0, 6.25],
        "beam_width": 3,
        "exact_finalists": 8,
        "max_workers": 8,
    },
    "exact": {"max_workers": 4, "exact_finalists": 8},
    "cone": {
        "coarse_cell_km": 100.0,
        "refinement_cells_km": [25.0, 6.25],
        "beam_width": 3,
        "full_fov_deg": [10, 20, 25, 30, 40, 50, 60, 70, 80, 90],
        "local_fov_deg": [10, 20, 25, 30, 40, 50],
        "fixed_half_angles_deg": [10, 15, 20, 30],
        "upward_cone_limit_deg": 45.0,
    },
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def find_forbidden_reference(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        hits = [path + "." + key for key in value if key.lower() in FORBIDDEN_REFERENCE_KEYS]
        for key, child in value.items():
            hits.extend(find_forbidden_reference(child, path + "." + key))
        return hits
    if isinstance(value, list):
        return [
            hit
            for index, child in enumerate(value)
            for hit in find_forbidden_reference(child, f"{path}[{index}]")
        ]
    return []


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(path)
    if registry.get("schema") != "ds2-position-model-registry/v1":
        raise ValueError("unexpected DS2 model registry schema")
    models = registry.get("models")
    if not isinstance(models, list):
        raise ValueError("model registry models must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            raise ValueError("model registry has an invalid model")
        if model["id"] in by_id:
            raise ValueError(f"duplicate model {model['id']}")
        by_id[model["id"]] = model
    expected = PRIMARY | CONDITIONAL | DIAGNOSTIC
    if set(by_id) != expected:
        raise ValueError("registry model set differs from the frozen 17-model DS2 registry")
    return by_id


def load_runners(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    payload = read_json(path)
    if payload.get("schema") != RUNNER_SCHEMA:
        raise ValueError("unexpected DS2 runner registry schema")
    result: dict[str, list[str]] = {}
    runners = payload.get("runners")
    if not isinstance(runners, dict):
        raise ValueError("runner registry runners must be an object")
    for model_id, entry in runners.items():
        command = entry.get("command") if isinstance(entry, dict) else None
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(piece, str) for piece in command)
        ):
            raise ValueError(f"invalid runner command for {model_id}")
        if "{task}" not in command:
            raise ValueError(f"runner command for {model_id} needs {{task}}")
        result[model_id] = command
    return result


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema must be {MANIFEST_SCHEMA}")
    if manifest.get("manifest_sealed") is not True:
        raise ValueError("manifest must declare manifest_sealed=true")
    if manifest.get("reference_coordinate_in_manifest") is not False:
        raise ValueError("manifest must declare reference_coordinate_in_manifest=false")
    if manifest.get("position_evaluation") != "post_seal_external_only":
        raise ValueError("manifest must reserve evaluation for post_seal_external_only")
    forbidden = find_forbidden_reference(manifest)
    if forbidden:
        raise ValueError("manifest contains prohibited reference data: " + ", ".join(forbidden))
    priors = manifest.get("priors")
    if not isinstance(priors, list) or not priors:
        raise ValueError("manifest must include at least one blind prior")
    for prior in priors:
        if not isinstance(prior, dict) or not isinstance(prior.get("id"), str):
            raise ValueError("each prior requires an id")
        if prior.get("reference_used_for_selection") is not False:
            raise ValueError("every prior must declare reference_used_for_selection=false")
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("manifest must contain groups")
    seen_sessions: set[str] = set()
    group_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("group must be an object")
        group_id, partition, sessions = (
            group.get("group_id"),
            group.get("partition"),
            group.get("session_ids"),
        )
        if not isinstance(group_id, str) or not group_id or group_id in group_ids:
            raise ValueError("each group needs a unique group_id")
        if partition not in {"train", "validation", "test"}:
            raise ValueError(f"group {group_id} has invalid partition")
        if (
            not isinstance(sessions, list)
            or not sessions
            or not all(isinstance(s, str) and s for s in sessions)
        ):
            raise ValueError(f"group {group_id} must contain whole nonempty session IDs")
        if len(set(sessions)) != len(sessions) or seen_sessions.intersection(sessions):
            raise ValueError(f"session IDs are duplicated across whole-session groups ({group_id})")
        seen_sessions.update(sessions)
        group_ids.add(group_id)
        products = group.get("tracking_products")
        if not isinstance(products, dict) or set(products) != set(sessions):
            raise ValueError(f"group {group_id} needs one tracking product record per session")
        normalized.append(group)
    return normalized


def tracking_gate(group: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    policies: set[str] = set()
    for session_id in group["session_ids"]:
        product = group["tracking_products"][session_id]
        if not isinstance(product, dict) or product.get("status") not in COMPLETE_TRACKING_STATUSES:
            reasons.append(f"tracking_product_not_ready:{session_id}")
            continue
        product_digest = product.get("tracking_product_digest")
        if not isinstance(product_digest, str) or not product_digest.startswith("sha256:"):
            reasons.append(f"tracking_product_digest_missing:{session_id}")
        policy = product.get("candidate_policy_digest")
        if not isinstance(policy, str) or not policy:
            reasons.append(f"candidate_policy_digest_missing:{session_id}")
        else:
            policies.add(policy)
        for field in ("receipt_path", "cache_path"):
            raw_path = product.get(field)
            if not isinstance(raw_path, str) or not Path(raw_path).is_file():
                reasons.append(f"{field}_missing:{session_id}")
    if len(policies) > 1:
        reasons.append("candidate_policy_digest_mismatch_within_group")
    return reasons


def geometry_gate(manifest: dict[str, Any]) -> list[str]:
    geometry = manifest.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("status") != "ready":
        return ["geometry_not_ready"]
    paths = geometry.get("receiver_geometry_path")
    if not isinstance(paths, str) or not Path(paths).is_file():
        return ["receiver_geometry_path_missing"]
    mapping = geometry.get("rx_to_lnb_mapping")
    if mapping not in {"verified", "symmetric_two_mapping_marginalization"}:
        return ["rx_to_lnb_mapping_not_verified_or_symmetric"]
    if not isinstance(geometry.get("upward_cone_limit_deg"), (int, float)):
        return ["upward_cone_limit_deg_missing"]
    return []


def model_class(model_id: str) -> str:
    if model_id in PRIMARY:
        return "primary"
    if model_id in CONDITIONAL:
        return "conditional"
    return "diagnostic"


def model_config(model_id: str) -> dict[str, Any]:
    if model_id == "staged_full_fov_cone_sweep":
        return {**RUNTIME["cone"], "search_mode": "staged_screen_then_exact_finalists"}
    if model_id == "local_fitted_full_fov_cone_position":
        return {**RUNTIME["cone"], "search_mode": "local_refit_from_staged_basins"}
    if model_id == "fixed_hard_cone_orientation":
        return {**RUNTIME["cone"], "search_mode": "upward_restricted_orientation_grid"}
    if model_id in {
        "equal_weight_joint_multiscan_position",
        "rate_aware_joint_geographic_screen",
        "consistent_cap800_joint_objective",
        "shared_norad_rate_joint",
        "regularized_common_plus_session_scale",
    }:
        return {**RUNTIME["screen"], "search_mode": "coarse_beam_then_exact_finalists"}
    if model_id == "causal_per_norad_orbit_rate":
        return {**RUNTIME["screen"], "variants": ["rate_only", "shared_global_tau_plus_rate"]}
    return {**RUNTIME["screen"], "search_mode": "coarse_beam_then_exact_finalists"}


def depends_on(model_id: str, group_id: str, prior_id: str) -> list[str]:
    if model_id == "regularized_per_scan_time":
        return [
            f"baseline_doppler:{group_id}:{prior_id}",
            f"shared_global_receive_time:{group_id}:{prior_id}",
        ]
    if model_id in {"rate_aware_joint_geographic_screen", "consistent_cap800_joint_objective"}:
        return [f"equal_weight_joint_multiscan_position:{group_id}:{prior_id}"]
    if model_id == "shared_norad_rate_joint":
        return [
            f"equal_weight_joint_multiscan_position:{group_id}:{prior_id}",
            f"post_baseline_norad_overlap:{group_id}:{prior_id}",
        ]
    if model_id == "regularized_common_plus_session_scale":
        return [f"equal_weight_joint_multiscan_position:{group_id}:{prior_id}"]
    if model_id in {
        "learned_pointing_cone_quantiles",
        "fixed_hard_cone_orientation",
        "staged_full_fov_cone_sweep",
        "local_fitted_full_fov_cone_position",
    }:
        return [f"baseline_doppler:{group_id}:{prior_id}"]
    if model_id in {"independent_per_track_time", "soft_identity_mixture"}:
        return [f"baseline_doppler:{group_id}:{prior_id}"]
    if model_id in {"robust_residual_likelihood_rerank", "legacy_joint_session_scale_lbfgsb"}:
        return [f"exact_finalists_only:{group_id}:{prior_id}"]
    return []


def plan_task(
    model_id: str,
    model: dict[str, Any],
    group_id: str,
    sessions: list[str],
    prior: dict[str, Any],
    input_reasons: list[str],
    runner: list[str] | None,
    extra_reasons: list[str] | None = None,
    completed_dependencies: set[str] | None = None,
) -> dict[str, Any]:
    prerequisites = depends_on(model_id, group_id, prior["id"])
    completed = completed_dependencies or set()
    dependency_reasons = [
        f"dependency_unsealed:{dependency}"
        for dependency in prerequisites
        if dependency not in completed
    ]
    reasons = list(input_reasons) + list(extra_reasons or []) + dependency_reasons
    task_id = f"{model_id}:{group_id}:{prior['id']}"
    status = "blocked" if reasons else ("ready" if runner else "adapter_required")
    return {
        "schema": "ds2-experiment-task/v1",
        "task_id": task_id,
        "model_id": model_id,
        "class": model_class(model_id),
        "registry_task_method": model["task_method"],
        "partition": "train",
        "group_id": group_id,
        "session_ids": sessions,
        "prior": prior,
        "reference_used_for_inference": False,
        "evaluation_policy": "external_after_sealed_inference",
        "depends_on": prerequisites,
        "configuration": model_config(model_id),
        "source_code_paths": model["code_paths"],
        "runner_command": runner,
        "status": status,
        "block_reasons": reasons,
        "output_path": f"inference/{model_id}/{group_id}/{prior['id']}.json",
    }


def build_schedule(
    manifest: dict[str, Any],
    models: dict[str, dict[str, Any]],
    runners: dict[str, list[str]],
    completed_dependencies: set[str] | None = None,
) -> dict[str, Any]:
    groups = validate_manifest(manifest)
    train = [group for group in groups if group["partition"] == "train"]
    if not train:
        raise ValueError("DS2 manifest has no TRAIN whole-session group")
    policy_digests = {
        product.get("candidate_policy_digest")
        for group in train
        for product in group["tracking_products"].values()
        if isinstance(product, dict) and product.get("status") in COMPLETE_TRACKING_STATUSES
    }
    global_policy_reasons = (
        ["candidate_policy_digest_mismatch_across_train"] if len(policy_digests) > 1 else []
    )
    prior_gates = {
        prior["id"]: []
        if prior.get("status", "ready") == "ready"
        else [f"blind_prior_not_ready:{prior['id']}"]
        for prior in manifest["priors"]
    }
    group_gates = {
        group["group_id"]: tracking_gate(group) + global_policy_reasons for group in train
    }
    geometry_reasons = geometry_gate(manifest)
    tasks: list[dict[str, Any]] = []
    nonjoint_ids = (PRIMARY | CONDITIONAL | DIAGNOSTIC) - {
        "equal_weight_joint_multiscan_position",
        "rate_aware_joint_geographic_screen",
        "consistent_cap800_joint_objective",
        "shared_norad_rate_joint",
        "regularized_common_plus_session_scale",
    }
    for group in train:
        for model_id in sorted(nonjoint_ids):
            model = models[model_id]
            for prior in manifest["priors"]:
                extra = (
                    geometry_reasons
                    if model_id
                    in {
                        "learned_pointing_cone_quantiles",
                        "fixed_hard_cone_orientation",
                        "staged_full_fov_cone_sweep",
                        "local_fitted_full_fov_cone_position",
                    }
                    else []
                )
                if model_id in {
                    "robust_residual_likelihood_rerank",
                    "legacy_joint_session_scale_lbfgsb",
                }:
                    extra = list(extra) + ["rejected_or_diagnostic_only"]
                tasks.append(
                    plan_task(
                        model_id,
                        model,
                        group["group_id"],
                        group["session_ids"],
                        prior,
                        group_gates[group["group_id"]] + prior_gates[prior["id"]],
                        runners.get(model_id),
                        extra,
                        completed_dependencies,
                    )
                )
    cohorts: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in train:
        cohorts[group.get("cohort_id", "all-train")].append(group)
    joint_ids = {
        "equal_weight_joint_multiscan_position",
        "rate_aware_joint_geographic_screen",
        "consistent_cap800_joint_objective",
        "shared_norad_rate_joint",
        "regularized_common_plus_session_scale",
    }
    for cohort_id, cohort_groups in sorted(cohorts.items()):
        joint_group_id = "train-union" if cohort_id == "all-train" else f"train-union-{cohort_id}"
        union_sessions = [session for group in cohort_groups for session in group["session_ids"]]
        union_reasons = [
            reason for group in cohort_groups for reason in group_gates[group["group_id"]]
        ]
        if len(cohort_groups) < 2:
            union_reasons.append("requires_at_least_two_train_groups_in_cohort")
        for model_id in sorted(joint_ids):
            model = models[model_id]
            for prior in manifest["priors"]:
                tasks.append(
                    plan_task(
                        model_id,
                        model,
                        joint_group_id,
                        union_sessions,
                        prior,
                        union_reasons + prior_gates[prior["id"]],
                        runners.get(model_id),
                        completed_dependencies=completed_dependencies,
                    )
                )
    tasks.sort(
        key=lambda task: (task["class"], task["model_id"], task["group_id"], task["prior"]["id"])
    )
    status_counts = Counter(task["status"] for task in tasks)
    class_counts = Counter(task["class"] for task in tasks)
    return {
        "schema": SCHEMA,
        "manifest_digest": digest(manifest),
        "model_registry_digest": digest({"models": list(models.values())}),
        "reference_coordinate_in_schedule": False,
        "inference_partition": "train",
        "heldout_partitions_reserved": ["validation", "test"],
        "runtime_policy": {
            "screen_then_exact": True,
            "reuse_receipt_bound_caches": True,
            "max_workers_screen": RUNTIME["screen"]["max_workers"],
            "max_workers_exact": RUNTIME["exact"]["max_workers"],
            "no_unbounded_geographic_refinement": True,
        },
        "completed_dependency_receipts": sorted(completed_dependencies or set()),
        "readiness": {
            "train_groups": {group["group_id"]: group_gates[group["group_id"]] for group in train},
            "geometry": geometry_reasons,
            "validation_and_test_not_used_for_inference": True,
        },
        "summary": {
            "task_count": len(tasks),
            "by_status": dict(status_counts),
            "by_class": dict(class_counts),
        },
        "tasks": tasks,
    }


def write_plan(schedule: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "schedule.json").write_text(canonical(schedule))
    (output / "schedule.sha256").write_text(
        hashlib.sha256((output / "schedule.json").read_bytes()).hexdigest() + "\n"
    )
    task_root = output / "tasks"
    for task in schedule["tasks"]:
        path = task_root / (task["task_id"].replace(":", "__") + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical(task))


def execute_ready(schedule: dict[str, Any], output: Path, max_tasks: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ready = [task for task in schedule["tasks"] if task["status"] == "ready"][:max_tasks]
    for task in ready:
        task_path = output / "tasks" / (task["task_id"].replace(":", "__") + ".json")
        command = [piece.replace("{task}", str(task_path)) for piece in task["runner_command"]]
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=output,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
        )
        rows.append(
            {
                "task_id": task["task_id"],
                "status": "completed" if completed.returncode == 0 else "failed",
                "returncode": completed.returncode,
                "runtime_s": round(time.monotonic() - started, 6),
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    return rows


def load_completed_dependencies(path: Path | None) -> set[str]:
    """Read only opaque predecessor IDs, never result bodies or evaluation data."""
    if path is None:
        return set()
    payload = read_json(path)
    forbidden = find_forbidden_reference(payload)
    if forbidden:
        raise ValueError("dependency receipt contains prohibited reference data")
    rows = payload.get("sealed_task_ids")
    if not isinstance(rows, list) or not all(isinstance(row, str) and row for row in rows):
        raise ValueError("dependency receipt needs nonempty sealed_task_ids")
    return set(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--model-registry",
        type=Path,
        default=HERE.parent / "2026_09_24_ds2_model_registry" / "model-registry.json",
    )
    parser.add_argument("--runner-registry", type=Path)
    parser.add_argument(
        "--completed-dependencies",
        type=Path,
        help="sealed predecessor task IDs; inference coordinates and evaluation data are rejected",
    )
    parser.add_argument("--output", type=Path, default=HERE / "artifacts")
    parser.add_argument(
        "--execute-ready",
        action="store_true",
        help="run only ready tasks through explicit local adapters",
    )
    parser.add_argument(
        "--max-tasks", type=int, default=0, help="required positive cap with --execute-ready"
    )
    args = parser.parse_args()
    if args.execute_ready and args.max_tasks < 1:
        raise ValueError("--execute-ready requires a positive --max-tasks bound")
    schedule = build_schedule(
        read_json(args.manifest),
        load_registry(args.model_registry),
        load_runners(args.runner_registry),
        load_completed_dependencies(args.completed_dependencies),
    )
    write_plan(schedule, args.output)
    execution = []
    if args.execute_ready:
        execution = execute_ready(schedule, args.output, args.max_tasks)
    status = {"schedule": schedule["summary"], "execution": execution}
    (args.output / "status.json").write_text(canonical(status))
    print(canonical(status), end="")


if __name__ == "__main__":
    main()
