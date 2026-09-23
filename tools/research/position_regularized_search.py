#!/usr/bin/env python3
"""Continuous train-only location fits with the frozen λ=1000 timing heuristic."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

LAMBDA = 1000.0


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _modules():
    root = Path(__file__).parent
    return (
        _load(root / "position_training_search.py", "regularized_search_training"),
        _load(root / "position_regularized_timing.py", "regularized_search_timing"),
        _load(root / "sixteen_joint_compare.py", "regularized_search_joint"),
        _load(root / "position_dataset_split.py", "regularized_search_partition"),
    )


def _cache_index(replication_root):
    caches, scan_rows, digests = {}, {}, {}
    for block in sorted(replication_root.glob("block_*")):
        cache = block / "cache"
        path = cache / "cache_manifest.json"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digests[block.name] = "sha256:" + hashlib.sha256(raw).hexdigest()
        for row in json.loads(raw)["scans"]:
            if row["session_id"] in caches:
                raise ValueError("duplicate cached session")
            caches[row["session_id"]] = cache
        for row in json.loads((block / "scans.json").read_text()):
            scan_rows[row["session_id"]] = row
    return caches, scan_rows, digests


def score_location(
    joint, timing, caches, sessions, point, evaluation=False, loaded=None, uncapped=False
):
    scans = []
    for session in sessions:
        evidence, arrays = (
            loaded[session]
            if loaded is not None
            else joint.load_scan_cache(caches[session], session)
        )
        predictions = [
            joint.prediction_for_track(evidence, arrays, track, *point)
            for track in evidence["tracks"]
        ]
        scans.append((session, predictions))
    answer = timing.score_location(scans, LAMBDA)
    if not uncapped:
        return answer[
            "reserved_capped_weighted_rms_hz" if evaluation else "training_capped_weighted_rms_hz"
        ]
    field = "reserved_rms_hz" if evaluation else "training_rms_hz"
    rows = []
    for _, predictions in scans:
        for prediction, choice in zip(
            predictions, timing.score_scan(predictions, LAMBDA)["choices"], strict=True
        ):
            rows.append((timing._weight(prediction), choice[field] if choice else 800.0))
    return timing._rms(rows)


def fit_window(training, joint, timing, caches, sessions, seeds, maximum, loaded):
    fits = []
    for index, seed in enumerate(seeds, 1):
        fit = training.bounded_fit(
            lambda point: score_location(joint, timing, caches, sessions, point, loaded=loaded),
            seed,
            maximum,
        )
        fits.append({"seed_id": index, "seed": seed, **fit})
    return fits, min(fits, key=lambda row: row["training_rmse_hz"])


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    training, timing, joint, partition = _modules()
    dataset = json.loads(args.dataset.read_text())
    validation_ids = set(partition.load_partition(args.dataset, "development_validation"))
    inventory = json.loads(args.day_inventory.read_text())
    if (
        "sha256:" + hashlib.sha256(args.day_inventory.read_bytes()).hexdigest()
        != dataset["provenance"]["day_inventory_digest"]
    ):
        raise ValueError("inventory digest mismatch")
    authority = {x["session_id"]: x for x in inventory["scans"] if x.get("state") == "eligible"}
    caches, scan_rows, cache_digests = _cache_index(args.replication_root)
    tiers = dataset["partitions"]["development_validation"]["duration_tiers"]
    selected = [
        tiers[name]["windows"][0] for name in ("about_8h", "about_3h", "about_1h", "single_300s")
    ]
    rows = []
    for window in selected:
        sessions = window["session_ids"]
        if not set(sessions).issubset(validation_ids):
            raise ValueError("window crosses frozen validation partition")
        if any(s not in caches or s not in scan_rows for s in sessions):
            raise ValueError("cache coverage missing")
        expected = training.value_digest(
            [
                {"session_id": s, "evidence_digest": authority[s]["evidence_digest"]}
                for s in sessions
            ]
        )
        if expected != window["observation_and_mask_authority_digest"]:
            raise ValueError("frozen mask authority mismatch")
        for session in sessions:
            evidence = json.loads((caches[session] / "evidence" / f"{session}.json").read_text())
            if (
                training.value_digest(evidence["tracks"]).removeprefix("sha256:")
                != authority[session]["evidence_digest"]
            ):
                raise ValueError("cached track evidence differs from frozen inventory")
        seed_rows = training.published_seed_rows(sessions, scan_rows, authority)
        seeds = training.deterministic_seeds(seed_rows)
        loaded = {session: joint.load_scan_cache(caches[session], session) for session in sessions}
        fits, chosen = fit_window(
            training, joint, timing, caches, sessions, seeds, args.max_evaluations, loaded
        )
        rows.append(
            {
                "window_id": window["window_id"],
                "scan_count": window["scan_count"],
                "session_ids": sessions,
                "authority_digest": expected,
                "seeds": seeds,
                "fits": fits,
                "selected": chosen,
            }
        )
    args.output.mkdir(parents=True)
    inference = {
        "schema": "regularized-continuous-search-inference/v1",
        "position_truth_used": False,
        "lambda_hz2_per_s2": LAMBDA,
        "objective": (
            "duration-weighted capped 800 Hz training RMS after regularized per-track "
            "tau/latent shared-center profile; heuristic, not joint MAP"
        ),
        "seed_policy": (
            "same frozen in-window published Sacramento/Reno mean and midpoint seeds "
            "as baseline/robust"
        ),
        "max_evaluations_per_seed": args.max_evaluations,
        "dataset_digest": "sha256:" + hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "source_hashes": {
            name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in {
                "regularized_search": Path(__file__),
                "regularized_timing": Path(__file__).with_name("position_regularized_timing.py"),
                "training_search": Path(__file__).with_name("position_training_search.py"),
                "joint": Path(__file__).with_name("sixteen_joint_compare.py"),
            }.items()
        },
        "cache_manifest_digests": cache_digests,
        "windows": rows,
        "runtime_s": time.monotonic() - started,
    }
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for row in results["windows"]:
        point = (row["selected"]["latitude_deg"], row["selected"]["longitude_deg"])
        loaded = {
            session: joint.load_scan_cache(caches[session], session)
            for session in row["session_ids"]
        }
        row["selected"]["reserved_capped800_rmse_hz"] = score_location(
            joint, timing, caches, row["session_ids"], point, True, loaded
        )
        row["selected"]["reserved_uncapped_rmse_hz"] = score_location(
            joint, timing, caches, row["session_ids"], point, True, loaded, True
        )
        row["selected"]["reference_error_km"] = joint.haversine_km(point, training.REFERENCE)
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--day-inventory", type=Path, required=True)
    p.add_argument("--replication-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-evaluations", type=int, default=150)
    run(p.parse_args())


if __name__ == "__main__":
    main()
