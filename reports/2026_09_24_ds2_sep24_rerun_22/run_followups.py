#!/usr/bin/env python3
"""Plan and run the deferred DS2 successor models without geographic truth.

The historical DS2 follow-up programs are immutable 20-session experiments.
This adapter keeps their reviewed numerical implementations while binding a
new run to a sealed successor manifest, causal caches, and one or more sealed
``joint-all<N>`` rate artifacts.  Geographic reference coordinates are not an
argument and do not appear in any inference output.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CAP800 = ROOT / "reports/2026_09_24_ds2_consistent_cap800_runner/runner.py"
RATE_SCREEN = ROOT / "reports/2026_09_24_ds2_consistent_rate_screen/run_rate_screen.py"
MISSING = ROOT / "reports/2026_09_24_ds2_missing_models/run.py"
JOINT = ROOT / "reports/2026_09_24_ds1_joint_rate_search/joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SCALE = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"

SCHEMA = "ds2-successor-followup-run-plan/v1"
MODEL_NAMES = (
    "consistent-cap800",
    "rate-aware-screen",
    "session-scale-residual",
    "shared-norad",
)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> bool:
    if not path.is_file():
        return False
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    return any(
        item.is_file() and item.read_text().strip().removeprefix("sha256:") == expected
        for item in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_sealed(path: Path, value: Any, *, replace: bool = False) -> None:
    if path.exists() and not replace:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    temporary.write_text(text)
    os.replace(temporary, path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_manifest(path: Path) -> dict[str, Any]:
    if not sealed(path):
        raise ValueError(f"successor manifest is not sealed: {path}")
    value = load_json(path)
    if (
        value.get("schema") != "ds2-whole-corpus-manifest/v1"
        or value.get("manifest_sealed") is not True
        or value.get("reference_coordinate_in_manifest") is not False
        or value.get("position_evaluation") != "external_post_inference_only"
    ):
        raise ValueError("invalid successor whole-corpus manifest")
    sessions = value.get("sessions")
    if not isinstance(sessions, list) or len(sessions) < 2:
        raise ValueError("successor manifest needs at least two sessions")
    return value


def validate_parent(path: Path, session_ids: list[str]) -> dict[str, Any]:
    if not sealed(path):
        raise ValueError(f"parent inference is not sealed: {path}")
    value = load_json(path)
    if (
        value.get("complete") is not True
        or value.get("reference_coordinate_present") is not False
        or value.get("reference_used_for_fit") is not False
        or value.get("exact_sgp4_winner_gate", {}).get("passed") is not True
    ):
        raise ValueError(f"parent failed the reference or exact-replay gate: {path}")
    if list(map(str, value.get("session_ids", []))) != session_ids:
        raise ValueError(f"parent session membership differs from the manifest: {path}")
    if "equal-weight-joint-rate" not in str(value.get("task_id", "")):
        raise ValueError(f"parent is not an equal-weight joint-rate result: {path}")
    return value


def exact_finalists(path: Path, label: str, document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row for row in document.get("search_trace", []) if row.get("stage") == "exact_rate_finalist"
    ]
    if len(rows) != 2:
        raise ValueError(f"expected two exact rate finalists: {path}")
    return [
        {
            "finalist_id": f"{label}-{index}",
            "source_stage": label,
            "source_artifact": str(path.resolve()),
            "source_sha256": digest(path),
            "latitude_deg": float(row["latitude_deg"]),
            "longitude_deg": float(row["longitude_deg"]),
            "tau_s": float(row["tau_s"]),
            "source_exact_objective": float(row["objective"]),
            "source_screening_objective": float(row["screening_objective"]),
        }
        for index, row in enumerate(rows, 1)
    ]


def split_sessions(manifest: dict[str, Any]) -> list[list[str]]:
    rows = sorted(
        manifest["sessions"], key=lambda row: (str(row.get("captured_at", "")), row["session_id"])
    )
    # Both groups participate in one balanced objective. Alternation spreads
    # the full-day temporal coverage across them; neither group is a holdout.
    return [[str(row["session_id"]) for row in rows[offset::2]] for offset in range(2)]


def embedded_task(
    group_id: str,
    sessions: list[str],
    prior: dict[str, Any],
    cache_root: Path,
) -> dict[str, Any]:
    return {
        "task_id": f"successor-cap800-{group_id}",
        "group_id": group_id,
        "partition": "development",
        "session_ids": sessions,
        "session_groups": {session_id: "ds2" for session_id in sessions},
        "prior": prior,
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str((HERE / "unused.json").resolve()),
        "options": {
            "cache_root": str(cache_root.resolve()),
            "equal_session_weight": True,
            "frequency_loss_cap_hz": 800.0,
            "minimum_track_duration_s": 3.0,
            "observation_policy": "all_qualified_observations",
            "within_track_holdout": "forbidden",
        },
    }


def discover_parents(successor_output_root: Path) -> list[Path]:
    """Return coarse, local, and fine rate parents from sealed successor indexes."""
    portable_plan_path = successor_output_root / "portable" / "plan.json"
    if not sealed(portable_plan_path):
        raise ValueError("successor portable plan is not sealed")
    portable_plan = load_json(portable_plan_path)
    prefix = str(portable_plan.get("joint_task_prefix", ""))
    task_id = prefix + "__equal-weight-joint-rate"
    matches = [row for row in portable_plan.get("tasks", []) if row.get("task_id") == task_id]
    if len(matches) != 1:
        raise ValueError("successor plan lacks one equal-weight joint-rate task")
    parents = [Path(matches[0]["output_path"])]
    for stage in ("stage-one", "fine"):
        index_path = successor_output_root / "portable" / "refinement" / stage / "index.json"
        if not index_path.exists():
            continue
        if not sealed(index_path):
            raise ValueError(f"successor refinement index is not sealed: {index_path}")
        index = load_json(index_path)
        rows = [
            row for row in index.get("models", []) if row.get("method") == "equal-weight-joint-rate"
        ]
        if len(rows) != 1:
            raise ValueError(f"refinement index lacks one joint-rate row: {index_path}")
        parents.append(Path(rows[0]["final_artifact"]))
    return parents


def build_plan(
    manifest_path: Path,
    cache_root: Path,
    parents: list[Path],
    output_root: Path,
) -> dict[str, Any]:
    manifest = validate_manifest(manifest_path)
    session_ids = [str(row["session_id"]) for row in manifest["sessions"]]
    parent_rows = []
    finalists = []
    for index, path in enumerate(parents):
        document = validate_parent(path, session_ids)
        label = (
            "coarse"
            if index == 0
            else ("fine" if index == len(parents) - 1 else f"refined-{index}")
        )
        parent_rows.append(
            {
                "stage": label,
                "path": str(path.resolve()),
                "sha256": digest(path),
                "task_id": document["task_id"],
            }
        )
        finalists.extend(exact_finalists(path, label, document))
    if not parent_rows:
        raise ValueError("at least one sealed joint-rate parent is required")
    fine_path = Path(parent_rows[-1]["path"])
    fine = load_json(fine_path)
    prior = {
        "name": "sacramento-250km-predeclared",
        "lat": 38.5816,
        "lon": -121.4944,
        "radius_km": 250.0,
        "reference_used_for_selection": False,
    }
    halves = split_sessions(manifest)
    tau = float(fine["global_tau_s"])
    cap_manifest = {
        "schema": "consistent-cap800-frozen-run/v1",
        "partition": "development",
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "dataset_manifest": {"path": str(manifest_path.resolve()), "sha256": digest(manifest_path)},
        "scope": {
            "all_sessions": session_ids,
            "initial_prior": "Sacramento 250 km in the sealed parent search",
            "local_reuse": "one 3x3 lattice around the sealed successor RF-only winner",
            "no_truth_before_postseal": True,
        },
        "origin": {
            **{
                key: float(fine["estimated_position"][key])
                for key in ("latitude_deg", "longitude_deg")
            },
            "origin_policy": "sealed successor joint-rate winner",
        },
        "parent_finalist": {"path": str(fine_path), "sha256": digest(fine_path)},
        "portable_cache_root": str(cache_root.resolve()),
        "groups": [
            {
                "group_id": f"balanced-interleave-{index}",
                "task": embedded_task(
                    f"balanced-interleave-{index}", ids, prior, cache_root
                ),
                "weight": 0.5,
            }
            for index, ids in enumerate(halves, 1)
        ],
        "tau_grid_s": sorted({tau - 1.0, tau, tau + 1.0}),
        "levels_km": [0.1953125],
        "seeds": [fine["estimated_position"]],
        "top_basins": 3,
        "top_taus_per_group": 2,
        "exact_top_coordinates": 2,
        "modules": {"joint": str(JOINT), "runner": str(RUNNER), "orbit": str(ORBIT)},
    }
    missing_plan = {
        "schema": "ds2-successor-missing-models-plan/v1",
        "complete": True,
        "partition": "development",
        "reference_coordinate_present": False,
        "reference_used_for_selection": False,
        "manifest": {"path": str(manifest_path.resolve()), "sha256": digest(manifest_path)},
        "prior": prior,
        "session_ids": session_ids,
        "session_scale": {
            "scientific_model": "repaired common plus per-session fractional Doppler scale",
            "centre": {**fine["estimated_position"], "tau_s": tau},
            "spacing_km": 0.09765625,
            "lattice": "symmetric 3x3",
            "association_policy": "fixed sealed finest-stage all-session rate-winner identities",
            "source_artifact": str(fine_path),
            "source_sha256": digest(fine_path),
        },
        "residual_likelihood": {
            "finalists": finalists,
            "candidate_policy": (
                "two pre-existing exact-rate finalists from every supplied sealed stage"
            ),
            "association_policy": (
                "reacquire once at each frozen coordinate and tau, then freeze for exact "
                "rate and likelihood fits"
            ),
        },
    }
    plan = {
        "schema": SCHEMA,
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "manifest": {"path": str(manifest_path.resolve()), "sha256": digest(manifest_path)},
        "cache_root_runtime_only": str(cache_root.resolve()),
        "session_ids": session_ids,
        "parents": parent_rows,
        "finest_parent": parent_rows[-1],
        "models": list(MODEL_NAMES),
        "outputs": {
            "consistent-cap800": str((output_root / "consistent-cap800.json").resolve()),
            "rate-aware-screen": str((output_root / "rate-aware-screen.json").resolve()),
            "session-scale-residual": str((output_root / "session-scale-residual.json").resolve()),
            "shared-norad": str((output_root / "shared-norad.json").resolve()),
        },
        "work_root": str((output_root / "work" / "consistent-cap800").resolve()),
        "source_bindings": {
            "cap800_runner": digest(CAP800),
            "rate_screen": digest(RATE_SCREEN),
            "missing_models": digest(MISSING),
            "joint_rate": digest(JOINT),
            "portable_runner": digest(RUNNER),
            "exact_orbit": digest(ORBIT),
            "session_scale": digest(SCALE),
        },
    }
    write_sealed(output_root / "cap800-manifest.json", cap_manifest)
    write_sealed(output_root / "missing-models-plan.json", missing_plan)
    write_sealed(output_root / "run-plan.json", plan)
    return plan


def completed(path: Path, plan_path: Path) -> bool:
    if not path.exists():
        return False
    if not sealed(path):
        raise ValueError(f"existing follow-up output is not sealed: {path}")
    document = load_json(path)
    if document.get("run_plan_sha256") != digest(plan_path):
        raise ValueError(f"existing output belongs to another follow-up plan: {path}")
    return document.get("complete") is True


def run_cap800(plan: dict[str, Any], plan_path: Path, workers: int) -> None:
    output = Path(plan["outputs"]["consistent-cap800"])
    if completed(output, plan_path):
        return
    cap = load_module(CAP800, "ds2_successor_cap800")
    result = cap.execute(
        plan_path.parent / "cap800-manifest.json",
        Path(plan["work_root"]),
        output,
        workers,
    )
    result["run_plan_sha256"] = digest(plan_path)
    result["reference_coordinate_present"] = False
    write_sealed(output, result, replace=True)


def rate_row_key(source: Any, arm: str, row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(source.row_key(row, arm))


def run_rate_screen(plan: dict[str, Any], plan_path: Path, workers: int) -> None:
    output = Path(plan["outputs"]["rate-aware-screen"])
    if completed(output, plan_path):
        return
    source = load_module(RATE_SCREEN, "ds2_successor_rate_screen")
    finalist_path = Path(plan["finest_parent"]["path"])
    finalist = validate_parent(finalist_path, plan["session_ids"])
    finalist["_source_path"] = str(finalist_path)
    points = source.point_grid(finalist["estimated_position"], 0.1953125)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        rows = list(
            pool.map(
                source.one_point,
                [(finalist, point, Path(plan["cache_root_runtime_only"])) for point in points],
            )
        )
    winners = {}
    for arm in ("rate_aware", "nominal_control"):
        winners[arm] = min(rows, key=partial(rate_row_key, source, arm))
    exact = {
        arm: source.exact_gate(finalist, winners[arm], arm, Path(plan["cache_root_runtime_only"]))
        for arm in winners
    }
    result = {
        "schema": "ds2-successor-rate-aware-local-screen/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "run_plan_sha256": digest(plan_path),
        "scope": {
            "spacing_km": 0.1953125,
            "point_count": len(rows),
            "session_count": len(plan["session_ids"]),
        },
        "finalist": {"path": str(finalist_path), "sha256": digest(finalist_path)},
        "rows": rows,
        "winners": winners,
        "exact_replay": exact,
        "bindings": {
            "source": digest(RATE_SCREEN),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    write_sealed(output, result)


def _missing_result(plan: dict[str, Any], plan_path: Path, workers: int) -> dict[str, Any]:
    source = load_module(MISSING, "ds2_successor_missing")
    child_path = plan_path.parent / "missing-models-plan.json"
    child = load_json(child_path)
    centre = child["session_scale"]["centre"]
    spacing = float(child["session_scale"]["spacing_km"])
    points = [
        source.offset_coordinate(centre["latitude_deg"], centre["longitude_deg"], east, north)
        for north in (-spacing, 0.0, spacing)
        for east in (-spacing, 0.0, spacing)
    ]
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("fork"),
        initializer=source.initialize,
        initargs=(str(child_path), plan["cache_root_runtime_only"]),
    ) as pool:
        scales = list(pool.map(source.audit_scale, points, chunksize=1))
        residuals = list(
            pool.map(source.audit_residual, child["residual_likelihood"]["finalists"], chunksize=1)
        )
        scales.sort(
            key=lambda row: (
                row["common_plus_session_scale"]["selection_objective"],
                row["north_km"],
                row["east_km"],
            )
        )
        scale_winner = scales[0]
        sensitivity = list(
            pool.map(
                source.audit_scale_start, [(scale_winner, -4e-4), (scale_winner, 4e-4)], chunksize=1
            )
        )
    baseline = min(
        scales,
        key=lambda row: (
            row["matched_rate_only"]["selection_objective"],
            row["north_km"],
            row["east_km"],
        ),
    )
    gaussian = source.rank(residuals, "gaussian")
    robust = source.rank(residuals, "ar1_student_t")
    return {
        "schema": "ds2-successor-session-scale-residual-inference/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "truth_used_for_fit": False,
        "run_plan_sha256": digest(plan_path),
        "session_count": len(plan["session_ids"]),
        "session_ids": plan["session_ids"],
        "common_plus_session_scale": {
            "status": "complete_unqualified_diagnostic",
            "rows": scales,
            "matched_rate_only_winner": {
                key: baseline[key]
                for key in ("latitude_deg", "longitude_deg", "east_km", "north_km")
            },
            "winner": {
                key: scale_winner[key]
                for key in ("latitude_deg", "longitude_deg", "east_km", "north_km")
            },
            "initialization_sensitivity": sensitivity,
            "qualified": bool(
                scale_winner["common_plus_session_scale"]["converged"]
                and not scale_winner["common_plus_session_scale"]["scale_reaches_guard"]
                and scale_winner["hierarchy_exact_gate"]["passed"]
                and abs(scale_winner["east_km"]) < spacing - 1e-12
                and abs(scale_winner["north_km"]) < spacing - 1e-12
                and abs(
                    sensitivity[0]["fit"]["selection_objective"]
                    - sensitivity[1]["fit"]["selection_objective"]
                )
                <= 1e-6
            ),
        },
        "robust_residual_likelihood": {
            "status": "complete_diagnostic",
            "rows": residuals,
            "gaussian_ranking": [row["finalist_id"] for row in gaussian],
            "ar1_student_t_ranking": [row["finalist_id"] for row in robust],
            "gaussian_winner": {
                key: gaussian[0][key]
                for key in ("finalist_id", "latitude_deg", "longitude_deg", "tau_s")
            },
            "ar1_student_t_winner": {
                key: robust[0][key]
                for key in ("finalist_id", "latitude_deg", "longitude_deg", "tau_s")
            },
            "qualified": bool(
                all(row["exact_gate"]["passed"] for row in residuals)
                and all(row["ar1_student_t"]["converged"] for row in residuals)
            ),
        },
        "elapsed_s": time.monotonic() - started,
        "workers": workers,
        "bindings": {
            "child_plan": digest(child_path),
            "source": digest(MISSING),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
            "scale": digest(SCALE),
        },
    }


def run_missing(plan: dict[str, Any], plan_path: Path, workers: int) -> None:
    output = Path(plan["outputs"]["session-scale-residual"])
    if not completed(output, plan_path):
        write_sealed(output, _missing_result(plan, plan_path, workers))


def run_shared_norad(plan: dict[str, Any], plan_path: Path) -> None:
    output = Path(plan["outputs"]["shared-norad"])
    if completed(output, plan_path):
        return
    parent_path = Path(plan["finest_parent"]["path"])
    parent = validate_parent(parent_path, plan["session_ids"])
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    for row in parent.get("track_associations", []):
        if row.get("candidate_id") is not None and row.get("session_id") is not None:
            by_source[str(row["candidate_id"])].add(str(row["session_id"]))
    repeated = {
        source: sorted(sessions)
        for source, sessions in sorted(by_source.items())
        if len(sessions) >= 2
    }
    rate_map = parent.get("fitted", {}).get("rate_corrections_s_h", {})
    result = {
        "schema": "ds2-successor-shared-norad-accounting/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "run_plan_sha256": digest(plan_path),
        "parent": {"path": str(parent_path), "sha256": digest(parent_path)},
        "session_count": len(plan["session_ids"]),
        "selected_source_count": len(by_source),
        "cross_session_shared_norad_count": len(repeated),
        "cross_session_shared_norads": repeated,
        "state": "complete_shared_support" if repeated else "complete_zero_overlap",
        "fit_policy": (
            "the sealed all-session joint-rate parent already fits one causal rate per "
            "NORAD across every session"
        ),
        "shared_rate_corrections_s_h": {
            source: rate_map[source] for source in repeated if source in rate_map
        },
    }
    write_sealed(output, result)


def execute(plan_path: Path, models: list[str], workers: int) -> None:
    if not sealed(plan_path):
        raise ValueError("follow-up plan is not sealed")
    if not 1 <= workers <= 4:
        raise ValueError("workers must be in 1..4")
    plan = load_json(plan_path)
    if plan.get("schema") != SCHEMA or plan.get("reference_coordinate_present") is not False:
        raise ValueError("invalid follow-up run plan")
    unknown = sorted(set(models) - set(MODEL_NAMES))
    if unknown:
        raise ValueError(f"unknown models: {unknown}")
    validate_manifest(Path(plan["manifest"]["path"]))
    for parent in plan["parents"]:
        validate_parent(Path(parent["path"]), plan["session_ids"])
    for model in models:
        if model == "consistent-cap800":
            run_cap800(plan, plan_path, workers)
        elif model == "rate-aware-screen":
            run_rate_screen(plan, plan_path, workers)
        elif model == "session-scale-residual":
            run_missing(plan, plan_path, workers)
        else:
            run_shared_norad(plan, plan_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "run"), required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--parent", type=Path, action="append", default=[])
    parser.add_argument(
        "--successor-output-root",
        type=Path,
        help="discover sealed coarse/refined joint-rate parents from this output root",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--models", default=",".join(MODEL_NAMES))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.mode == "plan":
        if args.manifest is None or args.cache_root is None:
            raise ValueError("planning requires --manifest and --cache-root")
        parents = args.parent
        if args.successor_output_root is not None:
            if parents:
                raise ValueError("use either --parent or --successor-output-root")
            parents = discover_parents(args.successor_output_root)
        plan = build_plan(args.manifest, args.cache_root, parents, args.output_root)
        print(
            json.dumps(
                {
                    "sessions": len(plan["session_ids"]),
                    "parents": len(plan["parents"]),
                    "output": str(args.output_root / "run-plan.json"),
                },
                sort_keys=True,
            )
        )
        return
    models = [item for item in args.models.split(",") if item]
    execute(args.output_root / "run-plan.json", models, args.workers)


if __name__ == "__main__":
    main()
