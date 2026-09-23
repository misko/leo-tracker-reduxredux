#!/usr/bin/env python3
"""Fit one host-bracket-constrained timing offset per scan during spatial inference."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

ARMS = (
    ("tau0_capped800", "tau0", "capped800"),
    ("shared_bracket_capped800", "bracket", "capped800"),
    ("shared_bracket_robust150", "bracket", "pseudo_huber_150hz"),
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def profile_track_by_tau(prediction, include_evaluation=False):
    measured = np.asarray(prediction.measured_hz, dtype=float)
    training = np.asarray(prediction.training_mask, dtype=bool)
    if not np.any(training):
        raise ValueError("track has no training observations")
    model = np.asarray(prediction.predictions_hz, dtype=float)
    residual = measured[None, None, training] - model[..., training]
    offset = np.mean(residual, axis=-1)
    mse = np.mean((residual - offset[..., None]) ** 2, axis=-1)
    mse = np.where(np.asarray(prediction.visible)[:, None], mse, np.inf)
    rows = []
    for tau_index, tau in enumerate(prediction.taus_s):
        candidate = int(np.argmin(mse[:, tau_index]))
        if not np.isfinite(mse[candidate, tau_index]):
            rows.append(None)
            continue
        row = {
            "candidate_id": str(prediction.candidate_ids[candidate]),
            "candidate_index": candidate,
            "tau_s": float(tau),
            "offset_hz": float(offset[candidate, tau_index]),
            "training_rms_hz": float(np.sqrt(mse[candidate, tau_index])),
        }
        if include_evaluation:
            evaluation = ~training
            held = measured[evaluation] - model[candidate, tau_index, evaluation] - row["offset_hz"]
            row["evaluation_rms_hz"] = float(np.sqrt(np.mean(held**2)))
        rows.append(row)
    return rows


def select_scan_tau(grouped, track_profiles, weights, loss_name):
    tau_count = len(track_profiles[0])
    objectives = []
    for tau_index in range(tau_count):
        rows = [
            {"session_id": "scan", "weight_s": weight, "score": profile[tau_index]}
            for profile, weight in zip(track_profiles, weights, strict=True)
        ]
        objectives.append(grouped.aggregate(rows, "training_rms_hz", loss_name, "duration"))
    selected = int(np.argmin(objectives))
    return selected, objectives


def score_location(
    prior,
    grouped,
    joint,
    prepared,
    sessions,
    point,
    timing_grids,
    mode,
    loss_name,
    include_evaluation=False,
):
    selected_rows = []
    scan_diagnostics = []
    for session in sessions:
        evidence, arrays = prepared[session]
        taus = np.asarray([0.0]) if mode == "tau0" else timing_grids[session]
        profiles, weights = [], []
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(
                evidence, arrays, track, float(point[0]), float(point[1]), taus_s=taus
            )
            profiles.append(profile_track_by_tau(prediction, include_evaluation))
            weights.append(int(len(np.unique(np.floor(prediction.times_s)))))
        tau_index, objectives = select_scan_tau(grouped, profiles, weights, loss_name)
        for profile, weight in zip(profiles, weights, strict=True):
            selected_rows.append(
                {"session_id": session, "weight_s": weight, "score": profile[tau_index]}
            )
        scan_diagnostics.append(
            {
                "session_id": session,
                "tau_s": float(taus[tau_index]),
                "tau_index": tau_index,
                "grid_size": len(taus),
                "boundary_hit": bool(tau_index in (0, len(taus) - 1) and len(taus) > 1),
                "training_objective_hz": objectives[tau_index],
            }
        )
    objective = grouped.aggregate(selected_rows, "training_rms_hz", loss_name, "duration")
    return objective, selected_rows, scan_diagnostics


def fit_window(prior, grouped, joint, prepared, sessions, seeds, grids, max_evaluations):
    arms = []
    for name, mode, loss in ARMS:
        fits = []
        for seed_index, seed in enumerate(seeds, start=1):
            fit = prior.bounded_fit(
                lambda point, selected_mode=mode, selected_loss=loss: score_location(
                    prior,
                    grouped,
                    joint,
                    prepared,
                    sessions,
                    point,
                    grids,
                    selected_mode,
                    selected_loss,
                )[0],
                seed,
                max_evaluations=max_evaluations,
            )
            fits.append({"seed_id": seed_index, "seed": seed, **fit})
        arms.append(
            {
                "method": name,
                "timing_model": mode,
                "loss": loss,
                "fits": fits,
                "selected": min(fits, key=lambda row: row["training_rmse_hz"]),
            }
        )
    return arms


def run(args):
    if (args.output / "inference.json").exists():
        raise FileExistsError(args.output / "inference.json")
    started = time.monotonic()
    split = json.loads(args.split.read_text())
    inventory = json.loads(args.inventory.read_text())
    timing = json.loads(args.timing_metadata.read_text())
    authority = {row["session_id"]: row for row in inventory["scans"]}
    timing_rows = {row["session_id"]: row["timing"] for row in timing["rows"]}
    validation = split["partitions"]["validation"]
    if set(timing_rows) != set(validation["session_ids"]):
        raise ValueError("timing metadata must cover exactly validation")
    grids = {}
    for session, row in timing_rows.items():
        if not row["qualified"]:
            raise ValueError(f"unqualified timing authority: {session}")
        low = (row["first_sample_earliest_utc_ns"] - row["first_sample_estimate_utc_ns"]) / 1e9
        high = (row["first_sample_latest_utc_ns"] - row["first_sample_estimate_utc_ns"]) / 1e9
        grids[session] = np.linspace(low, high, 17)
    prior = load_module(args.prior_tool, "shared_prior")
    grouped = load_module(args.grouped_tool, "shared_grouped")
    joint = load_module(args.joint_tool, "shared_joint")
    caches, scans, cache_digests = grouped.cache_sources(args.replication_root, args.original_cache)
    groups = [g for g in split["groups"] if g["group_id"] in validation["group_ids"]]
    windows = []
    for group in groups:
        windows.extend(
            [
                {"window_id": group["group_id"], "session_ids": group["session_ids"]},
                {
                    "window_id": group["group_id"] + "-first-scan",
                    "session_ids": group["session_ids"][:1],
                },
            ]
        )
    test_ids = set(split["partitions"]["test"]["session_ids"])
    if {sid for window in windows for sid in window["session_ids"]} & test_ids:
        raise ValueError("test scan entered validation windows")
    for session in validation["session_ids"]:
        evidence = json.loads((caches[session] / "evidence" / f"{session}.json").read_text())
        if (
            prior.value_digest(evidence["tracks"]).removeprefix("sha256:")
            != authority[session]["evidence_digest"]
        ):
            raise ValueError("cached evidence differs from inventory")
        for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if scans[session][field] != authority[session][field]:
                raise ValueError(f"{field} differs from inventory")
    output_windows = []
    for window in windows:
        sessions = window["session_ids"]
        prepared = {sid: joint.load_scan_cache(caches[sid], sid) for sid in sessions}
        seeds = prior.deterministic_seeds(prior.published_seed_rows(sessions, scans, authority))
        output_windows.append(
            {
                **window,
                "seeds": seeds,
                "arms": fit_window(
                    prior, grouped, joint, prepared, sessions, seeds, grids, args.max_evaluations
                ),
            }
        )
    inference = {
        "schema": "shared-bracket-position/v1",
        "position_truth_used": False,
        "test_evidence_accessed": False,
        "split_manifest_sha256": "sha256:" + hashlib.sha256(args.split.read_bytes()).hexdigest(),
        "inventory_sha256": "sha256:" + hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "timing_metadata_sha256": "sha256:"
        + hashlib.sha256(args.timing_metadata.read_bytes()).hexdigest(),
        "cache_manifest_sha256": cache_digests,
        "timing_grid_points": 17,
        "timing_grid_policy": "linear inclusive grid over saved host bracket relative to estimate",
        "windows": output_windows,
        "inference_runtime_s": time.monotonic() - started,
    }
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    evaluation_started = time.monotonic()
    for window in results["windows"]:
        sessions = window["session_ids"]
        prepared = {sid: joint.load_scan_cache(caches[sid], sid) for sid in sessions}
        for arm in window["arms"]:
            selected = arm["selected"]
            point = (selected["latitude_deg"], selected["longitude_deg"])
            _, held_rows, scan_diagnostics = score_location(
                prior,
                grouped,
                joint,
                prepared,
                sessions,
                point,
                grids,
                arm["timing_model"],
                arm["loss"],
                True,
            )
            selected["scan_timing"] = scan_diagnostics
            selected["reserved_capped800_rmse_hz"] = grouped.aggregate(
                held_rows, "evaluation_rms_hz", "capped800", "duration"
            )
            selected["reserved_uncapped_rmse_hz"] = grouped.aggregate(
                held_rows, "evaluation_rms_hz", "uncapped", "duration"
            )
            selected["reference_error_km"] = prior.haversine_km(point, prior.REFERENCE)
    results["reference_coordinate"] = {
        "latitude_deg": prior.REFERENCE[0],
        "longitude_deg": prior.REFERENCE[1],
        "role": "post-seal only",
    }
    results["post_seal_runtime_s"] = time.monotonic() - evaluation_started
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--timing-metadata", type=Path, required=True)
    parser.add_argument("--prior-tool", type=Path, required=True)
    parser.add_argument("--grouped-tool", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-evaluations", type=int, default=150)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
