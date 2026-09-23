#!/usr/bin/env python3
"""Fit frozen spatial objectives on randomized whole-group validation windows."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ARMS = (
    ("duration_capped800", "capped800", "duration"),
    ("duration_robust150", "pseudo_huber_150hz", "duration"),
    ("equal_scan_robust150", "pseudo_huber_150hz", "equal_scan"),
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def track_term(value: float, loss_name: str) -> float:
    if loss_name == "capped800":
        return min(800.0, value) ** 2
    if loss_name == "uncapped":
        return value**2
    if loss_name == "pseudo_huber_150hz":
        delta = 150.0
        return float(2 * delta**2 * (np.sqrt(1 + (value / delta) ** 2) - 1))
    raise ValueError(f"unknown loss {loss_name}")


def aggregate(rows: list[dict], field: str, loss_name: str, outer_weighting: str) -> float:
    if not rows:
        raise ValueError("cannot aggregate no tracks")
    if outer_weighting == "duration":
        total = sum(row["weight_s"] for row in rows)
        loss = sum(
            row["weight_s"]
            * track_term(800.0 if row["score"] is None else row["score"][field], loss_name)
            for row in rows
        )
        return float(np.sqrt(loss / total))
    if outer_weighting != "equal_scan":
        raise ValueError(f"unknown outer weighting {outer_weighting}")
    by_scan = {}
    for row in rows:
        by_scan.setdefault(row["session_id"], []).append(row)
    scan_losses = []
    for scan_rows in by_scan.values():
        total = sum(row["weight_s"] for row in scan_rows)
        scan_losses.append(
            sum(
                row["weight_s"]
                * track_term(800.0 if row["score"] is None else row["score"][field], loss_name)
                for row in scan_rows
            )
            / total
        )
    return float(np.sqrt(np.mean(scan_losses)))


def score_rows(prior, joint, prepared, sessions, point, include_evaluation=False):
    rows = []
    for session in sessions:
        evidence, arrays = prepared[session]
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                float(point[0]),
                float(point[1]),
                taus_s=prior.TAUS,
            )
            rows.append(
                {
                    "session_id": session,
                    "weight_s": int(len(np.unique(np.floor(prediction.times_s)))),
                    "score": prior.score_prediction_training(
                        prediction, include_evaluation=include_evaluation
                    ),
                }
            )
    return rows


def fit_window(prior, joint, prepared, sessions, seeds, max_evaluations):
    arms = []
    for name, loss_name, weighting in ARMS:
        fits = []
        for seed_index, seed in enumerate(seeds, start=1):
            fit = prior.bounded_fit(
                lambda point, selected_loss=loss_name, selected_weighting=weighting: aggregate(
                    score_rows(prior, joint, prepared, sessions, point),
                    "training_rms_hz",
                    selected_loss,
                    selected_weighting,
                ),
                seed,
                max_evaluations=max_evaluations,
            )
            fits.append({"seed_id": seed_index, "seed": seed, **fit})
        arms.append(
            {
                "method": name,
                "loss": loss_name,
                "outer_weighting": weighting,
                "fits": fits,
                "selected": min(fits, key=lambda row: row["training_rmse_hz"]),
            }
        )
    return arms


def cache_sources(replication_root: Path, original_cache: Path):
    caches, scans, digests = {}, {}, {}
    roots = [block / "cache" for block in sorted(replication_root.glob("block_*"))]
    roots.append(original_cache)
    for cache in roots:
        manifest_path = cache / "cache_manifest.json"
        if not manifest_path.is_file():
            continue
        digests[str(cache)] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        for row in json.loads(manifest_path.read_text())["scans"]:
            caches.setdefault(row["session_id"], cache)
        scans_path = cache.parent / "scans.json"
        if scans_path.is_file():
            for row in json.loads(scans_path.read_text()):
                scans.setdefault(row["session_id"], row)
    return caches, scans, digests


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    split = json.loads(args.split.read_text())
    inventory = json.loads(args.inventory.read_text())
    authority = {row["session_id"]: row for row in inventory["scans"]}
    test_ids = set(split["partitions"]["test"]["session_ids"])
    validation_ids = set(split["partitions"]["validation"]["session_ids"])
    groups = [
        group
        for group in split["groups"]
        if group["group_id"] in split["partitions"]["validation"]["group_ids"]
    ]
    windows = []

    def duration_metadata(session_ids):
        starts = [
            datetime.fromisoformat(authority[session]["captured_at"].replace("Z", "+00:00"))
            for session in session_ids
        ]
        return {
            "elapsed_span_seconds": (
                max(starts) + timedelta(seconds=300) - min(starts)
            ).total_seconds(),
            "summed_nominal_capture_seconds": 300 * len(session_ids),
        }

    for group in groups:
        windows.append(
            {
                "window_id": group["group_id"],
                "view": "whole_randomized_group",
                "session_ids": group["session_ids"],
                **duration_metadata(group["session_ids"]),
            }
        )
        windows.append(
            {
                "window_id": group["group_id"] + "-first-scan",
                "view": "predeclared_first_scan",
                "session_ids": group["session_ids"][:1],
                **duration_metadata(group["session_ids"][:1]),
            }
        )
    consumed = {session for window in windows for session in window["session_ids"]}
    if not consumed <= validation_ids or consumed & test_ids:
        raise ValueError("window membership violates random split")
    prior = load_module(args.prior_tool, "position_training_prior")
    joint = load_module(args.joint_tool, "position_group_joint")
    caches, scans, cache_digests = cache_sources(args.replication_root, args.original_cache)
    if any(session not in caches or session not in scans for session in validation_ids):
        raise ValueError("frozen caches or seed authority do not cover validation")
    for session in validation_ids:
        evidence = json.loads((caches[session] / "evidence" / f"{session}.json").read_text())
        if (
            prior.value_digest(evidence["tracks"]).removeprefix("sha256:")
            != authority[session]["evidence_digest"]
        ):
            raise ValueError("cached track evidence differs from frozen inventory")
        if scans[session]["input_manifest_sha256"] != authority[session]["input_manifest_sha256"]:
            raise ValueError("input manifest differs from frozen inventory")
        if (
            scans[session]["analysis_manifest_sha256"]
            != authority[session]["analysis_manifest_sha256"]
        ):
            raise ValueError("analysis manifest differs from frozen inventory")
    inference_windows = []
    for window in windows:
        sessions = window["session_ids"]
        prepared = {
            session: joint.load_scan_cache(caches[session], session) for session in sessions
        }
        seed_rows = prior.published_seed_rows(sessions, scans, authority)
        seeds = prior.deterministic_seeds(seed_rows)
        inference_windows.append(
            {
                **window,
                "seeds": seeds,
                "arms": fit_window(prior, joint, prepared, sessions, seeds, args.max_evaluations),
            }
        )
    inference = {
        "schema": "position-grouped-robust/v1",
        "position_truth_used": False,
        "split_manifest_sha256": "sha256:" + hashlib.sha256(args.split.read_bytes()).hexdigest(),
        "inventory_sha256": "sha256:" + hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "random_seed": split["seed"],
        "test_evidence_accessed": False,
        "test_ids_read_only_for_exclusion": True,
        "validation_group_ids": split["partitions"]["validation"]["group_ids"],
        "candidate_scope": (
            "conditional union of identities from prior published analyses; those "
            "published identity choices used reserved rows"
        ),
        "cache_manifest_sha256": cache_digests,
        "max_evaluations_per_seed": args.max_evaluations,
        "windows": inference_windows,
        "inference_runtime_s": time.monotonic() - started,
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    evaluation_started = time.monotonic()
    results = json.loads(payload)
    for window in results["windows"]:
        sessions = window["session_ids"]
        prepared = {
            session: joint.load_scan_cache(caches[session], session) for session in sessions
        }
        for arm in window["arms"]:
            selected = arm["selected"]
            point = (selected["latitude_deg"], selected["longitude_deg"])
            held_rows = score_rows(prior, joint, prepared, sessions, point, True)
            selected["common_reserved_capped800_rmse_hz"] = aggregate(
                held_rows, "evaluation_rms_hz", "capped800", "duration"
            )
            selected["common_reserved_uncapped_rmse_hz"] = aggregate(
                held_rows, "evaluation_rms_hz", "uncapped", "duration"
            )
            selected["native_reserved_objective"] = aggregate(
                held_rows,
                "evaluation_rms_hz",
                arm["loss"],
                arm["outer_weighting"],
            )
            selected["evaluation_only_error_km"] = prior.haversine_km(point, prior.REFERENCE)
            selected["reference_error_km"] = selected["evaluation_only_error_km"]
            selected["reserved_capped800_rmse_hz"] = selected["common_reserved_capped800_rmse_hz"]
            selected["reserved_uncapped_rmse_hz"] = selected["common_reserved_uncapped_rmse_hz"]
            selected["deletion_score_influence"] = []
            if len(sessions) > 1:
                full = aggregate(
                    score_rows(prior, joint, prepared, sessions, point),
                    "training_rms_hz",
                    arm["loss"],
                    arm["outer_weighting"],
                )
                for omitted in sessions:
                    retained = [
                        row
                        for row in score_rows(prior, joint, prepared, sessions, point)
                        if row["session_id"] != omitted
                    ]
                    without = aggregate(
                        retained,
                        "training_rms_hz",
                        arm["loss"],
                        arm["outer_weighting"],
                    )
                    selected["deletion_score_influence"].append(
                        {"omitted_session_id": omitted, "objective_change_hz": without - full}
                    )
    results["reference_coordinate"] = {
        "latitude_deg": prior.REFERENCE[0],
        "longitude_deg": prior.REFERENCE[1],
        "role": "post-seal evaluation only",
    }
    results["post_seal_runtime_s"] = time.monotonic() - evaluation_started
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--prior-tool", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-evaluations", type=int, default=150)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
