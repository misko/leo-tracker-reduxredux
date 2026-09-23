#!/usr/bin/env python3
"""Fit the sealed direct-SGP4 synthetic position control."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

LIGHT_KM_S = 299792.458
REFERENCE_RF_HZ = 11.2e9
PRIORS = {
    "sacramento": (38.5816, -121.4944, 250.0),
    "reno": (39.5296, -119.8138, 500.0),
}
CASES = (
    "zero_noise",
    "gaussian_300hz",
    "gaussian_300hz_satellite_epoch_0p3s",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def receiver_ecef(latitude_deg, longitude_deg):
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    a, flattening = 6378.137, 1 / 298.257223563
    eccentricity2 = flattening * (2 - flattening)
    radius = a / np.sqrt(1 - eccentricity2 * np.sin(latitude) ** 2)
    return np.asarray([
        radius * np.cos(latitude) * np.cos(longitude),
        radius * np.cos(latitude) * np.sin(longitude),
        radius * (1 - eccentricity2) * np.sin(latitude),
    ])


def offset_coordinate(centre, east_km, north_km):
    distance = float(np.hypot(east_km, north_km))
    if distance == 0:
        return float(centre[0]), float(centre[1])
    bearing = np.arctan2(east_km, north_km)
    angular = distance / 6371.0088
    latitude, longitude = np.deg2rad(centre)
    target_latitude = np.arcsin(
        np.sin(latitude) * np.cos(angular)
        + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    target_longitude = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(target_latitude),
    )
    return float(np.rad2deg(target_latitude)), float(np.rad2deg(target_longitude))


def haversine_km(left, right):
    lat1, lat2 = np.deg2rad([left[0], right[0]])
    dlat, dlon = lat2 - lat1, np.deg2rad(right[1] - left[1])
    value = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(2 * 6371.0088 * np.arctan2(np.sqrt(value), np.sqrt(1 - value)))


def local_offsets(parameters, radius):
    denominator = np.sqrt(1.0 + float(np.dot(parameters, parameters)))
    return radius * np.asarray(parameters) / denominator


def predict(arrays, point):
    receiver = receiver_ecef(*point)
    delta = arrays["position_ecef_km"] - receiver
    distance = np.linalg.norm(delta, axis=1)
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(
        delta * arrays["velocity_ecef_km_s"], axis=1
    ) / distance


def residual_rows(arrays, measured, point, training_only):
    prediction = predict(arrays, point)
    rows, details = [], []
    for index, (start, count, weight) in enumerate(zip(
        arrays["track_start"], arrays["track_count"], arrays["track_weight_s"], strict=True
    )):
        selection = slice(int(start), int(start + count))
        training = arrays["training_mask"][selection]
        raw = measured[selection] - prediction[selection]
        cfo = float(np.mean(raw[training]))
        error = raw - cfo
        chosen = error[training] if training_only else error
        if training_only:
            rows.extend(chosen * np.sqrt(float(weight) / np.count_nonzero(training)))
        details.append({
            "track_index": index, "frequency_offset_hz": cfo,
            "training_rms_hz": float(np.sqrt(np.mean(error[training] ** 2))),
            "held_rms_hz": float(np.sqrt(np.mean(error[~training] ** 2))),
            "weight_s": int(weight),
        })
    return np.asarray(rows), details


def summarize(details, key):
    total = sum(row["weight_s"] for row in details)
    uncapped = sum(row["weight_s"] * row[key] ** 2 for row in details)
    capped = sum(row["weight_s"] * min(800.0, row[key]) ** 2 for row in details)
    return float(np.sqrt(capped / total)), float(np.sqrt(uncapped / total))


def fit_one(arrays, measured, prior_name):
    centre = PRIORS[prior_name][:2]
    radius = PRIORS[prior_name][2]
    calls = 0

    def residual(parameters):
        nonlocal calls
        calls += 1
        east, north = local_offsets(parameters, radius)
        point = offset_coordinate(centre, east, north)
        return residual_rows(arrays, measured, point, True)[0]

    started = time.monotonic()
    fitted = least_squares(
        residual, np.zeros(2), jac="3-point", x_scale="jac", diff_step=1e-5,
        ftol=1e-13, xtol=1e-13, gtol=1e-13, max_nfev=500,
    )
    east, north = local_offsets(fitted.x, radius)
    point = offset_coordinate(centre, east, north)
    _rows, details = residual_rows(arrays, measured, point, True)
    capped, uncapped = summarize(details, "training_rms_hz")
    return {
        "prior": prior_name, "latitude_deg": point[0], "longitude_deg": point[1],
        "east_km": float(east), "north_km": float(north),
        "prior_radius_km": radius,
        "prior_boundary_margin_km": float(radius - np.hypot(east, north)),
        "training_capped800_rmse_hz": capped,
        "training_uncapped_rmse_hz": uncapped,
        "optimizer_success": bool(fitted.success), "optimizer_status": int(fitted.status),
        "optimizer_message": str(fitted.message), "optimizer_iterations": int(fitted.nfev),
        "optimizer_evaluations": calls, "optimality": float(fitted.optimality),
        "cost": float(fitted.cost), "runtime_s": time.monotonic() - started,
        "track_training": details,
    }


def invariant_projection(row):
    excluded = {"case", "runtime_s", "track_training"}
    return {key: value for key, value in row.items() if key not in excluded}


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh result directory required")
    archive = np.load(args.materialized, allow_pickle=False)
    arrays = {key: archive[key] for key in archive.files}
    archive.close()
    started = time.monotonic()
    fits = []
    for case in CASES:
        measured = arrays[f"{case}_hz"]
        for prior in PRIORS:
            fits.append({"case": case, **fit_one(arrays, measured, prior)})
    inference = {
        "schema": "long-position-synthetic-control-inference/v1",
        "control_only": True, "generator_coordinate_available_to_fit": False,
        "identity_policy": "known Sacramento baseline generating identities",
        "epoch_fit_s": 0.0, "cases": CASES, "fits": fits,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
            "materialized_npz": digest(args.materialized), "tool": digest(Path(__file__)),
        },
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )

    perturbed = {}
    observation_index = np.arange(len(arrays["training_mask"]), dtype=float)
    held_perturbation = (1_000_000.0 + 7919.0 * observation_index) * (~arrays["training_mask"])
    for case in CASES:
        changed = arrays[f"{case}_hz"] + held_perturbation
        for prior in PRIORS:
            perturbed[(case, prior)] = fit_one(arrays, changed, prior)
    invariance_rows = []
    for original in fits:
        rerun = perturbed[(original["case"], original["prior"])]
        matches = invariant_projection(original) == invariant_projection(rerun)
        invariance_rows.append({
            "case": original["case"], "prior": original["prior"],
            "bit_identical_fit_record": matches,
            "held_perturbation_minimum_absolute_hz": 1_000_000.0,
        })

    materialization = json.loads(args.materialization_receipt.read_text())
    truth = materialization["generator"]
    results = json.loads(payload)
    for row in results["fits"]:
        measured = arrays[f"{row['case']}_hz"]
        _values, details = residual_rows(
            arrays, measured, (row["latitude_deg"], row["longitude_deg"]), False
        )
        held_capped, held_uncapped = summarize(details, "held_rms_hz")
        row["held_capped800_rmse_hz"] = held_capped
        row["held_uncapped_rmse_hz"] = held_uncapped
        row["postseal_error_km"] = haversine_km(
            (row["latitude_deg"], row["longitude_deg"]),
            (truth["latitude_deg"], truth["longitude_deg"]),
        )
        row["track_evaluation"] = details
    noiseless = [row for row in results["fits"] if row["case"] == "zero_noise"]
    results["postseal_generator"] = truth
    results["postseal_checks"] = {
        "noiseless_recovery": {
            "threshold_km": 0.3, "residual_threshold_hz": 0.01,
            "passed": all(
                row["optimizer_success"] and row["prior_boundary_margin_km"] >= 0
                and row["postseal_error_km"] < 0.3
                and row["training_uncapped_rmse_hz"] < 0.01
                and row["held_uncapped_rmse_hz"] < 0.01
                for row in noiseless
            ),
        },
        "held_frequency_invariance": {
            "passed": all(row["bit_identical_fit_record"] for row in invariance_rows),
            "reruns": invariance_rows,
        },
    }
    results["bindings"]["materialization_receipt"] = digest(args.materialization_receipt)
    result_payload = json.dumps(results, indent=2, sort_keys=True) + "\n"
    (args.output / "results.json").write_text(result_payload)
    (args.output / "results.sha256").write_text(
        hashlib.sha256(result_payload.encode()).hexdigest() + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialized", type=Path, required=True)
    parser.add_argument("--materialization-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
