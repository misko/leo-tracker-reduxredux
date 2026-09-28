"""Numerically polish immutable reception-calibration LOSO fits and aggregate them."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np

import mixture_advancement
import mixture_calibration_inputs as adapter
import mixture_newton_polish as polish
import mixture_reception_core as core
import run_mixture_calibration as original
import run_mixture_polished_full as full_runner


HERE = Path(__file__).resolve().parent
ARMS = original.ARMS
PROTOCOL = HERE / "MIXTURE_POLISHED_LOSO_PROTOCOL.md"


def raw_fold_path(session_id: str) -> Path:
    return HERE / f"mixture-calibration-fold-{session_id}.json"


def polished_fold_path(session_id: str) -> Path:
    return HERE / f"mixture-calibration-polished-fold-{session_id}.json"


def partition(tracks, session_id):
    train = tuple(track for track in tracks if track.session_id != session_id)
    held = tuple(track for track in tracks if track.session_id == session_id)
    if not train or not held:
        raise ValueError("conditional LOSO partition is empty")
    return train, held


def verify_raw_fold(raw, index, sessions, tracks, receipt):
    held_session = sessions[index - 1]
    train, held = partition(tracks, held_session)
    bindings = original.source_bindings(receipt)
    bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    expected_training = [sid for sid in sessions if sid != held_session]
    if (raw.get("kind") != "conditional_loso" or raw.get("fit_index") != index or
            raw.get("held_session") != held_session or
            raw.get("training_sessions") != expected_training or
            raw.get("calibration_sessions") != sessions or
            raw.get("training_track_count") != len(train) or
            raw.get("score_track_count") != len(held) or
            raw.get("full_track_count") != len(tracks) or
            raw.get("row_count") != receipt["rows"] or
            raw.get("bindings") != bindings or set(raw.get("models", {})) != set(ARMS)):
        raise ValueError("immutable original LOSO artifact binding or partition changed")
    schema = adapter.fit_schema(train)
    if raw.get("feature_schema") != full_runner.json_value(asdict(schema)):
        raise ValueError("original LOSO feature schema no longer reproduces")
    return held_session, train, held, schema, bindings


def build_both(train, held, schema, arm):
    training, layout, names = adapter.build_arm(train, schema, arm, core)
    scoring, held_layout, held_names = adapter.build_arm(held, schema, arm, core)
    if (layout.detection_size != held_layout.detection_size or
            layout.ratio_size != held_layout.ratio_size or
            names != held_names or
            not np.array_equal(
                layout.detection_penalty_mask, held_layout.detection_penalty_mask) or
            not np.array_equal(
                layout.ratio_penalty_mask, held_layout.ratio_penalty_mask)):
        raise ValueError("held data changed training-fold feature contract")
    return training, scoring, layout, names


def expected_full_source_hashes() -> dict:
    paths = {
        "original_runner": HERE / "run_mixture_calibration.py",
        "original_core": HERE / "mixture_reception_core.py",
        "original_adapter": HERE / "mixture_calibration_inputs.py",
        "polish_core": HERE / "mixture_newton_polish.py",
        "polish_runner": HERE / "run_mixture_polished_full.py",
        "refinement_protocol": HERE / "MIXTURE_NUMERICAL_REFINEMENT.md",
    }
    return {name: original.digest(path.read_bytes()) for name, path in paths.items()}


def verified_polished_full(sessions, expected_bindings):
    path = HERE / "mixture-calibration-polished-full.json"
    payload = path.read_bytes(); value = json.loads(payload)
    raw_full = (HERE / "mixture-calibration-full.json").read_bytes()
    if (value.get("kind") != "descriptive_full_six_numerically_polished" or
            value.get("bindings") != expected_bindings or
            value.get("calibration_sessions") != sessions or
            value.get("source_hashes") != expected_full_source_hashes() or
            value.get("original_full_artifact_sha256") != original.digest(raw_full) or
            not value.get("all_models_converged") or
            set(value.get("models", {})) != set(ARMS) or
            not all(value["models"][arm].get("polish", {}).get("accepted")
                    for arm in ARMS)):
        raise ValueError("polished full-six artifact is incomplete or rebound")
    return value, original.digest(payload)


def fit_index(index: int) -> None:
    if not 1 <= index <= 6:
        raise ValueError("polished LOSO index must be 1..6")
    tracks, receipt = adapter.load_joined()
    sessions = receipt["sessions"]
    held_session = sessions[index - 1]
    target = polished_fold_path(held_session)
    if target.exists():
        raise FileExistsError(target)
    source = raw_fold_path(held_session)
    raw_bytes = source.read_bytes()
    raw = json.loads(raw_bytes)
    held_session, train, held, schema, bindings = verify_raw_fold(
        raw, index, sessions, tracks, receipt)
    _full, polished_full_sha256 = verified_polished_full(sessions, bindings)
    started = time.monotonic()
    models = {}
    objective_checks = {}
    for arm in ARMS:
        training, scoring, layout, names = build_both(train, held, schema, arm)
        raw_runs = raw["models"][arm]["optimizer"]["runs"]
        objective_checks[arm] = full_runner.verify_raw_objectives(
            raw_runs, training, layout)
        print("POLISH_LOSO_ARM", index, held_session, arm, flush=True)
        refined = polish.polish_multistart(
            raw_runs, training, layout, ridge=original.RIDGE)
        model = full_runner.serialize_model(arm, names, layout, refined, training)
        model["held_components"] = original.component_summary(
            refined["theta"], scoring, layout)
        model["score_components"] = model["held_components"]
        models[arm] = model
    output = {
        "kind": "conditional_loso_numerically_polished",
        "fit_index": index, "held_session": held_session,
        "training_sessions": [sid for sid in sessions if sid != held_session],
        "calibration_sessions": sessions,
        "training_track_count": len(train), "score_track_count": len(held),
        "row_count": receipt["rows"], "full_track_count": len(tracks),
        "ridge": original.RIDGE,
        "feature_schema": full_runner.json_value(asdict(schema)),
        "bindings": bindings,
        "original_fold_artifact_sha256": original.digest(raw_bytes),
        "polished_full_artifact_sha256": polished_full_sha256,
        "original_objective_checks": objective_checks,
        "models": models,
        "all_models_converged": all(model["converged"] for model in models.values()),
        "elapsed_s": time.monotonic() - started,
        "source_hashes": source_hashes(),
        "scope": "Calibration-only conditional reception LOSO; frequency candidate identities and weights remain conditioned on all six calibration scans.",
    }
    original.atomic(target, output)
    print("POLISHED_LOSO_DONE", index, held_session,
          "converged", output["all_models_converged"], flush=True)


def source_hashes() -> dict:
    paths = {
        "original_runner": HERE / "run_mixture_calibration.py",
        "original_core": HERE / "mixture_reception_core.py",
        "adapter": HERE / "mixture_calibration_inputs.py",
        "polish_core": HERE / "mixture_newton_polish.py",
        "polished_full_runner": HERE / "run_mixture_polished_full.py",
        "polished_loso_runner": Path(__file__),
        "advancement_gate": HERE / "mixture_advancement.py",
        "design": HERE / "CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md",
        "execution_protocol": HERE / "MIXTURE_CALIBRATION_EXECUTION.md",
        "full_refinement_protocol": HERE / "MIXTURE_NUMERICAL_REFINEMENT.md",
        "loso_refinement_protocol": PROTOCOL,
    }
    return {name: original.digest(path.read_bytes()) for name, path in paths.items()}


def aggregate() -> None:
    target = HERE / "mixture_calibration_polished.json"
    if target.exists():
        raise FileExistsError(target)
    tracks, receipt = adapter.load_joined()
    sessions = receipt["sessions"]
    expected_bindings = original.source_bindings(receipt)
    expected_bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    full_path = HERE / "mixture-calibration-polished-full.json"
    full, full_sha256 = verified_polished_full(sessions, expected_bindings)
    full_bytes = full_path.read_bytes()
    shards = []
    hashes = {full_path.name: original.digest(full_bytes)}
    current_hashes = source_hashes()
    for index, sid in enumerate(sessions, 1):
        path = polished_fold_path(sid)
        payload = path.read_bytes(); shard = json.loads(payload)
        train, held = partition(tracks, sid)
        expected_schema = full_runner.json_value(asdict(adapter.fit_schema(train)))
        if (shard.get("kind") != "conditional_loso_numerically_polished" or
                shard.get("fit_index") != index or shard.get("held_session") != sid or
                shard.get("training_sessions") != [x for x in sessions if x != sid] or
                shard.get("calibration_sessions") != sessions or
                shard.get("training_track_count") != len(train) or
                shard.get("score_track_count") != len(held) or
                shard.get("row_count") != receipt["rows"] or
                shard.get("full_track_count") != len(tracks) or
                shard.get("ridge") != original.RIDGE or
                shard.get("feature_schema") != expected_schema or
                shard.get("bindings") != expected_bindings or
                shard.get("polished_full_artifact_sha256") != full_sha256 or
                shard.get("source_hashes") != current_hashes or
                set(shard.get("models", {})) != set(ARMS) or
                shard.get("all_models_converged") != all(
                    bool(shard["models"][arm].get("converged")) for arm in ARMS)):
            raise ValueError("polished LOSO shard identity or binding changed")
        raw_payload = raw_fold_path(sid).read_bytes()
        if shard.get("original_fold_artifact_sha256") != original.digest(raw_payload):
            raise ValueError("polished LOSO shard no longer binds its raw fold")
        for arm in ARMS:
            model = shard["models"][arm]
            polish_receipt = model.get("polish", {})
            runs = polish_receipt.get("runs", [])
            train_components = model.get("training_components", {})
            held_components = model.get("score_components", {})
            if (len(runs) != 3 or bool(polish_receipt.get("accepted")) !=
                    bool(model.get("converged")) or
                    train_components.get("track_count") != len(train) or
                    held_components.get("track_count") != len(held)):
                raise ValueError("polished LOSO model receipt is malformed")
            for components in (train_components, held_components):
                sums = components.get("sums", {})
                values = [sums.get(name) for name in (
                    "detection_marginal_nll", "conditional_ratio_increment_nll", "joint_nll")]
                if (not all(isinstance(value, (int, float)) and np.isfinite(value)
                            for value in values) or
                        not np.isclose(values[0] + values[1], values[2], rtol=0, atol=1e-10)):
                    raise ValueError("polished LOSO component receipt is malformed")
        shards.append(shard); hashes[path.name] = original.digest(payload)
    folds = [{
        "session_id": shard["held_session"],
        "track_count": shard["score_track_count"],
        "models": {arm: {
            "joint_nll_sum": shard["models"][arm]["score_components"]["sums"]["joint_nll"],
            "converged": bool(shard["models"][arm]["converged"]),
        } for arm in ARMS},
    } for shard in shards]
    gate = mixture_advancement.evaluate_gate(folds, sessions)
    output = {
        "scope": "Six calibration scans only; polished full-six descriptive fit and polished conditional reception LOSO.",
        "calibration_sessions": sessions, "rows": receipt["rows"],
        "tracks": receipt["tracks"], "ridge": original.RIDGE,
        "bindings": expected_bindings, "source_hashes": current_hashes,
        "artifact_sha256": hashes,
        "descriptive_full_six": full,
        "conditional_loso": folds,
        "conditional_loso_shards": shards,
        "advancement_gate": gate,
        "full_six_all_models_converged": True,
        "calibration_accepted": bool(gate["advance"]),
        "caveat": "Conditional reception LOSO is not fully nested frequency validation and is not geographic evidence.",
    }
    original.atomic(target, output)
    print("POLISHED_AGGREGATE_DONE", "advance", gate["advance"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit-index", type=int, choices=range(1, 7))
    group.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    aggregate() if args.aggregate else fit_index(args.fit_index)
