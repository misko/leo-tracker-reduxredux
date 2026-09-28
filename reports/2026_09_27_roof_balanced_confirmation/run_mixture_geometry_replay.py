"""Replay accepted mean and candidate-mixture reception models on saved grids."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time

import numpy as np

import mixture_geometry_models
import paired_reception_evaluator as paired
import run_balanced_confirmation as balanced
import run_consistent_replay as prior_replay


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_27_roof_geometry_confirmation"
frozen = balanced.frozen
base = balanced.base
TOLERANCE = 1e-7
VARIANTS = ("old", "mean", "mixture")


def parity_report(saved_branch: dict, replay_rows: list[dict]) -> dict:
    points = prior_replay.grid_points(saved_branch)
    saved = {(float(row["east_km"]), float(row["north_km"])): row
             for row in saved_branch["point_components"]}
    replay = {(float(row["east_km"]), float(row["north_km"])): row
              for row in replay_rows}
    if len(replay) != len(replay_rows) or set(replay) != set(points):
        raise ValueError("mixture replay coordinate inventory differs from saved grid")
    maximum_old = 0.0; maximum_d = 0.0
    for point in points:
        original = saved[point]["scores"]
        variants = replay[point].get("variant_scores", {})
        if (set(variants) != set(VARIANTS) or
                any(set(variants[name]) != set(original) for name in VARIANTS)):
            raise ValueError("mixture replay variant or arm set changed")
        coordinates = [float(saved[point][name]) for name in
                       ("latitude_deg", "longitude_deg")]
        replay_coordinates = [float(replay[point][name]) for name in
                              ("latitude_deg", "longitude_deg")]
        if (not np.all(np.isfinite(coordinates + replay_coordinates)) or
                not np.allclose(coordinates, replay_coordinates, rtol=0, atol=1e-12)):
            raise ValueError("mixture replay geographic coordinate changed")
        values = [float(value) for scores in variants.values() for value in scores.values()]
        values.extend(float(value) for value in original.values())
        if not np.all(np.isfinite(values)):
            raise ValueError("saved or replay score is nonfinite")
        maximum_old = max(maximum_old, *(abs(float(variants["old"][name]) -
                                                  float(original[name]))
                                            for name in original))
        maximum_d = max(maximum_d, *(abs(float(variants["old"]["D"]) -
                                           float(variants[name]["D"]))
                                     for name in ("mean", "mixture")))
    if maximum_old > TOLERANCE:
        raise ValueError(f"old local-grid parity failed: {maximum_old} > {TOLERANCE}")
    if maximum_d > 1e-12:
        raise ValueError(f"reception calibration changed D: {maximum_d}")
    return {"points": len(points), "old_saved_max_absolute_difference": maximum_old,
            "all_variant_D_max_absolute_difference": maximum_d,
            "old_tolerance": TOLERANCE, "D_tolerance": 1e-12, "passed": True}


def select_min(rows: list[dict], variant: str) -> dict:
    return min(rows, key=lambda row: (
        float(row["variant_scores"][variant]["D_plus_geometry"]),
        float(row["east_km"]), float(row["north_km"])))


def evaluate_points(evaluator, points, sid, prior):
    rows = []
    for index, point in enumerate(points, 1):
        rows.append(evaluator.evaluate(*point))
        if index % 25 == 0 or index == len(points):
            print("MIXTURE_REPLAY_PROGRESS", sid, prior, index, len(points), flush=True)
    return rows


def run(index: int) -> None:
    started = time.monotonic()
    entries, _contract = balanced.inputs()
    if not 0 <= index < len(entries):
        raise IndexError("scan index out of range")
    entry = entries[index]; sid = entry["session_id"]
    target = HERE / f"mixture-geometry-replay-{sid}.json"
    if target.exists():
        raise FileExistsError(target)
    grid_path = HERE / f"local-grid-{sid}.json"
    grid_bytes = grid_path.read_bytes(); grid = json.loads(grid_bytes)
    report_path = HERE / "local-grid-distances.json"
    report_bytes = report_path.read_bytes(); report = json.loads(report_bytes)
    if (not grid.get("finished") or grid.get("session_id") != sid or
            grid.get("deduplicate_reception") is not False or
            not report.get("complete") or report.get("deduplicate_reception") is not False or
            report.get("artifact_sha256", {}).get(sid) != base.digest(grid_bytes)):
        raise ValueError("saved primary local grid/report is incomplete or rebound")

    calibration_audit, calibration_audit_sha = frozen.frozen_audit()
    frequency, old_detection, old_ratio, old_variance, bias, model_hashes = \
        frozen.frozen_models(calibration_audit, calibration_audit_sha)
    bundle = mixture_geometry_models.load_geometry_bundle()
    if set(bundle.models) != {"mean", "mixture"}:
        raise ValueError("geometry calibration bundle has unexpected models")
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
        raise ValueError("saved local-grid frozen binding changed")

    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]:
        raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(prepared, key) != entry[key] or getattr(prepared, key) != grid[key]:
            raise ValueError("prepared manifest binding changed")
    for key in ("evidence_sha256", "snapshot_digest"):
        if getattr(prepared, key) != grid[key]:
            raise ValueError("prepared evidence binding changed")
    links = frozen.resolve(raw)
    prepared, receipt = frozen.filter_prepared(prepared, links)
    audited = next(row for row in second_audit["sessions"] if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key] or receipt[key] != grid["topology_receipt"][key]:
            raise ValueError("topology receipt changed: " + key)
    canonical = json.dumps(links, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]:
        raise ValueError("source links changed")

    endpoint_rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    old_reception, old_receipt = frozen.original.reception_inputs(
        prepared, endpoint_rows, old_detection, old_ratio)
    variants = {"old": (old_reception, old_variance)}
    for name in ("mean", "mixture"):
        model = bundle.models[name]
        reception, endpoint_receipt = frozen.original.reception_inputs(
            prepared, endpoint_rows, model.detection, model.ratio)
        if endpoint_receipt != old_receipt:
            raise ValueError("geometry calibration changed endpoint membership")
        variants[name] = (reception, model.ratio_variance)
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    protocol_bytes = (HERE / "MIXTURE_GEOMETRY_PROTOCOL.md").read_bytes()
    output = {
        "session_id": sid, "finished": False,
        "protocol": {
            "status": "posthoc fixed-grid candidate-mixture calibration replay",
            "inventory": "exact saved primary local-grid coordinates per prior; no new points",
            "variants": list(VARIANTS),
            "truth_access": "the completed distance report is read only for completion and source-grid artifact-hash binding; reference/error fields do not choose coordinates, models, or scores",
        },
        "contract_sha256": contract_sha,
        "geometry_protocol_sha256": base.digest(protocol_bytes),
        "calibration_sha256": bundle.calibration_sha256,
        "calibration_sessions": list(bundle.calibration_sessions),
        "calibration_source_hashes": dict(bundle.source_hashes),
        "calibration_artifact_sha256": dict(bundle.artifact_sha256),
        "source_grid_sha256": base.digest(grid_bytes),
        "source_grid_report_sha256": base.digest(report_bytes),
        "cache_sha256": entry["cache_sha256"],
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "calibration_topology_audit_sha256": calibration_audit_sha,
        "topology_audit_sha256": second_audit_sha,
        "model_hashes": model_hashes, "parameters": frequency["parameters"],
        "topology_receipt": receipt, "prediction_receipt": asdict(bank_receipt),
        "branches": {},
    }
    for prior, (latitude, longitude, _radius) in base.PRIORS.items():
        saved = grid["branches"][prior]
        points = prior_replay.grid_points(saved)
        evaluator = paired.PairedEvaluator(
            banks, (latitude, longitude), variants, frequency["parameters"])
        evaluated = evaluate_points(evaluator, points, sid, prior)
        parity = parity_report(saved, evaluated)
        output["branches"][prior] = {
            "origin": [latitude, longitude], "grid_count": len(points),
            "parity": parity,
            "selected": {name: select_min(evaluated, name) for name in VARIANTS},
            "point_components": evaluated,
        }
    output["finished"] = True; output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {
        name: base.digest((HERE / name).read_bytes()) for name in (
            "run_mixture_geometry_replay.py", "mixture_geometry_models.py",
            "paired_reception_evaluator.py", "run_consistent_replay.py")}
    base.atomic(target, output)
    print("MIXTURE_REPLAY_DONE", sid, round(output["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-index", type=int, required=True, choices=range(4))
    run(parser.parse_args().scan_index)
