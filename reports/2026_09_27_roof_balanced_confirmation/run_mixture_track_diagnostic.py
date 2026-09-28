"""Track-level diagnostics at fixed mixture-replay selections and roof reference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time

import numpy as np

import mixture_geometry_models
import run_balanced_confirmation as balanced
import run_consistent_replay as prior_replay
from mixture_track_diagnostic import TrackDiagnosticEvaluator


HERE = Path(__file__).resolve().parent
frozen = balanced.frozen
base = balanced.base
ALLOWED_INDICES = (1, 2)
VARIANTS = ("old", "mean", "mixture")


def fixed_inventory(branch: dict) -> list[dict]:
    rows = branch.get("point_components", [])
    if not rows:
        raise ValueError("source replay has no points")
    selected = branch.get("selected", {})
    if set(selected) != set(VARIANTS):
        raise ValueError("source replay selections changed")
    choices = {
        "D": prior_replay.select_min(rows, "old", "D"),
        "mean": selected["mean"], "mixture": selected["mixture"],
    }
    result = []
    for label in ("D", "mean", "mixture"):
        row = choices[label]
        key = (float(row["latitude_deg"]), float(row["longitude_deg"]))
        existing = next((item for item in result if item["coordinate"] == list(key)), None)
        if existing is None:
            result.append({"coordinate": list(key), "labels": [label],
                           "source": row})
        else:
            existing["labels"].append(label)
    return result


def aggregate_parity(source: dict, diagnostic: dict, tolerance=1e-7) -> dict:
    expected = source.get("variant_scores", {})
    actual = diagnostic.get("variant_scores", {})
    if set(expected) != set(VARIANTS) or set(actual) != set(VARIANTS):
        raise ValueError("diagnostic variant set changed")
    maximum = 0.0
    for name in VARIANTS:
        if set(expected[name]) != set(actual[name]):
            raise ValueError("diagnostic arm set changed")
        for arm in expected[name]:
            left, right = float(expected[name][arm]), float(actual[name][arm])
            if not np.isfinite(left) or not np.isfinite(right):
                raise ValueError("diagnostic aggregate score is nonfinite")
            maximum = max(maximum, abs(left - right))
    if maximum > tolerance:
        raise ValueError(f"track diagnostic aggregate parity failed: {maximum}")
    return {"maximum_absolute_difference": maximum, "tolerance": tolerance,
            "passed": True}


def pose_reference(manifest: dict, sid: str) -> tuple[float, float, str]:
    matches = [row for row in manifest.get("sessions", [])
               if row.get("pose", {}).get("session_id") == sid]
    if len(matches) != 1:
        raise ValueError("manifest lacks one pose-bound session")
    authority = matches[0]["pose"]["pose_authority"]
    latitude = float(authority["latitude_deg"]); longitude = float(authority["longitude_deg"])
    if not np.all(np.isfinite([latitude, longitude])):
        raise ValueError("roof reference is nonfinite")
    return latitude, longitude, matches[0]["pose"]["pose_authority_digest"]


def run(index: int) -> None:
    if index not in ALLOWED_INDICES:
        raise ValueError("track diagnostics are restricted to SECOND indices 1 and 2")
    started = time.monotonic(); entries, _contract = balanced.inputs()
    entry = entries[index]; sid = entry["session_id"]
    target = HERE / f"mixture-track-diagnostic-{sid}.json"
    if target.exists():
        raise FileExistsError(target)
    replay_path = HERE / f"mixture-geometry-replay-{sid}.json"
    replay_bytes = replay_path.read_bytes(); replay = json.loads(replay_bytes)
    report_path = HERE / "mixture-geometry-distances.json"
    report_bytes = report_path.read_bytes(); report = json.loads(report_bytes)
    if (not replay.get("finished") or replay.get("session_id") != sid or
            not report.get("complete") or
            report.get("replay_sha256", {}).get(sid) != base.digest(replay_bytes)):
        raise ValueError("completed source replay/report binding changed")

    oldaudit, oldsha = frozen.frozen_audit()
    frequency, old_detection, old_ratio, old_variance, bias, old_model_hashes = \
        frozen.frozen_models(oldaudit, oldsha)
    bundle = mixture_geometry_models.load_geometry_bundle()
    if (replay.get("calibration_sha256") != bundle.calibration_sha256 or
            replay.get("calibration_source_hashes") != dict(bundle.source_hashes) or
            replay.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256)):
        raise ValueError("source replay calibration binding changed")
    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]:
        raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256",
                "evidence_sha256", "snapshot_digest"):
        expected = entry[key] if key in entry else replay[key]
        if getattr(prepared, key) != expected or getattr(prepared, key) != replay[key]:
            raise ValueError("prepared input/evidence binding changed: " + key)
    links = frozen.resolve(raw); prepared, receipt = frozen.filter_prepared(prepared, links)
    audit_path = HERE / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes(); audit = json.loads(audit_bytes)
    audited = next(row for row in audit["sessions"] if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key] or receipt[key] != replay["topology_receipt"][key]:
            raise ValueError("topology receipt changed: " + key)
    canonical = json.dumps(links, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]:
        raise ValueError("source links changed")

    endpoint_rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    old_reception, old_endpoint_receipt = frozen.original.reception_inputs(
        prepared, endpoint_rows, old_detection, old_ratio)
    variants = {"old": (old_reception, old_variance)}
    for name in ("mean", "mixture"):
        model = bundle.models[name]
        reception, endpoint_receipt = frozen.original.reception_inputs(
            prepared, endpoint_rows, model.detection, model.ratio)
        if endpoint_receipt != old_endpoint_receipt:
            raise ValueError("geometry model changed reception endpoint membership")
        variants[name] = (reception, model.ratio_variance)
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))

    manifest_path = HERE / "manifest.json"
    manifest_bytes = manifest_path.read_bytes(); manifest = json.loads(manifest_bytes)
    roof_lat, roof_lon, authority_digest = pose_reference(manifest, sid)
    protocol_path = HERE / "MIXTURE_TRACK_DIAGNOSTIC_PROTOCOL.md"
    output = {
        "session_id": sid, "finished": False,
        "source_replay_sha256": base.digest(replay_bytes),
        "whole_cohort_report_sha256": base.digest(report_bytes),
        "manifest_sha256": base.digest(manifest_bytes),
        "pose_authority_digest": authority_digest,
        "track_diagnostic_protocol_sha256": base.digest(protocol_path.read_bytes()),
        "calibration_sha256": bundle.calibration_sha256,
        "calibration_source_hashes": dict(bundle.source_hashes),
        "calibration_artifact_sha256": dict(bundle.artifact_sha256),
        "cache_sha256": entry["cache_sha256"],
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "topology_audit_sha256": base.digest(audit_bytes),
        "old_model_hashes": old_model_hashes,
        "parameters": frequency["parameters"], "topology_receipt": receipt,
        "prediction_receipt": asdict(bank_receipt), "branches": {},
        "protocol": {
            "inventory": "per prior: saved D minimum, saved mean selection, saved mixture selection; coincident physical coordinates evaluated once; plus one roof reference per scan",
            "evaluation": "each physical coordinate is an independent origin with zero offset and a fresh Doppler shortlist",
            "truth_use": "operator-supplied WGS84 roof reference is diagnostic only and never an estimator input or candidate source",
        },
    }
    for prior, branch in replay["branches"].items():
        evaluated = []
        for item in fixed_inventory(branch):
            latitude, longitude = item["coordinate"]
            evaluator = TrackDiagnosticEvaluator(
                banks, (latitude, longitude), variants, frequency["parameters"])
            diagnostic = evaluator.evaluate(0., 0.)
            parity = aggregate_parity(item["source"], diagnostic)
            evaluated.append({"labels": item["labels"], "coordinate": item["coordinate"],
                              "source": item["source"], "diagnostic": diagnostic,
                              "aggregate_parity": parity})
        output["branches"][prior] = {"positions": evaluated}
    roof_evaluator = TrackDiagnosticEvaluator(
        banks, (roof_lat, roof_lon), variants, frequency["parameters"])
    output["roof_reference"] = {
        "coordinate": [roof_lat, roof_lon],
        "diagnostic": roof_evaluator.evaluate(0., 0.),
        "role": "independent diagnostic only; not compared or shared with either prior's selected candidates",
    }
    output["finished"] = True; output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_mixture_track_diagnostic.py", "mixture_track_diagnostic.py",
        "mixture_geometry_models.py", "paired_reception_evaluator.py")}
    base.atomic(target, output)
    print("TRACK_DIAGNOSTIC_DONE", sid, round(output["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-index", type=int, required=True, choices=ALLOWED_INDICES)
    run(parser.parse_args().scan_index)
