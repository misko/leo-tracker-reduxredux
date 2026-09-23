#!/usr/bin/env python3
"""Aggregate the frozen blind tau-zero search over first-6/16 TRAIN scans."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

LEVELS_KM = (100.0, 50.0, 25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_single(path):
    spec = importlib.util.spec_from_file_location("long_training_single", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_session(single, directory, expected_session):
    receipt_path = directory / "cache_receipt.json"
    cache_path = directory / "state_cache.npz"
    receipt = json.loads(receipt_path.read_text())
    if receipt["session_id"] != expected_session:
        raise ValueError("cache session differs from frozen TRAIN order")
    arrays = np.load(cache_path, allow_pickle=False)
    prepared = []
    for track in receipt["prepared_evidence"]["tracks"]:
        times = np.asarray(track["times_s"], dtype=float)
        if times.max() - times.min() < 3.0:
            continue
        position, velocity = single.interpolate_track(
            arrays["position_ecef_km"], arrays["velocity_ecef_km_s"],
            arrays["receive_plus_tau_offset_ns"], times,
        )
        prepared.append({
            "track_id": track["track_id"], "times_s": times,
            "measured_hz": np.asarray(track["measured_hz"]),
            "training_mask": np.asarray(track["training_mask"], dtype=bool),
            "weight_s": int(len(np.unique(np.floor(times)))),
            "position": position, "velocity": velocity,
        })
    return {
        "session_id": expected_session,
        "prepared": prepared,
        "candidate_ids": arrays["candidate_id"],
        "weight": sum(track["weight_s"] for track in prepared),
        "receipt": receipt_path,
        "cache": cache_path,
    }


def combined_score(single, sessions, latitude, longitude, include_evaluation=False):
    weighted_loss = total_weight = 0.0
    scan_rows = []
    for session in sessions:
        objective, tracks = single.score_point(
            session["prepared"], session["candidate_ids"], latitude, longitude,
            include_evaluation,
        )
        weighted_loss += session["weight"] * objective**2
        total_weight += session["weight"]
        scan_rows.append({
            "session_id": session["session_id"],
            "training_objective_rmse_hz": objective,
            "tracks": tracks,
        })
    return float(np.sqrt(weighted_loss / total_weight)), scan_rows


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    single = load_single(args.single_tool)
    single.LEVELS_KM = LEVELS_KM
    manifest = json.loads(args.manifest.read_text())
    training = manifest["partitions"]["train"]["session_ids"]
    sessions = [
        load_session(single, args.cache_root / session, session)
        for session in training[:16]
    ]
    started = time.monotonic()
    views = []
    for count in (6, 16):
        active = sessions[:count]

        def evaluate(latitude, longitude, held=False, selected=active):
            return combined_score(single, selected, latitude, longitude, held)

        searches = [
            single.search_prior(name, prior, evaluate)
            for name, prior in single.PRIORS.items()
        ]
        for search in searches:
            coarse = [row for row in search["trace"] if row["level_km"] >= 1.5625]
            search["coarse_control_selected"] = min(
                coarse, key=lambda row: row["objective_rmse_hz"]
            )
        views.append({"scan_count": count, "session_ids": training[:count], "searches": searches})
    inference = {
        "schema": "long-training-multiscan-tau0-position/v1",
        "position_truth_used": False,
        "reserved_rows_used": False,
        "timing_s": 0.0,
        "altitude_m": 0.0,
        "levels_km": LEVELS_KM,
        "beam_width": single.BEAM,
        "views": views,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "manifest": digest(args.manifest),
            "single_tool": digest(args.single_tool),
            "tool": digest(Path(__file__)),
            "sessions": [
                {"session_id": row["session_id"], "receipt": digest(row["receipt"]),
                 "cache": digest(row["cache"])}
                for row in sessions
            ],
        },
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for view in results["views"]:
        active = sessions[: view["scan_count"]]
        for search in view["searches"]:
            point = search["selected"]
            _, scans = combined_score(
                single, active, point["latitude_deg"], point["longitude_deg"], True
            )
            capped_loss = uncapped_loss = total_weight = 0.0
            for scan, source in zip(scans, active, strict=True):
                for track, evidence in zip(
                    scan["tracks"], source["prepared"], strict=True
                ):
                    weight = evidence["weight_s"]
                    value = track.get("evaluation_rms_hz", 800.0)
                    capped_loss += weight * min(800.0, value) ** 2
                    uncapped_loss += weight * value**2
                    total_weight += weight
            point["scans"] = scans
            point["reserved_capped800_rmse_hz"] = float(
                np.sqrt(capped_loss / total_weight)
            )
            point["reserved_uncapped_rmse_hz"] = float(
                np.sqrt(uncapped_loss / total_weight)
            )
            point["reference_error_km"] = single.haversine_km(
                (point["latitude_deg"], point["longitude_deg"]), single.REFERENCE
            )
    results["reference_coordinate"] = {
        "latitude_deg": single.REFERENCE[0],
        "longitude_deg": single.REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
