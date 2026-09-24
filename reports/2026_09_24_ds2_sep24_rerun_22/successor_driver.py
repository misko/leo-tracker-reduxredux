#!/usr/bin/env python3
"""Build and, only when explicitly requested, run a DS2 successor plan.

The historical DS2 portable package is deliberately fixed to its 20-session
corpus.  This adapter gives a successor corpus a new root and binds every
task to the supplied whole-session manifest and receipt-bound causal cache.
It never accepts a reference coordinate.  ``postseal_evaluation.py`` is the
only companion program allowed to do that, after inference is sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORTABLE_ADAPTER = ROOT / "2026_09_24_ds2_portable_evaluation/run_portable.py"
TIMING_METHODS = {
    "baseline",
    "shared_global_tau",
    "regularized_per_scan_tau",
    "independent_per_track_tau",
}
PRIOR = {
    "name": "sacramento-250km-predeclared",
    "lat": 38.5816,
    "lon": -121.4944,
    "radius_km": 250.0,
    "reference_used_for_selection": False,
}
SINGLE_MODELS = (
    ("baseline", "baseline"),
    ("shared-time", "shared_global_tau"),
    ("causal-rate", "causal_per_norad_orbit_rate"),
    ("independent-track-time", "independent_per_track_tau"),
    ("soft-identity", "soft_joint_association"),
)
JOINT_MODELS = (
    ("baseline", "baseline"),
    ("shared-time", "shared_global_tau"),
    ("regularized-per-scan-time", "regularized_per_scan_tau"),
    ("independent-track-time", "independent_per_track_tau"),
    ("soft-identity", "soft_association_global_tau"),
    ("equal-weight-joint-rate", "global_tau_per_norad_orbit_rate"),
)
CONE_FAMILIES = (
    "learned_pointing_cone_quantiles",
    "fixed_hard_cone_orientation",
    "staged_full_fov_cone_sweep",
    "local_fitted_full_fov_cone_position",
)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> bool:
    if not path.is_file():
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return any(
        sidecar.is_file() and sidecar.read_text().strip().removeprefix("sha256:") == actual
        for sidecar in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    )


def write_new_sealed(path: Path, value: Any) -> None:
    """Write an artifact once; a successor never replaces report evidence."""
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to overwrite report artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical(value)
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def session_rows(manifest_path: Path, cache_root: Path) -> list[dict[str, Any]]:
    """Validate the public corpus contract and each causal-cache receipt."""
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "ds2-whole-corpus-manifest/v1":
        raise ValueError("successor requires a sealed DS2 whole-corpus manifest")
    if manifest.get("manifest_sealed") is not True:
        raise ValueError("successor manifest is not sealed")
    if manifest.get("reference_coordinate_in_manifest") is not False:
        raise ValueError("manifest may not contain a reference coordinate")
    if manifest.get("position_evaluation") != "external_post_inference_only":
        raise ValueError("manifest must reserve position evaluation for post-seal")
    rows = manifest.get("sessions")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("successor needs at least two complete whole sessions")
    ids = [str(row.get("session_id", "")) for row in rows]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("manifest session IDs must be unique and nonempty")
    validated = []
    for row, session_id in zip(rows, ids, strict=True):
        if row.get("tracking", {}).get("status") != "complete":
            raise ValueError(f"tracking is incomplete: {session_id}")
        receipt_path = cache_root / session_id / "cache_receipt.json"
        state_path = cache_root / session_id / "state_cache.npz"
        if not receipt_path.is_file() or not state_path.is_file():
            raise ValueError(f"receipt-bound causal cache is absent: {session_id}")
        receipt = load_json(receipt_path)
        if receipt.get("session_id") != session_id:
            raise ValueError(f"cache receipt session mismatch: {session_id}")
        if receipt.get("bindings", {}).get("state_cache") != digest(state_path):
            raise ValueError(f"cache receipt digest mismatch: {session_id}")
        evidence = receipt.get("prepared_evidence", {})
        if (
            not evidence.get("eligible_track_count")
            or not evidence.get("eligible_observation_count")
        ):
            raise ValueError(f"cache has no eligible causal evidence: {session_id}")
        validated.append(
            {
                "session_id": session_id,
                "captured_at": row.get("captured_at"),
                "tracking_product_digest": row["tracking"].get("tracking_product_digest"),
                "cache_receipt_sha256": digest(receipt_path),
                "state_cache_sha256": digest(state_path),
                "eligible_track_count": evidence["eligible_track_count"],
                "eligible_observation_count": evidence["eligible_observation_count"],
            }
        )
    return validated


def task(
    task_id: str, sessions: list[str], method: str, output: Path, *, joint: bool
) -> dict[str, Any]:
    levels = [100.0, 25.0, 6.25, 1.5625] if joint else [100.0, 25.0, 6.25]
    return {
        "task_id": task_id,
        "partition": "development",
        "group_id": (
            f"ds2-successor-all-{len(sessions)}" if joint else f"ds2-successor-{sessions[0]}"
        ),
        "session_ids": sessions,
        "prior": PRIOR,
        "method": method,
        "output_path": str(output.resolve()),
        "options": {
            "observation_policy": "all_qualified_observations",
            "within_track_holdout": "forbidden",
            "minimum_track_duration_s": 3.0,
            "frequency_loss_cap_hz": 800.0,
            "tau_grid_s": [-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0],
            "geographic_levels_km": levels,
            "search_levels_km": levels,
            "beam_width": 3,
            "exact_rate_finalists": 2,
            "exact_rate_workers": 2,
            "equal_session_weight": joint,
            "per_scan_sigma_s": 1.0,
            "per_scan_penalty_weight": 0.01,
            "per_scan_delta_limit_s": 5.0,
        },
    }


def geometry_plan(manifest_path: Path, output_root: Path) -> dict[str, Any]:
    """Admit only sessions carrying a capture-time LT3D geometry binding."""
    manifest = load_json(manifest_path)
    bound = []
    for row in manifest["sessions"]:
        geometry = row.get("receiver_geometry")
        if not isinstance(geometry, dict):
            continue
        assignments = geometry.get("assignments", [])
        receiver_ids = sorted(item.get("receiver_id") for item in assignments)
        if (
            geometry.get("eligibility") == "conditional_provisional_mapping"
            and geometry.get("capture_binding_digest")
            and geometry.get("fixture_digest")
            and receiver_ids == [0, 1]
        ):
            bound.append(
                {
                    "session_id": row["session_id"],
                    "capture_binding_digest": geometry["capture_binding_digest"],
                    "fixture_digest": geometry["fixture_digest"],
                }
            )
    return {
        "schema": "ds2-successor-geometry-cone-plan/v1",
        "reference_coordinate_present": False,
        "reference_used_for_inference": False,
        "admission_policy": "only explicit capture-time geometry bindings are eligible",
        "sessions": bound,
        "receiver_slot_mappings": [[0, 1], [1, 0]],
        "mapping_policy": (
            "evaluate both RX-to-slot symmetries; do not report either as calibrated fact"
        ),
        "fitted_cone_families": list(CONE_FAMILIES),
        "output_root": str((output_root / "geometry").resolve()),
        "execution": (
            "planner contract only: a fresh receipt-bound geometry export is required; "
            "never use unbound sessions"
        ),
    }


def registry_accounting(geometry: dict[str, Any]) -> dict[str, Any]:
    planned = [label for label, _ in SINGLE_MODELS] + [label for label, _ in JOINT_MODELS]
    return {
        "schema": "ds2-successor-registry-accounting/v1",
        "portable_models_planned": planned,
        "followup_models": {
            "consistent_cap800_joint_objective": "depends on sealed successor joint rate finalist",
            "rate_aware_joint_geographic_screen": "depends on sealed successor joint rate finalist",
            "regularized_common_plus_session_scale": (
                "depends on sealed successor exact rate finalists"
            ),
            "robust_residual_likelihood_rerank": (
                "depends on sealed successor exact rate finalists"
            ),
            "shared_norad_rate_joint": "recompute after successor joint support seals",
        },
        "geometry_models": {
            "state": "admitted" if geometry["sessions"] else "not_admitted",
            "families": geometry["fitted_cone_families"],
        },
        "legacy_joint_session_scale_lbfgsb": {
            "state": "rejected_not_rerun",
            "reason": "nonconvergent legacy formulation; repaired block-coordinate arm is retained",
        },
    }


def followup_plan(prefix: str, output_root: Path) -> dict[str, Any]:
    """Bind deferred adapters to the dynamic successor parent, never DS2-20."""
    parent = f"{prefix}__equal-weight-joint-rate"
    return {
        "schema": "ds2-successor-followup-plan/v1",
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "parent_joint_task_id": parent,
        "gates": [
            "parent portable result is digest sealed",
            "parent exact SGP4 gate passed",
            "no reference coordinate before the child inference seals",
        ],
        "adapters": {
            "consistent_rate_screen": {
                "source": str(
                    (ROOT / "2026_09_24_ds2_consistent_rate_screen/run_rate_screen.py").resolve()
                ),
                "output": str((output_root / "followups" / "consistent-rate.json").resolve()),
                "scope": (
                    "bounded local rate-aware proposal and nominal control around the sealed "
                    "successor finalist"
                ),
            },
            "missing_models": {
                "source": str((ROOT / "2026_09_24_ds2_missing_models/run.py").resolve()),
                "output": str((output_root / "followups" / "missing-models.json").resolve()),
                "scope": (
                    "repaired session-scale and residual diagnostics from successor exact finalists"
                ),
            },
        },
    }


def build(manifest_path: Path, cache_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"successor output root already exists: {output_root}")
    rows = session_rows(manifest_path, cache_root)
    session_ids = [row["session_id"] for row in rows]
    count = len(session_ids)
    tasks = []
    inference = output_root / "portable" / "inference"
    for session_id in session_ids:
        for label, method in SINGLE_MODELS:
            tasks.append(
                task(
                    f"single__{session_id}__{label}",
                    [session_id],
                    method,
                    inference / f"single__{session_id}__{label}.json",
                    joint=False,
                )
            )
    prefix = f"joint-all{count}"
    for label, method in JOINT_MODELS:
        tasks.append(
            task(
                f"{prefix}__{label}",
                session_ids,
                method,
                inference / f"{prefix}__{label}.json",
                joint=True,
            )
        )
    geometry = geometry_plan(manifest_path, output_root)
    plan = {
        "schema": "ds2-successor-portable-plan/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_selection": False,
        "reference_boundary": "reference coordinate is forbidden before sealed inference",
        "manifest": {"path": str(manifest_path.resolve()), "sha256": digest(manifest_path)},
        "cache_root_runtime_only": str(cache_root.resolve()),
        "whole_session_policy": (
            "every portable task consumes complete sessions; no train/validation/test split"
        ),
        "sessions": rows,
        "joint_task_prefix": prefix,
        "task_count": len(tasks),
        "single_scan_task_count": len(session_ids) * len(SINGLE_MODELS),
        "joint_task_count": len(JOINT_MODELS),
        "tasks": tasks,
        "adapters": {
            "portable_evaluation": str(PORTABLE_ADAPTER.resolve()),
            "consistent_rate_screen": str(
                (ROOT / "2026_09_24_ds2_consistent_rate_screen/run_rate_screen.py").resolve()
            ),
            "missing_models": str((ROOT / "2026_09_24_ds2_missing_models/run.py").resolve()),
            "geometry_cone_evaluation": str(
                (
                    ROOT
                    / "2026_09_24_ds2_geometry_cone_evaluation/run_blind_reassociated.py"
                ).resolve()
            ),
        },
    }
    write_new_sealed(output_root / "portable" / "plan.json", plan)
    for row in tasks:
        write_new_sealed(output_root / "portable" / "tasks" / f"{row['task_id']}.json", row)
    write_new_sealed(output_root / "geometry" / "plan.json", geometry)
    write_new_sealed(output_root / "followups" / "plan.json", followup_plan(prefix, output_root))
    write_new_sealed(output_root / "registry-accounting.json", registry_accounting(geometry))
    return plan


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def execute_portable(plan: dict[str, Any], cache_root: Path, output_root: Path) -> None:
    """Run only explicitly requested portable tasks, never overwriting a result."""
    adapter = load_module(PORTABLE_ADAPTER, "ds2_successor_portable_adapter")
    rows = []
    for original in plan["tasks"]:
        output = Path(original["output_path"])
        if output.exists():
            raise FileExistsError(f"refusing to replace task result: {output}")
        task_value = json.loads(json.dumps(original))
        task_value["partition"] = "train"  # reviewed runner's implementation token
        task_value["session_groups"] = {
            session_id: "ds2" for session_id in task_value["session_ids"]
        }
        task_value["options"]["cache_root"] = str(cache_root)
        if task_value["method"] in TIMING_METHODS:
            result = adapter.run_timing(task_value, cache_root)
        else:
            result = adapter.run_orbit(task_value, cache_root)
        if not sealed(output):
            raise RuntimeError(f"runner did not seal output: {output}")
        rows.append({"task_id": result["task_id"], "state": "complete", "sha256": digest(output)})
    write_new_sealed(
        output_root / "portable" / "execution.json",
        {
            "schema": "ds2-successor-portable-execution/v1",
            "complete": True,
            "reference_coordinate_present": False,
            "rows": rows,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("plan", "portable"), default="plan")
    parser.add_argument(
        "--execute", action="store_true", help="required to run expensive portable models"
    )
    args = parser.parse_args()
    if args.mode == "plan":
        plan = build(args.manifest, args.cache_root, args.output_root)
        print(
            json.dumps(
                {"sessions": len(plan["sessions"]), "joint_task_prefix": plan["joint_task_prefix"]},
                sort_keys=True,
            )
        )
        return
    if not args.execute:
        raise ValueError("portable execution requires --execute; planning never runs models")
    plan_path = args.output_root / "portable" / "plan.json"
    if not sealed(plan_path):
        raise ValueError("portable plan must be sealed before execution")
    plan = load_json(plan_path)
    if plan["manifest"]["sha256"] != digest(args.manifest):
        raise ValueError("manifest differs from the sealed successor plan")
    execute_portable(plan, args.cache_root, args.output_root)


if __name__ == "__main__":
    main()
