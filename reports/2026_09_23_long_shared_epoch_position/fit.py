#!/usr/bin/env python3
"""Fit shared position and per-scan epoch shifts with frozen baseline identities."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

SCALES = (0.2, 1.0, 5.0)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare_scan(single, directory, baseline_scan):
    receipt_path = directory / "cache_receipt.json"
    cache_path = directory / "state_cache.npz"
    receipt = json.loads(receipt_path.read_text())
    archive = np.load(cache_path, allow_pickle=False)
    arrays = {key: archive[key] for key in archive.files}
    candidate_index = {
        str(value): index for index, value in enumerate(arrays["candidate_id"])
    }
    tracks_by_id = {
        track["track_id"]: track for track in receipt["prepared_evidence"]["tracks"]
    }
    tracks = []
    for selected in baseline_scan["tracks"]:
        if selected["candidate_id"] is None:
            raise ValueError("baseline contains unmatched track")
        source = tracks_by_id[selected["track_id"]]
        times = np.asarray(source["times_s"], dtype=float)
        index = candidate_index[selected["candidate_id"]]
        tracks.append({
            "track_id": source["track_id"],
            "candidate_id": selected["candidate_id"],
            "times_s": times,
            "measured_hz": np.asarray(source["measured_hz"], dtype=float),
            "training_mask": np.asarray(source["training_mask"], dtype=bool),
            "weight_s": int(len(np.unique(np.floor(times)))),
            "grid_ns": arrays["receive_plus_tau_offset_ns"],
            "position": arrays["position_ecef_km"][index],
            "velocity": arrays["velocity_ecef_km_s"][index],
        })
    return {
        "session_id": receipt["session_id"],
        "tracks": tracks,
        "receipt": receipt_path,
        "cache": cache_path,
    }


def interpolate_selected(track, tau_s):
    grid = track["grid_ns"]
    query = np.rint((track["times_s"] + tau_s) * 1e9).astype(np.int64)
    if np.any(query < grid[0]) or np.any(query > grid[-1]):
        raise ValueError("shifted query outside cache")
    fractional = (query - grid[0]) / float(grid[1] - grid[0])
    low = np.floor(fractional).astype(int)
    high = np.minimum(low + 1, len(grid) - 1)
    weight = fractional - low
    position = track["position"][low] * (1 - weight)[:, None]
    position += track["position"][high] * weight[:, None]
    velocity = track["velocity"][low] * (1 - weight)[:, None]
    velocity += track["velocity"][high] * weight[:, None]
    return position, velocity


def score(single, scans, point, taus, scale, include_evaluation=False):
    receiver, up = single.receiver_ecef(*point)
    capped_loss = uncapped_loss = total_weight = 0.0
    rows = []
    visibility_failures = 0
    for scan, tau in zip(scans, taus, strict=True):
        scan_rows = []
        for track in scan["tracks"]:
            position, velocity = interpolate_selected(track, tau)
            delta = position - receiver
            distance = np.linalg.norm(delta, axis=1)
            visible = bool(np.max(np.sum(delta * up, axis=1) / distance) >= 0)
            if not visible:
                visibility_failures += 1
            prediction = (
                -single.REFERENCE_RF_HZ / single.LIGHT_KM_S
                * np.sum(delta * velocity, axis=1) / distance
            )
            training = track["training_mask"]
            residual = track["measured_hz"] - prediction
            cfo = float(np.mean(residual[training]))
            error = residual - cfo
            train_rms = float(np.sqrt(np.mean(error[training] ** 2)))
            if not visible:
                train_rms = 800.0
            weight = track["weight_s"]
            capped_loss += weight * min(800.0, train_rms) ** 2
            uncapped_loss += weight * train_rms**2
            total_weight += weight
            row = {
                "track_id": track["track_id"], "candidate_id": track["candidate_id"],
                "frequency_offset_hz": cfo, "training_rms_hz": train_rms,
                "weight_s": weight,
                "visible": visible,
            }
            if include_evaluation:
                row["evaluation_rms_hz"] = (
                    float(np.sqrt(np.mean(error[~training] ** 2))) if visible else 800.0
                )
            scan_rows.append(row)
        rows.append({"session_id": scan["session_id"], "tau_s": float(tau), "tracks": scan_rows})
    prior = 800.0**2 * float(np.sum((np.asarray(taus) / scale) ** 2))
    return {
        "penalized_objective_rmse_hz": float(np.sqrt((capped_loss + prior) / total_weight)),
        "training_capped800_rmse_hz": float(np.sqrt(capped_loss / total_weight)),
        "training_uncapped_rmse_hz": float(np.sqrt(uncapped_loss / total_weight)),
        "prior_penalty_hz2_s": prior,
        "visibility_failure_count": visibility_failures,
        "rows": rows,
    }


def fit_arm(single, scans, prior_name, baseline, scale):
    prior = single.PRIORS[prior_name]
    centre = prior[:2]
    start_east = baseline["selected"]["east_km"]
    start_north = baseline["selected"]["north_km"]
    initial = np.asarray([start_east, start_north] + [0.0] * len(scans))
    calls = 0

    def objective(values):
        nonlocal calls
        calls += 1
        east, north = values[:2]
        if np.hypot(east, north) > prior[2]:
            return 1e6 + np.hypot(east, north) - prior[2]
        point = single.offset_coordinate(centre, east, north)
        return score(single, scans, point, values[2:], scale)["penalized_objective_rmse_hz"]

    started = time.monotonic()
    fit = minimize(
        objective, initial, method="Powell",
        bounds=[(-prior[2], prior[2]), (-prior[2], prior[2])] + [(-5.0, 5.0)] * len(scans),
        options={"maxfev": 300, "xtol": 0.01, "ftol": 1e-5},
    )
    powell_choices = [(objective(initial), initial), (float(fit.fun), np.asarray(fit.x))]
    _, polish_start = min(powell_choices, key=lambda row: row[0])
    polish = minimize(
        objective, polish_start, method="L-BFGS-B",
        bounds=[(-prior[2], prior[2]), (-prior[2], prior[2])] + [(-5.0, 5.0)] * len(scans),
        options={"maxiter": 100, "maxfun": 2500, "ftol": 1e-9, "eps": 1e-3},
    )
    choices = powell_choices + [(float(polish.fun), np.asarray(polish.x))]
    value, selected = min(choices, key=lambda row: row[0])
    point = single.offset_coordinate(centre, selected[0], selected[1])
    scored = score(single, scans, point, selected[2:], scale)
    return {
        "prior": prior_name, "scale_s": scale,
        "latitude_deg": point[0], "longitude_deg": point[1],
        "east_km": float(selected[0]), "north_km": float(selected[1]),
        "taus_s": selected[2:].tolist(),
        "tau_boundary_count": int(np.sum(np.isclose(np.abs(selected[2:]), 5.0, atol=1e-5))),
        "objective_calls": calls, "optimizer_success": bool(fit.success),
        "optimizer_message": str(fit.message), "runtime_s": time.monotonic() - started,
        "polish_success": bool(polish.success),
        "polish_message": str(polish.message),
        "polish_iterations": int(polish.nit),
        "polish_evaluations": int(polish.nfev),
        **{key: value for key, value in scored.items() if key != "rows"},
        "fixed_tracks": scored["rows"],
        "selected_objective_rmse_hz": value,
    }


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    single = load_module(args.single_tool, "shared_epoch_single")
    baseline = json.loads(args.baseline.read_text())
    manifest = json.loads(args.manifest.read_text())
    training = manifest["partitions"]["train"]["session_ids"]
    started = time.monotonic()
    views = []
    for view in baseline["views"]:
        count = view["scan_count"]
        arms = []
        parity_rows = []
        for baseline_search in view["searches"]:
            scans = [
                prepare_scan(single, args.cache_root / sid, baseline_scan)
                for sid, baseline_scan in zip(
                    training[:count], baseline_search["selected"]["scans"], strict=True
                )
            ]
            baseline_point = (
                baseline_search["selected"]["latitude_deg"],
                baseline_search["selected"]["longitude_deg"],
            )
            parity = score(single, scans, baseline_point, np.zeros(count), 1.0)
            parity_rows.append({
                "prior": baseline_search["prior"],
                **{key: value for key, value in parity.items() if key != "rows"},
            })
            for scale in SCALES:
                arms.append(
                    fit_arm(single, scans, baseline_search["prior"], baseline_search, scale)
                )
        views.append({
            "scan_count": count, "session_ids": training[:count],
            "baseline_parity": parity_rows, "arms": arms,
        })
    inference = {
        "schema": "conditional-shared-epoch-position/v1",
        "position_truth_used": False, "reserved_rows_used": False,
        "identity_policy": "fixed from sealed blind tau-zero baseline",
        "scales_s": SCALES, "views": views, "runtime_s": time.monotonic() - started,
        "bindings": {"manifest": digest(args.manifest), "baseline": digest(args.baseline),
                     "single_tool": digest(args.single_tool), "tool": digest(Path(__file__))},
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for view in results["views"]:
        count = view["scan_count"]
        baseline_view = next(row for row in baseline["views"] if row["scan_count"] == count)
        for arm in view["arms"]:
            baseline_search = next(
                row for row in baseline_view["searches"] if row["prior"] == arm["prior"]
            )
            scans = [
                prepare_scan(single, args.cache_root / sid, source)
                for sid, source in zip(
                    training[:count], baseline_search["selected"]["scans"], strict=True
                )
            ]
            held = score(
                single, scans, (arm["latitude_deg"], arm["longitude_deg"]),
                arm["taus_s"], arm["scale_s"], True,
            )
            tracks = [track for scan in held["rows"] for track in scan["tracks"]]
            total = sum(row["weight_s"] for row in tracks)
            capped = sum(
                row["weight_s"] * min(800.0, row["evaluation_rms_hz"]) ** 2
                for row in tracks
            )
            uncapped = sum(
                row["weight_s"] * row["evaluation_rms_hz"] ** 2 for row in tracks
            )
            arm["reserved_capped800_rmse_hz"] = float(np.sqrt(capped / total))
            arm["reserved_uncapped_rmse_hz"] = float(np.sqrt(uncapped / total))
            arm["reference_error_km"] = single.haversine_km(
                (arm["latitude_deg"], arm["longitude_deg"]), single.REFERENCE
            )
    results["reference_coordinate"] = {
        "latitude_deg": single.REFERENCE[0],
        "longitude_deg": single.REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
