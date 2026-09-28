"""Replay accepted shared detection effect on immutable SECOND local grids."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import pickle
import time

import numpy as np

import mixture_geometry_models
import run_balanced_confirmation as balanced
import run_consistent_replay as prior_replay
import shared_effect_evaluator as shared_core


HERE = Path(__file__).resolve().parent
frozen = balanced.frozen
base = balanced.base
VARIANTS = ("old", "mixture", "shared")


def random_effect_binding() -> tuple[dict, float]:
    path = HERE / "track_random_intercept_refined.json"
    payload = path.read_bytes(); value = json.loads(payload)
    expected_checks = {
        "all_scales_numerically_accepted_and_interior",
        "mixture_pooled_joint_nll_improves",
        "mixture_at_least_four_folds_improve",
        "mixture_positive_without_largest_gain",
    }
    if (not value.get("advance") or
            set(value.get("advancement_checks", {})) != expected_checks or
            not all(value["advancement_checks"].values()) or
            set(value.get("pooled", {}).get("models", {})) != {"M0", "mean", "mixture"}):
        raise ValueError("accepted random-effect aggregate changed")
    expected_protocol = base.digest((HERE / "TRACK_RANDOM_INTERCEPT_REFINEMENT_PROTOCOL.md").read_bytes())
    expected_code = {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_track_random_intercept_refined.py", "detection_random_intercept_refined.py",
        "run_track_random_intercept.py", "detection_random_intercept.py",
        "mixture_calibration_inputs.py", "mixture_reception_core.py")}
    if value.get("protocol_sha256") != expected_protocol or value.get("code_sha256") != expected_code:
        raise ValueError("random-effect code/protocol binding changed")
    for name, expected in value.get("shard_sha256", {}).items():
        if base.digest((HERE / name).read_bytes()) != expected:
            raise ValueError("random-effect shard changed: " + name)
    if len(value.get("shard_sha256", {})) != 7:
        raise ValueError("random-effect aggregate does not bind full plus six folds")
    full_name = "track-random-intercept-refined-full.json"
    full_artifact = json.loads((HERE / full_name).read_text())
    if (value.get("shard_sha256", {}).get(full_name) !=
            base.digest((HERE / full_name).read_bytes()) or value.get("full") != full_artifact):
        raise ValueError("embedded random-effect full fit differs from bound shard")
    full = value.get("full", {}); model = full.get("models", {}).get("mixture", {})
    sigma = float(model.get("sigma_selection", {}).get("sigma", math.nan))
    if (not full.get("all_numerically_accepted") or not model.get("numerically_accepted") or
            not math.isfinite(sigma) or not 0 <= sigma < 8 or
            model.get("quadrature", {}).get("training", {}).get("passed") is not True or
            model.get("quadrature", {}).get("held", {}).get("passed") is not True):
        raise ValueError("full mixture random effect is not numerically accepted and interior")
    receipt = {
        "aggregate_sha256": base.digest(payload),
        "calibration_sha256": value["calibration_sha256"],
        "original_numerical_failure_sha256": value["original_numerical_failure_sha256"],
        "protocol_sha256": value["protocol_sha256"],
        "code_sha256": value["code_sha256"],
        "shard_sha256": value["shard_sha256"],
        "advancement_checks": value["advancement_checks"],
        "full_mixture_sigma": sigma,
    }
    return receipt, sigma


def parity_report(saved_branch, rows, tolerance=1e-7):
    points = prior_replay.grid_points(saved_branch)
    saved = {(float(row["east_km"]), float(row["north_km"])): row
             for row in saved_branch["point_components"]}
    replay = {(float(row["east_km"]), float(row["north_km"])): row for row in rows}
    if len(replay) != len(rows) or set(replay) != set(points):
        raise ValueError("shared replay coordinate inventory changed")
    score_difference = 0.; d_difference = 0.; quadrature_maximum = 0.
    for point in points:
        expected = saved[point]["variant_scores"]
        actual = replay[point].get("variant_scores", {})
        if set(expected) != {"old", "mean", "mixture"} or set(actual) != set(VARIANTS):
            raise ValueError("shared replay variant set changed")
        if any(set(actual[name]) != set(expected["old"]) for name in VARIANTS):
            raise ValueError("shared replay score arm set changed")
        saved_coordinates = [float(saved[point][key]) for key in
                             ("latitude_deg", "longitude_deg")]
        actual_coordinates = [float(replay[point][key]) for key in
                              ("latitude_deg", "longitude_deg")]
        if (not np.all(np.isfinite(saved_coordinates + actual_coordinates)) or
                not np.allclose(saved_coordinates, actual_coordinates, rtol=0, atol=1e-12)):
            raise ValueError("shared replay geographic coordinate changed")
        for name in ("old", "mixture"):
            score_difference = max(score_difference, *(abs(float(actual[name][arm]) -
                                                          float(expected[name][arm]))
                                                        for arm in actual[name]))
        score_values = [float(value) for variant in actual.values()
                        for value in variant.values()]
        score_values.extend(float(value) for variant in expected.values()
                            for value in variant.values())
        if not np.all(np.isfinite(score_values)):
            raise ValueError("saved or shared replay score is nonfinite")
        d_difference = max(d_difference, *(abs(float(actual[name]["D"]) -
                                                float(actual["old"]["D"]))
                                              for name in VARIANTS))
        quadrature = replay[point].get(
            "quadrature_maximum_candidate_loglik_absolute_difference", {})
        if set(quadrature) != set(VARIANTS) or not all(
                math.isfinite(float(value)) and float(value) >= 0
                for value in quadrature.values()):
            raise ValueError("shared replay quadrature receipt changed")
        quadrature_maximum = max(quadrature_maximum, *(float(value) for value in quadrature.values()))
    if score_difference > tolerance:
        raise ValueError("saved old/mixture score parity failed")
    if d_difference > 1e-12:
        raise ValueError("reception variant changed Doppler-only score")
    if quadrature_maximum > .001:
        raise ValueError("shared-effect quadrature tolerance failed")
    return {"points": len(points), "old_mixture_saved_max_absolute_difference": score_difference,
            "all_variant_D_max_absolute_difference": d_difference,
            "quadrature_maximum_candidate_loglik_absolute_difference": quadrature_maximum,
            "score_tolerance": tolerance, "D_tolerance": 1e-12,
            "quadrature_tolerance": .001, "passed": True}


def select_min(rows, variant):
    return min(rows, key=lambda row: (
        float(row["variant_scores"][variant]["D_plus_geometry"]),
        float(row["east_km"]), float(row["north_km"])))


def run(index: int) -> None:
    started = time.monotonic(); entries, _contract = balanced.inputs()
    if not 0 <= index < 4: raise IndexError("scan index out of range")
    entry = entries[index]; sid = entry["session_id"]
    target = HERE / f"shared-geometry-replay-{sid}.json"
    if target.exists(): raise FileExistsError(target)
    source_path = HERE / f"mixture-geometry-replay-{sid}.json"
    source_bytes = source_path.read_bytes(); source = json.loads(source_bytes)
    report_path = HERE / "mixture-geometry-distances.json"
    report_bytes = report_path.read_bytes(); report = json.loads(report_bytes)
    if (not source.get("finished") or source.get("session_id") != sid or
            not report.get("complete") or
            report.get("replay_sha256", {}).get(sid) != base.digest(source_bytes)):
        raise ValueError("completed mixture replay/report binding changed")
    source_grid_path = HERE / f"local-grid-{sid}.json"
    source_grid_bytes = source_grid_path.read_bytes()
    source_grid_report_bytes = (HERE / "local-grid-distances.json").read_bytes()
    if (source.get("source_grid_sha256") != base.digest(source_grid_bytes) or
            source.get("source_grid_report_sha256") != base.digest(source_grid_report_bytes)):
        raise ValueError("source replay local-grid binding changed")
    random_binding, detection_sigma = random_effect_binding()
    bundle = mixture_geometry_models.load_geometry_bundle()
    if random_binding["calibration_sha256"] != bundle.calibration_sha256:
        raise ValueError("random effect and mixture coefficients bind different calibrations")
    oldaudit, oldsha = frozen.frozen_audit()
    frequency, old_detection, old_ratio, old_variance, bias, model_hashes = \
        frozen.frozen_models(oldaudit, oldsha)
    audit_path = HERE / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes(); audit = json.loads(audit_bytes)
    contract_sha = base.digest((HERE / "contract.json").read_bytes())
    if (source.get("contract_sha256") != contract_sha or
            source.get("calibration_sha256") != bundle.calibration_sha256 or
            source.get("calibration_source_hashes") != dict(bundle.source_hashes) or
            source.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256) or
            source.get("cache_sha256") != entry["cache_sha256"] or
            source.get("model_hashes") != model_hashes or
            source.get("parameters") != frequency["parameters"] or
            source.get("topology_audit_sha256") != base.digest(audit_bytes)):
        raise ValueError("source replay frozen binding changed")
    payload = Path(entry["cache_file"]).read_bytes()
    if base.digest(payload) != entry["cache_sha256"]: raise ValueError("cache changed")
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(
        sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path("/var/lib/leo/tle")))
    for key in ("input_manifest_sha256", "analysis_manifest_sha256",
                "evidence_sha256", "snapshot_digest"):
        if getattr(prepared, key) != source[key]:
            raise ValueError("prepared input/evidence changed: " + key)
    links = frozen.resolve(raw); prepared, receipt = frozen.filter_prepared(prepared, links)
    audited = next(row for row in audit["sessions"] if row["session_id"] == sid)
    for key in ("removed_track_ids", "counts", "collisions", "unchanged"):
        if receipt[key] != audited[key] or receipt[key] != source["topology_receipt"][key]:
            raise ValueError("topology receipt changed: " + key)
    canonical = json.dumps(links, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if base.digest(canonical) != audited["source_links_sha256"]:
        raise ValueError("source links changed")
    endpoint_rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    old_reception, old_receipt = frozen.original.reception_inputs(
        prepared, endpoint_rows, old_detection, old_ratio)
    mixture_model = bundle.models["mixture"]
    mixture_reception, mixture_receipt = frozen.original.reception_inputs(
        prepared, endpoint_rows, mixture_model.detection, mixture_model.ratio)
    if mixture_receipt != old_receipt: raise ValueError("reception endpoint membership changed")
    variants = {
        "old": (old_reception, old_variance, 0.),
        "mixture": (mixture_reception, mixture_model.ratio_variance, 0.),
        "shared": (mixture_reception, mixture_model.ratio_variance, detection_sigma),
    }
    banks, bank_receipt = base.build_prediction_banks(
        prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
        prepared.tracks, taus_s=np.array([0.]))
    protocol_bytes = (HERE / "SHARED_GEOMETRY_PROTOCOL.md").read_bytes()
    output = {
        "session_id": sid, "finished": False,
        "contract_sha256": contract_sha,
        "shared_geometry_protocol_sha256": base.digest(protocol_bytes),
        "random_effect_binding": random_binding,
        "calibration_sha256": bundle.calibration_sha256,
        "calibration_sessions": list(bundle.calibration_sessions),
        "calibration_source_hashes": dict(bundle.source_hashes),
        "calibration_artifact_sha256": dict(bundle.artifact_sha256),
        "source_replay_sha256": base.digest(source_bytes),
        "source_replay_report_sha256": base.digest(report_bytes),
        "source_grid_sha256": base.digest(source_grid_bytes),
        "source_grid_report_sha256": base.digest(source_grid_report_bytes),
        "cache_sha256": entry["cache_sha256"],
        "input_manifest_sha256": prepared.input_manifest_sha256,
        "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
        "evidence_sha256": prepared.evidence_sha256, "snapshot_digest": prepared.snapshot_digest,
        "topology_audit_sha256": base.digest(audit_bytes), "model_hashes": model_hashes,
        "parameters": frequency["parameters"], "topology_receipt": receipt,
        "prediction_receipt": asdict(bank_receipt), "branches": {},
    }
    for prior, (latitude, longitude, _radius) in base.PRIORS.items():
        saved = source["branches"][prior]; points = prior_replay.grid_points(saved)
        evaluator = shared_core.SharedEffectEvaluator(
            banks, (latitude, longitude), variants, frequency["parameters"])
        evaluated = []
        for number, point in enumerate(points, 1):
            evaluated.append(evaluator.evaluate(*point))
            if number % 25 == 0 or number == len(points):
                print("SHARED_REPLAY_PROGRESS", sid, prior, number, len(points), flush=True)
        parity = parity_report(saved, evaluated)
        output["branches"][prior] = {
            "origin": [latitude, longitude], "grid_count": len(points), "parity": parity,
            "selected": {name: select_min(evaluated, name) for name in VARIANTS},
            "point_components": evaluated,
        }
    output["finished"] = True; output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_shared_geometry_replay.py", "shared_effect_evaluator.py",
        "detection_random_intercept_refined.py", "mixture_geometry_models.py",
        "paired_reception_evaluator.py", "run_consistent_replay.py")}
    base.atomic(target, output); print("SHARED_REPLAY_DONE", sid, round(output["elapsed_s"], 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument(
        "--scan-index", type=int, required=True, choices=range(4))
    run(parser.parse_args().scan_index)
