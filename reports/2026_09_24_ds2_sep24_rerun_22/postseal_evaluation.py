#!/usr/bin/env python3
"""Evaluate the sealed DS2-22 successor only after inference is complete."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXPECTED_PORTABLE_OUTPUTS = 116
PUBLISHED_DS2_20 = HERE.parent / "2026_09_24_ds2_portable_evaluation" / "evaluation.json"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_file() or not any(
        p.is_file() and p.read_text().strip() == actual
        for p in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    ):
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected an object: {path}")
    if any(
        value.get(k) is True
        for k in (
            "reference_coordinate_present",
            "reference_used_for_fit",
            "reference_used_for_inference",
            "truth_used_for_fit",
        )
    ):
        raise ValueError(f"inference is not reference-free: {path}")
    return value


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la, lb = map(math.radians, (a[0], b[0]))
    dlat, dlon = lb - la, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def point_row(
    result: dict[str, Any], scope: str, method: str, reference: tuple[float, float]
) -> dict[str, Any]:
    point = result.get("estimated_position")
    if not isinstance(point, dict):
        raise ValueError(f"{scope}/{method}: artifact has no estimated_position")
    lat, lon = float(point["latitude_deg"]), float(point["longitude_deg"])
    objective = result.get("rf_objective", {})
    return {
        "scope": scope,
        "method": method,
        "task_id": result.get("task_id"),
        "session_count": len(result.get("session_ids", [])),
        "postseal_error_km": haversine_km((lat, lon), reference),
        "rf_objective": objective.get("selection_value", objective.get("value")),
    }


def collect(
    root: Path, reference: tuple[float, float], expected_portable: int = EXPECTED_PORTABLE_OUTPUTS
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    execution_path = root / "portable/execution.json"
    execution = sealed(execution_path)
    if execution.get("complete") is not True or len(execution.get("rows", [])) != expected_portable:
        raise ValueError("portable execution is incomplete or has an unexpected output count")
    expected = {row.get("task_id") for row in execution["rows"]}
    paths = sorted((root / "portable/inference").glob("*.json"))
    values = [(p, sealed(p)) for p in paths]
    if {v.get("task_id") for _, v in values} != expected:
        raise ValueError("portable execution rows do not match sealed inference artifacts")
    rows = [
        point_row(v, "portable", str(v["task_id"]).rsplit("__", 1)[-1], reference)
        for _, v in values
    ]
    bindings = {"portable_execution": digest(execution_path)}
    for stage in ("stage-one", "fine"):
        index_path = root / "portable/refinement" / stage / "index.json"
        index = sealed(index_path)
        if index.get("complete") is not True or len(index.get("models", [])) != 6:
            raise ValueError(f"{stage} refinement index is incomplete")
        bindings[f"{stage}_index"] = digest(index_path)
        for model in index["models"]:
            path = Path(model["final_artifact"])
            value = sealed(path)
            rows.append(point_row(value, stage, str(model["method"]), reference))
            bindings[f"artifact:{value['task_id']}"] = digest(path)
    geometry_path = root / "geometry/inference.json"
    geometry = sealed(geometry_path)
    if geometry.get("complete") is not True:
        raise ValueError("geometry inference is incomplete")
    bindings["geometry_inference"] = digest(geometry_path)
    for result in geometry.get("results", []):
        for name in ("baseline", "staged_full_fov"):
            candidate = result.get(name)
            if isinstance(candidate, dict) and {"latitude_deg", "longitude_deg"} <= set(candidate):
                rows.append(
                    {
                        "scope": "geometry",
                        "method": f"{result.get('label', 'geometry')}:{name}",
                        "task_id": None,
                        "session_count": len(result.get("session_ids", [])),
                        "postseal_error_km": haversine_km(
                            (float(candidate["latitude_deg"]), float(candidate["longitude_deg"])),
                            reference,
                        ),
                        "rf_objective": candidate.get("training_capped_loss"),
                    }
                )
    followup_path = root / "followups-v2/run-plan.json"
    plan = sealed(followup_path)
    if plan.get("complete") is not True:
        raise ValueError("follow-up plan is incomplete")
    bindings["followups_v2_plan"] = digest(followup_path)
    for name, raw_path in sorted(plan.get("outputs", {}).items()):
        path = Path(raw_path)
        if not path.is_file():
            continue
        value = sealed(path)
        if value.get("complete") is not True:
            continue
        bindings[f"followup:{name}"] = digest(path)
        if name == "rate-aware-screen":
            winners = value.get("winners", {})
            items = winners.items() if isinstance(winners, dict) else enumerate(winners)
            for variant, item in items:
                if {"latitude_deg", "longitude_deg"} <= set(item):
                    objective = item.get("rate_aware", {}).get("selection_objective")
                    if objective is None:
                        objective = item.get("nominal_control", {}).get("selection_objective")
                    rows.append(
                        {
                            "scope": "followup",
                            "method": f"{name}:{str(variant).replace('_', '-')}",
                            "task_id": None,
                            "session_count": 22,
                            "postseal_error_km": haversine_km(
                                (float(item["latitude_deg"]), float(item["longitude_deg"])),
                                reference,
                            ),
                            "rf_objective": objective,
                        }
                    )
        if name == "consistent-cap800":
            winner = value.get("winner")
            if isinstance(winner, dict) and {"latitude_deg", "longitude_deg"} <= set(winner):
                rows.append(
                    {
                        "scope": "followup",
                        "method": name,
                        "task_id": None,
                        "session_count": 22,
                        "postseal_error_km": haversine_km(
                            (float(winner["latitude_deg"]), float(winner["longitude_deg"])),
                            reference,
                        ),
                        "rf_objective": winner.get("balanced_exact_capped_loss"),
                    }
                )
    return rows, bindings


def write_sealed(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    value = hashlib.sha256(text.encode()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(value + "\n")
    return "sha256:" + value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=HERE / "output")
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    parser.add_argument("--published-ds2-20", type=Path, default=PUBLISHED_DS2_20)
    parser.add_argument("--output", type=Path, default=HERE / "evaluation.json")
    parser.add_argument("--comparison", type=Path, default=HERE / "comparison.csv")
    args = parser.parse_args()
    rows, bindings = collect(args.input_root, (args.reference_latitude, args.reference_longitude))
    published = sealed(args.published_ds2_20)
    prior = {
        row["method"]: row["postseal_error_km"]
        for row in published.get("joint_rows", [])
        if row.get("scope") == "joint-all20-fine"
    }
    comparison = [
        {
            "method": r["method"],
            "ds2_22_error_km": r["postseal_error_km"],
            "ds2_20_error_km": prior.get(r["method"]),
            "delta_km": None
            if r["method"] not in prior
            else r["postseal_error_km"] - prior[r["method"]],
        }
        for r in rows
        if r["scope"] == "fine"
    ]
    document = {
        "schema": "ds2-successor-postseal-evaluation/v2",
        "development_evaluation": True,
        "reference_coordinate": {
            "latitude_deg": args.reference_latitude,
            "longitude_deg": args.reference_longitude,
            "role": "CLI input introduced after all inference seals",
        },
        "rows": rows,
        "ds2_20_comparison": comparison,
        "bindings": {**bindings, "published_ds2_20_evaluation": digest(args.published_ds2_20)},
    }
    write_sealed(args.output, canonical(document))
    fields = ["method", "ds2_22_error_km", "ds2_20_error_km", "delta_km"]
    with args.comparison.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(comparison)
    write_sealed(args.comparison, args.comparison.read_text())
    print(
        canonical(
            {"rows": len(rows), "comparison_rows": len(comparison), "evaluation": str(args.output)}
        ),
        end="",
    )


if __name__ == "__main__":
    main()
