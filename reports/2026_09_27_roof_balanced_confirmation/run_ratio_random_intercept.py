"""Calibration-only shared ratio-offset fits with all other quantities frozen."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time

import numpy as np
from scipy.optimize import minimize_scalar

import detection_random_intercept_refined as detection_core
import ratio_random_intercept as ratio_core
import run_track_random_intercept as reception
import run_track_random_intercept_refined as detection_runner


HERE = Path(__file__).resolve().parent
ARMS = reception.ARMS
GRID = (0., .0625, .125, .25, .5, 1., 2., 4.)


@dataclass(frozen=True)
class FixedTrack:
    log_weights: np.ndarray
    detection_loglik: np.ndarray
    ratio_residuals: np.ndarray
    ratio_variance: float
    row_count: int


def logsumexp(values) -> float:
    values = np.asarray(values, float); maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def precompute(tracks, theta, layout, detection_sigma) -> tuple[FixedTrack, ...]:
    pd, pr = layout.detection_size, layout.ratio_size
    variance = math.exp(2 * float(theta[-1])); output = []
    for track in tracks:
        logits = np.einsum("knp,p->kn", track.detection_design, theta[:pd])
        detection = detection_core.candidate_detection_loglik(
            logits, track.matched, detection_sigma, quadrature_order=128)
        means = np.einsum("knp,p->kn", track.ratio_design, theta[pd:pd + pr])
        matched = np.asarray(track.matched, bool)
        residuals = np.asarray(track.log_ratio)[None, matched] - means[:, matched]
        output.append(FixedTrack(np.asarray(track.log_weights, float), detection,
                                 residuals, variance, len(track.matched)))
    return tuple(output)


def score_tracks(tracks: tuple[FixedTrack, ...], tau: float) -> dict:
    joint = 0.; detection = 0.
    for track in tracks:
        ratio = ratio_core.candidate_ratio_loglik(
            track.ratio_residuals, track.ratio_variance, tau)
        joint -= logsumexp(track.log_weights + track.detection_loglik + ratio) / track.row_count
        detection -= logsumexp(track.log_weights + track.detection_loglik) / track.row_count
    return {"track_count": len(tracks), "joint_nll_sum": float(joint),
            "detection_nll_sum": float(detection),
            "conditional_ratio_nll_sum": float(joint - detection)}


def zero_parity(training, held, detection_model, tolerance=1e-10) -> dict:
    checks = {}
    for name, tracks in (("training", training), ("held", held)):
        current = score_tracks(tracks, 0.)
        expected = detection_model[name]["fitted"]
        metric_names = ("joint_nll_sum", "detection_nll_sum")
        if (current["track_count"] != expected.get("track_count") or
                not all(math.isfinite(float(current[key])) and
                        math.isfinite(float(expected.get(key, math.nan)))
                        for key in metric_names)):
            raise ValueError("tau-zero score receipt count or finiteness changed")
        differences = {
            "joint": abs(current["joint_nll_sum"] - expected["joint_nll_sum"]),
            "detection": abs(current["detection_nll_sum"] - expected["detection_nll_sum"]),
        }
        if max(differences.values()) > tolerance:
            raise ValueError("tau-zero score does not reproduce accepted detection model")
        checks[name] = {"differences": differences, "track_count": current["track_count"]}
    return {"parts": checks, "tolerance": tolerance, "passed": True}


def select_tau(training: tuple[FixedTrack, ...]) -> dict:
    cache = {}
    def objective(tau):
        value = float(tau)
        if value not in cache:
            cache[value] = score_tracks(training, value)["joint_nll_sum"]
        return cache[value]
    grid = [{"tau": value, "objective": objective(value)} for value in GRID]
    best = min(range(len(grid)), key=lambda i: (grid[i]["objective"], grid[i]["tau"]))
    lower, upper = GRID[max(0, best - 1)], GRID[min(len(GRID) - 1, best + 1)]
    result = minimize_scalar(objective, bounds=(lower, upper), method="bounded",
                             options={"xatol": 1e-9, "maxiter": 200})
    refinement = {"bounds": [lower, upper], "tau": float(result.x),
                  "objective": float(result.fun), "success": bool(result.success),
                  "message": str(result.message), "evaluations": int(result.nfev)}
    candidates = list(grid) + ([refinement] if refinement["success"] else [])
    selected = min(candidates, key=lambda row: (row["objective"], row["tau"]))
    finite = all(math.isfinite(float(row["objective"])) for row in candidates)
    return {"tau": float(selected["tau"]), "objective": float(selected["objective"]),
            "grid": grid, "refinement": refinement, "finite": finite,
            "upper_boundary": math.isclose(float(selected["tau"]), 4., abs_tol=1e-12)}


def compact(value):
    result = dict(value)
    count = result["track_count"]
    for name in ("joint_nll_sum", "detection_nll_sum", "conditional_ratio_nll_sum"):
        result[name.replace("_sum", "_per_track")] = result[name] / count
    return result


def model_metrics(train, held, schema, coefficient_model, detection_model, arm):
    train_tensor, layout, names = reception.adapter.build_arm(train, schema, arm, reception.core)
    held_tensor, held_layout, held_names = reception.adapter.build_arm(held, schema, arm, reception.core)
    if (names != held_names or layout.detection_size != held_layout.detection_size or
            layout.ratio_size != held_layout.ratio_size):
        raise ValueError("held feature contract changed")
    theta = reception.frozen_theta(coefficient_model, layout)
    sigma = float(detection_model["sigma_selection"]["sigma"])
    if not detection_model.get("numerically_accepted") or not 0 <= sigma < 8:
        raise ValueError("frozen detection scale is not accepted and interior")
    training = precompute(train_tensor, theta, layout, sigma)
    scoring = precompute(held_tensor, theta, layout, sigma)
    parity = zero_parity(training, scoring, detection_model)
    selection = select_tau(training); tau = selection["tau"]
    valid = bool(selection["refinement"]["success"] and selection["finite"] and
                 not selection["upper_boundary"])
    return {"arm": arm, "feature_names": names, "detection_sigma": sigma,
            "independent_ratio_variance": math.exp(2 * float(theta[-1])),
            "tau_selection": selection, "tau_zero_parity": parity,
            "training": {"zero": compact(score_tracks(training, 0.)),
                         "fitted": compact(score_tracks(training, tau))},
            "held": {"zero": compact(score_tracks(scoring, 0.)),
                     "fitted": compact(score_tracks(scoring, tau))},
            "numerically_accepted": valid}


def load_sources():
    tracks, receipt, calibration, calibration_sha = reception.load_calibration()
    path = HERE / "track_random_intercept_refined.json"
    payload = path.read_bytes(); detection = json.loads(payload)
    expected_code = detection_runner.source_hashes()
    expected_checks = {"all_scales_numerically_accepted_and_interior",
                       "mixture_pooled_joint_nll_improves",
                       "mixture_at_least_four_folds_improve",
                       "mixture_positive_without_largest_gain"}
    expected_protocol = reception.original.digest(
        (HERE / "TRACK_RANDOM_INTERCEPT_REFINEMENT_PROTOCOL.md").read_bytes())
    if (not detection.get("advance") or
            set(detection.get("advancement_checks", {})) != expected_checks or
            not all(detection["advancement_checks"].values()) or
            detection.get("calibration_sha256") != calibration_sha or
            detection.get("code_sha256") != expected_code or
            detection.get("protocol_sha256") != expected_protocol or
            len(detection.get("shard_sha256", {})) != 7):
        raise ValueError("accepted detection random-effect aggregate changed")
    for name, expected in detection["shard_sha256"].items():
        if reception.original.digest((HERE / name).read_bytes()) != expected:
            raise ValueError("detection random-effect shard changed: " + name)
    full_name = "track-random-intercept-refined-full.json"
    full = json.loads((HERE / full_name).read_text())
    if detection.get("full") != full:
        raise ValueError("embedded detection full fit differs from hashed shard")
    return tracks, receipt, calibration, calibration_sha, detection, reception.original.digest(payload)


def detection_shard(index, sessions, aggregate):
    if index == -1:
        return aggregate["full"]
    return json.loads((HERE / f"track-random-intercept-refined-fold-{sessions[index]}.json").read_text())


def shard_path(index, sessions):
    return (HERE / "ratio-random-intercept-full.json" if index == -1 else
            HERE / f"ratio-random-intercept-fold-{sessions[index]}.json")


def source_hashes():
    return {name: reception.original.digest((HERE / name).read_bytes()) for name in (
        "run_ratio_random_intercept.py", "ratio_random_intercept.py",
        "detection_random_intercept_refined.py", "run_track_random_intercept_refined.py",
        "run_track_random_intercept.py", "mixture_calibration_inputs.py",
        "mixture_reception_core.py")}


def fit_index(index):
    if index not in (-1, 0, 1, 2, 3, 4, 5):
        raise ValueError("fit index must be -1 or 0..5")
    tracks, receipt, calibration, calibration_sha, detection, detection_sha = load_sources()
    sessions = receipt["sessions"]; target = shard_path(index, sessions)
    if target.exists(): raise FileExistsError(target)
    held_sid = None if index == -1 else sessions[index]
    train = tuple(track for track in tracks if track.session_id != held_sid)
    held = tracks if held_sid is None else tuple(track for track in tracks if track.session_id == held_sid)
    coefficients = (calibration["descriptive_full_six"] if index == -1 else
                    next(row for row in calibration["conditional_loso_shards"]
                         if row["held_session"] == held_sid))
    detection_fit = detection_shard(index, sessions, detection)
    schema = reception.adapter.fit_schema(train)
    if coefficients["feature_schema"] != reception.full_runner.json_value(asdict(schema)):
        raise ValueError("frozen fold feature schema changed")
    started = time.monotonic(); models = {}
    for arm in ARMS:
        print("RATIO_RANDOM_ARM", index, held_sid or "full", arm, flush=True)
        models[arm] = model_metrics(train, held, schema, coefficients["models"][arm],
                                    detection_fit["models"][arm], arm)
    output = {"kind": "ratio_random_intercept_full" if index == -1 else "ratio_random_intercept_loso",
              "fit_index": index, "held_session": held_sid,
              "training_sessions": sessions if held_sid is None else [s for s in sessions if s != held_sid],
              "calibration_sessions": sessions, "training_track_count": len(train),
              "held_track_count": len(held), "models": models,
              "all_numerically_accepted": all(model["numerically_accepted"] for model in models.values()),
              "calibration_sha256": calibration_sha,
              "detection_random_effect_sha256": detection_sha,
              "detection_shard_sha256": (detection["shard_sha256"][
                  "track-random-intercept-refined-full.json"] if index == -1 else
                  detection["shard_sha256"][f"track-random-intercept-refined-fold-{held_sid}.json"]),
              "input_source_hashes": receipt["source_hashes"],
              "protocol_sha256": reception.original.digest((HERE / "RATIO_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes()),
              "code_sha256": source_hashes(), "elapsed_s": time.monotonic() - started,
              "scope": "Calibration-only analytic shared ratio offset; all coefficients, detection scales, independent ratio variance, identities, and schemas frozen."}
    reception.original.atomic(target, output); print("RATIO_RANDOM_DONE", index, output["all_numerically_accepted"])


def aggregate():
    target = HERE / "ratio_random_intercept.json"
    if target.exists(): raise FileExistsError(target)
    tracks, receipt, _calibration, calibration_sha, detection, detection_sha = load_sources()
    sessions = receipt["sessions"]; shards = []; hashes = {}; code = source_hashes()
    protocol = reception.original.digest((HERE / "RATIO_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes())
    for index in (-1, 0, 1, 2, 3, 4, 5):
        path = shard_path(index, sessions); payload = path.read_bytes(); shard = json.loads(payload)
        held = None if index == -1 else sessions[index]
        expected_train = len(tracks) if held is None else sum(t.session_id != held for t in tracks)
        expected_held = len(tracks) if held is None else sum(t.session_id == held for t in tracks)
        detection_name = ("track-random-intercept-refined-full.json" if held is None else
                          f"track-random-intercept-refined-fold-{held}.json")
        if (shard.get("fit_index") != index or shard.get("held_session") != held or
                shard.get("calibration_sessions") != sessions or
                shard.get("calibration_sha256") != calibration_sha or
                shard.get("detection_random_effect_sha256") != detection_sha or
                shard.get("detection_shard_sha256") != detection["shard_sha256"][detection_name] or
                shard.get("input_source_hashes") != receipt["source_hashes"] or
                shard.get("training_track_count") != expected_train or
                shard.get("held_track_count") != expected_held or
                shard.get("protocol_sha256") != protocol or shard.get("code_sha256") != code or
                set(shard.get("models", {})) != set(ARMS) or
                shard.get("all_numerically_accepted") != all(
                    bool(shard["models"][arm].get("numerically_accepted")) for arm in ARMS)):
            raise ValueError("ratio random-effect shard binding changed")
        shards.append(shard); hashes[path.name] = reception.original.digest(payload)
    folds = []
    for shard in shards[1:]:
        models = {}
        for arm in ARMS:
            model = shard["models"][arm]; zero = model["held"]["zero"]; fitted = model["held"]["fitted"]
            models[arm] = {"track_count": zero["track_count"], "tau": model["tau_selection"]["tau"],
                           "detection_sigma": model["detection_sigma"],
                           "zero_joint_nll_sum": zero["joint_nll_sum"],
                           "fitted_joint_nll_sum": fitted["joint_nll_sum"],
                           "zero_detection_nll_sum": zero["detection_nll_sum"],
                           "fitted_detection_nll_sum": fitted["detection_nll_sum"],
                           "zero_conditional_ratio_nll_sum": zero["conditional_ratio_nll_sum"],
                           "fitted_conditional_ratio_nll_sum": fitted["conditional_ratio_nll_sum"],
                           "numerically_accepted": model["numerically_accepted"]}
        folds.append({"session_id": shard["held_session"], "models": models})
    pooled = {}
    for arm in ARMS:
        count = sum(row["models"][arm]["track_count"] for row in folds)
        pooled[arm] = {metric.replace("_sum", "_per_track"):
                       sum(row["models"][arm][metric] for row in folds) / count
                       for metric in ("zero_joint_nll_sum", "fitted_joint_nll_sum",
                                      "zero_detection_nll_sum", "fitted_detection_nll_sum",
                                      "zero_conditional_ratio_nll_sum",
                                      "fitted_conditional_ratio_nll_sum")}
        pooled[arm]["track_count"] = count
        pooled[arm]["joint_gain_per_track"] = pooled[arm]["zero_joint_nll_per_track"] - pooled[arm]["fitted_joint_nll_per_track"]
    mixture = [{"session_id": row["session_id"],
                "gain": row["models"]["mixture"]["zero_joint_nll_sum"] - row["models"]["mixture"]["fitted_joint_nll_sum"],
                "count": row["models"]["mixture"]["track_count"]} for row in folds]
    gain = sum(row["gain"] for row in mixture); count = sum(row["count"] for row in mixture)
    largest = max(mixture, key=lambda row: (row["gain"], row["session_id"]))
    checks = {"all_fits_valid_and_interior": all(s["all_numerically_accepted"] for s in shards),
              "mixture_pooled_gain": gain / count > 0,
              "mixture_at_least_four_folds_improve": sum(row["gain"] > 0 for row in mixture) >= 4,
              "mixture_positive_without_largest_gain": (gain-largest["gain"])/(count-largest["count"]) > 0}
    output = {"scope": "Calibration-only shared ratio offset conditional LOSO; no geography.",
              "calibration_sessions": sessions, "tracks": len(tracks),
              "calibration_sha256": calibration_sha, "detection_random_effect_sha256": detection_sha,
              "protocol_sha256": protocol, "code_sha256": code, "shard_sha256": hashes,
              "full": shards[0], "folds": folds, "pooled": {"models": pooled,
                  "mixture_gain_per_track": gain/count, "largest_gain_session": largest["session_id"],
                  "gain_without_largest_per_track": (gain-largest["gain"])/(count-largest["count"])},
              "advancement_checks": checks, "advance": all(checks.values())}
    reception.original.atomic(target, output); print("RATIO_RANDOM_AGGREGATE", output["advance"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit-index", type=int, choices=(-1, 0, 1, 2, 3, 4, 5))
    group.add_argument("--aggregate", action="store_true")
    args = parser.parse_args(); aggregate() if args.aggregate else fit_index(args.fit_index)
