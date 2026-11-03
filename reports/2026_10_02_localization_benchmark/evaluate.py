import csv
import hashlib
import json

import numpy as np
from selection import MODEL_NAMES, ROOT


def coordinates(point):
    east, north = point
    angular = np.hypot(east, north) / 6371.0088
    bearing = np.arctan2(east, north)
    latitude, longitude = np.deg2rad([38.5816, -121.4944])
    result_lat = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    result_lon = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(result_lat),
    )
    return np.rad2deg([result_lat, result_lon])


def ecef(latitude, longitude):
    latitude, longitude = np.deg2rad([latitude, longitude])
    eccentricity = (1 / 298.257223563) * (2 - 1 / 298.257223563)
    radius = 6378.137 / np.sqrt(1 - eccentricity * np.sin(latitude) ** 2)
    return np.array(
        [
            radius * np.cos(latitude) * np.cos(longitude),
            radius * np.cos(latitude) * np.sin(longitude),
            radius * (1 - eccentricity) * np.sin(latitude),
        ]
    )


def summarize(rows, dataset="DS11"):
    output = []
    for model in MODEL_NAMES:
        selected = [row for row in rows if row["dataset"] == dataset and row["model"] == model]
        accepted = [
            row for row in selected if row["success"] and row["reference_error_km"] is not None
        ]
        errors = np.array([row["reference_error_km"] for row in accepted])
        output.append(
            {
                "dataset": dataset,
                "model": model,
                "requested_scans": len(selected),
                "attempted_scans": sum(row["attempted"] for row in selected),
                "successful_scans": len(accepted),
                "pending_scans": sum(not row["attempted"] for row in selected),
                "median_error_km": float(np.median(errors)) if len(errors) else None,
                "p90_error_km": float(np.quantile(errors, 0.9)) if len(errors) else None,
                "maximum_error_km": float(np.max(errors)) if len(errors) else None,
                "within_1km": int(np.sum(errors < 1)),
                "within_5km": int(np.sum(errors < 5)),
                "median_runtime_s": float(
                    np.median(
                        [row["runtime_s"] for row in selected if row["runtime_s"] is not None]
                    )
                )
                if any(row["runtime_s"] is not None for row in selected)
                else None,
            }
        )
    return output


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def common_score(data, parameters):
    prediction, visible = data.predict(np.asarray(parameters))
    alias = 1 / 4.4e-6
    errors = np.abs((data.measured[:, None] - prediction + alias / 2) % alias - alias / 2)
    errors[~visible] = np.inf
    groups, inverse = np.unique(data.group, return_inverse=True)
    grouped = np.full(len(groups), np.inf)
    np.minimum.at(grouped, inverse, np.min(errors, axis=1))
    loss = 2 * 200**2 * (np.sqrt(1 + (np.minimum(grouped, 2000) / 200) ** 2) - 1)
    return float(np.mean(loss)), int(np.sum(grouped < 1000))


