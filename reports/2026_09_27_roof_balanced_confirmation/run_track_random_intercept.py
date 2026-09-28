"""Calibration-only shared track-random-intercept fits with frozen coefficients."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import numpy as np
from scipy.optimize import minimize_scalar

import detection_random_intercept as random_core
import mixture_calibration_inputs as adapter
import mixture_reception_core as core
import run_mixture_calibration as original
import run_mixture_polished_full as full_runner
import run_mixture_polished_loso as polished


HERE = Path(__file__).resolve().parent
ARMS = original.ARMS
GRID = (0., .25, .5, 1., 2., 4., 8.)
FIT_ORDER = 128
VERIFY_ORDER = 256
QUADRATURE_TOLERANCE = .001


def logsumexp(values) -> float:
    values = np.asarray(values, float); maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def frozen_theta(model: dict, layout) -> np.ndarray:
    detection = np.asarray(model["coefficients"]["detection"], float)
    ratio = np.asarray(model["coefficients"]["ratio"], float)
    theta = np.r_[detection, ratio, float(model["log_sigma"])]
    if (detection.shape != (layout.detection_size,) or
            ratio.shape != (layout.ratio_size,) or not np.all(np.isfinite(theta))):
        raise ValueError("frozen coefficient dimensions changed")
    return theta


def track_components(track, theta, layout, sigma: float, order: int) -> dict:
    pd, pr = layout.detection_size, layout.ratio_size
    logits = np.einsum("knp,p->kn", track.detection_design, theta[:pd])
    detection = random_core.candidate_detection_loglik(
        logits, track.matched, sigma, quadrature_order=order)
    ratio_mean = np.einsum("knp,p->kn", track.ratio_design, theta[pd:pd + pr])
    variance = math.exp(2 * float(theta[-1])); matched = np.asarray(track.matched, bool)
    ratio = np.zeros(len(track.log_weights))
    if np.any(matched):
        residual = np.asarray(track.log_ratio)[None, matched] - ratio_mean[:, matched]
        ratio = np.sum(-.5 * (math.log(2 * math.pi * variance) +
                              residual ** 2 / variance), axis=1)
    rows = len(track.matched)
    return {
        "joint_nll": -logsumexp(track.log_weights + detection + ratio) / rows,
        "detection_nll": -logsumexp(track.log_weights + detection) / rows,
        "candidate_detection_log_likelihood": detection,
    }


def score_tracks(tracks, theta, layout, sigma: float, order: int) -> dict:
    rows = [track_components(track, theta, layout, sigma, order) for track in tracks]
    return {
        "track_count": len(rows),
        "joint_nll_sum": float(sum(row["joint_nll"] for row in rows)),
        "detection_nll_sum": float(sum(row["detection_nll"] for row in rows)),
        "candidate_detection_log_likelihood": [
            row["candidate_detection_log_likelihood"] for row in rows],
    }


def sigma_zero_parity(tracks, theta, layout, tolerance=1e-10) -> dict:
    existing = core.score_tracks(theta, tracks, layout)
    current = score_tracks(tracks, theta, layout, 0., FIT_ORDER)
    joint = max(abs(row["joint_nll"] - old["joint_nll"])
                for row, old in zip(
                    [track_components(track, theta, layout, 0., FIT_ORDER)
                     for track in tracks], existing, strict=True))
    detection = max(abs(row["detection_nll"] - old["detection_marginal_nll"])
                    for row, old in zip(
                        [track_components(track, theta, layout, 0., FIT_ORDER)
                         for track in tracks], existing, strict=True))
    if max(joint, detection) > tolerance:
        raise ValueError("sigma-zero likelihood does not reproduce frozen core")
    return {"joint_max_absolute_difference": joint,
            "detection_max_absolute_difference": detection,
            "tolerance": tolerance, "passed": True,
            "joint_nll_sum": current["joint_nll_sum"]}


def select_sigma(tracks, theta, layout) -> dict:
    cache = {}
    def objective(sigma):
        key = float(sigma)
        if key not in cache:
            cache[key] = score_tracks(tracks, theta, layout, key, FIT_ORDER)["joint_nll_sum"]
        return cache[key]
    grid = [{"sigma": value, "objective": objective(value)} for value in GRID]
    best_index = min(range(len(grid)), key=lambda i: (grid[i]["objective"], grid[i]["sigma"]))
    lower = GRID[max(0, best_index - 1)]
    upper = GRID[min(len(GRID) - 1, best_index + 1)]
    result = minimize_scalar(objective, bounds=(lower, upper), method="bounded",
                             options={"xatol": 1e-8, "maxiter": 200})
    refinement = {"bounds": [lower, upper], "sigma": float(result.x),
                  "objective": float(result.fun), "success": bool(result.success),
                  "message": str(result.message), "evaluations": int(result.nfev)}
    candidates = list(grid) + ([refinement] if refinement and refinement["success"] else [])
    selected = min(candidates, key=lambda row: (row["objective"], row["sigma"]))
    return {"sigma": float(selected["sigma"]), "objective": float(selected["objective"]),
            "grid": grid, "refinement": refinement,
            "upper_boundary": math.isclose(float(selected["sigma"]), 8., abs_tol=1e-12)}


def quadrature_check(tracks, theta, layout, sigma) -> dict:
    low = score_tracks(tracks, theta, layout, sigma, FIT_ORDER)
    high = score_tracks(tracks, theta, layout, sigma, VERIFY_ORDER)
    differences = [float(np.max(np.abs(a - b))) for a, b in zip(
        low["candidate_detection_log_likelihood"],
        high["candidate_detection_log_likelihood"], strict=True)]
    maximum = max(differences, default=0.)
    return {"fit_order": FIT_ORDER, "verification_order": VERIFY_ORDER,
            "maximum_candidate_track_loglik_absolute_difference": maximum,
            "tolerance": QUADRATURE_TOLERANCE,
            "passed": bool(maximum <= QUADRATURE_TOLERANCE)}


def model_metrics(train, held, schema, model, arm) -> dict:
    training, layout, names = adapter.build_arm(train, schema, arm, core)
    scoring, held_layout, held_names = adapter.build_arm(held, schema, arm, core)
    if (names != held_names or layout.detection_size != held_layout.detection_size or
            layout.ratio_size != held_layout.ratio_size):
        raise ValueError("held feature contract changed")
    theta = frozen_theta(model, layout)
    parity = sigma_zero_parity(training, theta, layout)
    selection = select_sigma(training, theta, layout)
    sigma = selection["sigma"]
    train_zero = score_tracks(training, theta, layout, 0., VERIFY_ORDER)
    train_fitted = score_tracks(training, theta, layout, sigma, VERIFY_ORDER)
    held_zero = score_tracks(scoring, theta, layout, 0., VERIFY_ORDER)
    held_fitted = score_tracks(scoring, theta, layout, sigma, VERIFY_ORDER)
    train_check = quadrature_check(training, theta, layout, sigma)
    held_check = quadrature_check(scoring, theta, layout, sigma)
    accepted = bool(selection["refinement"]["success"] and
                    train_check["passed"] and held_check["passed"] and
                    not selection["upper_boundary"])
    def compact(value):
        result = {key: value[key] for key in ("track_count", "joint_nll_sum",
                                               "detection_nll_sum")}
        result["joint_nll_per_track"] = result["joint_nll_sum"] / result["track_count"]
        result["detection_nll_per_track"] = (
            result["detection_nll_sum"] / result["track_count"])
        return result
    return {"arm": arm, "feature_names": names, "sigma_selection": selection,
            "sigma_zero_parity": parity,
            "training": {"zero": compact(train_zero), "fitted": compact(train_fitted)},
            "held": {"zero": compact(held_zero), "fitted": compact(held_fitted)},
            "quadrature": {"training": train_check, "held": held_check},
            "numerically_accepted": accepted}


def load_calibration():
    aggregate_path = HERE / "mixture_calibration_polished.json"
    payload = aggregate_path.read_bytes(); value = json.loads(payload)
    tracks, receipt = adapter.load_joined(); sessions = receipt["sessions"]
    expected_bindings = original.source_bindings(receipt)
    expected_bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    if (value.get("calibration_sessions") != sessions or value.get("bindings") != expected_bindings or
            not value.get("calibration_accepted") or
            set(value.get("descriptive_full_six", {}).get("models", {})) != set(ARMS) or
            len(value.get("conditional_loso_shards", [])) != 6):
        raise ValueError("accepted polished calibration artifact changed")
    return tracks, receipt, value, original.digest(payload)


def shard_path(index: int, sessions) -> Path:
    return (HERE / "track-random-intercept-full.json" if index == -1 else
            HERE / f"track-random-intercept-fold-{sessions[index]}.json")


def fit_index(index: int) -> None:
    if index not in (-1, 0, 1, 2, 3, 4, 5):
        raise ValueError("fit index must be -1 (full) or 0..5 (held session)")
    tracks, receipt, calibration, calibration_sha = load_calibration()
    sessions = receipt["sessions"]; target = shard_path(index, sessions)
    if target.exists(): raise FileExistsError(target)
    held_sid = None if index == -1 else sessions[index]
    train = tuple(track for track in tracks if track.session_id != held_sid)
    held = tracks if held_sid is None else tuple(track for track in tracks
                                                if track.session_id == held_sid)
    source = (calibration["descriptive_full_six"] if index == -1 else
              next(row for row in calibration["conditional_loso_shards"]
                   if row["held_session"] == held_sid))
    schema = adapter.fit_schema(train)
    if source["feature_schema"] != full_runner.json_value(asdict(schema)):
        raise ValueError("frozen fold-local feature schema changed")
    started = time.monotonic(); models = {}
    for arm in ARMS:
        print("RANDOM_INTERCEPT_ARM", index, held_sid or "full", arm, flush=True)
        models[arm] = model_metrics(train, held, schema, source["models"][arm], arm)
    output = {
        "kind": "track_random_intercept_full" if index == -1 else "track_random_intercept_loso",
        "fit_index": index, "held_session": held_sid,
        "training_sessions": sessions if held_sid is None else [s for s in sessions if s != held_sid],
        "calibration_sessions": sessions, "training_track_count": len(train),
        "held_track_count": len(held), "models": models,
        "all_numerically_accepted": all(x["numerically_accepted"] for x in models.values()),
        "calibration_sha256": calibration_sha,
        "source_calibration_artifact_sha256": calibration["artifact_sha256"],
        "input_source_hashes": receipt["source_hashes"],
        "protocol_sha256": original.digest((HERE / "TRACK_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes()),
        "code_sha256": {name: original.digest((HERE / name).read_bytes()) for name in (
            "run_track_random_intercept.py", "detection_random_intercept.py",
            "mixture_calibration_inputs.py", "mixture_reception_core.py")},
        "elapsed_s": time.monotonic() - started,
        "scope": "Calibration reception only; frozen coefficients, schemas, candidate IDs/weights, ratios, and frequency priors; no geography.",
    }
    original.atomic(target, output)
    print("RANDOM_INTERCEPT_DONE", index, output["all_numerically_accepted"], flush=True)


def aggregate() -> None:
    target = HERE / "track_random_intercept.json"
    if target.exists(): raise FileExistsError(target)
    tracks, receipt, calibration, calibration_sha = load_calibration(); sessions = receipt["sessions"]
    shards = []; hashes = {}
    expected_protocol = original.digest((HERE / "TRACK_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes())
    expected_code = {name: original.digest((HERE / name).read_bytes()) for name in (
        "run_track_random_intercept.py", "detection_random_intercept.py",
        "mixture_calibration_inputs.py", "mixture_reception_core.py")}
    for index in (-1, 0, 1, 2, 3, 4, 5):
        path = shard_path(index, sessions); payload = path.read_bytes(); shard = json.loads(payload)
        expected_held = None if index == -1 else sessions[index]
        expected_train = len(tracks) if index == -1 else sum(
            track.session_id != expected_held for track in tracks)
        expected_score = len(tracks) if index == -1 else sum(
            track.session_id == expected_held for track in tracks)
        if (shard.get("fit_index") != index or shard.get("held_session") != expected_held or
                shard.get("calibration_sessions") != sessions or
                shard.get("calibration_sha256") != calibration_sha or
                shard.get("source_calibration_artifact_sha256") != calibration["artifact_sha256"] or
                shard.get("input_source_hashes") != receipt["source_hashes"] or
                shard.get("protocol_sha256") != expected_protocol or
                shard.get("code_sha256") != expected_code or
                shard.get("training_track_count") != expected_train or
                shard.get("held_track_count") != expected_score or
                set(shard.get("models", {})) != set(ARMS) or
                shard.get("all_numerically_accepted") != all(
                    bool(shard["models"][arm].get("numerically_accepted")) for arm in ARMS)):
            raise ValueError("random-intercept shard identity or binding changed")
        shards.append(shard); hashes[path.name] = original.digest(payload)
    folds = []
    for shard in shards[1:]:
        models = {}
        for arm in ARMS:
            model = shard["models"][arm]; zero = model["held"]["zero"]
            fitted = model["held"]["fitted"]
            models[arm] = {
                "track_count": zero["track_count"], "sigma": model["sigma_selection"]["sigma"],
                "zero_joint_nll_sum": zero["joint_nll_sum"],
                "fitted_joint_nll_sum": fitted["joint_nll_sum"],
                "zero_detection_nll_sum": zero["detection_nll_sum"],
                "fitted_detection_nll_sum": fitted["detection_nll_sum"],
                "numerically_accepted": model["numerically_accepted"],
            }
        folds.append({"session_id": shard["held_session"], "models": models})
    pooled = {}
    for arm in ARMS:
        total = sum(row["models"][arm]["track_count"] for row in folds)
        pooled[arm] = {
            metric.replace("_sum", "_per_track"):
                sum(row["models"][arm][metric] for row in folds) / total
            for metric in ("zero_joint_nll_sum", "fitted_joint_nll_sum",
                           "zero_detection_nll_sum", "fitted_detection_nll_sum")}
        pooled[arm]["track_count"] = total
        pooled[arm]["joint_gain_per_track"] = (
            pooled[arm]["zero_joint_nll_per_track"] -
            pooled[arm]["fitted_joint_nll_per_track"])
        pooled[arm]["detection_gain_per_track"] = (
            pooled[arm]["zero_detection_nll_per_track"] -
            pooled[arm]["fitted_detection_nll_per_track"])
    mixture = [row | {"gain": row["models"]["mixture"]["zero_joint_nll_sum"] -
                               row["models"]["mixture"]["fitted_joint_nll_sum"],
                       "count": row["models"]["mixture"]["track_count"]} for row in folds]
    total_gain = sum(row["gain"] for row in mixture); total_count = sum(row["count"] for row in mixture)
    largest = max(mixture, key=lambda row: (row["gain"], row["session_id"]))
    checks = {
        "all_scales_numerically_accepted_and_interior": all(
            shard["all_numerically_accepted"] for shard in shards),
        "mixture_pooled_joint_nll_improves": total_gain / total_count > 0,
        "mixture_at_least_four_folds_improve": sum(row["gain"] > 0 for row in mixture) >= 4,
        "mixture_positive_without_largest_gain": (
            (total_gain - largest["gain"]) / (total_count - largest["count"]) > 0),
    }
    output = {"scope": "Calibration-only conditional reception LOSO; no geography.",
              "calibration_sessions": sessions, "tracks": len(tracks),
              "calibration_sha256": calibration_sha, "shard_sha256": hashes,
              "full": shards[0], "folds": folds,
              "pooled": {"models": pooled,
                         "mixture_gain_per_track": total_gain / total_count,
                         "largest_gain_session": largest["session_id"],
                         "gain_without_largest_per_track": (
                             total_gain - largest["gain"]) / (total_count - largest["count"])},
              "advancement_checks": checks, "advance": all(checks.values())}
    original.atomic(target, output); print("RANDOM_INTERCEPT_AGGREGATE", output["advance"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit-index", type=int, choices=(-1, 0, 1, 2, 3, 4, 5))
    group.add_argument("--aggregate", action="store_true")
    args = parser.parse_args(); aggregate() if args.aggregate else fit_index(args.fit_index)
