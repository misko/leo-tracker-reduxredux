"""Bounded random-group validation of hard and soft candidate refinements."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import time
from datetime import datetime
from pathlib import Path

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

import numpy as np  # noqa: E402 -- constrain BLAS before importing NumPy


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validation_windows(manifest):
    partitions = manifest["partitions"]
    sets = [set(partitions[p]["session_ids"]) for p in ("train", "validation", "test")]
    if any(sets[i] & sets[j] for i in range(3) for j in range(i)):
        raise ValueError("partition overlap")
    by_id = {g["group_id"]: g for g in manifest["groups"]}
    windows = []
    for gid in partitions["validation"]["group_ids"]:
        ids = by_id[gid]["session_ids"]
        if not ids or not set(ids) <= sets[1]:
            raise ValueError("group outside validation partition")
        windows.extend([(gid, ids), (gid + "-first", ids[:1])])
    return windows


def objective(joint, statistics, loaded, sessions, point, method):
    values = []
    field = "hard_mse_hz2" if method == "hard" else "soft_nll"
    for sid in sessions:
        evidence, arrays = loaded[sid]
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(evidence, arrays, track, *point)
            values.append(statistics.track_statistics(prediction)[field])
    return float(np.mean(values))


def evaluate(joint, training, statistics, loaded, sessions, point, method):
    diagnostics, weights, expected, hard = [], [], [], []
    for sid in sessions:
        evidence, arrays = loaded[sid]
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(evidence, arrays, track, *point)
            stats = statistics.track_statistics(prediction, include_evaluation=True)
            weights.append(len(np.unique(np.floor(prediction.times_s))))
            expected.append(stats[f"{method}_reserved_mse_hz2"])
            choice = training.score_prediction_training(prediction, include_evaluation=True)
            hard.append(800.0**2 if choice is None else choice["evaluation_rms_hz"] ** 2)
            diagnostics.append({k: stats[k] for k in ("null_probability", "entropy_nats")})
    return {
        "reserved_capped800_rmse_hz": float(
            np.sqrt(np.average(np.minimum(hard, 800**2), weights=weights))
        ),
        "reserved_uncapped_rmse_hz": float(np.sqrt(np.average(hard, weights=weights))),
        "native_frozen_posterior_reserved_rmse_hz": float(
            np.sqrt(np.average(expected, weights=weights))
        ),
        "mean_null_probability": float(np.mean([d["null_probability"] for d in diagnostics])),
        "mean_entropy_nats": float(np.mean([d["entropy_nats"] for d in diagnostics])),
        "track_count": len(weights),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    root = Path(__file__).parent
    training = load(root / "position_training_search.py", "training_search")
    joint = load(root / "sixteen_joint_compare.py", "joint_soft")
    statistics = load(root / "position_soft_statistics.py", "soft_statistics")
    cache_helper = load(root / "position_regularized_search.py", "cache_helper")
    if digest(args.manifest) != args.manifest.with_suffix(".sha256").read_text().strip():
        raise ValueError("random group manifest hash mismatch")
    manifest = json.loads(args.manifest.read_text())
    windows = validation_windows(manifest)
    authority = {s["session_id"]: s for s in json.loads(args.inventory.read_text())["scans"]}
    caches, scans, cache_digests = cache_helper._cache_index(args.replication_root)
    loaded, bindings = {}, {}
    for sid in sorted({s for _, ids in windows for s in ids}):
        evidence_path = caches[sid] / "evidence" / f"{sid}.json"
        evidence = json.loads(evidence_path.read_text())
        if (
            training.value_digest(evidence["tracks"]).removeprefix("sha256:")
            != authority[sid]["evidence_digest"]
        ):
            raise ValueError("track authority mismatch")
        loaded[sid] = joint.load_scan_cache(caches[sid], sid)
        bindings[sid] = {
            "evidence": digest(evidence_path),
            "states": digest(caches[sid] / "scans" / f"{sid}.npz"),
        }
    output = {
        "schema": "random-group-soft-candidate/v1",
        "truth_used_for_inference": False,
        "test_evidence_opened": False,
        "manifest_sha256": digest(args.manifest),
        "inventory_sha256": digest(args.inventory),
        "cache_manifest_digests": cache_digests,
        "input_bindings": bindings,
        "source_sha256": {
            p.name: digest(p)
            for p in (
                Path(__file__),
                root / "position_soft_statistics.py",
                root / "position_training_search.py",
                root / "sixteen_joint_compare.py",
            )
        },
        "settings": {
            "sigma_hz": 250,
            "null_sigma_hz": 30000,
            "signal_prior": 0.5,
            "hyperparameter_selection": "predeclared; no training or validation geographic tuning",
        },
        "scope": (
            "Conditional published candidate pools and seeds; hard equal-track MSE versus "
            "heuristic soft likelihood. IID likelihood is not calibrated confidence."
        ),
        "windows": [],
    }
    for window_id, sessions in windows:
        seeds = training.deterministic_seeds(
            training.published_seed_rows(sessions, scans, authority)
        )
        times = [
            datetime.fromisoformat(authority[s]["captured_at"].replace("Z", "+00:00"))
            for s in sessions
        ]
        window = {
            "window_id": window_id,
            "session_ids": sessions,
            "seeds": seeds,
            "scan_count": len(sessions),
            "elapsed_span_seconds": (max(times) - min(times)).total_seconds() + 300,
            "nominal_capture_seconds": 300 * len(sessions),
            "arms": [],
        }
        for method in ("hard", "soft"):
            fits = []
            for seed in seeds:
                fit = training.bounded_fit(
                    lambda p, ids=sessions, mode=method: objective(
                        joint, statistics, loaded, ids, p, mode
                    ),
                    seed,
                    150,
                )
                fit["native_training_objective"] = fit.pop("training_rmse_hz")
                fit["seed"] = seed
                fits.append(fit)
            selected = min(fits, key=lambda f: f["native_training_objective"])
            window["arms"].append({"method": method, "fits": fits, "selected": dict(selected)})
            print(window_id, method, selected, flush=True)
        output["windows"].append(window)
    output["inference_runtime_s"] = time.monotonic() - started
    args.output.mkdir(parents=True)
    seal = args.output / "inference.json"
    seal.write_text(json.dumps(output, indent=2) + "\n")
    seal.with_suffix(".sha256").write_text(digest(seal) + "\n")
    for window in output["windows"]:
        for arm in window["arms"]:
            selected = arm["selected"]
            point = selected["latitude_deg"], selected["longitude_deg"]
            selected.update(
                evaluate(
                    joint, training, statistics, loaded, window["session_ids"], point, arm["method"]
                )
            )
            selected["reference_error_km"] = training.haversine_km(point, training.REFERENCE)
    output["inference_sha256"] = digest(seal)
    output["total_runtime_s"] = time.monotonic() - started
    (args.output / "results.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
