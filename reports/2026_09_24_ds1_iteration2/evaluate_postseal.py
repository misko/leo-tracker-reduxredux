#!/usr/bin/env python3
"""Evaluate sealed DS1 iteration-2 results without influencing inference.

The evaluator verifies the frozen manifest, every sealed stage-1 source, and
every expected iteration-2 output before it introduces the Sausalito reference.
It is deliberately separate from both the scheduler and inference runners.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
TRAIN_ROOT = HERE.parent / "2026_09_24_ds1_train_full"
MANIFEST_SCHEMA = "ds1-iteration2-local-refinement-manifest/v1"
STAGE1_MANIFEST_SCHEMA = "ds1-train-one-hour-benchmark-manifest/v1"
RESULT_SCHEMA = "ds1-train-full-inference-result/v1"
REFERENCE = (37.84903264307456, -122.4856541910174)
FORBIDDEN_KEYS = frozenset(
    {
        "reference_coordinate",
        "truth_coordinate",
        "ground_truth_coordinate",
        "reference_error_km",
        "horizontal_error_km",
        "horizontal_error_m",
    }
)
METHODS = {"global_time", "per_scan_time"}
LEVELS = [6.25, 3.125, 1.5625, 0.78125, 0.390625]
CSV_COLUMNS = [
    "task_id",
    "status",
    "status_reason",
    "method",
    "case_id",
    "group_id",
    "prior_name",
    "scan_count",
    "stage1_task_id",
    "stage1_artifact_sha256",
    "artifact_path",
    "artifact_sha256",
    "seed_latitude_deg",
    "seed_longitude_deg",
    "final_latitude_deg",
    "final_longitude_deg",
    "seed_to_final_displacement_km",
    "reference_error_km",
    "stage1_rf_objective_value",
    "rf_objective_name",
    "rf_objective_value",
    "rf_objective_change",
    "elapsed_s",
    "peak_rss_kib",
    "timing_nuisance_count",
    "timing_nuisance_min_s",
    "timing_nuisance_median_s",
    "timing_nuisance_max_s",
    "tau_grid_s_json",
    "timing_boundary_hit",
    "geographic_boundary_hit",
    "geographic_interior",
    "selected_east_km",
    "selected_north_km",
    "prior_final_separation_km",
    "prior_converged_within_final_grid_km",
    "timing_parameters_json",
    "grid_diagnostics_json",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload)
    temporary.replace(path)


def sealed_json(path: Path) -> dict[str, Any]:
    seal = path.with_suffix(".sha256")
    if not path.is_file():
        raise ValueError(f"missing sealed input: {path}")
    if not seal.is_file():
        raise ValueError(f"missing input seal: {path}")
    recorded = seal.read_text().strip().split(maxsplit=1)[0].removeprefix("sha256:")
    if recorded != digest(path):
        raise ValueError(f"input seal mismatch: {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid sealed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"sealed JSON object required: {path}")
    return value


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*left, *right))
    value = math.sin((lat2 - lat1) / 2) ** 2
    value += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def finite(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"missing or non-finite {label}")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} outside permitted range")
    return float(value)


def contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_KEYS.intersection(value)) or any(
            contains_forbidden(item) for item in value.values()
        )
    return isinstance(value, list) and any(contains_forbidden(item) for item in value)


def coordinate(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} coordinate is absent")
    return (
        finite(value.get("latitude_deg"), f"{label} latitude", -90.0, 90.0),
        finite(value.get("longitude_deg"), f"{label} longitude", -180.0, 180.0),
    )


def objective_value(result: dict[str, Any]) -> tuple[str | None, float | None]:
    objective = result.get("rf_objective")
    if not isinstance(objective, dict):
        return None, None
    name = objective.get("name")
    if not isinstance(name, str):
        name = "selection_value" if "selection_value" in objective else None
    for key in ("selection_value", "full_observation_capped_loss", "value"):
        value = objective.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return name, float(value)
    return name, None


def timing_values(value: Any) -> list[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)] if math.isfinite(value) else []
    if isinstance(value, dict):
        return [number for item in value.values() for number in timing_values(item)]
    if isinstance(value, list):
        return [number for item in value for number in timing_values(item)]
    return []


def timing_parameters(result: dict[str, Any]) -> tuple[dict[str, Any], list[float]]:
    fitted = result.get("fitted_parameters")
    if isinstance(fitted, dict) and isinstance(fitted.get("timing"), dict):
        timing = fitted["timing"]
    elif isinstance(fitted, dict):
        timing = {
            key: value
            for key, value in fitted.items()
            if "tau" in key.lower() or "time" in key.lower()
        }
    else:
        selected = result.get("selected")
        timing = selected.get("parameters", {}) if isinstance(selected, dict) else {}
    return timing if isinstance(timing, dict) else {}, timing_values(timing)


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unexpected iteration-2 manifest schema")
    if manifest.get("reference_coordinate_in_manifest") is not False:
        raise ValueError("iteration-2 manifest contains a reference coordinate")
    if manifest.get("position_evaluation") != "post_seal_external_only":
        raise ValueError("iteration-2 manifest evaluation policy changed")
    if manifest.get("partitions_permitted") != ["train"]:
        raise ValueError("iteration-2 manifest is not TRAIN-only")
    search = manifest.get("local_search")
    if (
        not isinstance(search, dict)
        or search.get("radius_km") != 25.0
        or search.get("levels_km") != LEVELS
    ):
        raise ValueError("iteration-2 local geographic contract changed")
    if search.get("timing_policy") != "tau zero plus each sealed stage-1 winner +/-0.25 seconds":
        raise ValueError("iteration-2 timing contract changed")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 16 or manifest.get("task_count") != 16:
        raise ValueError("iteration-2 task count changed")
    ids: set[str] = set()
    for task in tasks:
        if (
            not isinstance(task, dict)
            or not isinstance(task.get("task_id"), str)
            or task["task_id"] in ids
        ):
            raise ValueError("invalid or duplicate iteration-2 task")
        ids.add(task["task_id"])
        if task.get("partition") != "train" or task.get("method") not in METHODS:
            raise ValueError(f"iteration-2 task escaped its permitted arm: {task['task_id']}")
        if task.get("stage") != "stage2_local_geographic_refinement":
            raise ValueError(f"iteration-2 stage changed: {task['task_id']}")
        options = task.get("options")
        if (
            not isinstance(options, dict)
            or options.get("observation_policy") != "all_qualified_observations"
        ):
            raise ValueError(f"iteration-2 observation policy changed: {task['task_id']}")
        if (
            options.get("within_track_holdout") != "forbidden"
            or options.get("geographic_levels_km") != LEVELS
        ):
            raise ValueError(f"iteration-2 search grid changed: {task['task_id']}")
        tau_grid = options.get("tau_grid_s")
        if (
            not isinstance(tau_grid, list)
            or len(tau_grid) != 4
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in tau_grid
            )
            or 0.0 not in tau_grid
        ):
            raise ValueError(f"iteration-2 tau stencil changed: {task['task_id']}")
        coordinate(task.get("initial_geographic_seed"), "iteration-2 seed")
        if not isinstance(task.get("output_path"), str):
            raise ValueError(f"iteration-2 output path missing: {task['task_id']}")
    return sorted(tasks, key=lambda item: item["task_id"])


def validate_stage1(manifest: dict[str, Any], task: dict[str, Any]) -> tuple[dict[str, Any], float]:
    stage1 = manifest.get("stage1")
    if not isinstance(stage1, dict) or not isinstance(stage1.get("manifest_path"), str):
        raise ValueError("iteration-2 stage-1 provenance is absent")
    source_manifest_path = Path(stage1["manifest_path"])
    source_manifest = sealed_json(source_manifest_path)
    if source_manifest.get("schema") != STAGE1_MANIFEST_SCHEMA:
        raise ValueError("unexpected stage-1 manifest schema")
    if source_manifest.get("reference_coordinate_in_manifest") is not False:
        raise ValueError("stage-1 manifest contains a reference coordinate")
    if source_manifest.get("partitions_permitted") != ["train"]:
        raise ValueError("stage-1 manifest is not TRAIN-only")
    if stage1.get("manifest_sha256") != f"sha256:{digest(source_manifest_path)}":
        raise ValueError("stage-1 manifest digest changed")
    source = task.get("stage1_source")
    if not isinstance(source, dict) or not isinstance(source.get("artifact_path"), str):
        raise ValueError(f"stage-1 source absent: {task['task_id']}")
    artifact = Path(source["artifact_path"])
    source_tasks = source_manifest.get("tasks")
    if not isinstance(source_tasks, list):
        raise ValueError("stage-1 manifest tasks are absent")
    source_task = next(
        (item for item in source_tasks if item.get("task_id") == source.get("task_id")), None
    )
    if not isinstance(source_task, dict) or source_task.get("method") != "global_time":
        raise ValueError(f"stage-1 source task contract mismatch: {task['task_id']}")
    if (
        source_task.get("partition") != "train"
        or source_task.get("case_id") != task.get("case_id")
        or source_task.get("scan_count") != task.get("scan_count")
        or source_task.get("prior", {}).get("name") != task.get("prior", {}).get("name")
    ):
        raise ValueError(f"stage-1 source task does not match iteration-2 arm: {task['task_id']}")
    expected_artifact = (source_manifest_path.parent / source_task.get("output_path", "")).resolve()
    if artifact.resolve() != expected_artifact:
        raise ValueError(f"stage-1 source path does not match its manifest task: {task['task_id']}")
    listed = stage1.get("artifacts")
    listed_source = next(
        (item for item in listed if item.get("task_id") == source.get("task_id"))
        if isinstance(listed, list)
        else None,
    )
    if not isinstance(listed_source, dict) or listed_source.get("sha256") != source.get(
        "artifact_sha256"
    ):
        raise ValueError(f"stage-1 source is not a sealed manifest binding: {task['task_id']}")
    result = sealed_json(artifact)
    if source.get("artifact_sha256") != f"sha256:{digest(artifact)}":
        raise ValueError(f"stage-1 source digest changed: {task['task_id']}")
    if result.get("schema") != RESULT_SCHEMA or result.get("complete") is not True:
        raise ValueError(f"invalid stage-1 result: {task['task_id']}")
    if result.get("task_id") != source.get("task_id") or result.get("partition") != "train":
        raise ValueError(f"stage-1 source contract mismatch: {task['task_id']}")
    if result.get("reference_used_for_fit") is not False or contains_forbidden(result):
        raise ValueError(f"stage-1 source contains reference data: {task['task_id']}")
    use = result.get("observation_use")
    if (
        not isinstance(use, dict)
        or use.get("policy") != "all_qualified_observations"
        or use.get("heldout_observation_count") != 0
    ):
        raise ValueError(f"stage-1 source is not full-observation: {task['task_id']}")
    if coordinate(result.get("estimated_position"), "stage-1 estimate") != coordinate(
        task.get("initial_geographic_seed"), "iteration-2 seed"
    ):
        raise ValueError(f"stage-1 seed mismatch: {task['task_id']}")
    _, value = objective_value(result)
    if value is None:
        raise ValueError(f"stage-1 source lacks RF objective: {task['task_id']}")
    selected = result.get("selected")
    parameters = selected.get("parameters") if isinstance(selected, dict) else None
    stage1_tau = parameters.get("global_tau_s") if isinstance(parameters, dict) else None
    stage1_tau = finite(stage1_tau, "stage-1 selected timing", -10.0, 10.0)
    expected_tau_grid = sorted({0.0, stage1_tau - 0.25, stage1_tau, stage1_tau + 0.25})
    if task.get("options", {}).get("tau_grid_s") != expected_tau_grid:
        raise ValueError(f"iteration-2 tau stencil does not bind stage-1 timing: {task['task_id']}")
    return result, value


def validate_result(task: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("schema") != RESULT_SCHEMA or result.get("complete") is not True:
        raise ValueError("unexpected or incomplete result")
    if result.get("task_id") != task["task_id"] or result.get("partition") != "train":
        raise ValueError("result task or partition mismatch")
    if result.get("reference_used_for_fit") is not False or contains_forbidden(result):
        raise ValueError("result contains reference data")
    use = result.get("observation_use")
    if not isinstance(use, dict) or use.get("policy") != "all_qualified_observations":
        raise ValueError("result lacks full-observation attestation")
    if use.get("heldout_observation_count") != 0:
        raise ValueError("result used held-out observations")
    coordinate(result.get("estimated_position"), "estimated")


def artifact_status(path: Path, task: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    if not path.is_file():
        return "missing", "artifact JSON is absent", None
    seal = path.with_suffix(".sha256")
    if not seal.is_file():
        return "invalid_seal", "artifact SHA-256 seal is absent", None
    recorded = seal.read_text().strip().split(maxsplit=1)[0].removeprefix("sha256:")
    if recorded != digest(path):
        return "invalid_seal", "artifact SHA-256 seal does not match", None
    try:
        result = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "invalid_json", "sealed bytes are not valid JSON", None
    if not isinstance(result, dict):
        return "invalid_result", "sealed JSON is not an object", None
    try:
        validate_result(task, result)
    except ValueError as exc:
        return "invalid_result", str(exc), None
    return "completed", "", result


def diagnostic(
    result: dict[str, Any], timing: list[float], tau_grid: list[float]
) -> dict[str, Any]:
    selected = result.get("selected") if isinstance(result.get("selected"), dict) else {}
    east = selected.get("east_km")
    north = selected.get("north_km")
    east = float(east) if isinstance(east, (int, float)) and not isinstance(east, bool) else None
    north = (
        float(north) if isinstance(north, (int, float)) and not isinstance(north, bool) else None
    )
    geographic_boundary = bool(
        (east is not None and abs(abs(east) - 25.0) < 1e-9)
        or (north is not None and abs(abs(north) - 25.0) < 1e-9)
    )
    timing_boundary = any(
        abs(value - endpoint) < 1e-9
        for value in timing
        for endpoint in (min(tau_grid), max(tau_grid))
    )
    convergence = result.get("convergence")
    trace = convergence.get("geographic_trace") if isinstance(convergence, dict) else None
    return {
        "selected_east_km": east,
        "selected_north_km": north,
        "geographic_boundary_hit": geographic_boundary,
        "geographic_interior": not geographic_boundary
        if east is not None and north is not None
        else None,
        "timing_boundary_hit": timing_boundary,
        "tau_grid_s": tau_grid,
        "geographic_trace_count": len(trace) if isinstance(trace, list) else None,
        "reported_geographic_levels_km": convergence.get("geographic_levels_km")
        if isinstance(convergence, dict)
        else None,
        "reported_timing_grid_s": convergence.get("timing_grid_s")
        if isinstance(convergence, dict)
        else None,
    }


def evaluate(manifest_path: Path, train_root: Path = TRAIN_ROOT) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = sealed_json(manifest_path)
    tasks = validate_manifest(manifest)
    train_root = train_root.resolve()
    artifact_root = (train_root / "artifacts").resolve()
    rows: list[dict[str, Any]] = []
    for task in tasks:
        _, stage1_objective = validate_stage1(manifest, task)
        artifact = (train_root / task["output_path"]).resolve()
        if not artifact.is_relative_to(artifact_root):
            raise ValueError(f"iteration-2 output escapes artifacts: {task['task_id']}")
        status, reason, result = artifact_status(artifact, task)
        seed = coordinate(task["initial_geographic_seed"], "iteration-2 seed")
        tau_grid = task["options"]["tau_grid_s"]
        row: dict[str, Any] = {
            "task_id": task["task_id"],
            "status": status,
            "status_reason": reason,
            "method": task["method"],
            "case_id": task["case_id"],
            "group_id": task["group_id"],
            "prior_name": task["prior"]["name"],
            "scan_count": task["scan_count"],
            "stage1_task_id": task["stage1_source"]["task_id"],
            "stage1_artifact_sha256": task["stage1_source"]["artifact_sha256"],
            "artifact_path": str(artifact.relative_to(train_root)),
            "artifact_sha256": digest(artifact) if result is not None else None,
            "seed_latitude_deg": seed[0],
            "seed_longitude_deg": seed[1],
            "final_latitude_deg": None,
            "final_longitude_deg": None,
            "seed_to_final_displacement_km": None,
            "reference_error_km": None,
            "stage1_rf_objective_value": stage1_objective,
            "rf_objective_name": None,
            "rf_objective_value": None,
            "rf_objective_change": None,
            "elapsed_s": None,
            "peak_rss_kib": None,
            "timing_nuisance_count": 0,
            "timing_nuisance_min_s": None,
            "timing_nuisance_median_s": None,
            "timing_nuisance_max_s": None,
            "tau_grid_s": tau_grid,
            "timing_parameters": {},
            "grid_diagnostics": {},
            "prior_final_separation_km": None,
            "prior_converged_within_final_grid_km": None,
        }
        if result is not None:
            final = coordinate(result["estimated_position"], "final")
            timing, values = timing_parameters(result)
            objective_name, objective = objective_value(result)
            row.update(
                {
                    "final_latitude_deg": final[0],
                    "final_longitude_deg": final[1],
                    "seed_to_final_displacement_km": haversine_km(seed, final),
                    "rf_objective_name": objective_name,
                    "rf_objective_value": objective,
                    "rf_objective_change": objective - stage1_objective
                    if objective is not None
                    else None,
                    "elapsed_s": result.get("elapsed_s"),
                    "peak_rss_kib": result.get("peak_rss_kib"),
                    "timing_nuisance_count": len(values),
                    "timing_nuisance_min_s": min(values) if values else None,
                    "timing_nuisance_median_s": median(values) if values else None,
                    "timing_nuisance_max_s": max(values) if values else None,
                    "timing_parameters": timing,
                    "grid_diagnostics": diagnostic(result, values, tau_grid),
                }
            )
        rows.append(row)
    complete = [row for row in rows if row["status"] == "completed"]
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in complete:
        by_pair.setdefault((row["case_id"], row["method"]), []).append(row)
    convergence: list[dict[str, Any]] = []
    for (case_id, method), pair in sorted(by_pair.items()):
        if len(pair) != 2:
            continue
        distance = haversine_km(
            (pair[0]["final_latitude_deg"], pair[0]["final_longitude_deg"]),
            (pair[1]["final_latitude_deg"], pair[1]["final_longitude_deg"]),
        )
        converged = distance <= LEVELS[-1]
        convergence.append(
            {
                "case_id": case_id,
                "method": method,
                "final_separation_km": distance,
                "converged_within_final_grid_km": converged,
            }
        )
        for row in pair:
            row["prior_final_separation_km"] = distance
            row["prior_converged_within_final_grid_km"] = converged
    counts = Counter(row["status"] for row in rows)
    all_valid = len(complete) == len(rows)
    if all_valid:
        for row in rows:
            row["reference_error_km"] = haversine_km(
                (row["final_latitude_deg"], row["final_longitude_deg"]), REFERENCE
            )
    return {
        "schema": "ds1-iteration2-post-seal-evaluation/v1",
        "reference_evaluation": {
            "introduced": all_valid,
            "role": "evaluation only after every expected result seal and contract validated",
            "coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]}
            if all_valid
            else None,
            "withheld_reason": None
            if all_valid
            else "one or more expected iteration-2 results are missing or invalid",
        },
        "manifest": {
            "path": str(manifest_path),
            "sha256": f"sha256:{digest(manifest_path)}",
            "task_count": len(tasks),
        },
        "local_grid": {
            "radius_km": 25.0,
            "levels_km": LEVELS,
            "timing_policy": "tau zero plus each sealed stage-1 winner +/-0.25 seconds",
        },
        "status_counts": dict(sorted(counts.items())),
        "completed_task_count": len(complete),
        "missing_or_failed_task_count": len(rows) - len(complete),
        "prior_convergence": convergence,
        "rows": rows,
    }


def csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        flat = dict(row)
        flat["tau_grid_s_json"] = json.dumps(flat.pop("tau_grid_s"))
        flat["timing_parameters_json"] = json.dumps(flat.pop("timing_parameters"), sort_keys=True)
        flat["grid_diagnostics_json"] = json.dumps(flat.pop("grid_diagnostics"), sort_keys=True)
        output.append({column: flat.get(column) for column in CSV_COLUMNS})
    return output


def render(evaluation: dict[str, Any], path: Path) -> None:
    rows = evaluation["rows"]
    complete = [row for row in rows if row["status"] == "completed"]
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), layout="constrained")
    error_axis, displacement_axis, objective_axis, timing_axis = axes.flat
    methods = sorted(METHODS)
    colors = {"sacramento": "#0072B2", "reno": "#D55E00"}
    for index, row in enumerate(complete):
        color = colors.get(row["prior_name"], "#555555")
        marker = "o" if row["scan_count"] == 1 else "s"
        if row["reference_error_km"] is not None:
            error_axis.scatter(
                methods.index(row["method"]),
                row["reference_error_km"],
                color=color,
                marker=marker,
                s=55,
            )
        displacement_axis.scatter(
            methods.index(row["method"]),
            row["seed_to_final_displacement_km"],
            color=color,
            marker=marker,
            s=55,
        )
        if row["rf_objective_value"] is not None:
            objective_axis.scatter(
                row["stage1_rf_objective_value"],
                row["rf_objective_value"],
                color=color,
                marker=marker,
                s=55,
            )
        if row["timing_nuisance_count"]:
            timing_axis.vlines(
                index, row["timing_nuisance_min_s"], row["timing_nuisance_max_s"], color=color
            )
            timing_axis.scatter(
                index, row["timing_nuisance_median_s"], color=color, marker=marker, s=45
            )
    error_axis.set(title="Post-seal error", ylabel="great-circle error (km)")
    displacement_axis.set(title="Seed-to-final displacement", ylabel="distance (km)")
    for axis in (error_axis, displacement_axis):
        axis.set_xticks(range(len(methods)), methods, rotation=25, ha="right")
        axis.grid(axis="y", alpha=0.3)
    objective_axis.set(
        title="Stage-1 versus iteration-2 RF objective",
        xlabel="sealed stage-1 objective",
        ylabel="iteration-2 objective",
    )
    objective_axis.grid(alpha=0.3)
    timing_axis.axhline(0.0, color="black", linewidth=0.8)
    timing_axis.set(title="Timing nuisance range", ylabel="seconds")
    timing_axis.grid(axis="y", alpha=0.3)
    if not complete:
        for axis in axes.flat:
            axis.text(
                0.5,
                0.5,
                "No complete sealed iteration-2 results",
                transform=axis.transAxes,
                ha="center",
            )
    fig.suptitle(f"DS1 iteration-2 post-seal evaluation: {len(complete)}/{len(rows)} complete")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_outputs(evaluation: dict[str, Any], output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    names = {
        "json": output_dir / "iteration2-post-seal-evaluation.json",
        "csv": output_dir / "iteration2-post-seal-evaluation.csv",
        "png": output_dir / "iteration2-post-seal-evaluation.png",
    }
    write_atomic(names["json"], canonical_json(evaluation))
    write_atomic(
        names["json"].with_name(names["json"].name + ".sha256"), digest(names["json"]) + "\n"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with names["csv"].open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows(evaluation["rows"]))
    write_atomic(names["csv"].with_name(names["csv"].name + ".sha256"), digest(names["csv"]) + "\n")
    render(evaluation, names["png"])
    write_atomic(names["png"].with_name(names["png"].name + ".sha256"), digest(names["png"]) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=HERE / "iteration2-inference-manifest.json"
    )
    parser.add_argument("--train-root", type=Path, default=TRAIN_ROOT)
    parser.add_argument("--output-dir", type=Path, default=HERE / "post-seal-evaluation")
    args = parser.parse_args()
    if args.output_dir.resolve().is_relative_to(args.train_root.resolve() / "artifacts"):
        raise ValueError("evaluation outputs must not be written among inference artifacts")
    evaluation = evaluate(args.manifest, args.train_root)
    write_outputs(evaluation, args.output_dir)
    print(
        json.dumps(
            {
                key: evaluation[key]
                for key in ("completed_task_count", "missing_or_failed_task_count", "status_counts")
            }
        )
    )


if __name__ == "__main__":
    main()
