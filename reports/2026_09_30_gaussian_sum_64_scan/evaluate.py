"""Seal-verified evaluation for the frozen 64-scan Gaussian-sum experiment."""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import json
from math import asin, atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Iterable

import numpy as np

REFERENCE_LATLON = (37.849056280893684, -122.48575489722863)
SACRAMENTO_CENTER_LATLON = (38.5816, -121.4944)
EARTH_RADIUS_KM = 6371.0088
ARMS = ("gaussian_sum", "greedy", "prior_only")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def great_circle_km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1., sqrt(h)))


def latlon_from_enu(center, east_km, north_km):
    lat1, lon1 = map(radians, center)
    distance = sqrt(east_km**2 + north_km**2)
    if distance == 0:
        return center
    bearing, angular = atan2(east_km, north_km), distance / EARTH_RADIUS_KM
    lat2 = asin(sin(lat1)*cos(angular) + cos(lat1)*sin(angular)*cos(bearing))
    lon2 = lon1 + atan2(sin(bearing)*sin(angular)*cos(lat1), cos(angular)-sin(lat1)*sin(lat2))
    return np.degrees(lat2), ((np.degrees(lon2)+180) % 360)-180


def enu_from_latlon(center, point):
    """Spherical inverse of ``latlon_from_enu`` for evaluator-only plotting."""
    lat1, lon1, lat2, lon2 = map(radians, (*center, *point))
    dlon = lon2 - lon1
    y = sin(dlon) * cos(lat2)
    x = cos(lat1)*sin(lat2) - sin(lat1)*cos(lat2)*cos(dlon)
    bearing = atan2(y, x)
    angular = atan2(sqrt(y*y + x*x), sin(lat1)*sin(lat2) + cos(lat1)*cos(lat2)*cos(dlon))
    distance = EARTH_RADIUS_KM * angular
    return distance*sin(bearing), distance*cos(bearing)


def selected_units(selection: dict) -> list[dict]:
    rows = selection.get("units", selection.get("selected", selection.get("selection", selection.get("scans", []))))
    if isinstance(rows, dict):
        rows = [item for values in rows.values() for item in values]
    normalized = []
    for index, row in enumerate(rows):
        if isinstance(row, str):
            unit, dataset, session = row, row.split("-")[0], None
        else:
            unit = row.get("unit_id", row.get("unit"))
            dataset = row.get("dataset", unit.split("-")[0])
            session = row.get("session_id")
        if not unit:
            raise ValueError("selection row lacks unit_id")
        normalized.append({"order": index, "dataset": dataset, "unit_id": unit, "session_id": session})
    if len(normalized) != 64 or len({row["unit_id"] for row in normalized}) != 64:
        raise ValueError("selection must contain exactly 64 unique units")
    if Counter(row["dataset"] for row in normalized) != {"DS9": 22, "DS10": 21, "DS11": 21}:
        raise ValueError("selection must contain DS9/DS10/DS11 counts 22/21/21")
    return normalized


def load_verified_receipts(run_root: Path) -> dict[tuple[str, str], dict]:
    receipts = {}
    verified_hashes: dict[Path, str] = {}

    def verify(path: Path, expected: str, label: str) -> None:
        actual = verified_hashes.get(path)
        if actual is None:
            if not path.exists():
                raise ValueError(f"missing immutable {label} for {path}")
            actual = sha256(path)
            verified_hashes[path] = actual
        if actual != expected:
            raise ValueError(f"immutable {label} mismatch for {path}")

    for seal_path in sorted(run_root.glob("batch-*/*.seal.json")):
        receipt_path = seal_path.with_name(seal_path.name.replace(".seal.json", ".json"))
        seal = json.loads(seal_path.read_text())
        if not receipt_path.exists() or seal.get("prediction_sha256") != sha256(receipt_path):
            raise ValueError(f"seal mismatch for {receipt_path}")
        receipt = json.loads(receipt_path.read_text())
        for bound_path, expected in receipt.get("source_sha256", {}).items():
            verify(Path(bound_path), expected, "source")
        # The sealed receipt binds bulk inputs and its state artifact by digest.
        # Evaluation does not reopen those large files while experiment writes are active.
        for expected in (*receipt.get("inputs", {}).values(),
                         receipt.get("state_artifact", {}).get("sha256")):
            if expected is not None and not str(expected).startswith("sha256:"):
                raise ValueError(f"invalid bound digest in {receipt_path}")
        receipt["_receipt_sha256"] = seal["prediction_sha256"]
        receipt["_receipt_path"] = str(receipt_path)
        key = (receipt["unit_id"], receipt["arm"])
        if key in receipts:
            raise ValueError(f"duplicate sealed receipt for {key}")
        receipts[key] = receipt
    return receipts


