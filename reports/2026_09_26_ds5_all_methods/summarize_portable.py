#!/usr/bin/env python3
"""Post-seal evaluation and stratified summaries for DS5 portable methods."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = ROOT / "reports/2026_09_26_ds5_since_local_midnight/manifest.json"
UNITS = ROOT / "reports/2026_09_26_ds5_since_local_midnight/evaluation-units.json"
RUN_ROOT = Path("/srv/bulk/leo/experiments/ds5-all-methods/portable-results")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_sealed(path: Path) -> bool:
    if not path.is_file():
        return False
    actual = digest(path)
    return any(
        seal.is_file() and seal.read_text().strip().removeprefix("sha256:") == actual
        for seal in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    )


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row["state"] == "complete"]
    errors = [float(row["horizontal_error_km"]) for row in complete]
    return {
        "expected_count": len(rows),
        "complete_count": len(complete),
        "pending_count": len(rows) - len(complete),
        "median_error_km": statistics.median(errors) if errors else None,
        "mean_error_km": statistics.fmean(errors) if errors else None,
        "p90_error_km": percentile(errors, 0.9),
        "minimum_error_km": min(errors) if errors else None,
        "maximum_error_km": max(errors) if errors else None,
    }


def build(reference_lat: float, reference_lon: float, run_root: Path = RUN_ROOT) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text())
    units = json.loads(UNITS.read_text())
    plan_path = run_root / "plan.json"
    if not valid_sealed(plan_path):
        raise ValueError("sealed portable plan unavailable")
    plan = json.loads(plan_path.read_text())
    capture = {row["session_id"]: row for row in manifest["captures"] if row["admission_status"] == "included"}
    unit_meta: dict[str, dict[str, Any]] = {}
    for unit in units["single_scans"] + units["groups_of_8"] + [units["full_dataset"]]:
        unit_meta[unit["unit_id"]] = unit
    for value in units["sample_rate_strata"].values():
        unit_meta[value["subset_unit"]["unit_id"]] = value["subset_unit"]

    rows: list[dict[str, Any]] = []
    for task in plan["tasks"]:
        output = Path(task["output_path"])
        sid_rows = [capture[sid] for sid in task["session_ids"]]
        row: dict[str, Any] = {
            "task_id": task["task_id"],
            "unit_id": task["task_id"].split("__", 1)[0],
            "scope": task["scope"],
            "method": task["method"],
            "session_count": len(sid_rows),
            "session_ids": task["session_ids"],
            "sample_rate_composition": dict(sorted((str(rate), sum(int(x["sample_rate_hz"]) == rate for x in sid_rows)) for rate in {int(x["sample_rate_hz"]) for x in sid_rows})),
            "active_dwell_seconds": sum(float(x["active_dwell_seconds"]) for x in sid_rows),
            "active_dwell_seconds_distribution": [float(x["active_dwell_seconds"]) for x in sid_rows],
            "median_valid_duty_fraction": statistics.median(float(x["valid_duty_fraction"]) for x in sid_rows),
            "median_visit_dwell_ms": statistics.median(float(x["median_visit_dwell_ms"]) for x in sid_rows),
            "state": "pending",
        }
        if len(sid_rows) == 1:
            row["sample_rate_hz"] = int(sid_rows[0]["sample_rate_hz"])
            row["active_dwell_time_stratum"] = sid_rows[0]["active_dwell_time_stratum"]
        if valid_sealed(output):
            result = json.loads(output.read_text())
            if (
                result.get("reference_coordinate_present") is not False
                or result.get("reference_used_for_fit") is not False
                or result.get("truth_used_for_fit") not in (None, False)
            ):
                raise ValueError(f"truth-blind boundary violated: {output}")
            estimate = result["estimated_position"]
            row.update({
                "state": "complete",
                "result_sha256": "sha256:" + digest(output),
                "latitude_deg": float(estimate["latitude_deg"]),
                "longitude_deg": float(estimate["longitude_deg"]),
                "horizontal_error_km": distance_km(reference_lat, reference_lon, float(estimate["latitude_deg"]), float(estimate["longitude_deg"])),
                "rf_objective": result.get("rf_objective"),
                "elapsed_s": result.get("elapsed_s"),
                "qualified_track_count": result.get("qualified_track_count"),
                "full_observation_count": result.get("full_observation_count"),
            })
        rows.append(row)

    summaries: dict[str, list[dict[str, Any]]] = {}
    groupings = {
        "scope_method": lambda row: (row["scope"], row["method"]),
        "single_rate_method": lambda row: (str(row["sample_rate_hz"]), row["method"]) if row["scope"] == "single" else None,
        "single_active_method": lambda row: (row["active_dwell_time_stratum"], row["method"]) if row["scope"] == "single" else None,
        "single_rate_active_method": lambda row: (str(row["sample_rate_hz"]), row["active_dwell_time_stratum"], row["method"]) if row["scope"] == "single" else None,
    }
    for name, key_fn in groupings.items():
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = key_fn(row)
            if key is not None:
                grouped[key].append(row)
        summaries[name] = [{"key": list(key), **aggregate(group)} for key, group in sorted(grouped.items())]
    return {
        "schema": "ds5-portable-postseal-evaluation/v1",
        "inference_reference_coordinate_present": False,
        "reference_used_postseal_only": True,
        "reference": {"latitude_deg": reference_lat, "longitude_deg": reference_lon},
        "plan_sha256": "sha256:" + digest(plan_path),
        "expected_result_count": len(rows),
        "complete_result_count": sum(row["state"] == "complete" for row in rows),
        "pending_result_count": sum(row["state"] == "pending" for row in rows),
        "rows": rows,
        "summaries": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    parser.add_argument("--run-root", type=Path, default=RUN_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(args.reference_latitude, args.reference_longitude, args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.write_text(text)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "\n")
    print(json.dumps({k: document[k] for k in ("expected_result_count", "complete_result_count", "pending_result_count")}, sort_keys=True))


if __name__ == "__main__":
    main()
