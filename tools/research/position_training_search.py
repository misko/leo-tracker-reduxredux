#!/usr/bin/env python3
"""Training-only continuous position fits on frozen development/validation windows."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

REFERENCE = (37.84903264307456, -122.4856541910174)
PRIORS = ((38.5816, -121.4944, 250.0), (39.5296, -119.8138, 500.0))
TAUS = np.arange(-5.0, 6.0)


def haversine_km(a, b):
    lat1, lat2 = np.deg2rad([a[0], b[0]])
    dlat, dlon = lat2 - lat1, np.deg2rad(b[1] - a[1])
    x = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(2 * 6371.0088 * np.arctan2(np.sqrt(x), np.sqrt(1 - x)))


def inside_prior_intersection(point) -> bool:
    return all(haversine_km(point, centre[:2]) <= centre[2] for centre in PRIORS)


def score_prediction_training(prediction, *, include_evaluation=False):
    measured = np.asarray(prediction.measured_hz, dtype=float)
    training = np.asarray(prediction.training_mask, dtype=bool)
    model = np.asarray(prediction.predictions_hz, dtype=float)
    residual = measured[None, None, training] - model[..., training]
    offset = np.mean(residual, axis=-1)
    train_mse = np.mean((residual - offset[..., None]) ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], train_mse.shape)
    train_mse = np.where(visible, train_mse, np.inf)
    flat = int(np.argmin(train_mse))
    candidate, tau = np.unravel_index(flat, train_mse.shape)
    if not np.isfinite(train_mse[candidate, tau]):
        return None
    result = {
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "tau_s": float(prediction.taus_s[tau]),
        "offset_hz": float(offset[candidate, tau]),
        "training_rms_hz": float(np.sqrt(train_mse[candidate, tau])),
    }
    if include_evaluation:
        evaluation = ~training
        held = measured[evaluation] - model[candidate, tau, evaluation] - offset[candidate, tau]
        result["evaluation_rms_hz"] = float(np.sqrt(np.mean(held**2)))
    return result


def aggregate_score(rows, field: str, loss_name="capped800") -> float:
    total = sum(row["weight_s"] for row in rows)
    values = [800.0 if row["score"] is None else row["score"][field] for row in rows]
    if loss_name == "uncapped":
        terms = [value**2 for value in values]
    elif loss_name == "capped800":
        terms = [min(800.0, value) ** 2 for value in values]
    elif loss_name == "pseudo_huber_150hz":
        delta = 150.0
        terms = [2 * delta**2 * (np.sqrt(1 + (value / delta) ** 2) - 1) for value in values]
    else:
        raise ValueError("unknown aggregate loss")
    loss = sum(row["weight_s"] * term for row, term in zip(rows, terms, strict=True))
    return float(np.sqrt(loss / total))


def bounded_fit(
    objective: Callable[[np.ndarray], float], seed: Sequence[float], max_evaluations=150
) -> dict:
    seed = np.asarray(seed, dtype=float)
    visited_outside = 0

    def guarded(point):
        nonlocal visited_outside
        if not inside_prior_intersection(point):
            visited_outside += 1
            return np.inf
        return float(objective(point))

    initial = np.asarray([seed, (seed[0] + 0.02, seed[1]), (seed[0], seed[1] + 0.02)])
    incumbent = guarded(seed)
    fit = minimize(
        guarded,
        seed,
        method="Nelder-Mead",
        options={
            "maxfev": max_evaluations,
            "xatol": 0.002,
            "fatol": 0.01,
            "initial_simplex": initial,
        },
    )
    candidates = [(incumbent, seed), (float(fit.fun), np.asarray(fit.x))]
    value, point = min(candidates, key=lambda row: row[0])
    if not inside_prior_intersection(point):
        raise ValueError("selected estimate escaped prior intersection")
    return {
        "latitude_deg": float(point[0]),
        "longitude_deg": float(point[1]),
        "training_rmse_hz": value,
        "evaluations": int(fit.nfev),
        "converged": bool(fit.success),
        "message": str(fit.message),
        "outside_trial_count": visited_outside,
    }


def deterministic_seeds(rows: Sequence[dict]) -> list[list[float]]:
    by_prior = {}
    for row in rows:
        by_prior.setdefault(row["prior"], []).append([row["latitude_deg"], row["longitude_deg"]])
    sacramento = np.mean(by_prior["sacramento"], axis=0)
    reno = np.mean(by_prior["reno"], axis=0)
    pooled = (sacramento + reno) / 2
    candidates = [sacramento.tolist(), reno.tolist(), pooled.tolist()]
    selected = [point for point in candidates if inside_prior_intersection(point)]
    if not selected:
        raise ValueError("all deterministic prior-derived seeds fall outside intersection")
    return selected


def _module(path):
    spec = importlib.util.spec_from_file_location("joint_training_search", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def value_digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def published_seed_rows(sessions, scan_rows, authority):
    rows = []
    for session in sessions:
        document = scan_rows[session]
        frozen = authority[session]
        if (
            document["input_manifest_sha256"] != frozen["input_manifest_sha256"]
            or document["analysis_manifest_sha256"] != frozen["analysis_manifest_sha256"]
        ):
            raise ValueError("published seed authority changed after dataset freeze")
        for name, prior in document["priors"].items():
            rows.append(
                {
                    "session_id": session,
                    "prior": name,
                    "latitude_deg": prior["selected"]["latitude_deg"],
                    "longitude_deg": prior["selected"]["longitude_deg"],
                }
            )
    return rows


def score_location(
    joint, cache, sessions, point, *, include_evaluation=False, loss_name="capped800"
):
    rows = []
    for session in sessions:
        source_cache = cache[session] if isinstance(cache, dict) else cache
        if isinstance(source_cache, tuple):
            evidence, arrays = source_cache
        else:
            evidence, arrays = joint.load_scan_cache(source_cache, session)
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(
                evidence, arrays, track, float(point[0]), float(point[1]), taus_s=TAUS
            )
            rows.append(
                {
                    "weight_s": int(len(np.unique(np.floor(prediction.times_s)))),
                    "score": score_prediction_training(
                        prediction, include_evaluation=include_evaluation
                    ),
                }
            )
    return aggregate_score(
        rows,
        "evaluation_rms_hz" if include_evaluation else "training_rms_hz",
        loss_name,
    )


def fit_window(joint, cache, sessions, seeds, max_evaluations):
    prepared = {}
    for session in sessions:
        source_cache = cache[session] if isinstance(cache, dict) else cache
        prepared[session] = joint.load_scan_cache(source_cache, session)
    arms = []
    for loss_name in ("capped800", "pseudo_huber_150hz"):
        fits = []
        for index, seed in enumerate(seeds, start=1):
            fit = bounded_fit(
                lambda point, selected_sessions=sessions, selected_loss=loss_name: score_location(
                    joint, prepared, selected_sessions, point, loss_name=selected_loss
                ),
                seed,
                max_evaluations=max_evaluations,
            )
            fits.append({"seed_id": index, "seed": seed, **fit})
        arms.append(
            {
                "loss": loss_name,
                "fits": fits,
                "selected": min(fits, key=lambda row: row["training_rmse_hz"]),
            }
        )
    return arms


def run(args):
    total_started = time.monotonic()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads(args.dataset.read_text())
    inventory = json.loads(args.day_inventory.read_text())
    authority = {
        row["session_id"]: row for row in inventory["scans"] if row.get("state") == "eligible"
    }
    if (
        "sha256:" + hashlib.sha256(args.day_inventory.read_bytes()).hexdigest()
        != manifest["provenance"]["day_inventory_digest"]
    ):
        raise ValueError("day inventory differs from frozen dataset provenance")
    tiers = manifest["partitions"]["development_validation"]["duration_tiers"]
    selected = [
        tiers[name]["windows"][0] for name in ("single_300s", "about_1h", "about_3h", "about_8h")
    ]
    unique_sessions = list(dict.fromkeys(s for window in selected for s in window["session_ids"]))
    args.output.mkdir(parents=True)
    joint = _module(args.joint_tool)
    original_source = json.loads(args.original_source.read_text())
    original_row = next(row for row in original_source["results"] if row["scan_count"] == 16)
    original_sessions = [
        row["session_id"]
        for row in json.loads((args.original_cache / "cache_manifest.json").read_text())["scans"]
    ]
    original_arms = fit_window(
        joint,
        args.original_cache,
        original_sessions,
        [row["seed"] for row in original_row["basins"]],
        args.max_evaluations,
    )
    cache, scan_rows, cache_manifest_digests = {}, {}, {}
    for block in sorted(args.replication_root.glob("block_*")):
        block_cache = block / "cache"
        if not (block_cache / "cache_manifest.json").is_file():
            continue
        manifest_path = block_cache / "cache_manifest.json"
        cache_manifest_digests[block.name] = (
            "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        )
        for row in json.loads(manifest_path.read_text())["scans"]:
            cache[row["session_id"]] = block_cache
        for row in json.loads((block / "scans.json").read_text()):
            scan_rows[row["session_id"]] = row
    if any(session not in cache or session not in scan_rows for session in unique_sessions):
        raise ValueError("replication caches do not cover selected validation windows")
    for session in unique_sessions:
        evidence = json.loads((cache[session] / "evidence" / f"{session}.json").read_text())
        if (
            value_digest(evidence["tracks"]).removeprefix("sha256:")
            != authority[session]["evidence_digest"]
        ):
            raise ValueError("cached observations or masks differ from frozen authority")
    inference_rows = []
    optimization_started = time.monotonic()
    for window in selected:
        sessions = window["session_ids"]
        expected_authority = value_digest(
            [
                {"session_id": session, "evidence_digest": authority[session]["evidence_digest"]}
                for session in sessions
            ]
        )
        if expected_authority != window["observation_and_mask_authority_digest"]:
            raise ValueError("window observation authority differs from frozen inventory")
        seed_rows = published_seed_rows(sessions, scan_rows, authority)
        seeds = deterministic_seeds(seed_rows)
        arms = fit_window(joint, cache, sessions, seeds, args.max_evaluations)
        inference_rows.append(
            {
                "window_id": window["window_id"],
                "scan_count": window["scan_count"],
                "session_ids": sessions,
                "authority_digest": window["observation_and_mask_authority_digest"],
                "seed_policy": (
                    "means of in-window published Sacramento and Reno selected "
                    "coordinates plus their midpoint"
                ),
                "candidate_scope": (
                    "conditional union of in-scan published identities; published "
                    "identity selection used evaluation rows"
                ),
                "arms": arms,
            }
        )
    inference = {
        "schema": "training-only-continuous-position-search/v1",
        "position_truth_used": False,
        "dataset_digest": "sha256:" + hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "day_inventory_digest": "sha256:"
        + hashlib.sha256(args.day_inventory.read_bytes()).hexdigest(),
        "cache_manifest_digests": cache_manifest_digests,
        "max_evaluations_per_seed": args.max_evaluations,
        "timing_grid_s": TAUS.tolist(),
        "objectives": ["capped800", "pseudo_huber_150hz"],
        "robust_scale_rationale": (
            "150 Hz frozen before validation near development training track p75 and scan median"
        ),
        "original16_diagnostic": {"session_ids": original_sessions, "arms": original_arms},
        "windows": inference_rows,
        "optimization_runtime_s": time.monotonic() - optimization_started,
        "inference_runtime_s": time.monotonic() - total_started,
    }
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    if (
        hashlib.sha256((args.output / "inference.json").read_bytes()).hexdigest()
        != (args.output / "inference.sha256").read_text().strip()
    ):
        raise ValueError("sealed inference digest verification failed")
    results = json.loads(payload)
    evaluation_started = time.monotonic()
    for arm in results["original16_diagnostic"]["arms"]:
        point = (arm["selected"]["latitude_deg"], arm["selected"]["longitude_deg"])
        arm["selected"]["common_reserved_capped800_rmse_hz"] = score_location(
            joint,
            args.original_cache,
            original_sessions,
            point,
            include_evaluation=True,
            loss_name="capped800",
        )
        arm["selected"]["evaluation_only_error_km"] = haversine_km(point, REFERENCE)
    for window in results["windows"]:
        for arm in window["arms"]:
            point = (arm["selected"]["latitude_deg"], arm["selected"]["longitude_deg"])
            arm["selected"]["common_reserved_capped800_rmse_hz"] = score_location(
                joint,
                cache,
                window["session_ids"],
                point,
                include_evaluation=True,
                loss_name="capped800",
            )
            arm["selected"]["common_reserved_uncapped_rmse_hz"] = score_location(
                joint,
                cache,
                window["session_ids"],
                point,
                include_evaluation=True,
                loss_name="uncapped",
            )
            arm["selected"]["native_reserved_objective"] = score_location(
                joint,
                cache,
                window["session_ids"],
                point,
                include_evaluation=True,
                loss_name=arm["loss"],
            )
            arm["selected"]["native_reserved_objective_units"] = "Hz-equivalent square-root loss"
            arm["selected"]["evaluation_only_error_km"] = haversine_km(point, REFERENCE)
    results["reference_coordinate"] = {
        "latitude_deg": REFERENCE[0],
        "longitude_deg": REFERENCE[1],
        "role": "post-seal evaluation only",
    }
    results["post_seal_evaluation_runtime_s"] = time.monotonic() - evaluation_started
    results["total_runtime_s"] = (
        results["inference_runtime_s"] + results["post_seal_evaluation_runtime_s"]
    )
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--day-inventory", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--original-source", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--max-evaluations", type=int, default=150)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
