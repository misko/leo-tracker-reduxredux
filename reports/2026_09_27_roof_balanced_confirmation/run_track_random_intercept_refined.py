"""Numerically refined calibration-only shared random-intercept experiment."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import detection_random_intercept_refined as refined_core
import run_track_random_intercept as original_experiment


HERE = Path(__file__).resolve().parent
ARMS = original_experiment.ARMS
FIT_ORDER = 64
VERIFY_ORDER = 128
PROTOCOL = HERE / "TRACK_RANDOM_INTERCEPT_REFINEMENT_PROTOCOL.md"


def configure_refined_quadrature() -> None:
    """Configure the frozen experiment mechanics with only the refined integrator."""
    original_experiment.random_core = refined_core
    original_experiment.FIT_ORDER = FIT_ORDER
    original_experiment.VERIFY_ORDER = VERIFY_ORDER


def original_failure_receipt() -> tuple[dict, str]:
    path = HERE / "track-random-intercept-full.json"
    payload = path.read_bytes(); value = json.loads(payload)
    expected_code = {name: original_experiment.original.digest((HERE / name).read_bytes())
                     for name in ("run_track_random_intercept.py",
                                  "detection_random_intercept.py",
                                  "mixture_calibration_inputs.py",
                                  "mixture_reception_core.py")}
    failures = [model["quadrature"][split]["passed"]
                for model in value.get("models", {}).values()
                for split in ("training", "held")]
    if (value.get("kind") != "track_random_intercept_full" or
            value.get("fit_index") != -1 or value.get("held_session") is not None or
            value.get("all_numerically_accepted") is not False or
            value.get("code_sha256") != expected_code or not failures or any(failures)):
        raise ValueError("original numerical-failure receipt changed")
    return value, original_experiment.original.digest(payload)


def source_hashes() -> dict:
    return {name: original_experiment.original.digest((HERE / name).read_bytes()) for name in (
        "run_track_random_intercept_refined.py",
        "detection_random_intercept_refined.py",
        "run_track_random_intercept.py",
        "detection_random_intercept.py",
        "mixture_calibration_inputs.py",
        "mixture_reception_core.py",
    )}


def shard_path(index: int, sessions) -> Path:
    return (HERE / "track-random-intercept-refined-full.json" if index == -1 else
            HERE / f"track-random-intercept-refined-fold-{sessions[index]}.json")


def fit_index(index: int) -> None:
    if index not in (-1, 0, 1, 2, 3, 4, 5):
        raise ValueError("fit index must be -1 (full) or 0..5 (held session)")
    configure_refined_quadrature()
    failure, failure_sha = original_failure_receipt()
    tracks, receipt, calibration, calibration_sha = original_experiment.load_calibration()
    sessions = receipt["sessions"]; target = shard_path(index, sessions)
    if target.exists(): raise FileExistsError(target)
    held_sid = None if index == -1 else sessions[index]
    train = tuple(track for track in tracks if track.session_id != held_sid)
    held = tracks if held_sid is None else tuple(
        track for track in tracks if track.session_id == held_sid)
    source = (calibration["descriptive_full_six"] if index == -1 else
              next(row for row in calibration["conditional_loso_shards"]
                   if row["held_session"] == held_sid))
    schema = original_experiment.adapter.fit_schema(train)
    if source["feature_schema"] != original_experiment.full_runner.json_value(asdict(schema)):
        raise ValueError("frozen fold-local feature schema changed")
    started = time.monotonic(); models = {}
    for arm in ARMS:
        print("REFINED_RANDOM_INTERCEPT_ARM", index, held_sid or "full", arm, flush=True)
        models[arm] = original_experiment.model_metrics(
            train, held, schema, source["models"][arm], arm)
    output = {
        "kind": "track_random_intercept_refined_full" if index == -1 else
                "track_random_intercept_refined_loso",
        "fit_index": index, "held_session": held_sid,
        "training_sessions": sessions if held_sid is None else [s for s in sessions if s != held_sid],
        "calibration_sessions": sessions, "training_track_count": len(train),
        "held_track_count": len(held), "models": models,
        "all_numerically_accepted": all(x["numerically_accepted"] for x in models.values()),
        "calibration_sha256": calibration_sha,
        "source_calibration_artifact_sha256": calibration["artifact_sha256"],
        "input_source_hashes": receipt["source_hashes"],
        "original_numerical_failure_sha256": failure_sha,
        "original_failure_maximum_differences": {
            arm: failure["models"][arm]["quadrature"]["training"][
                "maximum_candidate_track_loglik_absolute_difference"] for arm in ARMS},
        "protocol_sha256": original_experiment.original.digest(PROTOCOL.read_bytes()),
        "code_sha256": source_hashes(),
        "quadrature_refinement": {
            "scientific_model_changed": False, "fit_order": FIT_ORDER,
            "verification_order": VERIFY_ORDER,
            "method": "posterior-mode-centered and curvature-scaled Gauss-Hermite"},
        "elapsed_s": time.monotonic() - started,
        "scope": "Numerical refinement of the same calibration-only model/objective/grid/bounds/gates; no geography.",
    }
    original_experiment.original.atomic(target, output)
    print("REFINED_RANDOM_INTERCEPT_DONE", index,
          output["all_numerically_accepted"], flush=True)


def aggregate() -> None:
    configure_refined_quadrature()
    target = HERE / "track_random_intercept_refined.json"
    if target.exists(): raise FileExistsError(target)
    _failure, failure_sha = original_failure_receipt()
    tracks, receipt, calibration, calibration_sha = original_experiment.load_calibration()
    sessions = receipt["sessions"]; protocol_sha = original_experiment.original.digest(PROTOCOL.read_bytes())
    code = source_hashes(); shards = []; hashes = {}
    for index in (-1, 0, 1, 2, 3, 4, 5):
        path = shard_path(index, sessions); payload = path.read_bytes(); shard = json.loads(payload)
        held = None if index == -1 else sessions[index]
        train_count = len(tracks) if held is None else sum(t.session_id != held for t in tracks)
        score_count = len(tracks) if held is None else sum(t.session_id == held for t in tracks)
        if (shard.get("fit_index") != index or shard.get("held_session") != held or
                shard.get("calibration_sessions") != sessions or
                shard.get("calibration_sha256") != calibration_sha or
                shard.get("source_calibration_artifact_sha256") != calibration["artifact_sha256"] or
                shard.get("input_source_hashes") != receipt["source_hashes"] or
                shard.get("original_numerical_failure_sha256") != failure_sha or
                shard.get("protocol_sha256") != protocol_sha or
                shard.get("code_sha256") != code or
                shard.get("training_track_count") != train_count or
                shard.get("held_track_count") != score_count or
                set(shard.get("models", {})) != set(ARMS) or
                shard.get("all_numerically_accepted") != all(
                    bool(shard["models"][arm].get("numerically_accepted")) for arm in ARMS)):
            raise ValueError("refined random-intercept shard identity or binding changed")
        shards.append(shard); hashes[path.name] = original_experiment.original.digest(payload)
    folds = []
    for shard in shards[1:]:
        models = {}
        for arm in ARMS:
            model = shard["models"][arm]; zero = model["held"]["zero"]; fitted = model["held"]["fitted"]
            models[arm] = {"track_count": zero["track_count"],
                           "sigma": model["sigma_selection"]["sigma"],
                           "zero_joint_nll_sum": zero["joint_nll_sum"],
                           "fitted_joint_nll_sum": fitted["joint_nll_sum"],
                           "zero_detection_nll_sum": zero["detection_nll_sum"],
                           "fitted_detection_nll_sum": fitted["detection_nll_sum"],
                           "numerically_accepted": model["numerically_accepted"]}
        folds.append({"session_id": shard["held_session"], "models": models})
    pooled = {}
    for arm in ARMS:
        count = sum(row["models"][arm]["track_count"] for row in folds)
        pooled[arm] = {metric.replace("_sum", "_per_track"):
                       sum(row["models"][arm][metric] for row in folds) / count
                       for metric in ("zero_joint_nll_sum", "fitted_joint_nll_sum",
                                      "zero_detection_nll_sum", "fitted_detection_nll_sum")}
        pooled[arm]["track_count"] = count
        pooled[arm]["joint_gain_per_track"] = (
            pooled[arm]["zero_joint_nll_per_track"] - pooled[arm]["fitted_joint_nll_per_track"])
        pooled[arm]["detection_gain_per_track"] = (
            pooled[arm]["zero_detection_nll_per_track"] -
            pooled[arm]["fitted_detection_nll_per_track"])
    mixture = [{"session_id": row["session_id"],
                "gain": row["models"]["mixture"]["zero_joint_nll_sum"] -
                        row["models"]["mixture"]["fitted_joint_nll_sum"],
                "count": row["models"]["mixture"]["track_count"]} for row in folds]
    gain = sum(row["gain"] for row in mixture); count = sum(row["count"] for row in mixture)
    largest = max(mixture, key=lambda row: (row["gain"], row["session_id"]))
    checks = {
        "all_scales_numerically_accepted_and_interior": all(
            shard["all_numerically_accepted"] for shard in shards),
        "mixture_pooled_joint_nll_improves": gain / count > 0,
        "mixture_at_least_four_folds_improve": sum(row["gain"] > 0 for row in mixture) >= 4,
        "mixture_positive_without_largest_gain": (
            (gain - largest["gain"]) / (count - largest["count"]) > 0),
    }
    output = {"scope": "Numerically refined calibration-only conditional reception LOSO; no geography.",
              "calibration_sessions": sessions, "tracks": len(tracks),
              "calibration_sha256": calibration_sha,
              "original_numerical_failure_sha256": failure_sha,
              "protocol_sha256": protocol_sha, "code_sha256": code,
              "shard_sha256": hashes, "full": shards[0], "folds": folds,
              "pooled": {"models": pooled, "mixture_gain_per_track": gain / count,
                         "largest_gain_session": largest["session_id"],
                         "gain_without_largest_per_track":
                             (gain - largest["gain"]) / (count - largest["count"])},
              "advancement_checks": checks, "advance": all(checks.values())}
    original_experiment.original.atomic(target, output)
    print("REFINED_RANDOM_INTERCEPT_AGGREGATE", output["advance"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit-index", type=int, choices=(-1, 0, 1, 2, 3, 4, 5))
    group.add_argument("--aggregate", action="store_true")
    args = parser.parse_args(); aggregate() if args.aggregate else fit_index(args.fit_index)
