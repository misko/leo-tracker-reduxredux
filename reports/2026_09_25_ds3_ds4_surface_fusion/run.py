#!/usr/bin/env python3
"""Truth-blind multi-scan fusion of sealed Sacramento objective surfaces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = Path("/srv/bulk/leo/scanner-adaptive-tle-position-v2")
MEMBERSHIP = ROOT / "reports/2026_09_25_ds3_ds4_position_iteration1/inputs.json"
REFERENCE = (37.84903264307456, -122.4856541910174)
PRIOR = (38.5816, -121.4944)
EARTH_RADIUS_KM = 6371.0088
GRID_STEP_KM = 6.25
GRID_RADIUS_KM = 243.75
QUADRATIC_POINTS = 25
SCALE_FLOOR_HZ2 = 1.0
METHODS = (
    "raw_mse",
    "delta_mse",
    "robust_scaled_delta_mse",
    "fractional_rank",
)
FORBIDDEN_INFERENCE_KEYS = (
    "reference",
    "horizontal_error",
    "ground_truth",
    "truth",
)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def compact(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(path: Path) -> None:
    expected = digest(path).removeprefix("sha256:")
    seals = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(
        seal.is_file()
        and seal.read_text().strip().split()[0].removeprefix("sha256:") == expected
        for seal in seals
    ):
        raise ValueError(f"unsealed input: {path}")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        pending = Path(handle.name)
    pending.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def source_document(session_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    manifest_path = SOURCE / session_id / "manifest.json"
    document_path = SOURCE / session_id / "document.json"
    envelope = load(manifest_path)
    outer = envelope.get("document")
    if not isinstance(outer, dict) or envelope.get("sha256") != "sha256:" + hashlib.sha256(
        compact(outer)
    ).hexdigest():
        raise ValueError(f"invalid source manifest seal: {session_id}")
    document = outer.get("document")
    if not isinstance(document, dict) or document != load(document_path):
        raise ValueError(f"source document mismatch: {session_id}")
    return document, {
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": digest(manifest_path),
        "document_file_sha256": digest(document_path),
        "storage_document_sha256": str(envelope["sha256"]),
    }


def build_units(memberships: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for dataset_name, dataset in memberships.items():
        sessions = list(map(str, dataset["sessions"]))
        units.extend(
            {
                "unit_id": f"{dataset_name}-single-{index + 1:03d}",
                "dataset": dataset_name,
                "scope": "single",
                "session_ids": [session_id],
            }
            for index, session_id in enumerate(sessions)
        )
        units.extend(
            {
                "unit_id": f"{dataset_name}-group8-{index + 1:02d}",
                "dataset": dataset_name,
                "scope": "group8",
                "session_ids": list(map(str, group)),
            }
            for index, group in enumerate(dataset["groups8"])
        )
        units.append(
            {
                "unit_id": f"{dataset_name}-full",
                "dataset": dataset_name,
                "scope": "full",
                "session_ids": sessions,
            }
        )
    units.append(
        {
            "unit_id": "DS3+DS4-full",
            "dataset": "DS3+DS4",
            "scope": "combined_full",
            "session_ids": list(map(str, memberships["DS3"]["sessions"]))
            + list(map(str, memberships["DS4"]["sessions"])),
        }
    )
    return units


def extract(output: Path) -> dict[str, Any]:
    started = time.monotonic()
    verify_seal(MEMBERSHIP)
    source_membership = load(MEMBERSHIP)
    memberships = source_membership["dataset_memberships"]
    sessions: dict[str, Any] = {}
    configuration_sha256 = None
    for dataset in memberships.values():
        for session_id in dataset["sessions"]:
            if session_id in sessions:
                raise ValueError(f"duplicate membership: {session_id}")
            document, binding = source_document(session_id)
            if document.get("analysis_id") != "scanner-adaptive-tle-position-v2":
                raise ValueError(f"wrong analysis: {session_id}")
            diagnostics = document.get("diagnostics", {})
            config = diagnostics.get("configuration", {})
            if config.get("known_position_used_for_inference") is not False:
                raise ValueError(f"source inference used known position: {session_id}")
            current_configuration = document.get("configuration_sha256")
            if configuration_sha256 is None:
                configuration_sha256 = current_configuration
            if current_configuration != configuration_sha256:
                raise ValueError("mixed source configurations")
            points = diagnostics.get("evaluated_points", {}).get("sacramento", [])
            if len(points) != 400:
                raise ValueError(f"expected 400 Sacramento points: {session_id}")
            surface = []
            seen = set()
            for point in points:
                key = (float(point["east_km"]), float(point["north_km"]))
                if key in seen:
                    raise ValueError(f"duplicate point {key}: {session_id}")
                seen.add(key)
                surface.append(
                    {
                        "east_km": key[0],
                        "north_km": key[1],
                        "capped_weighted_rmse_hz": float(point["capped_weighted_rmse_hz"]),
                        "matched_track_count": int(point["matched_track_count"]),
                        "qualifying_observation_count": int(
                            point["qualifying_observation_count"]
                        ),
                    }
                )
            sessions[session_id] = {
                "session_id": session_id,
                "surface": surface,
                "source": binding,
            }
    units = build_units(memberships)
    overlap: dict[str, Any] = {}
    for unit in units:
        sets = [
            {
                (point["east_km"], point["north_km"])
                for point in sessions[session_id]["surface"]
            }
            for session_id in unit["session_ids"]
        ]
        intersection = set.intersection(*sets)
        union = set.union(*sets)
        exact_objective = []
        for east_km, north_km in intersection:
            per_session = []
            for session_id in unit["session_ids"]:
                row = next(
                    point
                    for point in sessions[session_id]["surface"]
                    if point["east_km"] == east_km and point["north_km"] == north_km
                )
                per_session.append(row["capped_weighted_rmse_hz"] ** 2)
            exact_objective.append((float(np.mean(per_session)), east_km, north_km))
        exact_minimum = min(exact_objective)
        overlap[unit["unit_id"]] = {
            "session_count": len(sets),
            "exact_intersection_count": len(intersection),
            "exact_union_count": len(union),
            "raw_mse_exact_intersection_minimum": {
                "east_km": exact_minimum[1],
                "north_km": exact_minimum[2],
                "mean_capped_mse_hz2": exact_minimum[0],
            },
        }
    result = {
        "schema": "ds3-ds4-surface-fusion-inputs/v1",
        "complete": True,
        "truth_blind": True,
        "known_position_used_for_inference": False,
        "reference_coordinate_present": False,
        "runner": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        "membership_source": {"path": str(MEMBERSHIP), "sha256": digest(MEMBERSHIP)},
        "source_analysis": "scanner-adaptive-tle-position-v2",
        "source_configuration_sha256": configuration_sha256,
        "datasets": memberships,
        "units": units,
        "exact_overlap_audit": overlap,
        "sessions": sessions,
        "runtime_s": time.monotonic() - started,
    }
    write_sealed(output, result)
    return result


def common_grid() -> np.ndarray:
    values = np.arange(-GRID_RADIUS_KM, GRID_RADIUS_KM + 0.5 * GRID_STEP_KM, GRID_STEP_KM)
    return np.asarray(
        [
            (east, north)
            for east in values
            for north in values
            if east * east + north * north <= GRID_RADIUS_KM**2
        ],
        dtype=float,
    )


def fractional_rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks / max(len(values) - 1, 1)


def transform_surface(mse: np.ndarray, method: str) -> np.ndarray:
    delta = mse - float(np.min(mse))
    if method == "raw_mse":
        return mse
    if method == "delta_mse":
        return delta
    if method == "robust_scaled_delta_mse":
        scale = max(float(np.quantile(mse, 0.75) - np.quantile(mse, 0.25)), SCALE_FLOOR_HZ2)
        return delta / scale
    if method == "fractional_rank":
        return fractional_rank(mse)
    raise ValueError(method)


def interpolate_session(surface: list[dict[str, Any]], grid: np.ndarray, method: str):
    points = np.asarray([[row["east_km"], row["north_km"]] for row in surface], dtype=float)
    rmse = np.asarray([row["capped_weighted_rmse_hz"] for row in surface], dtype=float)
    transformed = transform_surface(rmse**2, method)
    interpolated = np.asarray(LinearNDInterpolator(points, transformed)(grid), dtype=float)
    nearest = np.asarray(cKDTree(points).query(grid)[0], dtype=float)
    return interpolated, nearest


def quadratic_refine(points: np.ndarray, objective: np.ndarray) -> dict[str, Any]:
    discrete_index = int(np.argmin(objective))
    discrete = points[discrete_index]
    distance = np.linalg.norm(points - discrete, axis=1)
    local_indices = np.argsort(distance, kind="stable")[:QUADRATIC_POINTS]
    local = points[local_indices]
    scaled = (local - discrete) / GRID_STEP_KM
    design = np.column_stack(
        (
            np.ones(len(scaled)),
            scaled[:, 0],
            scaled[:, 1],
            0.5 * scaled[:, 0] ** 2,
            scaled[:, 0] * scaled[:, 1],
            0.5 * scaled[:, 1] ** 2,
        )
    )
    values = objective[local_indices]
    coefficients, _, rank, singular_values = np.linalg.lstsq(design, values, rcond=None)
    hessian = np.asarray(
        [[coefficients[3], coefficients[4]], [coefficients[4], coefficients[5]]],
        dtype=float,
    )
    eigenvalues = np.linalg.eigvalsh(hessian)
    fit = design @ coefficients
    total = float(np.sum((values - float(np.mean(values))) ** 2))
    residual = float(np.sum((values - fit) ** 2))
    r_squared = 1.0 - residual / total if total > 0 else 1.0
    positive_curvature = bool(eigenvalues[0] > 0)
    if positive_curvature:
        offset_scaled = -np.linalg.solve(hessian, coefficients[1:3])
        refined = discrete + offset_scaled * GRID_STEP_KM
    else:
        offset_scaled = np.asarray([math.nan, math.nan])
        refined = np.asarray([math.nan, math.nan])
    displacement_km = float(np.linalg.norm(refined - discrete)) if positive_curvature else None
    local_radius_km = float(np.max(np.linalg.norm(local - discrete, axis=1)))
    inside_local_support = bool(
        positive_curvature and displacement_km is not None and displacement_km <= local_radius_km
    )
    inside_prior = bool(positive_curvature and float(np.linalg.norm(refined)) < GRID_RADIUS_KM)
    interior_grid_minimum = bool(float(np.linalg.norm(discrete)) + local_radius_km < GRID_RADIUS_KM)
    qualified = bool(
        positive_curvature
        and inside_local_support
        and inside_prior
        and interior_grid_minimum
        and rank == 6
        and r_squared >= 0.80
    )
    return {
        "discrete_east_km": float(discrete[0]),
        "discrete_north_km": float(discrete[1]),
        "refined_east_km": float(refined[0]) if positive_curvature else None,
        "refined_north_km": float(refined[1]) if positive_curvature else None,
        "quadratic_qualified": qualified,
        "quadratic_reasons": {
            "positive_curvature": positive_curvature,
            "stationary_point_inside_local_support": inside_local_support,
            "stationary_point_inside_prior": inside_prior,
            "interior_grid_minimum": interior_grid_minimum,
            "design_full_rank": bool(rank == 6),
            "r_squared_at_least_0_80": bool(r_squared >= 0.80),
        },
        "quadratic_point_count": len(local),
        "quadratic_local_radius_km": local_radius_km,
        "quadratic_displacement_km": displacement_km,
        "quadratic_r_squared": r_squared,
        "hessian_eigenvalues": list(map(float, eigenvalues)),
        "hessian_condition": (
            float(eigenvalues[-1] / eigenvalues[0]) if eigenvalues[0] > 0 else None
        ),
        "design_singular_values": list(map(float, singular_values)),
        "reported_east_km": float(refined[0]) if qualified else float(discrete[0]),
        "reported_north_km": float(refined[1]) if qualified else float(discrete[1]),
        "reported_estimator": "quadratic" if qualified else "discrete_grid",
    }


def infer_unit(
    unit: dict[str, Any], sessions: dict[str, Any], grid: np.ndarray, method: str
) -> dict[str, Any]:
    values, nearest = [], []
    for session_id in unit["session_ids"]:
        interpolated, support = interpolate_session(sessions[session_id]["surface"], grid, method)
        values.append(interpolated)
        nearest.append(support)
    matrix = np.asarray(values)
    support_matrix = np.asarray(nearest)
    valid = np.all(np.isfinite(matrix), axis=0)
    valid_grid = grid[valid]
    aggregate = np.mean(matrix[:, valid], axis=0)
    refined = quadratic_refine(valid_grid, aggregate)
    selected = np.asarray([refined["reported_east_km"], refined["reported_north_km"]])
    selected_grid_index = int(np.argmin(np.linalg.norm(valid_grid - selected, axis=1)))
    support = support_matrix[:, valid][:, selected_grid_index]
    return {
        **{key: unit[key] for key in ("unit_id", "dataset", "scope", "session_ids")},
        "method": method,
        "session_weighting": "equal",
        "objective_aggregation": "arithmetic mean after per-scan transform",
        "valid_common_grid_point_count": int(np.count_nonzero(valid)),
        "interpolation_support_at_reported_cell_km": {
            "median": float(np.median(support)),
            "p90": float(np.quantile(support, 0.90)),
            "maximum": float(np.max(support)),
            "exact_session_count": int(np.count_nonzero(support == 0)),
        },
        **refined,
    }


def infer(inputs_path: Path, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    verify_seal(inputs_path)
    inputs = load(inputs_path)
    if inputs.get("reference_coordinate_present") is not False:
        raise ValueError("inference input reference attestation failed")
    grid = common_grid()
    results = [
        infer_unit(unit, inputs["sessions"], grid, method)
        for method in METHODS
        for unit in inputs["units"]
    ]
    value = {
        "schema": "ds3-ds4-surface-fusion-inference/v1",
        "complete": True,
        "truth_blind": True,
        "known_position_used_for_inference": False,
        "reference_coordinate_present": False,
        "input": {"path": str(inputs_path), "sha256": digest(inputs_path)},
        "runner": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        "method_contract": {
            "methods": list(METHODS),
            "common_grid_step_km": GRID_STEP_KM,
            "common_grid_radius_km": GRID_RADIUS_KM,
            "interpolation": "piecewise-linear Delaunay per scan",
            "session_weighting": "equal",
            "quadratic_nearest_point_count": QUADRATIC_POINTS,
            "quadratic_r_squared_gate": 0.80,
            "robust_scale": "sample-surface MSE IQR",
            "robust_scale_floor_hz2": SCALE_FLOOR_HZ2,
            "rank_transform": "fractional rank over each scan's 400 evaluated points",
        },
        "results": results,
        "runtime_s": time.monotonic() - started,
    }
    lowered = canonical(value).lower()
    if any(key in lowered for key in FORBIDDEN_INFERENCE_KEYS):
        # The two explicit false attestations are permitted; no coordinates or error are present.
        scrubbed = lowered.replace('"reference_coordinate_present": false', "")
        scrubbed = scrubbed.replace('"known_position_used_for_inference": false', "")
        scrubbed = scrubbed.replace('"truth_blind": true', "")
        if any(key in scrubbed for key in FORBIDDEN_INFERENCE_KEYS):
            raise ValueError("forbidden scoring data leaked into inference")
    write_sealed(output, value)
    return value


def coordinates(east_km: float, north_km: float) -> tuple[float, float]:
    angular = math.hypot(east_km, north_km) / EARTH_RADIUS_KM
    bearing = math.atan2(east_km, north_km)
    lat0, lon0 = map(math.radians, PRIOR)
    latitude = math.asin(
        math.sin(lat0) * math.cos(angular)
        + math.cos(lat0) * math.sin(angular) * math.cos(bearing)
    )
    longitude = lon0 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat0),
        math.cos(angular) - math.sin(lat0) * math.sin(latitude),
    )
    return math.degrees(latitude), (math.degrees(longitude) + 180) % 360 - 180


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lat2 = map(math.radians, (first[0], second[0]))
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second[1] - first[1])
    term = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        delta_lon / 2
    ) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(term)))


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for method in METHODS:
        for dataset in ("DS3", "DS4", "DS3+DS4"):
            for scope in ("single", "group8", "full", "combined_full"):
                selected = [
                    row
                    for row in rows
                    if row["method"] == method
                    and row["dataset"] == dataset
                    and row["scope"] == scope
                ]
                if not selected:
                    continue
                errors = np.asarray([row["horizontal_error_km"] for row in selected])
                summaries.append(
                    {
                        "method": method,
                        "dataset": dataset,
                        "scope": scope,
                        "unit_count": len(selected),
                        "qualified_count": sum(row["quadratic_qualified"] for row in selected),
                        "median_error_km": float(np.median(errors)),
                        "p90_error_km": float(np.quantile(errors, 0.90)),
                        "minimum_error_km": float(np.min(errors)),
                        "maximum_error_km": float(np.max(errors)),
                    }
                )
    return summaries


def postseal(inference_path: Path, output: Path) -> dict[str, Any]:
    import matplotlib.pyplot as plt

    started = time.monotonic()
    verify_seal(inference_path)
    inference = load(inference_path)
    scored = []
    for row in inference["results"]:
        latitude, longitude = coordinates(row["reported_east_km"], row["reported_north_km"])
        scored.append(
            {
                **row,
                "latitude_deg": latitude,
                "longitude_deg": longitude,
                "horizontal_error_km": distance_km((latitude, longitude), REFERENCE),
            }
        )
    summaries = summarize(scored)
    value = {
        "schema": "ds3-ds4-surface-fusion-postseal/v1",
        "complete": True,
        "inference": {"path": str(inference_path), "sha256": digest(inference_path)},
        "reference": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "results": scored,
        "summaries": summaries,
        "runtime_s": time.monotonic() - started,
    }
    write_sealed(output, value)

    csv_path = output.parent / "summary.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    figure, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    labels = {
        "raw_mse": "Raw MSE",
        "delta_mse": "Delta MSE",
        "robust_scaled_delta_mse": "IQR-scaled delta",
        "fractional_rank": "Fractional rank",
    }
    x = np.arange(len(METHODS))
    for axis, dataset in zip(axes, ("DS3", "DS4"), strict=True):
        group_values = []
        full_values = []
        for method in METHODS:
            group_values.append(
                next(
                    item["median_error_km"]
                    for item in summaries
                    if item["dataset"] == dataset
                    and item["scope"] == "group8"
                    and item["method"] == method
                )
            )
            full_values.append(
                next(
                    item["median_error_km"]
                    for item in summaries
                    if item["dataset"] == dataset
                    and item["scope"] == "full"
                    and item["method"] == method
                )
            )
        axis.bar(x - 0.18, group_values, 0.36, label="Group8 median")
        axis.bar(x + 0.18, full_values, 0.36, label="Full dataset")
        axis.axhline(1.0, color="red", linestyle="--", linewidth=1, label="1 km target")
        axis.set_title(dataset)
        axis.set_ylabel("Horizontal error (km)")
        axis.set_xticks(x, [labels[method] for method in METHODS], rotation=20, ha="right")
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    figure.suptitle("Truth-blind objective-surface fusion: post-seal position error")
    figure.savefig(output.parent / "comparison.png", dpi=180)
    plt.close(figure)

    truth_angular = distance_km(PRIOR, REFERENCE)
    lat0, lat1 = map(math.radians, (PRIOR[0], REFERENCE[0]))
    delta_lon = math.radians(REFERENCE[1] - PRIOR[1])
    bearing = math.atan2(
        math.sin(delta_lon) * math.cos(lat1),
        math.cos(lat0) * math.sin(lat1)
        - math.sin(lat0) * math.cos(lat1) * math.cos(delta_lon),
    )
    truth_east = truth_angular * math.sin(bearing)
    truth_north = truth_angular * math.cos(bearing)
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.5), constrained_layout=True)
    for axis, dataset in zip(axes, ("DS3", "DS4"), strict=True):
        groups = [
            row
            for row in scored
            if row["method"] == "raw_mse"
            and row["dataset"] == dataset
            and row["scope"] == "group8"
        ]
        full = next(
            row
            for row in scored
            if row["method"] == "raw_mse"
            and row["dataset"] == dataset
            and row["scope"] == "full"
        )
        axis.scatter(
            [row["reported_east_km"] for row in groups],
            [row["reported_north_km"] for row in groups],
            label="Group8 estimates",
            alpha=0.8,
        )
        axis.scatter(
            [full["reported_east_km"]],
            [full["reported_north_km"]],
            marker="*",
            s=180,
            label="Full estimate",
        )
        axis.scatter([truth_east], [truth_north], marker="x", s=100, label="Post-seal reference")
        axis.set_title(dataset)
        axis.set_xlabel("East of Sacramento prior (km)")
        axis.set_ylabel("North of Sacramento prior (km)")
        axis.grid(alpha=0.25)
        axis.set_aspect("equal", adjustable="datalim")
        axis.legend()
    figure.suptitle("Raw-MSE surface fusion positions")
    figure.savefig(output.parent / "positions.png", dpi=180)
    plt.close(figure)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--output", type=Path, default=HERE / "inputs.json")
    infer_parser = subparsers.add_parser("infer")
    infer_parser.add_argument("--inputs", type=Path, default=HERE / "inputs.json")
    infer_parser.add_argument("--output", type=Path, default=HERE / "inference.json")
    score_parser = subparsers.add_parser("postseal")
    score_parser.add_argument("--inference", type=Path, default=HERE / "inference.json")
    score_parser.add_argument("--output", type=Path, default=HERE / "postseal.json")
    args = parser.parse_args()
    if args.command == "extract":
        result = extract(args.output)
    elif args.command == "infer":
        result = infer(args.inputs, args.output)
    else:
        result = postseal(args.inference, args.output)
    print(json.dumps({"complete": result["complete"], "schema": result["schema"]}))


if __name__ == "__main__":
    main()
