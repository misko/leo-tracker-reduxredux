#!/usr/bin/env python3
"""Render the sealed DS1 one-hour inference matrix after inference completes.

This evaluator is deliberately outside the runners.  It first accepts only
sealed, complete TRAIN inference results and only then adds the Sausalito
coordinate to calculate evaluation-only great-circle errors.
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
MANIFEST_SCHEMA = "ds1-train-one-hour-benchmark-manifest/v1"
RESULT_SCHEMA = "ds1-train-full-inference-result/v1"
REFERENCE = (37.84903264307456, -122.4856541910174)
GRID_SCREEN_LABEL = (
    "12.5 km final geographic grid screen; post-seal errors are not sub-grid accuracy claims."
)
FORBIDDEN_RESULT_KEYS = {
    "reference_coordinate",
    "truth_coordinate",
    "ground_truth_coordinate",
    "reference_error_km",
}
CSV_COLUMNS = [
    "task_id",
    "status",
    "status_reason",
    "stage",
    "tier",
    "method",
    "group_id",
    "case_id",
    "prior_name",
    "scan_count",
    "grid_screen_km",
    "artifact_path",
    "artifact_sha256",
    "estimated_latitude_deg",
    "estimated_longitude_deg",
    "reference_error_km",
    "rf_objective_name",
    "rf_objective_value",
    "rf_objective_detail_json",
    "timing_nuisance_count",
    "timing_nuisance_min_s",
    "timing_nuisance_median_s",
    "timing_nuisance_max_s",
    "timing_nuisance_parameters_json",
    "nuisance_parameters_json",
    "fitted_parameter_keys_json",
    "fitted_parameters_json",
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
    """Read a JSON document only after its sibling SHA-256 seal verifies."""
    seal = path.with_suffix(".sha256")
    if not path.is_file():
        raise ValueError(f"missing artifact: {path}")
    if not seal.is_file():
        raise ValueError(f"missing SHA-256 seal: {path}")
    recorded = seal.read_text().strip().removeprefix("sha256:")
    if recorded != digest(path):
        raise ValueError(f"SHA-256 seal mismatch: {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*left, *right))
    haversine = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_RESULT_KEYS.intersection(value)) or any(
            _contains_forbidden_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _finite_coordinate(value: Any, name: str, lower: float, upper: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"missing or non-finite {name}")
    if not lower <= value <= upper:
        raise ValueError(f"{name} outside geographic range")
    return float(value)


def validate_result(task: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("schema") != RESULT_SCHEMA:
        raise ValueError("unexpected result schema")
    if result.get("complete") is not True:
        raise ValueError("result is not complete")
    if result.get("task_id") != task["task_id"]:
        raise ValueError("result task ID mismatch")
    if result.get("partition") != "train":
        raise ValueError("result is not TRAIN-only")
    if result.get("reference_used_for_fit") is not False:
        raise ValueError("result does not attest reference exclusion")
    if _contains_forbidden_key(result):
        raise ValueError("result contains post-seal reference data")
    use = result.get("observation_use")
    if not isinstance(use, dict) or use.get("policy") != "all_qualified_observations":
        raise ValueError("result lacks full-observation attestation")
    if use.get("heldout_observation_count") != 0:
        raise ValueError("result used held-out observations")
    estimate = result.get("estimated_position")
    if not isinstance(estimate, dict):
        raise ValueError("result lacks estimated position")
    _finite_coordinate(estimate.get("latitude_deg"), "estimated latitude", -90.0, 90.0)
    _finite_coordinate(estimate.get("longitude_deg"), "estimated longitude", -180.0, 180.0)


def _artifact_status(path: Path, task: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    """Classify an expected output without inspecting unsealed result bytes."""
    seal = path.with_suffix(".sha256")
    if not path.is_file():
        return "missing", "artifact JSON is absent", None
    if not seal.is_file():
        return "invalid_seal", "artifact SHA-256 seal is absent", None
    if seal.read_text().strip().removeprefix("sha256:") != digest(path):
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


def _timing_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if math.isfinite(value) else []
    if isinstance(value, dict):
        return [number for item in value.values() for number in _timing_values(item)]
    if isinstance(value, list):
        return [number for item in value for number in _timing_values(item)]
    return []


def timing_nuisance(result: dict[str, Any]) -> tuple[dict[str, Any], list[float]]:
    fitted = result.get("fitted_parameters")
    selected = result.get("selected")
    timing: dict[str, Any] = {}
    if isinstance(fitted, dict) and isinstance(fitted.get("timing"), dict):
        timing = fitted["timing"]
    elif isinstance(fitted, dict):
        timing = {
            key: value
            for key, value in fitted.items()
            if any(token in key.lower() for token in ("tau", "time"))
        }
    elif isinstance(selected, dict) and isinstance(selected.get("parameters"), dict):
        timing = selected["parameters"]
    return timing, _timing_values(timing)


def compact_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Retain nuisance summaries without copying per-track association internals."""
    summary: dict[str, Any] = {}
    for name, value in parameters.items():
        values = _timing_values(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            summary[name] = float(value)
        elif values:
            summary[name] = {
                "value_count": len(values),
                "minimum": min(values),
                "median": median(values),
                "maximum": max(values),
            }
        else:
            summary[name] = {"value_count": 0}
    return summary


def rf_objective(result: dict[str, Any]) -> tuple[str | None, float | None, dict[str, Any]]:
    objective = result.get("rf_objective")
    if not isinstance(objective, dict):
        return None, None, {}
    name = objective.get("name")
    if not isinstance(name, str):
        name = "selection_value" if "selection_value" in objective else None
    for key in ("selection_value", "full_observation_capped_loss", "value"):
        value = objective.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return name, float(value), objective
    return name, None, objective


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unexpected one-hour manifest schema")
    if manifest.get("reference_coordinate_in_manifest") is not False:
        raise ValueError("manifest must exclude the reference coordinate")
    if manifest.get("position_evaluation") != "post_seal_external_only":
        raise ValueError("manifest does not require post-seal evaluation")
    if manifest.get("partitions_permitted") != ["train"]:
        raise ValueError("manifest is not TRAIN-only")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("manifest tasks missing")
    if manifest.get("task_count") != len(tasks):
        raise ValueError("manifest task count mismatch")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict) or task.get("task_id") in ids:
            raise ValueError("manifest has invalid or duplicate task IDs")
        ids.add(task["task_id"])
        if task.get("partition") != "train" or task.get("scan_count") not in {1, 6}:
            raise ValueError("manifest task lies outside the one-hour TRAIN matrix")
        if task.get("options", {}).get("geographic_levels_km", [])[-1:] != [12.5]:
            raise ValueError("manifest task does not end at the fixed 12.5-km grid")
        if not isinstance(task.get("output_path"), str):
            raise ValueError("manifest task lacks output path")
    return sorted(tasks, key=lambda task: task["task_id"])


