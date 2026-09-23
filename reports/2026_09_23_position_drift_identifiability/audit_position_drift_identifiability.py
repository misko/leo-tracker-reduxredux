#!/usr/bin/env python3
"""Training-only local position sensitivity after CFO and scan-slope profiling."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from helper.drift_information import eigensummary, profiled_information


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_joint(path: Path):
    spec = importlib.util.spec_from_file_location("drift_identifiability_joint", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def displaced_coordinate(latitude_deg, longitude_deg, east_m, north_m):
    """Local spherical east/north displacement, adequate for a 100-m difference."""
    radius_m = 6_371_008.8
    latitude = latitude_deg + np.rad2deg(north_m / radius_m)
    longitude = longitude_deg + np.rad2deg(east_m / (radius_m * np.cos(np.deg2rad(latitude_deg))))
    return float(latitude), float(longitude)


def select_track(prediction):
    """Freeze conditional candidate/tau and the training-row constant CFO."""
    train = np.asarray(prediction.training_mask, dtype=bool)
    residual = prediction.measured_hz[None, None, train] - prediction.predictions_hz[..., train]
    cfo = residual.mean(axis=-1)
    mse = np.mean((residual - cfo[..., None]) ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], mse.shape)
    mse = np.where(visible, mse, np.inf)
    candidate, tau = np.unravel_index(np.argmin(mse), mse.shape)
    if not np.isfinite(mse[candidate, tau]):
        return None
    return int(candidate), int(tau), float(cfo[candidate, tau])


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output directory required")
    split = json.loads(args.manifest.read_text())
    joint = load_joint(args.joint_tool)
    index, bindings = {}, {}
    for block in sorted(args.replication_root.glob("block_*")):
        cache_manifest, scans = block / "cache/cache_manifest.json", block / "scans.json"
        if not cache_manifest.exists() or not scans.exists():
            continue
        bindings[block.name] = {"cache_manifest": digest(cache_manifest), "scans": digest(scans)}
        published = {row["session_id"]: row for row in json.loads(scans.read_text())}
        for row in json.loads(cache_manifest.read_text())["scans"]:
            sid = row["session_id"]
            if sid in index:
                raise ValueError(f"duplicate cached session: {sid}")
            index[sid] = (block / "cache", published[sid])
    sessions = [sid for sid in split["partitions"]["train"]["session_ids"] if sid in index][
        : args.scan_limit
    ]
    if len(sessions) != args.scan_limit:
        raise ValueError("insufficient cached frozen training sessions")

    rows, scan_results = [], []
    for sid in sessions:
        cache, published = index[sid]
        prior, source = min(
            published["priors"].items(),
            key=lambda item: item[1]["selected"]["capped_weighted_rmse_hz"],
        )
        seed = source["selected"]
        evidence, arrays = joint.load_scan_cache(cache, sid)
        selected_count = 0
        for track_index, track in enumerate(evidence["tracks"]):
            baseline = joint.prediction_for_track(
                evidence, arrays, track, seed["latitude_deg"], seed["longitude_deg"]
            )
            choice = select_track(baseline)
            if choice is None:
                continue
            candidate, tau, cfo = choice
            plus_e = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                *displaced_coordinate(
                    seed["latitude_deg"], seed["longitude_deg"], args.step_m, 0.0
                ),
            )
            minus_e = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                *displaced_coordinate(
                    seed["latitude_deg"], seed["longitude_deg"], -args.step_m, 0.0
                ),
            )
            plus_n = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                *displaced_coordinate(
                    seed["latitude_deg"], seed["longitude_deg"], 0.0, args.step_m
                ),
            )
            minus_n = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                *displaced_coordinate(
                    seed["latitude_deg"], seed["longitude_deg"], 0.0, -args.step_m
                ),
            )
            train = np.asarray(baseline.training_mask, dtype=bool)
            derivative = np.column_stack(
                (
                    (plus_e.predictions_hz[candidate, tau] - minus_e.predictions_hz[candidate, tau])
                    / (2 * args.step_m),
                    (plus_n.predictions_hz[candidate, tau] - minus_n.predictions_hz[candidate, tau])
                    / (2 * args.step_m),
                )
            )
            for observation, time_s, value in zip(
                np.asarray(track["observation_ids"])[train],
                baseline.times_s[train],
                derivative[train],
                strict=True,
            ):
                rows.append(
                    {
                        "session_id": sid,
                        "track": track_index,
                        "observation_id": str(observation),
                        "time_s": float(time_s),
                        "east_hz_per_m": float(value[0]),
                        "north_hz_per_m": float(value[1]),
                        "candidate_id": str(baseline.candidate_ids[candidate]),
                        "tau_s": float(baseline.taus_s[tau]),
                        "training_cfo_hz": cfo,
                    }
                )
            selected_count += 1
        scan_rows = [row for row in rows if row["session_id"] == sid]
        design = np.array([[row["east_hz_per_m"], row["north_hz_per_m"]] for row in scan_rows])
        ids = np.array([row["track"] for row in scan_rows])
        times = np.array([row["time_s"] for row in scan_rows])
        before, after, centered, slope = profiled_information(design, ids, times)
        scan_results.append(
            {
                "session_id": sid,
                "seed_prior": prior,
                "seed_latitude_deg": seed["latitude_deg"],
                "seed_longitude_deg": seed["longitude_deg"],
                "selected_tracks": selected_count,
                "training_rows": len(scan_rows),
                "cfo_profiled_information": eigensummary(before),
                "cfo_and_shared_scan_slope_profiled_information": eigensummary(after),
                "slope_absorption": {
                    "trace_retained_fraction": float(np.trace(after) / np.trace(before))
                    if np.trace(before)
                    else None,
                    "east_column_norm_retained_fraction": float(
                        np.linalg.norm(
                            centered[:, 0] - slope * (slope @ centered[:, 0]) / (slope @ slope)
                        )
                        ** 2
                        / np.linalg.norm(centered[:, 0]) ** 2
                    )
                    if np.linalg.norm(centered[:, 0]) and (slope @ slope)
                    else 1.0,
                    "north_column_norm_retained_fraction": float(
                        np.linalg.norm(
                            centered[:, 1] - slope * (slope @ centered[:, 1]) / (slope @ slope)
                        )
                        ** 2
                        / np.linalg.norm(centered[:, 1]) ** 2
                    )
                    if np.linalg.norm(centered[:, 1]) and (slope @ slope)
                    else 1.0,
                },
            }
        )
    # Scans have independent slopes; profiling this nuisance per scan is the stated model.
    before_all = np.zeros((2, 2))
    after_all = np.zeros((2, 2))
    for sid in sessions:
        selected = [row for row in rows if row["session_id"] == sid]
        d = np.array([[r["east_hz_per_m"], r["north_hz_per_m"]] for r in selected])
        i = np.array([r["track"] for r in selected])
        t = np.array([r["time_s"] for r in selected])
        b, a, _, _ = profiled_information(d, i, t)
        before_all += b
        after_all += a
    result = {
        "schema": "position-drift-identifiability/v1",
        "scope": (
            "first 12 cached sessions in frozen random-group training order; "
            "randomized training rows only"
        ),
        "conditional_model": (
            "per track, candidate and integer tau selected at its published "
            "lower-residual Sacramento-or-Reno seed using training rows; "
            "discrete choice is then held fixed"
        ),
        "finite_difference": {
            "central_step_m": args.step_m,
            "coordinates": "local spherical east/north displacement",
            "prediction": "public research prediction_for_track on existing conditional caches",
        },
        "nuisances": {
            "per_track_cfo": "one unconstrained intercept per selected track",
            "shared_scan_frequency_slope": (
                "one slope per scan multiplying time centred within each track; "
                "scan slopes are independently profiled"
            ),
        },
        "aggregate": {
            "training_rows": len(rows),
            "tracks": int(sum(s["selected_tracks"] for s in scan_results)),
            "cfo_profiled_information": eigensummary(before_all),
            "cfo_and_shared_scan_slope_profiled_information": eigensummary(after_all),
            "slope_trace_retained_fraction": float(np.trace(after_all) / np.trace(before_all)),
        },
        "scans": scan_results,
        "row_derivatives": rows,
        "limitations": [
            (
                "This is a descriptive local sensitivity calculation, not a calibrated "
                "CRLB or an accuracy claim."
            ),
            (
                "Candidate identity and integer tau switches are frozen, so their "
                "discontinuities and model-selection uncertainty are not represented."
            ),
            (
                "CFO, scan slope, timing, orbit, identity and unmodelled curvature "
                "can be confounded; no physical drift estimate follows."
            ),
        ],
        "bindings": {
            "partition_manifest": digest(args.manifest),
            "joint_tool": digest(args.joint_tool),
            "audit_tool": digest(Path(__file__)),
            "helper": digest(Path(__file__).parent / "helper/drift_information.py"),
            "replication_blocks": bindings,
        },
    }
    args.output.mkdir(parents=True)
    (args.output / "drift_identifiability.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result["aggregate"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-limit", type=int, default=12)
    parser.add_argument("--step-m", type=float, default=100.0)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
