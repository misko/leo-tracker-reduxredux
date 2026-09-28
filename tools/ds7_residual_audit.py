#!/usr/bin/env python3
"""Reference-free residual audit for frozen DS7 position estimates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import ds7_fast_baseline_adapter as solver
import numpy as np
from scipy.special import gammaln, logsumexp


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_sealed_response(
    response_path: Path, expected_unit: str, expected_sessions: list[str]
) -> tuple[dict, dict]:
    request_path = response_path.with_name("request.json")
    seal_path = response_path.parents[1] / "seal.json"
    response_sha256 = digest(response_path)
    request_sha256 = digest(request_path)
    seal = json.loads(seal_path.read_text())
    response_name = str(response_path.relative_to(seal_path.parent))
    request_name = str(request_path.relative_to(seal_path.parent))
    if (
        seal.get("schema") != "ds7-run-seal/v1"
        or seal.get("files", {}).get(response_name) != response_sha256
        or seal.get("files", {}).get(request_name) != request_sha256
    ):
        raise ValueError("response or request is not bound by its run seal")
    request = json.loads(request_path.read_text())
    response = json.loads(response_path.read_text())
    if (
        request.get("unit", {}).get("unit_id") != expected_unit
        or request.get("unit", {}).get("session_ids") != expected_sessions
        or response.get("unit_id") != expected_unit
    ):
        raise ValueError("sealed source unit or session order mismatch")
    return response, {
        "request": {"path": str(request_path.resolve()), "sha256": request_sha256},
        "response": {"path": str(response_path.resolve()), "sha256": response_sha256},
        "seal": {"path": str(seal_path.resolve()), "sha256": digest(seal_path)},
    }


def student_t4_log_density(centered_hz: np.ndarray) -> np.ndarray:
    z = centered_hz / 100.0
    return (
        gammaln(2.5)
        - gammaln(2.0)
        - 0.5 * math.log(4 * math.pi)
        - math.log(100.0)
        - 2.5 * np.log1p(z * z / 4)
    )


def held_predictive_log_density(train_scores: np.ndarray, held_scores: np.ndarray) -> float:
    """Posterior predictive held density with weights fixed by training."""
    return float(logsumexp(train_scores + held_scores) - logsumexp(train_scores))


def candidate_training_state(residual: np.ndarray, mask: np.ndarray, visible: np.ndarray):
    train_scores, _, audits, offsets = solver.profile(residual, mask)
    if not all(audit["converged"] for audit in audits):
        raise RuntimeError("offset stationarity check failed")
    train_scores = np.where(visible, train_scores, -np.inf)
    normalizer = logsumexp(train_scores)
    if not np.isfinite(normalizer):
        raise RuntimeError("no visible candidate")
    responsibility = np.exp(train_scores - normalizer)
    return train_scores, responsibility, offsets, int(np.argmax(train_scores))


def slope_hz_per_normalized_time(times: np.ndarray, residual: np.ndarray, duration: float) -> float:
    u = times / duration
    centered = u - u.mean()
    denominator = float(centered @ centered)
    return float(centered @ residual / denominator) if denominator > 0 else 0.0


def audit_track(model, track: dict, x: np.ndarray, duration: float) -> dict:
    prediction, visible = model.prediction(track, x)
    residual = track["y"][None, :] - prediction
    mask = track["mask"]
    train_scores, responsibility, offsets, winner = candidate_training_state(
        residual, mask, visible
    )
    centered = residual - offsets[:, None]
    density = student_t4_log_density(centered)
    held_score = density[:, ~mask].sum(axis=1)
    map_train = centered[winner, mask]
    map_held = centered[winner, ~mask]
    map_all = centered[winner]
    positive = responsibility[responsibility > 0]
    entropy = -float(np.sum(positive * np.log(positive)))
    return {
        "track_id": track["track_id"],
        "receiver_id": track["receiver_id"],
        "channel": track["channel"],
        "rf_hz": track["rf_hz"],
        "training_observations": int(mask.sum()),
        "held_observations": int((~mask).sum()),
        "training_log_score": float(logsumexp(train_scores) - math.log(track["catalogue_size"])),
        "held_predictive_log_density": held_predictive_log_density(train_scores, held_score),
        "training_rms_hz": float(np.sqrt(np.mean(map_train**2))),
        "held_rms_hz": float(np.sqrt(np.mean(map_held**2))),
        "map_candidate_index": winner,
        "map_candidate_probability": float(responsibility[winner]),
        "effective_candidate_count": float(1 / (responsibility @ responsibility)),
        "candidate_entropy_nats": entropy,
        "training_slope_hz_per_normalized_recording": slope_hz_per_normalized_time(
            np.asarray(track["times_s"])[mask], map_train, duration
        ),
        "held_slope_hz_per_normalized_recording": slope_hz_per_normalized_time(
            np.asarray(track["times_s"])[~mask], map_held, duration
        ),
        "map_centered_residual_hz": map_all.tolist(),
        "times_s": list(track["times_s"]),
        "normalized_recording_time": (np.asarray(track["times_s"]) / duration).tolist(),
        "training_mask": mask.tolist(),
    }


def response_x(response: dict) -> np.ndarray:
    if (
        response.get("status") != "ok"
        or response.get("converged") is not True
        or response.get("boundary_hit") is not False
    ):
        raise ValueError("audit requires a qualified frozen estimate")
    diagnostics = response["diagnostics"]
    return np.asarray(diagnostics["east_north_km"] + diagnostics["timing_offsets_s"])


def summarize_groups(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in key_fields)].append(row)
    output = []
    for key, items in sorted(groups.items()):
        residual = np.concatenate([np.asarray(item["map_centered_residual_hz"]) for item in items])
        slopes = {}
        for label, select_training in (("training", True), ("held", False)):
            predictors, responses = [], []
            for item in items:
                selected = np.asarray(item["training_mask"]) == select_training
                local = np.asarray(item["normalized_recording_time"])[selected]
                predictors.append(local - local.mean())
                responses.append(np.asarray(item["map_centered_residual_hz"])[selected])
            predictor = np.concatenate(predictors)
            response = np.concatenate(responses)
            slopes[f"{label}_slope_hz_per_normalized_recording"] = float(
                predictor @ response / (predictor @ predictor)
            )
        entry = {field: value for field, value in zip(key_fields, key, strict=True)}
        entry.update(
            {
                "tracks": len(items),
                "observations": len(residual),
                "rms_hz": float(np.sqrt(np.mean(residual**2))),
                "mean_hz": float(np.mean(residual)),
                **slopes,
            }
        )
        output.append(entry)
    return output


def run_audit(request_path: Path, joint_path: Path, independent_paths: list[Path]) -> dict:
    started = time.monotonic()
    request = json.loads(request_path.read_text())
    if len(independent_paths) != len(request["inputs"]):
        raise ValueError("one independent response required per input")
    expected_sessions = [row["session_id"] for row in request["inputs"]]
    joint_response, joint_provenance = load_sealed_response(
        joint_path, request["unit"]["unit_id"], expected_sessions
    )
    if request_path.resolve() != joint_path.with_name("request.json").resolve():
        raise ValueError("supplied request is not the sealed joint request")
    independent = []
    independent_provenance = []
    for index, (path, session_id) in enumerate(
        zip(independent_paths, expected_sessions, strict=True), 1
    ):
        response, source = load_sealed_response(path, f"single-{index:03}", [session_id])
        independent.append(response)
        independent_provenance.append(source)
    documents = solver.load_documents(request)
    joint_x = response_x(joint_response)
    if len(joint_x) != len(documents) + 2:
        raise ValueError("joint timing dimension mismatch")

    provenance = {
        "request": {"path": str(request_path.resolve()), "sha256": digest(request_path)},
        "joint_source": joint_provenance,
        "independent_sources": independent_provenance,
    }
    recordings = []
    all_rows = {"joint": [], "independent": []}
    for index, (document, response) in enumerate(zip(documents, independent, strict=True)):
        if response["unit_id"] != f"single-{index + 1:03}":
            raise ValueError("independent response order mismatch")
        model = solver.Stationary(document, request["config"])
        independent_x = response_x(response)
        if len(independent_x) != 3:
            raise ValueError("independent timing dimension mismatch")
        local_joint = np.asarray([joint_x[0], joint_x[1], joint_x[index + 2]])
        duration = max(max(track["times_s"]) for track in document["tracks"])
        joint_rows = [
            audit_track(model, track, local_joint, duration) for track in document["tracks"]
        ]
        independent_rows = [
            audit_track(model, track, independent_x, duration) for track in document["tracks"]
        ]
        by_id = {row["track_id"]: row for row in independent_rows}
        comparisons = []
        for joint_row in joint_rows:
            independent_row = by_id[joint_row["track_id"]]
            comparisons.append(
                {
                    "track_id": joint_row["track_id"],
                    "joint_minus_independent_training_score": joint_row["training_log_score"]
                    - independent_row["training_log_score"],
                    "joint_minus_independent_held_predictive": joint_row[
                        "held_predictive_log_density"
                    ]
                    - independent_row["held_predictive_log_density"],
                    "joint_minus_independent_held_rms_hz": joint_row["held_rms_hz"]
                    - independent_row["held_rms_hz"],
                }
            )
        recordings.append(
            {
                "session_id": document["session_id"],
                "sample_rate_hz": document["sample_rate_hz"],
                "joint": joint_rows,
                "independent": independent_rows,
                "comparison": comparisons,
            }
        )
        all_rows["joint"].extend(joint_rows)
        all_rows["independent"].extend(independent_rows)

    compact = {}
    for model_name, rows in all_rows.items():
        compact[model_name] = {
            "by_receiver_channel": summarize_groups(rows, ("receiver_id", "channel")),
            "by_rf_hz": summarize_groups(rows, ("rf_hz",)),
            "median_map_probability": float(
                np.median([r["map_candidate_probability"] for r in rows])
            ),
            "median_effective_candidates": float(
                np.median([r["effective_candidate_count"] for r in rows])
            ),
            "total_training_score": float(sum(r["training_log_score"] for r in rows)),
            "total_held_predictive": float(sum(r["held_predictive_log_density"] for r in rows)),
        }
    influences = sorted(
        (
            {"session_id": recording["session_id"], **row}
            for recording in recordings
            for row in recording["comparison"]
        ),
        key=lambda row: abs(row["joint_minus_independent_training_score"]),
        reverse=True,
    )
    return {
        "schema": "ds7-residual-audit/v1",
        "reference_policy": "reference, pose, and scores excluded",
        "candidate_policy": (
            "training responsibilities and training-MAP only; held data never select "
            "candidates or offsets"
        ),
        "held_predictive_definition": (
            "logsumexp(training_score + fixed-offset held log density) - "
            "logsumexp(training_score)"
        ),
        "slope_normalization": (
            "exploratory diagnostic reported separately for training and held observations; "
            "within each track and partition, time_s is divided by recording duration and "
            "centered; slope units are Hz per normalized recording"
        ),
        "provenance": provenance,
        "summary": compact,
        "worst_training_influence": influences[:20],
        "recordings": recordings,
        "elapsed_seconds": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--joint-response", type=Path, required=True)
    parser.add_argument("--independent-response", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(args.request, args.joint_response, args.independent_response)
    with args.output.open("x") as stream:
        json.dump(result, stream, allow_nan=False, indent=2)


if __name__ == "__main__":
    main()
