#!/usr/bin/env python3
"""Bounded blind tau-zero position search over one compact long-TRAIN cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

LIGHT_KM_S = 299792.458
REFERENCE_RF_HZ = 11.2e9
REFERENCE = (37.84903264307456, -122.4856541910174)
PRIORS = {
    "sacramento": (38.5816, -121.4944, 250.0),
    "reno": (39.5296, -119.8138, 500.0),
}
LEVELS_KM = (100.0, 50.0, 25.0, 12.5, 6.25, 3.125, 1.5625)
BEAM = 3


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def receiver_ecef(latitude_deg, longitude_deg):
    lat, lon = np.deg2rad([latitude_deg, longitude_deg])
    a, f = 6378.137, 1 / 298.257223563
    e2 = f * (2 - f)
    radius = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    point = np.asarray(
        [radius * np.cos(lat) * np.cos(lon), radius * np.cos(lat) * np.sin(lon),
         radius * (1 - e2) * np.sin(lat)]
    )
    up = np.asarray([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return point, up


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


def interpolate_track(position, velocity, grid_ns, times_s):
    query = np.rint(np.asarray(times_s) * 1e9).astype(np.int64)
    if np.any(query < grid_ns[0]) or np.any(query > grid_ns[-1]):
        raise ValueError("track query lies outside regular cache")
    fractional = (query - grid_ns[0]) / float(grid_ns[1] - grid_ns[0])
    low = np.floor(fractional).astype(int)
    high = np.minimum(low + 1, len(grid_ns) - 1)
    weight = fractional - low
    pos = position[:, low] * (1 - weight)[None, :, None]
    pos += position[:, high] * weight[None, :, None]
    vel = velocity[:, low] * (1 - weight)[None, :, None]
    vel += velocity[:, high] * weight[None, :, None]
    return pos, vel


def score_point(prepared, candidate_ids, latitude, longitude, include_evaluation=False):
    receiver, up = receiver_ecef(latitude, longitude)
    total_weight = loss = 0.0
    selected = []
    for track in prepared:
        delta = track["position"] - receiver
        distance = np.linalg.norm(delta, axis=-1)
        prediction = (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * track["velocity"], axis=-1)
            / distance
        )
        visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0
        training = track["training_mask"]
        residual = track["measured_hz"][None, :] - prediction
        offsets = np.mean(residual[:, training], axis=1)
        errors = residual - offsets[:, None]
        rms = np.sqrt(np.mean(errors[:, training] ** 2, axis=1))
        rms = np.where(visible, rms, np.inf)
        weight = track["weight_s"]
        total_weight += weight
        if not np.any(np.isfinite(rms)):
            loss += weight * 800.0**2
            selected.append({"track_id": track["track_id"], "candidate_id": None})
            continue
        winner = int(np.argmin(rms))
        row = {
            "track_id": track["track_id"],
            "candidate_id": str(candidate_ids[winner]),
            "frequency_offset_hz": float(offsets[winner]),
            "training_rms_hz": float(rms[winner]),
            "weight_s": weight,
        }
        loss += weight * min(800.0, row["training_rms_hz"]) ** 2
        if include_evaluation:
            held = errors[winner, ~training]
            row["evaluation_rms_hz"] = float(np.sqrt(np.mean(held**2)))
        selected.append(row)
    return float(np.sqrt(loss / total_weight)), selected


def diverse_best(rows, spacing, count=BEAM):
    retained = []
    def order(value):
        return value["objective_rmse_hz"], value["east_km"], value["north_km"]
    for row in sorted(rows, key=order):
        separated = all(
            np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"])
            >= spacing
            for old in retained
        )
        if separated:
            retained.append(row)
        if len(retained) == count:
            break
    return retained


def search_prior(name, prior, evaluate):
    centre = prior[:2]
    radius = prior[2]
    cache, trace = {}, []

    def visit(east, north, level):
        key = (round(east, 8), round(north, 8))
        if key not in cache:
            latitude, longitude = offset_coordinate(centre, east, north)
            if haversine_km(centre, (latitude, longitude)) > radius + 1e-9:
                raise ValueError("search trial escaped its frozen prior disk")
            objective, _ = evaluate(latitude, longitude, False)
            cache[key] = {"east_km": east, "north_km": north, "latitude_deg": latitude,
                          "longitude_deg": longitude, "objective_rmse_hz": objective}
            trace.append({"level_km": level, **cache[key]})
        return cache[key]

    axis = np.arange(-radius, radius + 0.1, LEVELS_KM[0])
    current = [visit(float(e), float(n), LEVELS_KM[0]) for e in axis for n in axis
               if np.hypot(e, n) <= radius]
    beam = diverse_best(current, LEVELS_KM[0])
    for spacing in LEVELS_KM[1:]:
        candidates = list(beam)
        for parent in beam:
            for de in (-spacing, 0.0, spacing):
                for dn in (-spacing, 0.0, spacing):
                    east, north = parent["east_km"] + de, parent["north_km"] + dn
                    if np.hypot(east, north) <= radius:
                        candidates.append(visit(east, north, spacing))
        beam = diverse_best(candidates, spacing)
    return {"prior": name, "evaluations": len(cache), "trace": trace,
            "selected": min(cache.values(), key=lambda row: row["objective_rmse_hz"])}


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    manifest = json.loads(args.manifest.read_text())
    receipt = json.loads(args.receipt.read_text())
    session = manifest["partitions"]["train"]["session_ids"][0]
    if session != "scan-hop-85afa91453f8847b" or receipt["session_id"] != session:
        raise ValueError("first frozen TRAIN session mismatch")
    arrays = np.load(args.cache, allow_pickle=False)
    tracks = receipt["prepared_evidence"]["tracks"]
    prepared = []
    for track in tracks:
        times = np.asarray(track["times_s"], dtype=float)
        if times.max() - times.min() < 3.0:
            continue
        position, velocity = interpolate_track(
            arrays["position_ecef_km"], arrays["velocity_ecef_km_s"],
            arrays["receive_plus_tau_offset_ns"], times,
        )
        prepared.append({"track_id": track["track_id"], "times_s": times,
                         "measured_hz": np.asarray(track["measured_hz"]),
                         "training_mask": np.asarray(track["training_mask"], dtype=bool),
                         "weight_s": int(len(np.unique(np.floor(times)))),
                         "position": position, "velocity": velocity})
    candidate_ids = arrays["candidate_id"]
    def evaluate(lat, lon, held=False):
        return score_point(prepared, candidate_ids, lat, lon, held)
    started = time.monotonic()
    searches = [search_prior(name, prior, evaluate) for name, prior in PRIORS.items()]
    inference = {"schema": "long-training-tau0-position/v1", "session_id": session,
                 "position_truth_used": False, "reserved_rows_used": False,
                 "candidate_scope": receipt["candidate_policy"], "altitude_m": 0.0,
                 "timing_s": 0.0, "levels_km": LEVELS_KM, "beam_width": BEAM,
                 "eligible_tracks": len(prepared), "candidate_count": len(candidate_ids),
                 "searches": searches, "runtime_s": time.monotonic() - started,
                 "bindings": {"manifest": digest(args.manifest), "receipt": digest(args.receipt),
                              "cache": digest(args.cache), "tool": digest(Path(__file__))}}
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for search in results["searches"]:
        point = search["selected"]
        _, tracks = evaluate(point["latitude_deg"], point["longitude_deg"], True)
        matched = [row for row in tracks if row["candidate_id"] is not None]
        total = sum(row["weight_s"] for row in matched)
        search["selected"]["tracks"] = tracks
        capped = sum(
            row["weight_s"] * min(800.0, row["evaluation_rms_hz"]) ** 2
            for row in matched
        )
        uncapped = sum(
            row["weight_s"] * row["evaluation_rms_hz"] ** 2 for row in matched
        )
        search["selected"]["reserved_capped800_rmse_hz"] = float(np.sqrt(capped / total))
        search["selected"]["reserved_uncapped_rmse_hz"] = float(
            np.sqrt(uncapped / total)
        )
        search["selected"]["reference_error_km"] = haversine_km(
            (point["latitude_deg"], point["longitude_deg"]), REFERENCE
        )
    results["reference_coordinate"] = {
        "latitude_deg": REFERENCE[0],
        "longitude_deg": REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
