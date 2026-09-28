#!/usr/bin/env python3
"""Audit causal-refit isolation, selected objectives, and score arithmetic."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from tools.rx_causal_geometry_cv import ARMS, prepare_training
from tools.rx_joint_geometry_fit import calibration_score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_training_ids(document, held):
    return {
        window["source_window_id"]
        for lane in document["lanes"]
        if lane["recording_split"] == "calibration" and lane["lane"]["session_id"] != held
        for window in lane["windows"]
        if window["role"] == "reception"
    }


def diagnostic_ids(diagnostics):
    by_receiver = {}
    roles = set()
    for lane in diagnostics:
        for receiver in lane["receivers"]:
            key = receiver["receiver"]
            ids = by_receiver.setdefault(key, set())
            for window in receiver["windows"]:
                if window["source_window_id"] in ids:
                    raise ValueError("duplicate diagnostic source window")
                ids.add(window["source_window_id"])
                roles.add(window["role"])
    if set(by_receiver) != {"rx0", "rx1"} or by_receiver["rx0"] != by_receiver["rx1"]:
        raise ValueError("receiver diagnostic populations differ")
    return by_receiver["rx0"], roles


def audit(document, cv_results, results, checkpoint_dir):
    if results.get("schema") != "rx-causal-geometry-cv/v1" or results.get("status") != "complete":
        raise ValueError("result incomplete")
    original = {fold["held_session"]: fold for fold in cv_results["folds"]}
    if len(results["folds"]) != 6 or len({fold["held_session"] for fold in results["folds"]}) != 6:
        raise ValueError("fold population mismatch")
    checkpoints = sorted(checkpoint_dir.glob("fold-*.json"))
    if len(checkpoints) != 6:
        raise ValueError("checkpoint population mismatch")
    checkpoint_hashes = {}
    result_folds = {fold["held_session"]: fold for fold in results["folds"]}
    for path in checkpoints:
        stored = json.loads(path.read_text())
        held = stored["held_session"]
        if (
            stored.get("schema") != "rx-causal-geometry-cv-fold/v1"
            or stored.get("fold") != result_folds.get(held)
            or stored.get("fingerprint", {}).get("experiment_seal")
            != results.get("experiment_seal")
            or stored.get("fingerprint", {}).get("input_sha256")
            != results.get("source_sha256")
        ):
            raise ValueError("checkpoint/result provenance mismatch")
        checkpoint_hashes[path.name] = digest(path)
    training_windows = 0
    optimizer_receipts = 0
    for fold in results["folds"]:
        held = fold["held_session"]
        expected = expected_training_ids(document, held)
        actual, roles = diagnostic_ids(fold["training_causal_diagnostics"])
        if actual != expected or roles != {"reception"}:
            raise ValueError("training outcome isolation failure")
        training_windows += len(actual)
        held_ids, held_roles = diagnostic_ids(fold["held_causal_diagnostics"])
        source_held = {
            window["source_window_id"]
            for lane in document["lanes"]
            if lane["recording_split"] == "calibration" and lane["lane"]["session_id"] == held
            for window in lane["windows"]
        }
        if held_ids != source_held or held_roles != {"reception", "held_frequency"}:
            raise ValueError("omitted-record population mismatch")
        training, _ = prepare_training(document, original[held])
        for arm in ARMS:
            fit = fold["fits"][arm]
            optimizer_receipts += len(fit["candidates"])
            converged = [row for row in fit["candidates"] if row["success"]]
            if not converged:
                raise ValueError("arm has no converged start")
            best = max(converged, key=lambda row: row["map_gain"])
            selected = fit["selected"]
            if selected["null_selected"]:
                if best["map_gain"] > 0 or selected["map_gain"] != 0:
                    raise ValueError("invalid null selection")
            elif not math.isclose(selected["map_gain"], best["map_gain"], abs_tol=1e-10):
                raise ValueError("selected optimizer candidate mismatch")
            scored = calibration_score(
                training, selected["beta"], selected["occupancy"], selected["tau_s"]
            )
            if not math.isclose(
                scored,
                selected["calibration_relative_log_evidence"],
                abs_tol=1e-8,
            ):
                raise ValueError("selected calibration objective replay mismatch")
        for evaluation in fold["evaluations"].values():
            for role in ("reception", "held_frequency"):
                row = evaluation["roles"][role]
                if not math.isclose(
                    row["full_log_score"],
                    row["reference_log_score"] + row["relative_log_score"],
                    abs_tol=1e-8,
                ):
                    raise ValueError("full score arithmetic mismatch")
                for metric in ("reference_log_score", "relative_log_score", "full_log_score"):
                    if not math.isclose(
                        row[f"{metric}_per_window"], row[metric] / row["windows"], abs_tol=1e-12
                    ):
                        raise ValueError("per-window arithmetic mismatch")
    for name, aggregate in results["aggregate_equal_record"].items():
        values = list(aggregate["records"].values())
        if not math.isclose(aggregate["mean"], math.fsum(values) / len(values), abs_tol=1e-12):
            raise ValueError(f"aggregate mean mismatch: {name}")
        if aggregate["positive_records"] != sum(value > 0 for value in values):
            raise ValueError(f"aggregate positive sign mismatch: {name}")
        if aggregate["negative_records"] != sum(value < 0 for value in values):
            raise ValueError(f"aggregate negative sign mismatch: {name}")
    return {"schema": "rx-causal-refit-audit/v1", "status": "pass", "folds": 6,
            "training_receiver_window_sets": training_windows,
            "optimizer_start_receipts": optimizer_receipts,
            "checkpoint_sha256": checkpoint_hashes}


def main():
    parser = argparse.ArgumentParser()
    for name in ("dataset", "cv_results", "results", "output"):
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in ("dataset", "cv_results", "results")}
    payloads = {name: path.read_bytes() for name, path in paths.items()}
    receipt = audit(
        *(json.loads(payloads[name]) for name in ("dataset", "cv_results", "results")),
        args.checkpoint_dir,
    )
    receipt["source_sha256"] = {name: hashlib.sha256(value).hexdigest()
                                for name, value in payloads.items()}
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
