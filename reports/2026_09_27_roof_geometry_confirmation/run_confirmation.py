"""Frozen-cohort robust confirmation search; truth is never loaded here.

This runner is intentionally not launched by this module's tests.  It consumes
only the freezer's digest-bound public TrackingInput caches and frozen models.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
FROZEN_SESSION_IDS = (
    "scan-fw-b5604c3d838fa7ed",
    "scan-fw-f147dd8a5bc99346",
    "scan-fw-609d7a8d9861f3db",
    "scan-fw-40ebc07665464c7d",
)
FROZEN_MANIFEST_SHA256 = (
    "sha256:b73cd64530585fc53e8dff4c61de2c50f9fd711ba7f2f7ac696999ed7a22a4d2"
)
sys.path.insert(0, str(LOCATION))

import reception_endpoints
import run_search as base
from measured_search import search
from run_robust_search import RobustBranchEvaluator


def load_json(path: Path) -> object:
    return json.loads(path.read_text())


def verify_manifest_digest(payload: bytes) -> str:
    actual = base.digest(payload)
    if actual != FROZEN_MANIFEST_SHA256:
        raise ValueError("opaque confirmation manifest digest changed")
    return actual


def confirmation_entries() -> tuple[list[dict], str, str]:
    manifest_path = HERE / "manifest.json"
    inventory_path = HERE / "inventory.json"
    manifest_bytes = manifest_path.read_bytes()
    inventory_bytes = inventory_path.read_bytes()
    manifest_sha = verify_manifest_digest(manifest_bytes)
    inventory = json.loads(inventory_bytes)
    by_id = {item["session_id"]: item for item in inventory}
    if len(by_id) != len(inventory) or set(by_id) != set(FROZEN_SESSION_IDS):
        raise ValueError("confirmation inventory does not exactly match manifest")
    entries = []
    for sid in FROZEN_SESSION_IDS:
        entry = by_id[sid]
        if not entry.get("ready") or not entry.get("pose_verified") or entry.get("split") != "confirmation":
            raise ValueError(f"{sid}: confirmation input is not ready and pose-verified")
        entries.append(entry)
    return entries, manifest_sha, base.digest(inventory_bytes)


def frozen_frequency() -> tuple[dict, str]:
    path = LOCATION / "fixedpoint_parameters.json"
    payload = path.read_bytes()
    config = json.loads(payload)
    if not config.get("converged") or not config["parameters"].get("optimizer_success"):
        raise ValueError("frequency calibration is not converged")
    for filename, key in (("robust_core.py", "robust_core_sha256"),
                          ("fit_frequency.py", "fit_frequency_sha256")):
        if config[key] != base.digest((LOCATION / filename).read_bytes()):
            raise ValueError("frequency calibration implementation changed")
    development = load_json(DIRECTION / "evaluation_inventory.json")
    expected = sorted(row["session_id"] for row in development if row["split"] == "calibration")
    if config["calibration_sessions"] != expected:
        raise ValueError("frequency calibration membership changed")
    extraction = Path(config["extraction_file"])
    if extraction.name != str(extraction):
        raise ValueError("frequency extraction must be local to its report")
    if config["extraction_sha256"] != base.digest((LOCATION / extraction).read_bytes()):
        raise ValueError("frequency extraction digest mismatch")
    return config, base.digest(payload)


def frozen_reception():
    frozen_path = LOCATION / "calibration.json"
    calibration = load_json(frozen_path)
    # Deserialize the frozen fits instead of numerically refitting them.  The
    # latter can differ by machine-epsilon across BLAS builds and is not part of
    # confirmation.
    detection = base.model_eval.FittedModel(**calibration["detection"])
    continuous = base.model_eval.FittedModel(**calibration["ratio"])
    variance = float(calibration["ratio_variance"])
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("invalid frozen reception variance")
    source_rows = DIRECTION / "model_rows.json"
    source_results = DIRECTION / "results.json"
    if calibration["source_model_rows_sha256"] != base.digest(source_rows.read_bytes()):
        raise ValueError("frozen reception source rows changed")
    if calibration["source_results_sha256"] != base.digest(source_results.read_bytes()):
        raise ValueError("frozen reception result changed")
    pairing_path = DIRECTION / "pairing_summary.json"
    pairing_bytes = pairing_path.read_bytes()
    pairing = json.loads(pairing_bytes)
    bias = float(pairing["calibration_fit"]["bias_hz"])
    if not np.isfinite(bias):
        raise ValueError("nonfinite frozen receiver bias")
    return detection, continuous, variance, bias, {
        "calibration_sha256": base.digest(frozen_path.read_bytes()),
        "pairing_summary_sha256": base.digest(pairing_bytes),
    }


def attach_physical_keys(reception: dict, rows: list[dict]) -> list[dict]:
    """Retain endpoint identities for a later pair-dedup sensitivity."""
    lookup = {(row["track_id"], row["observation_id"]): row for row in rows}
    receipt = []
    for track_id, values in reception.items():
        for value in values:
            row = lookup[(track_id, value.pop("_observation_id"))]
            value["physical_pair_key"] = row["physical_pair_key"]
            value["anchor_key"] = row["anchor_key"]
            receipt.append({key: row[key] for key in (
                "track_id", "observation_id", "anchor_key", "physical_pair_key",
                "receiver_id", "matched")})
    return receipt


def reception_inputs(prepared, rows, detection, continuous):
    """Call the frozen feature adapter and bind auditable physical identities."""
    result = base.reception_inputs(prepared, rows, detection, continuous)
    observations = {track.track_id: {
        index: oid for index, oid in enumerate(track.observation_ids)
    } for track in prepared.tracks}
    for track_id, values in result.items():
        for value in values:
            value["_observation_id"] = observations[track_id][value["observation_index"]]
    receipt = attach_physical_keys(result, rows)
    return result, receipt


def run_scan(index: int, budget: int = 160) -> None:
    if budget != 160:
        raise ValueError("confirmation budget is frozen at 160 points per arm")
    entries, manifest_sha, inventory_sha = confirmation_entries()
    if not 0 <= index < len(entries):
        raise IndexError("confirmation scan index out of range")
    entry = entries[index]
    sid = entry["session_id"]
    target = HERE / f"confirmation-search-{sid}.json"
    if target.exists():
        raise FileExistsError("confirmation output exists; review before rerunning")
    frequency, frequency_sha = frozen_frequency()
    detection, continuous, ratio_variance, bias_hz, reception_hashes = frozen_reception()
    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]:
        raise ValueError("tracking input cache digest mismatch")
    raw = pickle.loads(payload)
    if raw.session_id != sid or raw.input_manifest_sha256 != entry["input_manifest_sha256"]:
        raise ValueError("cached TrackingInput identity mismatch")
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw), archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    if (prepared.input_manifest_sha256 != entry["input_manifest_sha256"] or
            prepared.analysis_manifest_sha256 != entry["analysis_manifest_sha256"]):
        raise ValueError("prepared public input digest mismatch")
    rows = reception_endpoints.build(raw, prepared, bias_hz=bias_hz)
    reception, endpoint_receipt = reception_inputs(prepared, rows, detection, continuous)
    banks, prediction_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    started = time.monotonic()
    out = {
        "session_id": sid,
        "finished": False,
        "protocol": {
            "cohort": "frozen disjoint confirmation; no refitting",
            "priors": base.PRIORS,
            "levels_km": base.LEVELS,
            "budget_per_arm": 160,
            "arms": base.ARMS,
            "timing_s": 0,
            "top_k": 3,
            "track_weight": "occupied one-second bins",
            "search": "measured-priority best-first; independent Sacramento 250 km and Reno 500 km branches",
            "truth_access": "none; metadata position evaluation must occur in a separate post-search script",
            "identity": "full causal catalogue independently at each point; robust train-only shortlist; no development candidate IDs",
        },
        "manifest_sha256": manifest_sha,
        "inventory_sha256": inventory_sha,
        "cache_sha256": entry["cache_sha256"],
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "frequency_parameters_sha256": frequency_sha,
        **reception_hashes,
        "pairing_bias_hz": bias_hz,
        "parameters": frequency["parameters"],
        "prediction_receipt": asdict(prediction_receipt),
        "tracks": len(prepared.tracks),
        "reception_rows": len(rows),
        "physical_pair_counts": dict(Counter(
            row["physical_pair_key"] for row in endpoint_receipt
            if row["physical_pair_key"] is not None)),
        "reception_endpoint_receipt": endpoint_receipt,
        "branches": {},
    }
    print("BANK_READY", sid, len(prepared.tracks), len(rows), flush=True)
    for name, (latitude, longitude, radius) in base.PRIORS.items():
        evaluator = RobustBranchEvaluator(
            banks, (latitude, longitude), reception, ratio_variance,
            frequency["parameters"])
        branch = {"origin": [latitude, longitude], "radius_km": radius, "arms": {}}
        for arm in base.ARMS:
            result = search(evaluator.for_arm(arm), radius_km=radius,
                            levels_km=base.LEVELS, budget_points=160)
            selected = result.global_incumbent
            chosen = evaluator.cache[(selected.east_km, selected.north_km)]
            branch["arms"][arm] = {
                "selected": chosen,
                "stop_reason": result.stop_reason,
                "complete": result.complete,
                "evaluated_points": len(result.all_evaluations),
                "finest_points": len(result.finest_evaluations),
                "selection": "global best evaluated objective",
                "trace": list(result.trace),
            }
            print("ARM_DONE", sid, name, arm, chosen["scores"], flush=True)
        branch["common_inventory_best"] = {
            arm: min(evaluator.cache.values(),
                     key=lambda row: (row["scores"][arm], row["east_km"], row["north_km"]))
            for arm in ("D", "D_plus_detection", "D_plus_geometry", "D_plus_reversed_geometry")
        }
        branch["point_components"] = [
            {key: value for key, value in row.items() if key != "tracks"}
            for row in evaluator.cache.values()]
        out["branches"][name] = branch
        out["elapsed_s"] = time.monotonic() - started
        base.atomic(target, out)
    out["finished"] = True
    out["elapsed_s"] = time.monotonic() - started
    out["code_sha256"] = {
        filename: base.digest(path.read_bytes()) for filename, path in {
            "run_confirmation.py": Path(__file__),
            "run_robust_search.py": LOCATION / "run_robust_search.py",
            "run_search.py": LOCATION / "run_search.py",
            "robust_core.py": LOCATION / "robust_core.py",
            "reception_endpoints.py": LOCATION / "reception_endpoints.py",
            "measured_search.py": LOCATION / "measured_search.py",
        }.items()}
    base.atomic(target, out)
    print("SCAN_DONE", sid, round(out["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-index", type=int, required=True)
    parser.add_argument("--budget", type=int, default=160)
    arguments = parser.parse_args()
    run_scan(arguments.scan_index, arguments.budget)
