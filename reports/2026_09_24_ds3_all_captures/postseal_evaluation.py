#!/usr/bin/env python3
"""Evaluate sealed DS3 inference only after a reference is supplied by CLI."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DS2_EVALUATION = HERE.parent / "2026_09_24_ds2_sep24_rerun_22/evaluation.json"
DS1_ITERATION15_ERROR_KM = 0.575577
FORBIDDEN = {
    "reference_coordinate_present",
    "reference_used_for_fit",
    "reference_used_for_inference",
    "truth_used_for_fit",
}
PORTABLE_MODELS = {
    "baseline": "baseline",
    "shared-time": "shared-time",
    "regularized-per-scan-time": "regularized-per-scan-time",
    "equal-weight-joint-rate": "joint_causal_per_norad_orbit_rate",
    "soft-identity": "soft-identity",
}
FOLLOWUP_MODELS = {"consistent-cap800.json": "consistent-cap800"}
GEOMETRY_MODELS = (
    "lt3d_geometry_only",
    "lt3d_fixed_up_cone",
    "lt3d_learned_zenith_cone",
    "global_time_plus_lt3d_cone",
)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing artifact: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecars = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(sidecar.is_file() and sidecar.read_text().strip() == actual for sidecar in sidecars):
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    if any(value.get(key) is True for key in FORBIDDEN):
        raise ValueError(f"reference-bearing inference: {path}")
    return value


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat_a, lat_b = map(math.radians, (a[0], b[0]))
    dlat = lat_b - lat_a
    dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def position(value: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("estimated_position", "winner", "position", "best_position"):
        item = value.get(key)
        if isinstance(item, dict) and {"latitude_deg", "longitude_deg"} <= set(item):
            return float(item["latitude_deg"]), float(item["longitude_deg"])
    if {"latitude_deg", "longitude_deg"} <= set(value):
        return float(value["latitude_deg"]), float(value["longitude_deg"])
    return None


def row(
    path: Path, scope: str, reference: tuple[float, float], model_id: str | None = None
) -> dict[str, Any]:
    value = sealed(path)
    point = position(value)
    if point is None:
        raise ValueError(f"{path}: no unambiguous position")
    return {
        "scope": scope,
        "model_id": model_id or value.get("method") or value.get("model") or path.stem,
        "estimated_position": {"latitude_deg": point[0], "longitude_deg": point[1]},
        "artifact": str(path),
        "artifact_digest": digest(path),
        "postseal_error_km": haversine_km(point, reference),
    }


def collect(root: Path, reference: tuple[float, float]) -> list[dict[str, Any]]:
    inference = root / "portable/inference"
    rows = []
    for filename, model_id in PORTABLE_MODELS.items():
        path = inference / f"joint-all56__{filename}.json"
        rows.append(row(path, "all56", reference, model_id))
    for filename, model_id in FOLLOWUP_MODELS.items():
        rows.append(row(root / "followups-v2" / filename, "all56", reference, model_id))
    summary_path = root / "geometry/geometry-model-summary.json"
    summary = sealed(summary_path)
    models = summary.get("models")
    if summary.get("complete") is not True or not isinstance(models, list):
        raise ValueError("geometry model summary is incomplete")
    by_id = {model.get("model_id"): model for model in models if isinstance(model, dict)}
    if set(by_id) != set(GEOMETRY_MODELS):
        raise ValueError("geometry model summary does not bind exactly four DS3 geometry models")
    for model_id in GEOMETRY_MODELS:
        model = by_id[model_id]
        if model.get("qualification") != "qualified":
            raise ValueError(f"geometry model is not qualified: {model_id}")
        joint = model.get("joint_five")
        point = joint.get("position") if isinstance(joint, dict) else None
        if not isinstance(point, dict) or {"latitude_deg", "longitude_deg"} - set(point):
            raise ValueError(f"geometry summary has no position: {model_id}")
        rows.append(
            {
                "scope": "geometry5",
                "model_id": model_id,
                "estimated_position": {
                    "latitude_deg": float(point["latitude_deg"]),
                    "longitude_deg": float(point["longitude_deg"]),
                },
                "artifact": str(summary_path),
                "artifact_digest": digest(summary_path),
                "postseal_error_km": haversine_km(
                    (float(point["latitude_deg"]), float(point["longitude_deg"])), reference
                ),
            }
        )
    return rows


def comparison(rows: list[dict[str, Any]], ds2: dict[str, Any]) -> list[dict[str, Any]]:
    ds2_rows = [
        row
        for row in ds2.get("rows", [])
        if row.get("scope") in {"fine", "followup"} and row.get("postseal_error_km")
    ]
    if not ds2_rows:
        raise ValueError("sealed DS2 evaluation has no qualified fine/followup rows")
    all56 = [row for row in rows if row["scope"] == "all56"]
    geometry5 = [row for row in rows if row["scope"] == "geometry5"]
    result = [
        {"dataset_scope": "DS1 qualified / iteration15", "best_error_km": DS1_ITERATION15_ERROR_KM},
        {
            "dataset_scope": "DS2-22 / all22",
            "best_error_km": min(float(row["postseal_error_km"]) for row in ds2_rows),
        },
        {
            "dataset_scope": "DS3 / all56",
            "best_error_km": min(row["postseal_error_km"] for row in all56),
        },
    ]
    if geometry5:
        result.append(
            {
                "dataset_scope": "DS3 / geometry5",
                "best_error_km": min(row["postseal_error_km"] for row in geometry5),
            }
        )
    return result


def write(path: Path, content: str) -> None:
    path.write_text(content)
    sha256 = hashlib.sha256(content.encode()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(sha256 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=HERE / "output")
    parser.add_argument("--ds2-evaluation", type=Path, default=DS2_EVALUATION)
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "evaluation.json")
    parser.add_argument("--comparison", type=Path, default=HERE / "comparison.csv")
    args = parser.parse_args()
    reference = (args.reference_latitude, args.reference_longitude)
    rows = collect(args.input_root, reference)
    ds2 = sealed(args.ds2_evaluation)
    summary = comparison(rows, ds2)
    document = {
        "schema": "ds3-postseal-evaluation/v1",
        "reference_coordinate": {"role": "CLI input after inference seals"},
        "rows": rows,
        "bound_model_ids": [row["model_id"] for row in rows],
        "comparison": summary,
        "ds2_evaluation_digest": digest(args.ds2_evaluation),
    }
    write(args.output, canonical(document))
    with args.comparison.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dataset_scope", "best_error_km"])
        writer.writeheader()
        writer.writerows(summary)
    write(args.comparison, args.comparison.read_text())


if __name__ == "__main__":
    main()
