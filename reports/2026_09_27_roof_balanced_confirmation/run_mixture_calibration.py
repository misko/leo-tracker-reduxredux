"""Sharded calibration-only candidate-mixture fits and final evidence gate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

import mixture_advancement
import mixture_calibration_inputs as adapter
import mixture_reception_core as core


HERE = Path(__file__).resolve().parent
ARMS = ("M0", "mean", "mixture")
RIDGE = 1.0


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_bindings(receipt: dict) -> dict:
    files = {
        "adapter": HERE / "mixture_calibration_inputs.py",
        "core": HERE / "mixture_reception_core.py",
        "advancement_gate": HERE / "mixture_advancement.py",
        "design": HERE / "CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md",
        "execution_protocol": HERE / "MIXTURE_CALIBRATION_EXECUTION.md",
        "runner": Path(__file__),
    }
    return {"code_and_protocol_sha256": {
                name: digest(path.read_bytes()) for name, path in files.items()},
            "input_source_hashes": receipt["source_hashes"],
            "candidate_prior_sha256": receipt["candidate_prior_sha256"],
            "structural_input_sha256": None}


def component_summary(theta, tracks, layout) -> dict:
    rows = core.score_tracks(theta, tracks, layout)
    fields = ("detection_marginal_nll", "conditional_ratio_increment_nll", "joint_nll")
    sums = {name: float(sum(row[name] for row in rows)) for name in fields}
    if not np.isclose(sums["detection_marginal_nll"] +
                      sums["conditional_ratio_increment_nll"],
                      sums["joint_nll"], rtol=0, atol=1e-10):
        raise ValueError("shared-identity score components do not sum to joint NLL")
    return {"track_count": len(rows), "sums": sums,
            "per_track": {name: value / len(rows) for name, value in sums.items()}}


def fit_arm(train, test, schema, arm: str) -> dict:
    training, layout, feature_names = adapter.build_arm(train, schema, arm, core)
    held, held_layout, held_names = adapter.build_arm(test, schema, arm, core)
    if (layout.detection_size != held_layout.detection_size or
            layout.ratio_size != held_layout.ratio_size or
            not np.array_equal(layout.detection_penalty_mask,
                               held_layout.detection_penalty_mask) or
            not np.array_equal(layout.ratio_penalty_mask,
                               held_layout.ratio_penalty_mask) or
            feature_names != held_names):
        raise ValueError("held data changed training-fold feature contract")
    starts = core.default_starts(layout)
    if len(starts) != 3:
        raise ValueError("execution protocol requires exactly three starts")
    optimization = core.optimize_multistart(
        training, layout, ridge=RIDGE, starts=starts,
        gradient_tolerance=1e-6, stability_tolerance=1e-7,
        prediction_stability_tolerance=1e-4)
    theta = np.asarray(optimization["theta"], float)
    pd, pr = layout.detection_size, layout.ratio_size
    return {
        "arm": arm, "feature_names": feature_names,
        "penalty_masks": {
            "detection": np.asarray(layout.detection_penalty_mask, bool).tolist(),
            "ratio": np.asarray(layout.ratio_penalty_mask, bool).tolist()},
        "coefficients": {"detection": theta[:pd].tolist(),
                         "ratio": theta[pd:pd + pr].tolist()},
        "log_sigma": float(theta[-1]),
        "variance": float(math.exp(2 * theta[-1])),
        "optimizer": optimization,
        "converged": bool(optimization["accepted"]),
        "training_components": component_summary(theta, training, layout),
        "score_components": component_summary(theta, held, layout),
    }


def shard_path(index: int, sessions: list[str]) -> Path:
    if index == 0:
        return HERE / "mixture-calibration-full.json"
    return HERE / f"mixture-calibration-fold-{sessions[index - 1]}.json"


def fit_index(index: int) -> None:
    tracks, receipt = adapter.load_joined()
    sessions = receipt["sessions"]
    if not 0 <= index <= 6:
        raise ValueError("fit index must be 0 (full) or 1..6 (held session)")
    target = shard_path(index, sessions)
    if target.exists():
        raise FileExistsError(target)
    started = time.monotonic()
    held_session = None if index == 0 else sessions[index - 1]
    train = tuple(track for track in tracks if track.session_id != held_session)
    test = tracks if held_session is None else tuple(
        track for track in tracks if track.session_id == held_session)
    if held_session is not None and (not train or not test):
        raise ValueError("conditional LOSO partition is empty")
    schema = adapter.fit_schema(train)
    models = {}
    for arm in ARMS:
        print("FIT_ARM", index, held_session or "full", arm, flush=True)
        models[arm] = fit_arm(train, test, schema, arm)
    bindings = source_bindings(receipt)
    bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    output = {
        "kind": "descriptive_full_six" if index == 0 else "conditional_loso",
        "fit_index": index, "held_session": held_session,
        "training_sessions": [sid for sid in sessions if sid != held_session],
        "calibration_sessions": sessions,
        "training_track_count": len(train), "score_track_count": len(test),
        "row_count": receipt["rows"], "full_track_count": receipt["tracks"],
        "excluded_track_keys": receipt["excluded_track_keys"],
        "join_accounting": receipt["join_accounting"],
        "feature_schema": asdict(schema), "ridge": RIDGE,
        "starts": "core.default_starts: zero; coefficients +0.2/log_sigma +0.25; coefficients -0.2/log_sigma -0.25",
        "bindings": bindings, "models": models,
        "all_models_converged": all(model["converged"] for model in models.values()),
        "elapsed_s": time.monotonic() - started,
        "caveat": "Reception LOSO holds out this scan, but candidate identities, weights, and frequency parameters were fitted using all six scans; this is conditional, not fully nested validation.",
    }
    atomic(target, output)
    print("FIT_DONE", index, round(output["elapsed_s"], 2), flush=True)


def aggregate() -> None:
    target = HERE / "mixture_calibration.json"
    if target.exists():
        raise FileExistsError(target)
    tracks, receipt = adapter.load_joined()
    sessions = receipt["sessions"]
    expected_bindings = source_bindings(receipt)
    expected_bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    shards = []
    shard_hashes = {}
    for index in range(7):
        path = shard_path(index, sessions)
        if not path.exists():
            raise FileNotFoundError(f"missing immutable fit shard: {path.name}")
        payload = path.read_bytes(); shard = json.loads(payload)
        if (shard.get("fit_index") != index or shard.get("bindings") != expected_bindings or
                shard.get("calibration_sessions") != sessions or
                set(shard.get("models", {})) != set(ARMS)):
            raise ValueError("fit shard identity/source binding changed")
        expected_held = None if index == 0 else sessions[index - 1]
        expected_training = sessions if index == 0 else [
            sid for sid in sessions if sid != expected_held]
        expected_score_count = (344 if index == 0 else
                                sum(track.session_id == expected_held for track in tracks))
        expected_training_count = 344 if index == 0 else 344 - expected_score_count
        if (shard.get("held_session") != expected_held or
                shard.get("training_sessions") != expected_training or
                shard.get("score_track_count") != expected_score_count or
                shard.get("training_track_count") != expected_training_count or
                shard.get("all_models_converged") != all(
                    bool(shard["models"][arm].get("converged")) for arm in ARMS)):
            raise ValueError("fit shard partition/count/convergence receipt changed")
        shards.append(shard); shard_hashes[path.name] = digest(payload)
    folds = []
    for shard in shards[1:]:
        folds.append({
            "session_id": shard["held_session"],
            "track_count": shard["score_track_count"],
            "models": {arm: {
                "joint_nll_sum": shard["models"][arm]["score_components"]["sums"]["joint_nll"],
                "converged": bool(shard["models"][arm]["converged"])}
                for arm in ARMS},
        })
    gate = mixture_advancement.evaluate_gate(folds, sessions)
    full_converged = bool(shards[0]["all_models_converged"])
    output = {
        "scope": "Six calibration scans only; full-six descriptive and conditional reception LOSO; no geographic/evaluation outcomes.",
        "calibration_sessions": sessions, "rows": 6378, "tracks": 344,
        "ridge": RIDGE, "bindings": expected_bindings,
        "shard_sha256": shard_hashes,
        "descriptive_full_six": shards[0],
        "conditional_loso": folds,
        "conditional_loso_shards": shards[1:],
        "advancement_gate": gate,
        "full_six_all_models_converged": full_converged,
        "calibration_accepted": bool(full_converged and gate["advance"]),
        "legacy_reference": "Existing consistent-mean calibration is context only and is not the isolation contrast.",
    }
    atomic(target, output)
    print("AGGREGATE_DONE", "advance", gate["advance"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit-index", type=int, choices=range(7))
    group.add_argument("--aggregate", action="store_true")
    arguments = parser.parse_args()
    aggregate() if arguments.aggregate else fit_index(arguments.fit_index)
