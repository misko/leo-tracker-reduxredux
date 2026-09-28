"""Fixed-winner per-track diagnostics for two dual-effect development scans."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time

import numpy as np

from dual_track_diagnostic import DualTrackDiagnosticEvaluator
import mixture_geometry_models
import run_balanced_confirmation as balanced
import run_consistent_replay as prior_replay
import run_dual_shared_geometry as dual_runner
import run_shared_geometry_replay as detection_runner


HERE = Path(__file__).resolve().parent
frozen = balanced.frozen
base = balanced.base
ALLOWED_INDICES = (0, 1)
VARIANTS = ("old", "detection", "dual")


def fixed_inventory(branch):
    rows = branch.get("point_components", [])
    selected = branch.get("selected", {})
    if not rows or set(selected) != set(VARIANTS):
        raise ValueError("source replay winners are incomplete")
    choices = {"D": prior_replay.select_min(rows, "old", "D"),
               "old": selected["old"], "detection": selected["detection"],
               "dual": selected["dual"]}
    result = []
    for label in ("D", "old", "detection", "dual"):
        source = choices[label]
        coordinate = [float(source["latitude_deg"]), float(source["longitude_deg"])]
        existing = next((row for row in result if row["coordinate"] == coordinate), None)
        if existing is None:
            result.append({"coordinate": coordinate, "labels": [label], "source": source})
        else:
            existing["labels"].append(label)
    return result


def aggregate_parity(source, diagnostic, tolerance=1e-7):
    expected = source.get("variant_scores", {}); actual = diagnostic.get("variant_scores", {})
    if set(expected) != set(VARIANTS) or set(actual) != set(VARIANTS):
        raise ValueError("diagnostic variant inventory changed")
    maximum = 0.
    for name in VARIANTS:
        if set(expected[name]) != set(actual[name]):
            raise ValueError("diagnostic score arm inventory changed")
        for arm in expected[name]:
            left, right = float(expected[name][arm]), float(actual[name][arm])
            if not np.isfinite(left) or not np.isfinite(right):
                raise ValueError("diagnostic aggregate score is nonfinite")
            maximum = max(maximum, abs(left - right))
    quadrature = diagnostic.get("quadrature_maximum_candidate_loglik_absolute_difference", {})
    if set(quadrature) != set(VARIANTS) or not all(
            np.isfinite(float(value)) and 0 <= float(value) <= .001
            for value in quadrature.values()):
        raise ValueError("diagnostic quadrature receipt changed")
    source_coordinate = [float(source[key]) for key in ("latitude_deg", "longitude_deg")]
    actual_coordinate = [float(diagnostic[key]) for key in ("latitude_deg", "longitude_deg")]
    if (not np.all(np.isfinite(source_coordinate + actual_coordinate)) or
            not np.allclose(source_coordinate, actual_coordinate, rtol=0, atol=1e-12)):
        raise ValueError("diagnostic physical coordinate changed")
    if maximum > tolerance:
        raise ValueError(f"dual track diagnostic aggregate parity failed: {maximum}")
    return {"maximum_absolute_difference": maximum, "tolerance": tolerance, "passed": True}


def expected_source_code():
    return {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_dual_shared_geometry.py", "dual_shared_effect_evaluator.py",
        "shared_effect_evaluator.py", "ratio_random_intercept.py",
        "detection_random_intercept_refined.py", "mixture_geometry_models.py",
        "paired_reception_evaluator.py", "run_shared_geometry_replay.py",
        "run_consistent_replay.py")}


def run(index):
    if index not in ALLOWED_INDICES:
        raise ValueError("dual track diagnostic is restricted to indices 0 and 1")
    started = time.monotonic(); entries, _ = balanced.inputs(); entry = entries[index]
    sid = entry["session_id"]; target = HERE / f"dual-track-diagnostic-{sid}.json"
    if target.exists(): raise FileExistsError(target)
    source_path = HERE / f"dual-shared-geometry-replay-{sid}.json"
    source_bytes = source_path.read_bytes(); source = json.loads(source_bytes)
    report_path = HERE / "dual-shared-geometry-distances.json"
    report_bytes = report_path.read_bytes(); report = json.loads(report_bytes)
    if (not source.get("finished") or source.get("session_id") != sid or
            source.get("code_sha256") != expected_source_code() or
            not report.get("complete") or
            report.get("replay_sha256", {}).get(sid) != base.digest(source_bytes)):
        raise ValueError("completed dual replay/report/code binding changed")
    ratio_binding, ratio_tau = dual_runner.ratio_effect_binding()
    detection_binding, detection_sigma = detection_runner.random_effect_binding()
    bundle = mixture_geometry_models.load_geometry_bundle()
    if (source.get("ratio_effect_binding") != ratio_binding or
            source.get("detection_effect_binding") != detection_binding or
            ratio_binding["calibration_sha256"] != bundle.calibration_sha256 or
            ratio_binding["detection_random_effect_sha256"] != detection_binding["aggregate_sha256"] or
            ratio_binding["full_mixture_detection_sigma"] != detection_sigma or
            source.get("calibration_sha256") != bundle.calibration_sha256 or
            source.get("calibration_source_hashes") != dict(bundle.source_hashes) or
            source.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256)):
        raise ValueError("accepted dual calibration chain changed")
    report_bindings = report.get("bindings", {})
    if (report_bindings.get("ratio_effect_binding") != ratio_binding or
            report_bindings.get("detection_effect_binding") != detection_binding or
            report_bindings.get("calibration_sha256") != bundle.calibration_sha256 or
            report_bindings.get("calibration_source_hashes") != dict(bundle.source_hashes) or
            report_bindings.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256)):
        raise ValueError("completed report calibration binding changed")
    oldaudit, oldsha = frozen.frozen_audit()
    frequency, old_detection, old_ratio, old_variance, bias, model_hashes = \
        frozen.frozen_models(oldaudit, oldsha)
    audit_path = HERE / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes(); audit = json.loads(audit_bytes)
    contract_sha = base.digest((HERE / "contract.json").read_bytes())
    if (source.get("contract_sha256") != contract_sha or
            source.get("cache_sha256") != entry["cache_sha256"] or
            source.get("model_hashes") != model_hashes or source.get("parameters") != frequency["parameters"] or
            source.get("topology_audit_sha256") != base.digest(audit_bytes)):
        raise ValueError("source replay frozen input/model binding changed")
    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]: raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw), archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256", "evidence_sha256", "snapshot_digest"):
        if getattr(prepared, key) != source[key]: raise ValueError("prepared input changed: " + key)
    links = frozen.resolve(raw); prepared, receipt = frozen.filter_prepared(prepared, links)
    audited = next(row for row in audit["sessions"] if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key] or receipt[key] != source["topology_receipt"][key]:
            raise ValueError("topology receipt changed: " + key)
    canonical = json.dumps(links, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]: raise ValueError("source links changed")
    endpoint_rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    old_reception, old_receipt = frozen.original.reception_inputs(prepared, endpoint_rows,
                                                                  old_detection, old_ratio)
    mixture = bundle.models["mixture"]
    mixture_reception, mixture_receipt = frozen.original.reception_inputs(
        prepared, endpoint_rows, mixture.detection, mixture.ratio)
    if old_receipt != mixture_receipt: raise ValueError("reception endpoint membership changed")
    variants = {"old": (old_reception, old_variance, 0., 0.),
                "detection": (mixture_reception, mixture.ratio_variance, detection_sigma, 0.),
                "dual": (mixture_reception, mixture.ratio_variance, detection_sigma, ratio_tau)}
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    protocol_path = HERE / "DUAL_TRACK_DIAGNOSTIC_PROTOCOL.md"
    output = {"session_id": sid, "finished": False,
              "source_replay_sha256": base.digest(source_bytes),
              "source_report_sha256": base.digest(report_bytes),
              "dual_track_diagnostic_protocol_sha256": base.digest(protocol_path.read_bytes()),
              "ratio_effect_binding": ratio_binding,
              "detection_effect_binding": detection_binding,
              "calibration_sha256": bundle.calibration_sha256,
              "calibration_source_hashes": dict(bundle.source_hashes),
              "calibration_artifact_sha256": dict(bundle.artifact_sha256),
              "contract_sha256": contract_sha, "cache_sha256": entry["cache_sha256"],
              "input_manifest_sha256": prepared.input_manifest_sha256,
              "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
              "evidence_sha256": prepared.evidence_sha256,
              "snapshot_digest": prepared.snapshot_digest,
              "topology_audit_sha256": base.digest(audit_bytes), "model_hashes": model_hashes,
              "parameters": frequency["parameters"], "topology_receipt": receipt,
              "prediction_receipt": asdict(bank_receipt), "branches": {}}
    for prior, branch in source["branches"].items():
        positions = []
        for item in fixed_inventory(branch):
            latitude, longitude = item["coordinate"]
            evaluator = DualTrackDiagnosticEvaluator(
                banks, (latitude, longitude), variants, frequency["parameters"])
            diagnostic = evaluator.evaluate(0., 0.)
            positions.append({"labels": item["labels"], "coordinate": item["coordinate"],
                              "source": item["source"], "diagnostic": diagnostic,
                              "aggregate_parity": aggregate_parity(item["source"], diagnostic)})
        output["branches"][prior] = {"positions": positions}
    output["finished"] = True; output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_dual_track_diagnostic.py", "dual_track_diagnostic.py",
        "dual_shared_effect_evaluator.py", "run_dual_shared_geometry.py",
        "mixture_track_diagnostic.py")}
    base.atomic(target, output); print("DUAL_TRACK_DIAGNOSTIC_DONE", sid,
                                      round(output["elapsed_s"], 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument(
        "--scan-index", type=int, required=True, choices=ALLOWED_INDICES)
    run(parser.parse_args().scan_index)