def evaluate(manifest_path: Path, report_root: Path) -> dict[str, Any]:
    manifest = sealed_json(manifest_path)
    tasks = validate_manifest(manifest)
    artifact_root = (report_root / "artifacts").resolve()
    rows: list[dict[str, Any]] = []
    for task in tasks:
        artifact = (report_root / task["output_path"]).resolve()
        if not artifact.is_relative_to(artifact_root):
            raise ValueError(f"artifact path escapes report artifacts: {task['task_id']}")
        status, reason, result = _artifact_status(artifact, task)
        row: dict[str, Any] = {
            "task_id": task["task_id"],
            "status": status,
            "status_reason": reason,
            "stage": task.get("stage"),
            "tier": task.get("tier"),
            "method": task.get("method"),
            "group_id": task.get("group_id"),
            "case_id": task.get("case_id"),
            "prior_name": task.get("prior", {}).get("name"),
            "scan_count": task.get("scan_count"),
            "grid_screen_km": 12.5,
            "artifact_path": str(artifact.relative_to(report_root.resolve())),
            "artifact_sha256": digest(artifact) if status == "completed" else None,
            "estimated_latitude_deg": None,
            "estimated_longitude_deg": None,
            "reference_error_km": None,
            "rf_objective_name": None,
            "rf_objective_value": None,
            "rf_objective_detail": {},
            "timing_nuisance_count": 0,
            "timing_nuisance_min_s": None,
            "timing_nuisance_median_s": None,
            "timing_nuisance_max_s": None,
            "timing_nuisance_parameters": {},
            "nuisance_parameters": {},
            "fitted_parameter_keys": [],
            "fitted_parameters": {},
        }
        if result is not None:
            estimate = result["estimated_position"]
            latitude = float(estimate["latitude_deg"])
            longitude = float(estimate["longitude_deg"])
            timing, timing_values = timing_nuisance(result)
            objective_name, objective_value, objective = rf_objective(result)
            fitted = result.get("fitted_parameters")
            fitted_keys = sorted(fitted) if isinstance(fitted, dict) else []
            nuisance = (
                {
                    key: value
                    for key, value in fitted.items()
                    if key not in {"receiver_position", "track_associations"}
                }
                if isinstance(fitted, dict)
                else {}
            )
            row.update(
                {
                    "estimated_latitude_deg": latitude,
                    "estimated_longitude_deg": longitude,
                    "rf_objective_name": objective_name,
                    "rf_objective_value": objective_value,
                    "rf_objective_detail": objective,
                    "timing_nuisance_count": len(timing_values),
                    "timing_nuisance_min_s": min(timing_values) if timing_values else None,
                    "timing_nuisance_median_s": median(timing_values) if timing_values else None,
                    "timing_nuisance_max_s": max(timing_values) if timing_values else None,
                    "timing_nuisance_parameters": compact_parameters(timing),
                    "nuisance_parameters": compact_parameters(nuisance),
                    "fitted_parameter_keys": fitted_keys,
                    "fitted_parameters": {
                        "available_keys": fitted_keys,
                        "nuisance_parameter_summary": compact_parameters(nuisance),
                        "omitted_detail": "per-track associations and CFO values",
                    },
                }
            )
        rows.append(row)
    # The reference is introduced here, after every accepted inference artifact
    # has been verified and rendered into an inference-only row.
    for row in rows:
        if row["status"] == "completed":
            row["reference_error_km"] = haversine_km(
                (row["estimated_latitude_deg"], row["estimated_longitude_deg"]), REFERENCE
            )
    counts = Counter(row["status"] for row in rows)
    return {
        "schema": "ds1-train-one-hour-post-seal-evaluation/v1",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "reference_role": "introduced only after sealed inference validation; evaluation only",
        "grid_screen_label": GRID_SCREEN_LABEL,
        "manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": digest(manifest_path),
            "task_count": len(tasks),
        },
        "status_counts": dict(sorted(counts.items())),
        "completed_task_count": counts["completed"],
        "missing_or_failed_task_count": len(rows) - counts["completed"],
        "rows": rows,
    }


def csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        flat = dict(row)
        for source, target in (
            ("rf_objective_detail", "rf_objective_detail_json"),
            ("timing_nuisance_parameters", "timing_nuisance_parameters_json"),
            ("nuisance_parameters", "nuisance_parameters_json"),
            ("fitted_parameter_keys", "fitted_parameter_keys_json"),
            ("fitted_parameters", "fitted_parameters_json"),
        ):
            flat[target] = json.dumps(flat.pop(source, {}), sort_keys=True)
        output.append({column: flat.get(column) for column in CSV_COLUMNS})
    return output


def _method_order(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row["method"]) for row in rows})


def render(rows: list[dict[str, Any]], path: Path) -> None:
    completed = [row for row in rows if row["status"] == "completed"]
    methods = _method_order(rows)
    priors = sorted({str(row["prior_name"]) for row in rows})
    colors = {prior: color for prior, color in zip(priors, ("#0072B2", "#D55E00"), strict=False)}
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), layout="constrained")
    for axis, scan_count in zip(axes[0], (1, 6), strict=True):
        values = [row for row in completed if row["scan_count"] == scan_count]
        for prior in priors:
            series = {row["method"]: row for row in values if row["prior_name"] == prior}
            x = [index for index, method in enumerate(methods) if method in series]
            y = [series[methods[index]]["reference_error_km"] for index in x]
            axis.scatter(x, y, label=prior, color=colors[prior], s=55)
        axis.set_title(f"{scan_count}-scan post-seal error")
        axis.set_ylabel("great-circle error (km)")
        axis.set_xticks(range(len(methods)), methods, rotation=45, ha="right", fontsize=8)
        axis.grid(axis="y", alpha=0.3)
        if values:
            axis.legend(title="prior")
        else:
            axis.text(0.5, 0.5, "No complete sealed tasks", transform=axis.transAxes, ha="center")

    objective_axis = axes[1, 0]
    for scan_count, marker in ((1, "o"), (6, "s")):
        values = [
            row
            for row in completed
            if row["scan_count"] == scan_count and row.get("rf_objective_value") is not None
        ]
        for prior in priors:
            series = [row for row in values if row["prior_name"] == prior]
            objective_axis.scatter(
                [row["rf_objective_value"] for row in series],
                [row["reference_error_km"] for row in series],
                marker=marker,
                color=colors[prior],
                label=f"{prior}, {scan_count} scan",
                s=52,
            )
    objective_axis.set_title("Runner-reported RF objective versus post-seal error")
    objective_axis.set_xlabel("RF objective selection value")
    objective_axis.set_ylabel("great-circle error (km)")
    objective_axis.grid(alpha=0.3)
    if objective_axis.collections:
        objective_axis.legend(fontsize=8)
    else:
        objective_axis.text(
            0.5,
            0.5,
            "No RF objective values",
            transform=objective_axis.transAxes,
            ha="center",
        )

    timing_axis = axes[1, 1]
    timing_rows = [row for row in completed if row.get("timing_nuisance_count", 0)]
    for index, row in enumerate(timing_rows):
        color = colors[str(row["prior_name"])]
        timing_axis.vlines(
            index,
            row["timing_nuisance_min_s"],
            row["timing_nuisance_max_s"],
            color=color,
        )
        timing_axis.scatter(
            index,
            row["timing_nuisance_median_s"],
            color=color,
            marker="o" if row["scan_count"] == 1 else "s",
        )
    timing_axis.axhline(0.0, color="black", linewidth=0.8)
    timing_axis.set_title("Timing nuisance range; marker = median")
    timing_axis.set_ylabel("fitted timing value (s)")
    timing_axis.set_xticks(
        range(len(timing_rows)),
        [row["method"] for row in timing_rows],
        rotation=45,
        ha="right",
        fontsize=8,
    )
    timing_axis.grid(axis="y", alpha=0.3)
    if not timing_rows:
        timing_axis.text(
            0.5,
            0.5,
            "No fitted timing nuisance parameters",
            transform=timing_axis.transAxes,
            ha="center",
        )
    fig.suptitle(
        f"DS1 one-hour post-seal matrix: {len(completed)}/{len(rows)} complete\n"
        f"{GRID_SCREEN_LABEL}",
        fontsize=13,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_outputs(evaluation: dict[str, Any], output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    json_path = output_dir / "one-hour-post-seal-evaluation.json"
    csv_path = output_dir / "one-hour-post-seal-evaluation.csv"
    png_path = output_dir / "one-hour-post-seal-evaluation.png"
    write_atomic(json_path, canonical_json(evaluation))
    write_atomic(json_path.with_name(json_path.name + ".sha256"), digest(json_path) + "\n")
    output_dir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows(evaluation["rows"]))
    write_atomic(csv_path.with_name(csv_path.name + ".sha256"), digest(csv_path) + "\n")
    render(evaluation["rows"], png_path)
    write_atomic(png_path.with_name(png_path.name + ".sha256"), digest(png_path) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=HERE / "one-hour-inference-manifest.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "post-seal-evaluation")
    args = parser.parse_args()
    report_root = HERE.resolve()
    if args.output_dir.resolve().is_relative_to(report_root / "artifacts"):
        raise ValueError("evaluation outputs must not be written among inference artifacts")
    evaluation = evaluate(args.manifest.resolve(), report_root)
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