def main():
    selection = json.loads((ROOT / "selection.json").read_text())
    rows = []
    provenance = {}
    for session_id in [selection["original_sample"], *selection["selected"]]:
        dataset = "original_sample" if session_id == selection["original_sample"] else "DS11"
        directory = ROOT / "scans" / session_id
        fitted_path = directory / "fits.json"
        fits = json.loads(fitted_path.read_text()) if fitted_path.exists() else {"models": {}}
        truth_path = directory / "evaluation.json"
        truth = (
            json.loads(truth_path.read_text())["reference_site"] if truth_path.exists() else None
        )
        if fitted_path.exists():
            provenance[session_id] = hashlib.sha256(fitted_path.read_bytes()).hexdigest()
        data = None
        if fits["models"]:
            from bundle import Data

            data = Data(directory)
        for model in MODEL_NAMES:
            fitted = fits["models"].get(model)
            row = {
                "dataset": dataset,
                "session_id": session_id,
                "model": model,
                "attempted": fitted is not None,
                "success": False,
                "status": "pending",
                "free_parameters": None,
                "assigned_groups": None,
                "reference_error_km": None,
                "fitted_objective": None,
                "all64_nearest_loss_diagnostic": None,
                "all64_groups_within_1000hz": None,
                "common_diagnostic_status": (
                    "not applicable: independent track offsets do not define a scan-wide RX model"
                    if model == "track_independent"
                    else "pending"
                ),
                "runtime_s": None,
                "message": None,
                "rx_policy": None,
                "initialization_provenance": None,
                "fixed_assignment_rms_hz": None,
                "candidate_count": None,
                "rx0_intercept_hz_at_150s": None,
                "rx0_slope_hz_s": None,
                "rx1_intercept_hz_at_150s": None,
                "rx1_slope_hz_s": None,
                "timing_sigma_s": None,
                "timing_bound_s": None,
                "timing_at_bound": None,
                "retained_track_group_accounting": None,
            }
            if fitted is not None:
                free = fitted.get("free_parameters")
                free_count = len(free) if isinstance(free, list) else free
                row.update(
                    attempted=bool(fitted.get("attempted", True)),
                    success=bool(fitted.get("success", False)),
                    status=fitted.get("status", "finished"),
                    free_parameters=free_count,
                    assigned_groups=fitted.get("assigned_groups"),
                    fitted_objective=fitted.get("objective"),
                    runtime_s=fitted.get("elapsed_s", fitted.get("runtime_s")),
                    message=fitted.get("message"),
                    rx_policy=fitted.get("rx_policy"),
                    initialization_provenance=fitted.get("initialization_provenance"),
                    fixed_assignment_rms_hz=fitted.get("fixed_assignment_rms_hz"),
                    candidate_count=fitted.get("candidate_count"),
                    timing_sigma_s=fitted.get("timing_sigma_s"),
                    timing_bound_s=fitted.get("timing_bound_s"),
                    timing_at_bound=fitted.get("timing_at_bound"),
                    retained_track_group_accounting=json.dumps(
                        fitted.get("track_group_accounting"), sort_keys=True
                    ),
                )
                parameters = fitted.get("parameters")
                if parameters is not None and model != "track_independent":
                    for column, value in zip(
                        (
                            "rx0_intercept_hz_at_150s",
                            "rx0_slope_hz_s",
                            "rx1_intercept_hz_at_150s",
                            "rx1_slope_hz_s",
                        ),
                        parameters[2:6],
                        strict=True,
                    ):
                        row[column] = value
                if (
                    parameters is not None
                    and truth is not None
                    and fitted.get("objective") is not None
                ):
                    point = np.asarray(parameters[:2], dtype=float)
                    if np.all(np.isfinite(point)):
                        row["reference_error_km"] = float(
                            np.linalg.norm(
                                ecef(*coordinates(point))
                                - ecef(truth["latitude_deg"], truth["longitude_deg"])
                            )
                        )
                        if model != "track_independent" and data is not None:
                            loss, matched = common_score(data, parameters)
                            row["all64_nearest_loss_diagnostic"] = loss
                            row["all64_groups_within_1000hz"] = matched
                            row["common_diagnostic_status"] = (
                                "evaluated on common 64-satellite pool"
                            )
            rows.append(row)
    report = {
        "selection": selection,
        "rows": rows,
        "summary": summarize(rows),
        "fits_sha256": provenance,
        "complete": all(row["attempted"] for row in rows),
        "caveats": [
            "Conditional shortlists, not blind localization",
            "Different fitted objectives are not directly comparable",
            "Aggregate errors use successful fits only; failures stay in denominators",
            "No heldout samples; reference coordinates only read by evaluator",
        ],
    }
    (ROOT / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    write_csv(ROOT / "per-scan-comparison.csv", rows)
    write_csv(ROOT / "ds11-summary.csv", report["summary"])
    write_csv(
        ROOT / "sample-comparison.csv", [row for row in rows if row["dataset"] == "original_sample"]
    )
    print(
        json.dumps(
            {
                "complete": report["complete"],
                "attempted_cells": sum(row["attempted"] for row in rows),
                "expected_cells": len(rows),
            }
        )
    )


if __name__ == "__main__":
    main()
