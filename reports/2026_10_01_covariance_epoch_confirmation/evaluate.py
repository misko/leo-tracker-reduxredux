"""Truth evaluator gated by the complete final integrity audit."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("C1", "M2", "M4", "M24")
EXPECTED_CELLS = 128
CENTER = (38.5816, -121.4944)
EARTH_KM = 6371.0088
MAP_RADIUS_KM = 6371.007180918475


def digest(path: Path | str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def destination(east: float, north: float) -> tuple[float, float]:
    latitude, longitude = map(math.radians, CENTER)
    arc = math.hypot(east, north) / MAP_RADIUS_KM
    azimuth = math.atan2(east, north)
    latitude_two = math.asin(
        math.sin(latitude) * math.cos(arc)
        + math.cos(latitude) * math.sin(arc) * math.cos(azimuth)
    )
    longitude_two = longitude + math.atan2(
        math.sin(azimuth) * math.sin(arc) * math.cos(latitude),
        math.cos(arc) - math.sin(latitude) * math.sin(latitude_two),
    )
    return math.degrees(latitude_two), math.degrees(longitude_two)


def distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    latitude, longitude, latitude_two, longitude_two = map(math.radians, (*first, *second))
    haversine = (
        math.sin((latitude_two - latitude) / 2) ** 2
        + math.cos(latitude)
        * math.cos(latitude_two)
        * math.sin((longitude_two - longitude) / 2) ** 2
    )
    return 2000 * EARTH_KM * math.asin(min(1.0, math.sqrt(haversine)))


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    return ordered[lower] + (position - lower) * (
        ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]
    )


def summarize(rows: list[dict]) -> dict:
    qualified = [row["error_m"] for row in rows if row["qualified"] and row["error_m"] is not None]
    diagnostic = [row["error_m"] for row in rows if row["error_m"] is not None]
    return {
        "planned": len(rows),
        "qualified": len(qualified),
        "returned_points": len(diagnostic),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "median_m": quantile(qualified, 0.5),
        "p90_m": quantile(qualified, 0.9),
        "worst_m": max(qualified) if qualified else None,
        "sub_km_qualified_over_planned": sum(value < 1000 for value in qualified) / len(rows),
        "diagnostic_returned_point_median_m": quantile(diagnostic, 0.5),
        "median_wall_s": quantile([row["seconds"] for row in rows], 0.5),
    }


def require_passed_audit() -> tuple[dict, str]:
    audit_path = HERE / "final-integrity-audit.json"
    audit = json.loads(audit_path.read_text())
    if (
        audit.get("passed") is not True
        or audit.get("planned_cells") != EXPECTED_CELLS
        or audit.get("launch_receipts") != EXPECTED_CELLS
    ):
        raise ValueError("complete 128-cell integrity audit has not passed")
    return audit, digest(audit_path)


def evaluate() -> dict:
    # No reference coordinate is constructed until this gate passes.
    audit, audit_hash = require_passed_audit()
    frozen_path = HERE / "execution-freeze.json"
    if audit["execution_freeze_sha256"] != digest(frozen_path):
        raise ValueError("integrity audit is not bound to the current execution freeze")
    frozen = json.loads(frozen_path.read_text())
    if frozen["arms"] != list(ARMS) or len(frozen["units"]) * len(ARMS) != EXPECTED_CELLS:
        raise ValueError("evaluator matrix differs from frozen matrix")
    # User-supplied, unsurveyed, whole-arcsecond coordinate, unchanged from the prior report.
    reference = (37 + 50 / 60 + 57 / 3600, -(122 + 29 / 60 + 9 / 3600))
    rows = []
    for unit in frozen["units"]:
        for arm in ARMS:
            output = HERE / "runs" / f"{unit}-{arm}.json"
            launch = json.loads(output.with_suffix(".launch.json").read_text())
            row = {
                "unit": unit,
                "dataset": unit.split("-")[0],
                "arm": arm,
                "status": launch["status"],
                "seconds": launch["seconds"],
                "qualified": False,
                "error_m": None,
                "east_km": None,
                "north_km": None,
            }
            if output.exists():
                seal_path = output.with_suffix(".seal.json")
                if json.loads(seal_path.read_text())["prediction_sha256"] != digest(output):
                    raise ValueError("prediction seal mismatch during evaluation")
                prediction = json.loads(output.read_text())
                if prediction.get("reference_coordinate_accessed") is not False:
                    raise ValueError("prediction does not attest truth isolation")
                row["qualified"] = (
                    launch["returncode"] == 0
                    and prediction["status"] == "completed"
                    and prediction.get("qualified") is True
                )
                point = prediction.get("point_estimate")
                if point is None:
                    point = prediction.get("diagnostic_unqualified_point")
                if point is not None:
                    east = float(point["east_km"])
                    north = float(point["north_km"])
                    if not math.isfinite(east + north) or math.hypot(east, north) > 250.000001:
                        raise ValueError("point is nonfinite or outside frozen prior support")
                    row.update(
                        east_km=east,
                        north_km=north,
                        error_m=distance_m(destination(east, north), reference),
                    )
            rows.append(row)
    if len(rows) != EXPECTED_CELLS:
        raise ValueError("evaluator did not construct 128 cells")
    baseline = {row["unit"]: row for row in rows if row["arm"] == "C1"}
    summary = {
        "schema": "covariance-epoch-confirmation-results/v1",
        "reference_latlon": reference,
        "reference_provenance": "Unchanged user-supplied 37 50 57 N, 122 29 9 W; unsurveyed and whole-arcsecond rounded",
        "execution_freeze_sha256": digest(frozen_path),
        "final_integrity_audit_sha256": audit_hash,
        "overall": {},
        "by_dataset": {},
    }
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        value = summarize(selected)
        pairs = [
            (row, baseline[row["unit"]])
            for row in selected
            if row["qualified"]
            and baseline[row["unit"]]["qualified"]
            and row["error_m"] is not None
            and baseline[row["unit"]]["error_m"] is not None
        ]
        deltas = [first["error_m"] - second["error_m"] for first, second in pairs]
        value.update(
            paired_qualified_vs_C1=len(pairs),
            paired_wins_vs_C1=sum(delta < 0 for delta in deltas),
            paired_ties_vs_C1=sum(delta == 0 for delta in deltas),
            paired_losses_vs_C1=sum(delta > 0 for delta in deltas),
            median_paired_delta_m=quantile(deltas, 0.5),
        )
        summary["overall"][arm] = value
        summary["by_dataset"][arm] = {
            dataset: summarize([row for row in selected if row["dataset"] == dataset])
            for dataset in ("DS9", "DS10", "DS11")
        }
    with (HERE / "per-scan.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (HERE / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