def load_attempt_records(run_root: Path) -> dict[tuple[str, str], dict]:
    """Load sealed native receipts and preserve launch-only attempts as failures."""
    records = load_verified_receipts(run_root)
    for launch_path in sorted(run_root.glob("batch-*/*.launch.json")):
        launch = json.loads(launch_path.read_text())
        key = (launch["unit_id"], launch["arm"])
        if key in records:
            records[key]["_launcher_wall_seconds"] = launch.get("wall_seconds")
            records[key]["_launcher_status"] = launch.get("status")
            records[key]["_launcher_path"] = str(launch_path)
            continue
        launch_status = launch.get("status", "unknown")
        status = launch_status if launch_status in {"timeout", "error", "cancelled"} else "unsealed_output"
        records[key] = {"_launch_only": True, "unit_id":key[0], "arm":key[1], "status":status,
                        "wall_seconds":launch.get("wall_seconds"), "returncode":launch.get("returncode"),
                        "native_progress_exists":bool(launch.get("native_progress_exists")),
                        "launch_path":str(launch_path)}
    return records


def pipeline_context_row(document: dict, unit_by_session: dict[str, dict]) -> dict:
    """Decode the published standard-pipeline Sacramento result as unmatched context."""
    session = document.get("session_id")
    if session not in unit_by_session:
        raise ValueError(f"pipeline output session is outside frozen panel: {session}")
    try:
        priors = document["manifest"]["document"]["priors"]
        sacramento = next(item for item in priors if item["name"] == "sacramento")
        selected = sacramento["selected"]
        point = (float(selected["latitude_deg"]), float(selected["longitude_deg"]))
    except (KeyError, StopIteration, TypeError, ValueError) as error:
        raise ValueError(f"invalid Sacramento pipeline output for {session}") from error
    unit = unit_by_session[session]
    return {"dataset":unit["dataset"], "unit_id":unit["unit_id"], "session_id":session,
            "status":"complete" if sacramento.get("search_complete") else "incomplete",
            "error_km":great_circle_km(point, REFERENCE_LATLON), "latitude_deg":point[0],
            "longitude_deg":point[1], "comparison":"historical_unmatched_standard_pipeline",
            "qualification":"different tracks, objective, and 400-point search budget; not a matched arm"}


def load_pipeline_context(directory: Path, units: list[dict]) -> list[dict]:
    """Load one read-only published pipeline response per frozen unit."""
    by_session = {str(unit["session_id"]): unit for unit in units}
    rows = []
    for unit in units:
        path = directory / f"{unit['unit_id']}.json"
        error_path = directory / f"{unit['unit_id']}.fetch-error.json"
        if path.exists():
            document = json.loads(path.read_text())
            row = pipeline_context_row(document, by_session)
            row["source_sha256"] = sha256(path)
            rows.append(row)
        elif error_path.exists():
            failure = json.loads(error_path.read_text())
            rows.append({**unit, "status":"fetch_error", "error_km":None,
                         "comparison":"historical_unmatched_standard_pipeline",
                         "qualification":"metadata fetch failed; no point comparison",
                         "fetch_error":failure.get("error")})
        else:
            rows.append({**unit, "status":"missing", "error_km":None,
                         "comparison":"historical_unmatched_standard_pipeline",
                         "qualification":"metadata was not fetched"})
    return rows


