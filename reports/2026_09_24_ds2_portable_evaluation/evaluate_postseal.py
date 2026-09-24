#!/usr/bin/env python3
"""Evaluate sealed DS2 position estimates against the external reference."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    candidates = [path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256")]
    if not any(
        seal.is_file() and seal.read_text().strip() == hashlib.sha256(path.read_bytes()).hexdigest()
        for seal in candidates
    ):
        raise ValueError(f"unsealed inference artifact: {path}")
    value = json.loads(path.read_text())
    if value.get("reference_coordinate_present") is not False:
        raise ValueError(f"inference contains or fails to reject reference coordinate: {path}")
    if value.get("reference_used_for_fit") is not False:
        raise ValueError(f"inference does not attest reference-free selection: {path}")
    return value


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    radius = 6371.0088
    lat1, lat2 = map(math.radians, (left[0], right[0]))
    dlat = lat2 - lat1
    dlon = math.radians(right[1] - left[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def method_label(task_id: str) -> str:
    return task_id.rsplit("__", 1)[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--output", type=Path, default=HERE / "evaluation.json")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = []
    inference_bindings = []
    for task in plan["tasks"]:
        path = Path(task["output_path"])
        result = sealed(path)
        point = result["estimated_position"]
        error = haversine_km(
            (float(point["latitude_deg"]), float(point["longitude_deg"])), REFERENCE
        )
        objective = result["rf_objective"]
        value = objective.get("selection_value", objective.get("value"))
        gate = result.get("exact_sgp4_winner_gate")
        timing = result.get("fitted_parameters", {}).get("timing", {})
        if not timing:
            timing = {"global_tau_s": result.get("global_tau_s")}
        rows.append(
            {
                "task_id": task["task_id"],
                "scope": (
                    "single"
                    if task["task_id"].startswith("single__")
                    else "joint-all20-coarse"
                ),
                "method": method_label(task["task_id"]),
                "session_count": len(task["session_ids"]),
                "latitude_deg": float(point["latitude_deg"]),
                "longitude_deg": float(point["longitude_deg"]),
                "postseal_error_km": error,
                "rf_objective": float(value),
                "global_tau_s": timing.get("global_tau_s"),
                "exact_gate_passed": gate.get("passed") if gate else None,
                "exact_gate_maximum_absolute_hz": gate.get("maximum_absolute_hz") if gate else None,
                "elapsed_s": float(result["elapsed_s"]),
            }
        )
        inference_bindings.append({"task_id": task["task_id"], "sha256": digest(path)})
    refinement_path = HERE / "refinement-index.json"
    refinement = sealed(refinement_path)
    for model in refinement["models"]:
        path = Path(model["final_artifact"])
        result = sealed(path)
        point = result["estimated_position"]
        error = haversine_km(
            (float(point["latitude_deg"]), float(point["longitude_deg"])), REFERENCE
        )
        objective = result["rf_objective"]
        objective_value = objective.get("selection_value", objective.get("value"))
        gate = result.get("exact_sgp4_winner_gate")
        timing = result.get("fitted_parameters", {}).get("timing", {})
        if not timing:
            timing = {"global_tau_s": result.get("global_tau_s")}
        rows.append(
            {
                "task_id": result["task_id"],
                "scope": "joint-all20-refined",
                "method": model["method"],
                "session_count": len(result["session_ids"]),
                "latitude_deg": float(point["latitude_deg"]),
                "longitude_deg": float(point["longitude_deg"]),
                "postseal_error_km": error,
                "rf_objective": float(objective_value),
                "global_tau_s": timing.get("global_tau_s"),
                "exact_gate_passed": gate.get("passed") if gate else None,
                "exact_gate_maximum_absolute_hz": (
                    gate.get("maximum_absolute_hz") if gate else None
                ),
                "elapsed_s": float(result["elapsed_s"]),
            }
        )
        inference_bindings.append({"task_id": result["task_id"], "sha256": digest(path)})
    fine_path = HERE / "fine-refinement-index.json"
    fine = sealed(fine_path)
    for model in fine["models"]:
        path = Path(model["final_artifact"])
        result = sealed(path)
        point = result["estimated_position"]
        error = haversine_km(
            (float(point["latitude_deg"]), float(point["longitude_deg"])), REFERENCE
        )
        objective = result["rf_objective"]
        objective_value = objective.get("selection_value", objective.get("value"))
        gate = result.get("exact_sgp4_winner_gate")
        timing = result.get("fitted_parameters", {}).get("timing", {})
        if not timing:
            timing = {"global_tau_s": result.get("global_tau_s")}
        rows.append(
            {
                "task_id": result["task_id"],
                "scope": "joint-all20-fine",
                "method": model["method"],
                "session_count": len(result["session_ids"]),
                "latitude_deg": float(point["latitude_deg"]),
                "longitude_deg": float(point["longitude_deg"]),
                "postseal_error_km": error,
                "rf_objective": float(objective_value),
                "global_tau_s": timing.get("global_tau_s"),
                "exact_gate_passed": gate.get("passed") if gate else None,
                "exact_gate_maximum_absolute_hz": (
                    gate.get("maximum_absolute_hz") if gate else None
                ),
                "elapsed_s": float(result["elapsed_s"]),
            }
        )
        inference_bindings.append({"task_id": result["task_id"], "sha256": digest(path)})
    grouped: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["scope"] == "single":
            grouped[row["method"]].append(row["postseal_error_km"])
    summaries = []
    for method, values in sorted(grouped.items()):
        summaries.append(
            {
                "method": method,
                "count": len(values),
                "minimum_error_km": min(values),
                "p25_error_km": percentile(values, 0.25),
                "median_error_km": percentile(values, 0.5),
                "p75_error_km": percentile(values, 0.75),
                "maximum_error_km": max(values),
                "sub_10km_count": sum(value < 10 for value in values),
                "sub_1km_count": sum(value < 1 for value in values),
            }
        )
    document = {
        "schema": "ds2-portable-postseal-evaluation/v1",
        "development_evaluation": True,
        "reference_coordinate": {
            "latitude_deg": REFERENCE[0],
            "longitude_deg": REFERENCE[1],
            "role": "introduced only after every inference artifact was sealed",
        },
        "rows": rows,
        "single_scan_summaries": summaries,
        "coarse_joint_rows": [
            row for row in rows if row["scope"] == "joint-all20-coarse"
        ],
        "refined_joint_rows": [
            row for row in rows if row["scope"] == "joint-all20-refined"
        ],
        "joint_rows": [row for row in rows if row["scope"] == "joint-all20-fine"],
        "bindings": {
            "plan": digest(args.plan),
            "refinement_index": digest(refinement_path),
            "fine_refinement_index": digest(fine_path),
            "inference": inference_bindings,
        },
    }
    content = canonical(document)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    with (HERE / "comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(canonical({"rows": len(rows), "single_methods": len(summaries)}), end="")


if __name__ == "__main__":
    main()
