#!/usr/bin/env python3
"""Compare integer and continuous-within-quarter-second timing in spatial fits."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

QUARTER_TAUS = np.arange(-5.0, 5.0001, 0.25)
ARMS = (
    ("integer_capped800", "integer", "capped800"),
    ("fractional_capped800", "fractional", "capped800"),
    ("fractional_robust150", "fractional", "pseudo_huber_150hz"),
)


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fractional_profile(prediction, include_evaluation=False):
    """Jointly profile candidate, piecewise-linear tau, and CFO on training rows."""
    measured = np.asarray(prediction.measured_hz, dtype=float)
    training = np.asarray(prediction.training_mask, dtype=bool)
    if not np.any(training):
        raise ValueError("fractional profiling requires training observations")
    model = np.asarray(prediction.predictions_hz, dtype=float)
    if model.shape[1] < 2:
        raise ValueError("fractional profiling requires at least two timing nodes")
    y = measured[training]
    m0 = model[:, :-1, :][:, :, training]
    slope = np.diff(model, axis=1)[:, :, training]
    residual0 = y[None, None, :] - m0
    residual0_centered = residual0 - np.mean(residual0, axis=-1, keepdims=True)
    slope_centered = slope - np.mean(slope, axis=-1, keepdims=True)
    denominator = np.sum(slope_centered**2, axis=-1)
    alpha = np.divide(
        np.sum(residual0_centered * slope_centered, axis=-1),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    alpha = np.clip(alpha, 0.0, 1.0)
    fitted = m0 + alpha[..., None] * slope
    offset = np.mean(y[None, None, :] - fitted, axis=-1)
    mse = np.mean((y[None, None, :] - fitted - offset[..., None]) ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    mse = np.where(visible[:, None], mse, np.inf)
    candidate, interval = np.unravel_index(int(np.argmin(mse)), mse.shape)
    if not np.isfinite(mse[candidate, interval]):
        return None
    fraction = float(alpha[candidate, interval])
    tau = float(
        prediction.taus_s[interval]
        + fraction * (prediction.taus_s[interval + 1] - prediction.taus_s[interval])
    )
    result = {
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "tau_s": tau,
        "interval_index": int(interval),
        "interval_fraction": fraction,
        "offset_hz": float(offset[candidate, interval]),
        "training_rms_hz": float(np.sqrt(mse[candidate, interval])),
    }
    if include_evaluation:
        evaluation = ~training
        held_model = model[candidate, interval, evaluation] + fraction * (
            model[candidate, interval + 1, evaluation] - model[candidate, interval, evaluation]
        )
        residual = measured[evaluation] - held_model - result["offset_hz"]
        result["evaluation_rms_hz"] = float(np.sqrt(np.mean(residual**2)))
    return result


def interpolation_audit(prior, joint, prepared, sessions, point):
    """Compare selected linear-Doppler curves with direct arbitrary-tau evaluation."""
    differences = []
    centered_differences = []
    for session in sessions:
        evidence, arrays = prepared[session]
        for track in evidence["tracks"]:
            dense = joint.prediction_for_track(
                evidence, arrays, track, float(point[0]), float(point[1]), taus_s=QUARTER_TAUS
            )
            score = fractional_profile(dense)
            if score is None:
                continue
            candidate = int(np.flatnonzero(dense.candidate_ids == score["candidate_id"])[0])
            interval = score["interval_index"]
            fraction = score["interval_fraction"]
            linear = dense.predictions_hz[candidate, interval] + fraction * (
                dense.predictions_hz[candidate, interval + 1]
                - dense.predictions_hz[candidate, interval]
            )
            exact = joint.prediction_for_track(
                evidence,
                arrays,
                track,
                float(point[0]),
                float(point[1]),
                taus_s=np.asarray([score["tau_s"]]),
            )
            exact_candidate = int(np.flatnonzero(exact.candidate_ids == score["candidate_id"])[0])
            difference = linear - exact.predictions_hz[exact_candidate, 0]
            differences.extend(difference.tolist())
            centered_differences.extend((difference - np.mean(difference)).tolist())
    raw = np.asarray(differences)
    centered = np.asarray(centered_differences)
    return {
        "observation_count": int(raw.size),
        "raw_rms_hz": float(np.sqrt(np.mean(raw**2))),
        "raw_max_abs_hz": float(np.max(np.abs(raw))),
        "cfo_removed_rms_hz": float(np.sqrt(np.mean(centered**2))),
        "cfo_removed_max_abs_hz": float(np.max(np.abs(centered))),
    }


def score_rows(prior, joint, prepared, sessions, point, mode, include_evaluation=False):
    rows = []
    taus = prior.TAUS if mode == "integer" else QUARTER_TAUS
    for session in sessions:
        evidence, arrays = prepared[session]
        for track in evidence["tracks"]:
            prediction = joint.prediction_for_track(
                evidence, arrays, track, float(point[0]), float(point[1]), taus_s=taus
            )
            scorer = prior.score_prediction_training if mode == "integer" else fractional_profile
            rows.append(
                {
                    "session_id": session,
                    "weight_s": int(len(np.unique(np.floor(prediction.times_s)))),
                    "score": scorer(prediction, include_evaluation=include_evaluation),
                    "curvature_proxy_hz": (
                        0.0
                        if mode == "integer"
                        else float(
                            np.max(np.abs(np.diff(prediction.predictions_hz, n=2, axis=1))) / 8
                        )
                    ),
                }
            )
    return rows


def fit_window(prior, grouped, joint, prepared, sessions, seeds, max_evaluations):
    arms = []
    for name, mode, loss in ARMS:
        fits = []
        for seed_index, seed in enumerate(seeds, start=1):
            fit = prior.bounded_fit(
                lambda point, selected_mode=mode, selected_loss=loss: grouped.aggregate(
                    score_rows(prior, joint, prepared, sessions, point, selected_mode),
                    "training_rms_hz",
                    selected_loss,
                    "duration",
                ),
                seed,
                max_evaluations=max_evaluations,
            )
            fits.append({"seed_id": seed_index, "seed": seed, **fit})
        arms.append(
            {
                "method": name,
                "timing": mode,
                "loss": loss,
                "fits": fits,
                "selected": min(fits, key=lambda row: row["training_rmse_hz"]),
            }
        )
    return arms


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    split = json.loads(args.split.read_text())
    inventory = json.loads(args.inventory.read_text())
    authority = {row["session_id"]: row for row in inventory["scans"]}
    prior = module(args.prior_tool, "fractional_prior")
    grouped = module(args.grouped_tool, "fractional_grouped")
    joint = module(args.joint_tool, "fractional_joint")
    caches, scans, cache_digests = grouped.cache_sources(args.replication_root, args.original_cache)
    validation = split["partitions"]["validation"]
    test_ids = set(split["partitions"]["test"]["session_ids"])
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
    used = {sid for window in windows for sid in window["session_ids"]}
    if used & test_ids or not used <= set(validation["session_ids"]):
        raise ValueError("validation windows violate split")
    for session in validation["session_ids"]:
        evidence = json.loads((caches[session] / "evidence" / f"{session}.json").read_text())
        if (
            prior.value_digest(evidence["tracks"]).removeprefix("sha256:")
            != authority[session]["evidence_digest"]
        ):
            raise ValueError("cached evidence differs from frozen inventory")
        for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if scans[session][field] != authority[session][field]:
                raise ValueError(f"{field} differs from frozen inventory")
    inferred = []
    for window in windows:
        sessions = window["session_ids"]
        prepared = {sid: joint.load_scan_cache(caches[sid], sid) for sid in sessions}
        seeds = prior.deterministic_seeds(prior.published_seed_rows(sessions, scans, authority))
        inferred.append(
            {
                **window,
                "seeds": seeds,
                "arms": fit_window(
                    prior, grouped, joint, prepared, sessions, seeds, args.max_evaluations
                ),
            }
        )
    inference = {
        "schema": "fractional-timing-position/v1",
        "position_truth_used": False,
        "test_evidence_accessed": False,
        "split_manifest_sha256": "sha256:" + hashlib.sha256(args.split.read_bytes()).hexdigest(),
        "inventory_sha256": "sha256:" + hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "cache_manifest_sha256": cache_digests,
        "tau_support_s": [-5.0, 5.0],
        "state_grid_step_s": 0.25,
        "fractional_method": "joint CFO and linear tau fit inside each cached 0.25 s interval",
        "windows": inferred,
        "inference_runtime_s": time.monotonic() - started,
    }
    args.output.mkdir(parents=True)
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
            held = score_rows(prior, joint, prepared, sessions, point, arm["timing"], True)
            selected["common_training_capped800_rmse_hz"] = grouped.aggregate(
                held, "training_rms_hz", "capped800", "duration"
            )
            selected["reserved_capped800_rmse_hz"] = grouped.aggregate(
                held, "evaluation_rms_hz", "capped800", "duration"
            )
            selected["reserved_uncapped_rmse_hz"] = grouped.aggregate(
                held, "evaluation_rms_hz", "uncapped", "duration"
            )
            selected["reference_error_km"] = prior.haversine_km(point, prior.REFERENCE)
            scores = [row["score"] for row in held if row["score"] is not None]
            taus = np.asarray([score["tau_s"] for score in scores])
            selected["support_boundary_tau_fraction"] = float(np.mean(np.abs(taus) > 4.999))
            selected["noninteger_tau_fraction"] = float(
                np.mean(np.abs(taus - np.round(taus)) > 1e-6)
            )
            selected["max_linear_interpolation_curvature_proxy_hz"] = max(
                row["curvature_proxy_hz"] for row in held
            )
            if arm["timing"] == "fractional":
                selected["direct_arbitrary_tau_audit"] = interpolation_audit(
                    prior, joint, prepared, sessions, point
                )
        control = next(
            arm["selected"] for arm in window["arms"] if arm["method"] == "integer_capped800"
        )
        for arm in window["arms"]:
            if arm["timing"] == "fractional":
                arm["selected"]["common_training_capped800_gain_vs_integer_hz"] = (
                    control["common_training_capped800_rmse_hz"]
                    - arm["selected"]["common_training_capped800_rmse_hz"]
                )
                arm["selected"]["reserved_capped800_gain_vs_integer_hz"] = (
                    control["reserved_capped800_rmse_hz"]
                    - arm["selected"]["reserved_capped800_rmse_hz"]
                )
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
