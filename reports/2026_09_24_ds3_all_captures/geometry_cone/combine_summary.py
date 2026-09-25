#!/usr/bin/env python3
"""Qualify and seal the four DS3 LT3D geometry model results."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
OUTPUT = REPORT / "output" / "geometry"
EXPECTED_PLAN_SCHEMA = "ds3-lt3d-geometry-cone-plan/v1"
EXPECTED_INFERENCE_SCHEMA = "ds3-lt3d-staged-local-cone-inference/v1"
EXPECTED_GLOBAL_SCHEMA = "ds2-portable-inference-result/v1"
SUMMARY_SCHEMA = "ds3-lt3d-geometry-model-summary/v1"
EXPECTED_MODEL_IDS = (
    "lt3d_geometry_only",
    "lt3d_fixed_up_cone",
    "lt3d_learned_zenith_cone",
    "global_time_plus_lt3d_cone",
)


def digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verified_artifact(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Load an artifact only after its sibling SHA-256 seal validates."""

    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    seal_path = path.with_suffix(path.suffix + ".sha256")
    recorded = seal_path.read_text().strip()
    if recorded.startswith("sha256:"):
        recorded = recorded.removeprefix("sha256:")
    if recorded != actual:
        raise ValueError(f"artifact seal mismatch: {path}")
    return load_object(path), {
        "path": str(path),
        "sha256": f"sha256:{actual}",
        "seal_path": str(seal_path),
        "seal_value": f"sha256:{recorded}",
    }


def require_false(document: Mapping[str, Any], key: str, artifact: str) -> None:
    if document.get(key) is not False:
        raise ValueError(f"{artifact} must explicitly set {key}=false")


def require_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def validate_plan(plan: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    if plan.get("schema") != EXPECTED_PLAN_SCHEMA:
        raise ValueError("unexpected geometry plan schema")
    require_false(plan, "reference_used", "geometry plan")
    require_false(plan, "phase_used", "geometry plan")
    models = plan.get("models")
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)):
        raise ValueError("geometry plan models must be a list")
    model_ids = [str(model.get("model_id")) for model in models if isinstance(model, Mapping)]
    if tuple(model_ids) != EXPECTED_MODEL_IDS:
        raise ValueError("geometry plan model IDs/order do not match the sealed four-model set")
    sessions = plan.get("eligible_session_ids")
    if not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes)):
        raise ValueError("geometry plan eligible_session_ids must be a list")
    session_ids = list(map(str, sessions))
    if len(session_ids) != 5 or len(set(session_ids)) != 5:
        raise ValueError("geometry plan must contain exactly five distinct eligible sessions")
    return model_ids, sorted(session_ids)


