#!/usr/bin/env python3
"""Account for every frozen registry model in the DS2 report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REGISTRY = HERE.parent / "2026_09_24_ds2_model_registry/model-registry.json"

TASK_MODEL = {
    "baseline": "baseline_doppler",
    "shared-time": "shared_global_receive_time",
    "regularized-per-scan-time": "regularized_per_scan_time",
    "independent-track-time": "independent_per_track_time",
    "causal-rate": "causal_per_norad_orbit_rate",
    "soft-identity": "soft_identity_mixture",
    "equal-weight-joint-rate": "equal_weight_joint_multiscan_position",
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def valid(path: Path) -> bool:
    if not path.is_file():
        return False
    seals = [path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256")]
    return any(
        seal.is_file() and seal.read_text().strip() == hashlib.sha256(path.read_bytes()).hexdigest()
        for seal in seals
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--geometry-status", type=Path)
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text())
    plan = json.loads(args.plan.read_text())
    artifacts: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    joint_rate = None
    for task in plan["tasks"]:
        path = Path(task["output_path"])
        label = task["task_id"].rsplit("__", 1)[-1]
        model = TASK_MODEL.get(label)
        if model is None or not valid(path):
            continue
        artifacts[model].append({"task_id": task["task_id"], "sha256": digest(path)})
        if task["task_id"] == "joint-all20__equal-weight-joint-rate":
            joint_rate = json.loads(path.read_text())
    repeated: dict[str, set[str]] = defaultdict(set)
    if joint_rate:
        for row in joint_rate.get("track_associations", []):
            candidate = row.get("candidate_id")
            if candidate is not None:
                repeated[str(candidate)].add(str(row["session_id"]))
    repeated = {key: value for key, value in repeated.items() if len(value) >= 2}
    rows = []
    for model in registry["models"]:
        model_id = model["id"]
        state = "complete" if artifacts[model_id] else "not_run"
        reason = None
        bindings = artifacts[model_id]
        if model_id == "shared_norad_rate_joint":
            if joint_rate and repeated:
                state = "complete_shared_support"
                reason = f"{len(repeated)} NORADs occur in at least two whole sessions"
                bindings = artifacts["equal_weight_joint_multiscan_position"]
            elif joint_rate:
                state = "complete_zero_overlap"
                reason = "joint support contains no NORAD repeated across whole sessions"
            else:
                state = "dependency_pending"
                reason = "equal-weight joint causal-rate task has not sealed"
        elif model_id == "rate_aware_joint_geographic_screen":
            state = "adapter_required"
            reason = (
                "the portable causal-rate runner reacquires nominal identities geographically "
                "and fits rates only for RF-selected finalists; it is not the registry's "
                "rate-aware proposal screen"
            )
        elif model_id == "consistent_cap800_joint_objective":
            state = "bounded_runtime_deferred"
            reason = (
                "the reviewed DS2 cached runner is available, but the matched proposal/exact "
                "DS1 trial projected 82-100 minutes; it was not substituted with a partial winner"
            )
        elif model_id == "regularized_common_plus_session_scale":
            state = "adapter_required"
            reason = (
                "the repaired block-coordinate implementation consumes DS1 exact support objects; "
                "a receipt-bound DS2 exact-support adapter is not yet implemented"
            )
        elif model_id == "robust_residual_likelihood_rerank":
            state = "adapter_required"
            reason = (
                "the existing reranker consumes DS1 fixed-finalist artifacts; no DS2 finalist "
                "contract is available, so no surrogate rerank was reported"
            )
        elif model_id == "legacy_joint_session_scale_lbfgsb":
            state = "rejected_not_rerun"
            reason = "registry rejects this nonconvergent formulation in favor of the repaired arm"
        elif model_id in {
            "learned_pointing_cone_quantiles",
            "fixed_hard_cone_orientation",
            "staged_full_fov_cone_sweep",
            "local_fitted_full_fov_cone_position",
        }:
            state = "delegated_geometry_evaluation"
            reason = "reported by the separate LT3D-001A geometry/cone DS2 package"
        rows.append(
            {
                "model_id": model_id,
                "registry_status": model["rerun_status"],
                "execution_state": state,
                "reason": reason,
                "artifacts": bindings,
            }
        )
    document = {
        "schema": "ds2-model-registry-accounting/v1",
        "registry_sha256": digest(REGISTRY),
        "model_count": len(rows),
        "all_models_accounted": len(rows) == 17,
        "shared_norad_overlap": {
            "repeated_norad_count": len(repeated),
            "sessions_per_norad": {key: len(value) for key, value in sorted(repeated.items())},
        },
        "models": rows,
    }
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path = HERE / "registry-accounting.json"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"models": len(rows), "repeated_norads": len(repeated)}))


if __name__ == "__main__":
    main()