def summarize_pipeline_context(rows: Iterable[dict], denominator: int) -> dict:
    rows = list(rows)
    points = np.asarray([row["error_km"] for row in rows if row.get("error_km") is not None])
    return {
        "planned_denominator": denominator,
        "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        "selected_point_count": int(points.size),
        "median_selected_point_error_km": float(np.median(points)) if points.size else None,
        "p90_selected_point_error_km": float(np.quantile(points, .9)) if points.size else None,
        "worst_selected_point_error_km": float(points.max()) if points.size else None,
        "sub_km_selected_point_count": int(np.count_nonzero(points < 1.)),
        "sub_km_selected_point_fraction_all_planned": float(np.count_nonzero(points < 1.) / denominator),
        "qualification":"diagnostic selected points; search completion is reported separately",
    }


def receipt_row(planned: dict, arm: str, receipt: dict | None) -> dict:
    base = {**planned, "arm": arm, "attempted": receipt is not None}
    if receipt is None:
        return {**base, "status": "missing", "completed": False, "error_km": None,
                "runtime_s": None, "consumed_fraction": 0., "max_discarded_mass": None,
                "highest_weight_component_error_km": None}
    if receipt.get("_launch_only"):
        return {**base, "status":receipt["status"], "completed":False, "error_km":None,
                "runtime_s":receipt.get("wall_seconds"), "launcher_runtime_s":receipt.get("wall_seconds"),
                "native_pre_artifact_runtime_s":None, "consumed_fraction":0.,
                "max_discarded_mass":None, "highest_weight_component_error_km":None,
                "launch_only":True, "progress_diagnostic_available":receipt["native_progress_exists"],
                "returncode":receipt.get("returncode"), "failure_reason":receipt["status"]}
    if planned["session_id"] and receipt.get("session_id") != planned["session_id"]:
        raise ValueError(f"session mismatch for {planned['unit_id']}")
    checkpoints = receipt.get("checkpoints", [])
    components = receipt.get("components", [])
    physics = receipt.get("config", {}).get("physics", {})
    try:
        prior_center = (float(physics["prior_center_lat_deg"]), float(physics["prior_center_lon_deg"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"receipt lacks declared prior center for {planned['unit_id']} {arm}") from error
    if receipt.get("prior_name") != "sacramento_uniform":
        raise ValueError(f"unexpected prior for {planned['unit_id']} {arm}")
    if prior_center != SACRAMENTO_CENTER_LATLON:
        raise ValueError(f"unexpected Sacramento center for {planned['unit_id']} {arm}")
    point = receipt.get("prior_point_estimate", {})
    declared_point = (point.get("latitude_deg"), point.get("longitude_deg"))
    if declared_point != prior_center or point.get("rule") != "center_of_intended_uniform_disk":
        raise ValueError(f"prior point estimate disagrees with configured center for {planned['unit_id']}")
    spatial = receipt.get("config", {}).get("spatial_prior", {})
    if (spatial.get("component_count") != 32 or spatial.get("intended_radius_km") != 250.0
            or spatial.get("approximation") != "equal_area_annular_sector_cell_moment_gaussians"
            or not 0.0 < float(spatial.get("represented_mass_outside_intended_disk", -1.)) < .2):
        raise ValueError(f"unexpected uniform-disk approximation for {planned['unit_id']}")
    completed = receipt.get("status") == "complete"
    error = None
    highest_component_error = None
    estimate_latlon = None
    spatial_components = [{"weight":float(component["weight"]),
                           "mean_en_km":[float(component["mean"][0]),float(component["mean"][1])],
                           "covariance_en_km2":[[float(component["covariance"][0][0]),float(component["covariance"][0][1])],
                                                [float(component["covariance"][1][0]),float(component["covariance"][1][1])]]}
                          for component in components]
    if components:
        # Stable receipt order resolves equal-weight prior components.
        top = min(enumerate(components), key=lambda pair: (-float(pair[1]["weight"]), pair[0]))[1]
        point = latlon_from_enu(prior_center, float(top["mean"][0]), float(top["mean"][1]))
        estimate_latlon = [float(point[0]), float(point[1])]
        highest_component_error = great_circle_km(point, REFERENCE_LATLON)
        error = highest_component_error
        if arm == "prior_only":
            # Equal-weight component ordering is arbitrary; the configured center is
            # also the symmetric prior mixture mean and is the frozen point baseline.
            error = great_circle_km(prior_center, REFERENCE_LATLON)
    if not completed:
        # Failed-prefix component locations remain explicitly diagnostic below;
        # the generic point-error field is reserved for accepted estimates.
        error = None
    planned_factors = int(receipt.get("selection", {}).get("retained_tracks", len(checkpoints)))
    max_discarded = max((1-float(cp["retained_mass"]) for cp in checkpoints), default=0.)
    return {**base, "status": receipt.get("status", "missing"), "completed": completed,
            "error_km": error, "runtime_s": receipt.get("_launcher_wall_seconds", receipt.get("wall_seconds")),
            "launcher_runtime_s": receipt.get("_launcher_wall_seconds"),
            "native_pre_artifact_runtime_s": receipt.get("wall_seconds"),
            "launcher_status": receipt.get("_launcher_status"),
            "launcher_path": receipt.get("_launcher_path"),
            "consumed_factors": len(checkpoints), "planned_factors": planned_factors,
            "consumed_fraction": len(checkpoints)/planned_factors if planned_factors else 1.,
            "max_discarded_mass": max_discarded,
            "highest_weight_component_error_km": highest_component_error,
            "highest_weight_component_latlon": estimate_latlon,
            "spatial_components": spatial_components,
            "gate_failures": receipt.get("gate_failures", []),
            "failure_reason": (receipt.get("exception", {}).get("message")
                               if receipt.get("status") == "error" else None),
            "prior_center_latlon": list(prior_center),
            "receipt_path": receipt.get("_receipt_path"),
            "receipt_sha256": receipt.get("_receipt_sha256"),
            "config_sha256": receipt.get("config_sha256"),
            "input_sha256": receipt.get("inputs", {}),
            "receipt_status_is_scientifically_accepted": completed}


def summarize(rows: Iterable[dict], denominator: int) -> dict:
    rows = list(rows)
    completed = [row for row in rows if row["completed"] and row["error_km"] is not None]
    errors = np.array([row["error_km"] for row in completed])
    failure_reasons = Counter()
    for row in rows:
        failure_reasons.update(row.get("gate_failures", []))
        if row.get("failure_reason"):
            failure_reasons[row["failure_reason"]] += 1
    return {
        "planned_denominator": denominator,
        "attempted_count": sum(bool(row["attempted"]) for row in rows),
        "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        "failure_reason_counts": dict(sorted(failure_reasons.items())),
        "completed_count": len(completed),
        "median_error_km_completed": float(np.median(errors)) if errors.size else None,
        "p90_error_km_completed": float(np.quantile(errors, .9)) if errors.size else None,
        "worst_error_km_completed": float(errors.max()) if errors.size else None,
        "sub_km_count": int(np.count_nonzero(errors < 1.)),
        "sub_km_fraction_all_planned": float(np.count_nonzero(errors < 1.) / denominator),
    }


def evaluate(selection: dict, receipts: dict[tuple[str, str], dict]) -> dict:
    units = selected_units(selection)
    rows = [receipt_row(unit, arm, receipts.get((unit["unit_id"], arm))) for unit in units for arm in ARMS]
    summaries = {}
    for dataset in ("DS9", "DS10", "DS11", "pooled"):
        subset = rows if dataset == "pooled" else [row for row in rows if row["dataset"] == dataset]
        denominator = 64 if dataset == "pooled" else {"DS9":22,"DS10":21,"DS11":21}[dataset]
        summaries[dataset] = {arm: summarize((row for row in subset if row["arm"] == arm), denominator) for arm in ARMS}
    paired = []
    by_key = {(row["unit_id"], row["arm"]): row for row in rows}
    for unit in units:
        gsf, greedy = by_key[(unit["unit_id"], "gaussian_sum")], by_key[(unit["unit_id"], "greedy")]
        if gsf["completed"] and greedy["completed"]:
            paired.append({"dataset":unit["dataset"], "unit_id":unit["unit_id"],
                           "gaussian_sum_error_km":gsf["error_km"], "greedy_error_km":greedy["error_km"],
                           "gaussian_sum_minus_greedy_km":gsf["error_km"]-greedy["error_km"]})
    centers = {tuple(row["prior_center_latlon"]) for row in rows if row.get("prior_center_latlon")}
    if len(centers) > 1:
        raise ValueError("sealed receipts disagree on prior center")
    center = next(iter(centers)) if centers else None
    paired_prior = []
    if center:
        baseline = great_circle_km(center, REFERENCE_LATLON)
        paired_prior = [{"dataset":row["dataset"], "unit_id":row["unit_id"], "arm":row["arm"],
                         "error_km":row["error_km"], "prior_center_error_km":baseline,
                         "error_minus_prior_center_km":row["error_km"]-baseline}
                        for row in rows if row["completed"] and row["arm"] != "prior_only"]
    return {
        "schema":"gaussian-sum-64-scan-evaluation/v1", "planned_units":64,
        "planned_attempts":192, "rows":rows, "summaries":summaries,
        "paired_completed_gaussian_sum_greedy":paired,
        "paired_completed_vs_prior_center":paired_prior,
        "prior_center_latlon":list(center) if center else None,
        "prior_center_error_km":great_circle_km(center, REFERENCE_LATLON) if center else None,
        "reference":{"latitude_deg":REFERENCE_LATLON[0],"longitude_deg":REFERENCE_LATLON[1],
                     "authority":"gauss-r20-roof-20260926-v1",
                     "source":"reports/2026_09_30_rx_sky_coverage/README.md",
                     "qualification":"operator-supplied common unsurveyed roof coordinate"},
    }


def require_complete_attempt_panel(selection: dict, receipts: dict[tuple[str, str], dict]) -> None:
    expected = {(unit["unit_id"], arm) for unit in selected_units(selection) for arm in ARMS}
    missing = sorted(expected - set(receipts))
    extra = sorted(set(receipts) - expected)
    if missing or extra:
        raise ValueError(f"publication requires exactly 192 attempts; missing={len(missing)}, extra={len(extra)}")


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value)
    temporary.replace(path)


def publish(report: Path, run_root: Path) -> list[Path]:
    """Regenerate final evaluation artifacts from the complete sealed v3 panel."""
    selection = json.loads((report / "selection.json").read_text())
    receipts = load_attempt_records(run_root)
    require_complete_attempt_panel(selection, receipts)
    result = evaluate(selection, receipts)
    units = selected_units(selection)
    historical = json.loads((report / "historical-context.json").read_text())
    result["historical_pipeline_context"] = historical
    result["provenance"] = {
        "primary_run_root": str(run_root.resolve()),
        "selection_sha256": sha256(report / "selection.json"),
        "historical_context_sha256": sha256(report / "historical-context.json"),
        "qualification":"only seal-verified runs-v3 receipts enter the primary 192-attempt panel",
    }
    _atomic_text(report / "evaluation.json", json.dumps(result, indent=2, allow_nan=False) + "\n")

    fields = sorted({key for row in result["rows"] for key in row})
    temporary = report / "evaluation.csv.tmp"
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({key:(json.dumps(value,sort_keys=True) if isinstance(value,(dict,list)) else value)
                             for key,value in row.items()})
    temporary.replace(report / "evaluation.csv")
    from plots import generate_summary_figures
    return generate_summary_figures(result, report / "figures")


def ecdf_with_failures(rows: Iterable[dict], denominator: int) -> tuple[np.ndarray, np.ndarray]:
    errors = np.sort([row["error_km"] for row in rows if row["completed"] and row["error_km"] is not None])
    return errors, np.arange(1, errors.size+1, dtype=float)/denominator


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--run-root", type=Path)
    arguments = parser.parse_args()
    root = arguments.run_root or arguments.report / "runs-v3"
    for generated in publish(arguments.report, root):
        print(generated)