def validate_cone_artifact(
    document: Mapping[str, Any],
    *,
    artifact_name: str,
    orientation_mode: str,
    model_ids: Sequence[str],
    session_ids: Sequence[str],
    plan_digest: str,
) -> Mapping[str, Any]:
    if document.get("schema") != EXPECTED_INFERENCE_SCHEMA:
        raise ValueError(f"unexpected {artifact_name} schema")
    if document.get("complete") is not True:
        raise ValueError(f"{artifact_name} is incomplete")
    require_false(document, "reference_used_for_inference", artifact_name)
    require_false(document, "held_used_for_selection", artifact_name)
    if document.get("orientation_mode") != orientation_mode:
        raise ValueError(f"{artifact_name} orientation mode mismatch")
    if document.get("top10_model_ids") != list(model_ids):
        raise ValueError(f"{artifact_name} model binding mismatch")
    bindings = document.get("ds3_bindings")
    if not isinstance(bindings, Mapping) or bindings.get("geometry_plan") != plan_digest:
        raise ValueError(f"{artifact_name} does not bind this geometry plan")
    results = document.get("results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError(f"{artifact_name} results must be a list")
    joint = [
        result
        for result in results
        if isinstance(result, Mapping)
        and sorted(map(str, result.get("session_ids", []))) == list(session_ids)
    ]
    if len(joint) != 1 or joint[0].get("label") != "joint-five-geometry-captures":
        raise ValueError(f"{artifact_name} must contain one exact joint-five result")
    return joint[0]


def position(
    row: Mapping[str, Any], fallback: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    source = row
    if row.get("latitude_deg") is None and fallback is not None:
        source = fallback
    return {
        "latitude_deg": require_number(source.get("latitude_deg"), "latitude_deg"),
        "longitude_deg": require_number(source.get("longitude_deg"), "longitude_deg"),
        "xy_km": [require_number(value, "xy_km") for value in source.get("xy_km", [])],
    }


def scenario_diagnostics(
    row: Mapping[str, Any], position_fallback: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    supported = int(row.get("supported_tracks", -1))
    unsupported = int(row.get("unsupported_tracks", -1))
    fraction = require_number(
        row.get("supported_occupied_second_fraction"),
        "supported_occupied_second_fraction",
    )
    if supported < 1 or unsupported < 0 or not 0.0 <= fraction <= 1.0:
        raise ValueError("invalid cone support diagnostics")
    return {
        "position": position(row, position_fallback),
        "objective": {
            "training_capped_loss": require_number(
                row.get("training_capped_loss"), "training_capped_loss"
            ),
            "held_capped_loss": require_number(row.get("held_capped_loss"), "held_capped_loss"),
        },
        "support": {
            "supported_tracks": supported,
            "unsupported_tracks": unsupported,
            "supported_occupied_second_fraction": fraction,
            "changed_candidate_id_count": int(row.get("changed_candidate_id_count", 0)),
        },
        "cone": {
            "full_fov_deg": require_number(row.get("full_fov_deg"), "full_fov_deg"),
            "mapping": row.get("mapping"),
            "orientation_index": row.get("orientation_index"),
        },
    }


def choose_scenario(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not rows:
        raise ValueError("model has no cone scenarios")
    return min(
        rows,
        key=lambda row: (
            require_number(row.get("training_capped_loss"), "training_capped_loss"),
            require_number(row.get("full_fov_deg"), "full_fov_deg"),
        ),
    )


def local_scenarios(joint: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    local = joint.get("local_fitted_cone")
    if not isinstance(local, Mapping) or not isinstance(local.get("winners"), Mapping):
        raise ValueError("learned artifact lacks local fitted cone winners")
    return [row for row in local["winners"].values() if isinstance(row, Mapping)]


def fixed_scenarios(joint: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    fixed = joint.get("fixed_hard_half_angle")
    if not isinstance(fixed, Mapping) or set(fixed) != {"10", "15", "20", "30"}:
        raise ValueError("fixed-up artifact lacks the reviewed half-angle set")
    return [row for row in fixed.values() if isinstance(row, Mapping)]


def baseline_diagnostics(joint: Mapping[str, Any]) -> dict[str, Any]:
    baseline = joint.get("baseline")
    staged = joint.get("staged_full_fov")
    if not isinstance(baseline, Mapping) or not isinstance(staged, Mapping):
        raise ValueError("learned artifact lacks baseline diagnostics")
    track_count = int(staged.get("track_count", -1))
    if baseline.get("converged") is not True or track_count < 1:
        raise ValueError("joint-five geometry baseline did not converge with track support")
    return {
        "position": position(baseline),
        "objective": {
            "training_capped_loss": require_number(
                baseline.get("training_capped_loss"), "baseline training_capped_loss"
            ),
            "held_capped_loss": None,
        },
        "support": {
            "supported_tracks": track_count,
            "unsupported_tracks": 0,
            "supported_occupied_second_fraction": 1.0,
        },
        "fit": {
            "converged": True,
            "attempt_count": int(baseline.get("attempt_count", 0)),
        },
    }


def validate_global_time(
    document: Mapping[str, Any], session_ids: Sequence[str]
) -> dict[str, Any]:
    if document.get("schema") != EXPECTED_GLOBAL_SCHEMA:
        raise ValueError("unexpected global-time control schema")
    if document.get("complete") is not True:
        raise ValueError("global-time control is incomplete")
    for key in ("reference_coordinate_present", "reference_used_for_fit", "truth_used_for_fit"):
        require_false(document, key, "global-time control")
    if document.get("method") != "shared_global_tau":
        raise ValueError("global-time control did not run shared_global_tau")
    if sorted(map(str, document.get("session_ids", []))) != list(session_ids):
        raise ValueError("global-time control session binding mismatch")
    parameters = document.get("fitted_parameters")
    timing = parameters.get("timing") if isinstance(parameters, Mapping) else None
    tau = timing.get("global_tau_s") if isinstance(timing, Mapping) else None
    tau_value = require_number(tau, "global_tau_s")
    if tau_value != 0.0:
        raise ValueError("global-time cone reuse requires global_tau_s exactly equal to 0.0")
    estimated = document.get("estimated_position")
    objective = document.get("rf_objective")
    if not isinstance(estimated, Mapping) or not isinstance(objective, Mapping):
        raise ValueError("global-time control lacks position/objective diagnostics")
    return {
        "global_tau_s": tau_value,
        "control_position": {
            "latitude_deg": require_number(estimated.get("latitude_deg"), "control latitude"),
            "longitude_deg": require_number(estimated.get("longitude_deg"), "control longitude"),
        },
        "control_objective": {
            "selection_value": require_number(
                objective.get("selection_value"), "control selection_value"
            ),
            "full_observation_capped_loss": require_number(
                objective.get("full_observation_capped_loss"),
                "control full_observation_capped_loss",
            ),
        },
        "control_support": {
            "qualified_tracks": int(document.get("qualified_track_count", 0)),
            "full_observations": int(document.get("full_observation_count", 0)),
            "occupied_seconds": int(document.get("occupied_second_denominator", 0)),
        },
    }


def combine(
    plan: Mapping[str, Any],
    learned: Mapping[str, Any],
    fixed: Mapping[str, Any],
    global_time: Mapping[str, Any],
    provenance: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    model_ids, sessions = validate_plan(plan)
    plan_digest = provenance["geometry_plan"]["sha256"]
    learned_joint = validate_cone_artifact(
        learned,
        artifact_name="learned15 inference",
        orientation_mode="learned15",
        model_ids=model_ids[0:1] + model_ids[2:3],
        session_ids=sessions,
        plan_digest=plan_digest,
    )
    fixed_joint = validate_cone_artifact(
        fixed,
        artifact_name="fixed-up inference",
        orientation_mode="fixed-up",
        model_ids=model_ids[1:2],
        session_ids=sessions,
        plan_digest=plan_digest,
    )
    geometry = baseline_diagnostics(learned_joint)
    fixed_baseline = fixed_joint.get("baseline")
    if not isinstance(fixed_baseline, Mapping):
        raise ValueError("fixed-up artifact lacks baseline position")
    fixed_result = scenario_diagnostics(
        choose_scenario(fixed_scenarios(fixed_joint)), fixed_baseline
    )
    learned_result = scenario_diagnostics(choose_scenario(local_scenarios(learned_joint)))
    time_control = validate_global_time(global_time, sessions)
    global_result = copy.deepcopy(learned_result)
    global_result["time_control"] = time_control
    global_result["reuse"] = {
        "status": "valid_exact_zero_tau_reuse",
        "source_model_id": "lt3d_learned_zenith_cone",
        "required_seals": [
            provenance["learned15_inference"]["sha256"],
            provenance["global_time_control"]["sha256"],
        ],
    }

    diagnostics = [geometry, fixed_result, learned_result, global_result]
    rows = []
    source_names = (
        "learned15_inference",
        "fixed_up_inference",
        "learned15_inference",
        "learned15_inference+global_time_control",
    )
    for model_id, source, result in zip(model_ids, source_names, diagnostics, strict=True):
        rows.append(
            {
                "model_id": model_id,
                "qualification": "qualified",
                "qualification_reason": "joint-five sealed diagnostics passed all model gates",
                "session_ids": sessions,
                "source": source,
                "joint_five": result,
            }
        )
    return {
        "schema": SUMMARY_SCHEMA,
        "complete": True,
        "dataset_name": "DS3",
        "reference_coordinate_present": False,
        "reference_used_for_qualification": False,
        "phase_used": False,
        "session_ids": sessions,
        "model_ids": model_ids,
        "models": rows,
        "qualification_policy": (
            "structural completeness, joint-five support, convergence, sealed provenance, "
            "and declared causal/reference exclusions; no position truth"
        ),
        "provenance": dict(provenance),
    }


def write_sealed(path: Path, document: Mapping[str, Any]) -> None:
    seal_path = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or seal_path.exists():
        raise FileExistsError(f"refusing to replace sealed output: {path}")
    content = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    seal_path.write_text(hashlib.sha256(content).hexdigest() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=REPORT / "geometry-cone-plan.json")
    parser.add_argument("--learned", type=Path, default=OUTPUT / "learned15-inference.json")
    parser.add_argument("--fixed", type=Path, default=OUTPUT / "fixed-up-inference.json")
    parser.add_argument("--global-time", type=Path, default=OUTPUT / "global-time-control.json")
    parser.add_argument("--output", type=Path, default=OUTPUT / "geometry-model-summary.json")
    args = parser.parse_args()
    plan, plan_provenance = verified_artifact(args.plan)
    learned, learned_provenance = verified_artifact(args.learned)
    fixed, fixed_provenance = verified_artifact(args.fixed)
    global_time, global_provenance = verified_artifact(args.global_time)
    provenance = {
        "geometry_plan": plan_provenance,
        "learned15_inference": learned_provenance,
        "fixed_up_inference": fixed_provenance,
        "global_time_control": global_provenance,
    }
    write_sealed(args.output, combine(plan, learned, fixed, global_time, provenance))


if __name__ == "__main__":
    main()
