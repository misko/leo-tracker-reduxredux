"""Replay old and consistent reception calibrations on frozen local grids."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_27_roof_geometry_confirmation"
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
sys.path[:0] = [str(HERE), str(PREVIOUS), str(LOCATION)]

import paired_reception_evaluator as paired
import run_balanced_confirmation as balanced


frozen = balanced.frozen
base = balanced.base
TOLERANCE = 1e-7


def validate_serialized_model(actual: dict, expected: dict,
                              tolerance: float = 1e-12) -> None:
    actual_metadata = {key: value for key, value in actual.items()
                       if key != "coefficients"}
    expected_metadata = {key: value for key, value in expected.items()
                         if key != "coefficients"}
    if actual_metadata != expected_metadata:
        raise ValueError("serialized old model metadata differs from frozen model")
    left = np.asarray(actual.get("coefficients"), float)
    right = np.asarray(expected.get("coefficients"), float)
    if (left.shape != right.shape or not np.all(np.isfinite(left)) or
            not np.all(np.isfinite(right)) or
            not np.allclose(left, right, rtol=0, atol=tolerance)):
        raise ValueError("serialized old model coefficients differ from frozen model")


def validate_calibration(calibration: dict, detection, continuous,
                         variance: float) -> tuple[object, object, float]:
    required = {"old", "consistent", "source_hashes", "m0_invariance",
                "join_accounting", "calibration_sessions"}
    if required - calibration.keys():
        raise ValueError("consistent calibration artifact is incomplete")
    validate_serialized_model(
        calibration["old"]["detection"]["M1"], asdict(detection))
    validate_serialized_model(
        calibration["old"]["ratio"]["M1"], asdict(continuous))
    old_variance = float(calibration["old"]["ratio_variance"]["M1"])
    if not np.isclose(old_variance, float(variance), rtol=0, atol=1e-14):
        raise ValueError("serialized old ratio variance differs from frozen model")
    if calibration["join_accounting"].get("exact_join_rows") != 6378:
        raise ValueError("consistent calibration did not use the complete retained join")
    if calibration["m0_invariance"] != {
            "detection_model_exact": True, "ratio_model_exact": True,
            "ratio_variance_exact": True}:
        raise ValueError("consistent calibration M0 gates did not pass")
    consistent_detection = base.model_eval.FittedModel(
        **calibration["consistent"]["detection"]["M1"])
    consistent_ratio = base.model_eval.FittedModel(
        **calibration["consistent"]["ratio"]["M1"])
    consistent_variance = float(
        calibration["consistent"]["ratio_variance"]["M1"])
    if not np.isfinite(consistent_variance) or consistent_variance <= 0:
        raise ValueError("invalid consistent ratio variance")
    return consistent_detection, consistent_ratio, consistent_variance


def grid_points(branch: dict) -> tuple[tuple[float, float], ...]:
    if not isinstance(branch.get("point_components"), list):
        raise ValueError("saved local grid lacks point components")
    points = tuple((float(row["east_km"]), float(row["north_km"]))
                   for row in branch["point_components"])
    if (len(points) != branch.get("grid_count") or len(points) != len(set(points))
            or not points or not np.all(np.isfinite(np.asarray(points)))):
        raise ValueError("saved local-grid inventory is incomplete or duplicated")
    return points


def parity_report(saved_branch: dict, replay_rows: list[dict],
                  tolerance: float = TOLERANCE) -> dict:
    points = grid_points(saved_branch)
    saved = {(float(row["east_km"]), float(row["north_km"])): row
             for row in saved_branch["point_components"]}
    replay = {(float(row["east_km"]), float(row["north_km"])): row
              for row in replay_rows}
    if len(replay) != len(replay_rows) or set(replay) != set(points):
        raise ValueError("replay coordinate inventory differs from saved grid")
    maximum = 0.0
    maximum_d = 0.0
    for point in points:
        original = saved[point]["scores"]
        old = replay[point]["variant_scores"]["old"]
        consistent = replay[point]["variant_scores"]["consistent"]
        if set(original) != set(old):
            raise ValueError("old replay arm set differs from saved grid")
        values = [float(value) for source in (original, old, consistent)
                  for value in source.values()]
        if not np.all(np.isfinite(values)):
            raise ValueError("saved or replay score is nonfinite")
        maximum = max(maximum, *(abs(float(old[name]) - float(original[name]))
                                  for name in original))
        maximum_d = max(maximum_d,
                        abs(float(old["D"]) - float(consistent["D"])))
    if maximum > tolerance:
        raise ValueError(f"old local-grid parity failed: {maximum} > {tolerance}")
    if maximum_d > 1e-12:
        raise ValueError(f"reception calibration changed D: {maximum_d}")
    return {"points": len(points), "old_saved_max_absolute_difference": maximum,
            "old_consistent_D_max_absolute_difference": maximum_d,
            "tolerance": tolerance, "passed": True}


def select_min(rows: list[dict], variant: str, arm: str) -> dict:
    if not rows:
        raise ValueError("cannot select from empty replay")
    return min(rows, key=lambda row: (
        float(row["variant_scores"][variant][arm]), float(row["east_km"]),
        float(row["north_km"])))


def evaluate_points(evaluator, points, session_id: str, prior: str) -> list[dict]:
    rows = []
    for index, (east, north) in enumerate(points, start=1):
        rows.append(evaluator.evaluate(east, north))
        if index % 25 == 0 or index == len(points):
            print("REPLAY_PROGRESS", session_id, prior, index, len(points), flush=True)
    return rows


def run(index: int) -> None:
    started = time.monotonic()
    entries, contract = balanced.inputs()
    if not 0 <= index < len(entries):
        raise IndexError("scan index out of range")
    entry = entries[index]
    sid = entry["session_id"]
    target = HERE / f"consistent-replay-{sid}.json"
    if target.exists():
        raise FileExistsError(target)
    grid_path = HERE / f"local-grid-{sid}.json"
    grid_bytes = grid_path.read_bytes()
    grid = json.loads(grid_bytes)
    if (not grid.get("finished") or grid.get("session_id") != sid or
            grid.get("deduplicate_reception") is not False):
        raise ValueError("saved primary local grid is incomplete or wrong sensitivity")
    distances_path = HERE / "local-grid-distances.json"
    distances_bytes = distances_path.read_bytes()
    distances = json.loads(distances_bytes)
    if (not distances.get("complete") or
            distances.get("deduplicate_reception") is not False or
            distances.get("artifact_sha256", {}).get(sid) != base.digest(grid_bytes)):
        raise ValueError("saved grid is not bound by the completed primary grid report")

    calibration_audit, calibration_audit_sha = frozen.frozen_audit()
    frequency, detection, continuous, variance, bias, model_hashes = \
        frozen.frozen_models(calibration_audit, calibration_audit_sha)
    second_audit_path = HERE / "audit_source_topology.json"
    second_audit_bytes = second_audit_path.read_bytes()
    second_audit = json.loads(second_audit_bytes)
    second_audit_sha = base.digest(second_audit_bytes)
    contract_sha = base.digest((HERE / "contract.json").read_bytes())
    if (grid.get("contract_sha256") != contract_sha or
            grid.get("topology_audit_sha256") != second_audit_sha or
            grid.get("model_hashes") != model_hashes or
            grid.get("parameters") != frequency["parameters"] or
            grid.get("cache_sha256") != entry["cache_sha256"]):
        raise ValueError("saved local-grid frozen input/model binding changed")
    calibration_path = HERE / "calibration_consistent_calibration.json"
    calibration_bytes = calibration_path.read_bytes()
    calibration = json.loads(calibration_bytes)
    replay_protocol_path = HERE / "CONSISTENT_REPLAY_PROTOCOL.md"
    replay_protocol_bytes = replay_protocol_path.read_bytes()
    expected_sessions = sorted(row["session_id"] for row in calibration_audit["sessions"]
                               if row["split"] == "calibration")
    if calibration["calibration_sessions"] != expected_sessions:
        raise ValueError("consistent calibration cohort differs from frozen calibration")
    for key, path in (
        ("model_rows", frozen.original.DIRECTION / "model_rows.json"),
        ("topology_audit", PREVIOUS / "audit_source_topology.json"),
        ("model_eval", frozen.original.DIRECTION / "model_eval.py"),
        ("evaluation_inventory", frozen.original.DIRECTION / "evaluation_inventory.json"),
        ("fit_code", HERE / "calibration_consistent_fit.py"),
        ("consistent_protocol", HERE / "CONSISTENT_CALIBRATION_PROTOCOL.md"),
        ("calibration_directions_data", HERE / "calibration_directions_data.json"),
    ):
        if calibration["source_hashes"][key] != base.digest(path.read_bytes()):
            raise ValueError("consistent calibration source changed: " + key)
    consistent_detection, consistent_ratio, consistent_variance = \
        validate_calibration(calibration, detection, continuous, variance)

    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]:
        raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(prepared, key) != entry[key] or getattr(prepared, key) != grid[key]:
            raise ValueError("prepared input or saved-grid binding changed")
    for key in ("evidence_sha256", "snapshot_digest"):
        if getattr(prepared, key) != grid[key]:
            raise ValueError("prepared evidence or snapshot differs from saved grid")
    links = frozen.resolve(raw)
    prepared, receipt = frozen.filter_prepared(prepared, links)
    audited = next(row for row in second_audit["sessions"]
                   if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key] or receipt[key] != grid["topology_receipt"][key]:
            raise ValueError("topology receipt changed: " + key)
    canonical = json.dumps(
        links, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]:
        raise ValueError("source links changed")
    rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    old_reception, old_endpoints = frozen.original.reception_inputs(
        prepared, rows, detection, continuous)
    consistent_reception, consistent_endpoints = frozen.original.reception_inputs(
        prepared, rows, consistent_detection, consistent_ratio)
    if old_endpoints != consistent_endpoints:
        raise ValueError("calibration changed reception endpoint membership")
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    variants = {
        "old": (old_reception, variance),
        "consistent": (consistent_reception, consistent_variance),
    }
    output = {
        "session_id": sid, "finished": False,
        "protocol": {
            "status": "posthoc fixed-grid paired reception-calibration replay",
            "inventory": "exact saved primary local-grid point_components per prior; no new coordinates",
            "frequency": "same shortlist/CFO fit once per point and shared by both reception variants",
            "selection": "minimum D_plus_geometry within each variant on identical points",
            "truth_access": "local-grid-distances is read only to verify the source-grid artifact hash; no distance/error/reference fields choose points or scores",
            "parity_tolerance": TOLERANCE,
        },
        "contract_sha256": contract_sha,
        "consistent_calibration_sha256": base.digest(calibration_bytes),
        "consistent_replay_protocol_sha256": base.digest(replay_protocol_bytes),
        "source_grid_sha256": base.digest(grid_bytes),
        "source_grid_report_sha256": base.digest(distances_bytes),
        "cache_sha256": entry["cache_sha256"],
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "calibration_topology_audit_sha256": calibration_audit_sha,
        "topology_audit_sha256": second_audit_sha,
        "model_hashes": model_hashes,
        "parameters": frequency["parameters"],
        "topology_receipt": receipt,
        "prediction_receipt": asdict(bank_receipt),
        "branches": {},
    }
    for prior, (latitude, longitude, _radius) in base.PRIORS.items():
        saved_branch = grid["branches"][prior]
        points = grid_points(saved_branch)
        evaluator = paired.PairedEvaluator(
            banks, (latitude, longitude), variants, frequency["parameters"])
        evaluated = evaluate_points(evaluator, points, sid, prior)
        parity = parity_report(saved_branch, evaluated)
        output["branches"][prior] = {
            "origin": [latitude, longitude],
            "grid_count": len(points), "parity": parity,
            "selected": {name: select_min(evaluated, name, "D_plus_geometry")
                         for name in variants},
            "point_components": evaluated,
        }
        print("REPLAY_DONE", sid, prior, len(points), flush=True)
    if not all(branch["parity"]["passed"] for branch in output["branches"].values()):
        raise ValueError("not all replay parity gates passed")
    output["finished"] = True
    output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {
        name: base.digest((HERE / name).read_bytes()) for name in
        ("run_consistent_replay.py", "paired_reception_evaluator.py",
         "calibration_consistent_fit.py")}
    base.atomic(target, output)
    print("SCAN_DONE", sid, round(output["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-index", type=int, required=True, choices=range(4))
    arguments = parser.parse_args()
    run(arguments.scan_index)
