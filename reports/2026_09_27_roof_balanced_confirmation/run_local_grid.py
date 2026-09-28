"""Posthoc development local-ranking diagnostic around each saved D solution."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import pickle
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_27_roof_geometry_confirmation"
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
sys.path[:0] = [str(HERE), str(PREVIOUS), str(LOCATION)]

import run_balanced_confirmation as balanced


frozen = balanced.frozen
base = balanced.base
OFFSETS_KM = tuple(float(value) for value in np.arange(-4., 4.0001, .5))


def local_grid(center_east: float, center_north: float, radius_km: float):
    """Return the fixed Cartesian inventory clipped to the original prior disk."""
    center = (float(center_east), float(center_north))
    radius = float(radius_km)
    if not all(math.isfinite(value) for value in (*center, radius)) or radius <= 0:
        raise ValueError("invalid grid center or prior radius")
    points = []
    for north_offset in OFFSETS_KM:
        for east_offset in OFFSETS_KM:
            point = (center[0] + east_offset, center[1] + north_offset)
            if math.hypot(*point) <= radius + 1e-10:
                points.append(point)
    if center not in points:
        raise ValueError("saved D center is outside its prior disk")
    return tuple(points)


def select_min(rows, arm):
    if not rows:
        raise ValueError("cannot select from an empty local grid")
    return min(rows, key=lambda row: (
        float(row["scores"][arm]), float(row["east_km"]),
        float(row["north_km"])))


def validated_seed(session_id: str, search_path: Path, distances: dict,
                   contract_sha256: str):
    payload = search_path.read_bytes()
    expected = distances.get("search_sha256", {}).get(session_id)
    if (not distances.get("complete") or
            distances.get("contract_sha256") != contract_sha256 or
            expected != base.digest(payload)):
        raise ValueError("primary search is incomplete or changed after distance scoring")
    search = json.loads(payload)
    if (not search.get("finished") or search.get("session_id") != session_id or
            search.get("contract_sha256") != contract_sha256):
        raise ValueError("primary search identity or frozen contract binding changed")
    for prior in base.PRIORS:
        branch = search.get("branches", {}).get(prior, {})
        selected = branch.get("arms", {}).get("D", {}).get("selected")
        if selected is None or not all(key in selected for key in ("east_km", "north_km")):
            raise ValueError("primary search lacks a saved D selection")
    return search, base.digest(payload)


def run(index: int, deduplicate: bool = False) -> None:
    started = time.monotonic()
    entries, contract = balanced.inputs()
    if not 0 <= index < len(entries):
        raise IndexError("scan index out of range")
    entry = entries[index]
    sid = entry["session_id"]
    target = HERE / f"local-grid{'-dedup' if deduplicate else ''}-{sid}.json"
    if target.exists():
        raise FileExistsError(target)
    contract_sha = base.digest((HERE / "contract.json").read_bytes())
    distance_path = HERE / "distance_results.json"
    distance_bytes = distance_path.read_bytes()
    distances = json.loads(distance_bytes)
    protocol_path = HERE / "LOCAL_GRID_PROTOCOL.md"
    protocol_bytes = protocol_path.read_bytes()
    search_path = HERE / f"search-{sid}.json"
    seed, search_sha = validated_seed(sid, search_path, distances, contract_sha)

    oldaudit, oldsha = frozen.frozen_audit()
    frequency, detection, continuous, variance, bias, models = frozen.frozen_models(
        oldaudit, oldsha)
    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]:
        raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(prepared, key) != entry[key]:
            raise ValueError("prepared input changed")
    links = frozen.resolve(raw)
    prepared, receipt = frozen.filter_prepared(prepared, links)
    audit_bytes = (HERE / "audit_source_topology.json").read_bytes()
    audit = json.loads(audit_bytes)
    audited = next(row for row in audit["sessions"] if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key]:
            raise ValueError("topology changed: " + key)
    canonical = json.dumps(
        links, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]:
        raise ValueError("source links changed")
    rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    reception, endpoints = frozen.original.reception_inputs(
        prepared, rows, detection, continuous)
    dependence = None
    if deduplicate:
        reception, dependence = frozen.deduplicate_matched_physical_pairs(
            reception, endpoints)
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))

    output = {
        "session_id": sid,
        "finished": False,
        "deduplicate_reception": deduplicate,
        "protocol": {
            "status": "posthoc development local-ranking diagnostic",
            "grid": "17x17 offsets -4..4 km by 0.5 km around each prior's own saved D selection; clipped to original prior disk",
            "objectives": ["D", "D_plus_geometry"],
            "inventory": "identical evaluated coordinates for both objectives within each prior",
            "candidate_policy": "full causal catalogue shortlist recomputed independently at every point",
            "truth_access": "reference errors are not used; the completed distance artifact is read only for source-search and contract binding",
        },
        "contract_sha256": contract_sha,
        "source_search_sha256": search_sha,
        "distance_results_sha256": base.digest(distance_bytes),
        "local_grid_protocol_sha256": base.digest(protocol_bytes),
        "topology_audit_sha256": base.digest(audit_bytes),
        "cache_sha256": entry["cache_sha256"],
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "model_hashes": models,
        "parameters": frequency["parameters"],
        "topology_receipt": receipt,
        "prediction_receipt": asdict(bank_receipt),
        "dependence_sensitivity": dependence,
        "branches": {},
    }
    for name, (latitude, longitude, radius) in base.PRIORS.items():
        saved = seed["branches"][name]["arms"]["D"]["selected"]
        center = (float(saved["east_km"]), float(saved["north_km"]))
        points = local_grid(*center, radius)
        evaluator = frozen.original.RobustBranchEvaluator(
            banks, (latitude, longitude), reception, variance,
            frequency["parameters"])
        evaluated = [evaluator.evaluate(east, north) for east, north in points]
        if {(row["east_km"], row["north_km"]) for row in evaluated} != set(points):
            raise ValueError("evaluator changed local-grid coordinate inventory")
        selected = {arm: select_min(evaluated, arm)
                    for arm in ("D", "D_plus_geometry")}
        output["branches"][name] = {
            "origin": [latitude, longitude],
            "radius_km": radius,
            "seed": {"arm": "D", "east_km": center[0],
                     "north_km": center[1],
                     "source_search_sha256": search_sha},
            "raw_grid_points": len(OFFSETS_KM) ** 2,
            "grid_count": len(points),
            "boundary_flags": {
                "grid_clipped_to_prior_disk": len(points) != len(OFFSETS_KM) ** 2,
                "center_on_prior_boundary": math.isclose(math.hypot(*center), radius,
                                                         abs_tol=1e-10),
                "selected_D_on_prior_boundary": math.isclose(
                    math.hypot(selected["D"]["east_km"], selected["D"]["north_km"]),
                    radius, abs_tol=1e-10),
                "selected_geometry_on_prior_boundary": math.isclose(
                    math.hypot(selected["D_plus_geometry"]["east_km"],
                               selected["D_plus_geometry"]["north_km"]),
                    radius, abs_tol=1e-10),
                "selected_D_on_grid_edge": (
                    math.isclose(abs(selected["D"]["east_km"] - center[0]), 4., abs_tol=1e-10)
                    or math.isclose(abs(selected["D"]["north_km"] - center[1]), 4., abs_tol=1e-10)),
                "selected_geometry_on_grid_edge": (
                    math.isclose(abs(selected["D_plus_geometry"]["east_km"] - center[0]), 4., abs_tol=1e-10)
                    or math.isclose(abs(selected["D_plus_geometry"]["north_km"] - center[1]), 4., abs_tol=1e-10)),
            },
            "arms": {arm: {"selected": selected[arm]}
                     for arm in ("D", "D_plus_geometry")},
            "point_components": [
                {key: value for key, value in row.items() if key != "tracks"}
                for row in evaluated],
        }
        print("GRID_DONE", sid, name, len(points), flush=True)
    output["finished"] = True
    output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {
        "run_local_grid.py": base.digest(Path(__file__).read_bytes()),
        "run_balanced_confirmation.py": base.digest(
            (HERE / "run_balanced_confirmation.py").read_bytes()),
        "run_topology_confirmation.py": base.digest(
            (PREVIOUS / "run_topology_confirmation.py").read_bytes()),
        "run_robust_search.py": base.digest(
            (LOCATION / "run_robust_search.py").read_bytes()),
        "run_search.py": base.digest((LOCATION / "run_search.py").read_bytes()),
        "robust_core.py": base.digest((LOCATION / "robust_core.py").read_bytes()),
    }
    base.atomic(target, output)
    print("SCAN_DONE", sid, round(output["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-index", type=int, required=True, choices=range(4))
    parser.add_argument("--deduplicate-reception", action="store_true")
    arguments = parser.parse_args()
    run(arguments.scan_index, arguments.deduplicate_reception)
