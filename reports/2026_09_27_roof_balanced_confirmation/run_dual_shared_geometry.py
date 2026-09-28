"""Replay accepted shared detection and ratio effects on immutable grids."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import pickle
import time

import numpy as np

import dual_shared_effect_evaluator as dual_core
import mixture_geometry_models
import run_balanced_confirmation as balanced
import run_consistent_replay as prior_replay
import run_ratio_random_intercept as ratio_runner
import run_shared_geometry_replay as source_runner


HERE = Path(__file__).resolve().parent
frozen = balanced.frozen
base = balanced.base
VARIANTS = ("old", "detection", "dual")


def ratio_effect_binding() -> tuple[dict, float]:
    path = HERE / "ratio_random_intercept.json"
    payload = path.read_bytes(); value = json.loads(payload)
    expected_checks = {"all_fits_valid_and_interior", "mixture_pooled_gain",
                       "mixture_at_least_four_folds_improve",
                       "mixture_positive_without_largest_gain"}
    expected_protocol = base.digest((HERE / "RATIO_RANDOM_INTERCEPT_PROTOCOL.md").read_bytes())
    expected_code = ratio_runner.source_hashes()
    if (not value.get("advance") or
            set(value.get("advancement_checks", {})) != expected_checks or
            not all(value["advancement_checks"].values()) or
            value.get("protocol_sha256") != expected_protocol or
            value.get("code_sha256") != expected_code or
            len(value.get("shard_sha256", {})) != 7):
        raise ValueError("accepted ratio random-effect aggregate changed")
    for name, expected in value["shard_sha256"].items():
        if base.digest((HERE / name).read_bytes()) != expected:
            raise ValueError("ratio random-effect shard changed: " + name)
    full_name = "ratio-random-intercept-full.json"
    full = json.loads((HERE / full_name).read_text())
    if value.get("full") != full or value["shard_sha256"].get(full_name) != base.digest(
            (HERE / full_name).read_bytes()):
        raise ValueError("embedded ratio full fit differs from hashed shard")
    model = full.get("models", {}).get("mixture", {})
    tau = float(model.get("tau_selection", {}).get("tau", math.nan))
    detection_sigma = float(model.get("detection_sigma", math.nan))
    if (not full.get("all_numerically_accepted") or not model.get("numerically_accepted") or
            not math.isfinite(tau) or not 0 <= tau < 4 or
            not math.isfinite(detection_sigma) or not 0 <= detection_sigma < 8):
        raise ValueError("full mixture ratio effect is not accepted and interior")
    return ({"aggregate_sha256": base.digest(payload),
             "calibration_sha256": value["calibration_sha256"],
             "detection_random_effect_sha256": value["detection_random_effect_sha256"],
             "protocol_sha256": value["protocol_sha256"], "code_sha256": value["code_sha256"],
             "shard_sha256": value["shard_sha256"],
             "advancement_checks": value["advancement_checks"],
             "full_mixture_tau": tau,
             "full_mixture_detection_sigma": detection_sigma}, tau)


def parity_report(saved, rows, tolerance=1e-7):
    points = prior_replay.grid_points(saved)
    expected = {(float(row["east_km"]), float(row["north_km"])): row
                for row in saved["point_components"]}
    actual = {(float(row["east_km"]), float(row["north_km"])): row for row in rows}
    if len(actual) != len(rows) or set(actual) != set(points):
        raise ValueError("dual replay coordinate inventory changed")
    score_max = 0.; d_max = 0.; quadrature_max = 0.
    for point in points:
        source_scores = expected[point].get("variant_scores", {})
        scores = actual[point].get("variant_scores", {})
        if set(source_scores) != {"old", "mixture", "shared"} or set(scores) != set(VARIANTS):
            raise ValueError("dual replay variant inventory changed")
        if any(set(scores[name]) != set(source_scores["old"]) for name in VARIANTS):
            raise ValueError("dual replay score arm inventory changed")
        for name, source_name in (("old", "old"), ("detection", "shared")):
            score_max = max(score_max, *(abs(float(scores[name][arm]) -
                                              float(source_scores[source_name][arm]))
                                        for arm in scores[name]))
        values = [float(value) for variant in scores.values() for value in variant.values()]
        values.extend(float(value) for variant in source_scores.values() for value in variant.values())
        if not np.all(np.isfinite(values)):
            raise ValueError("source or dual replay score is nonfinite")
        d_max = max(d_max, *(abs(float(scores[name]["D"]) - float(scores["old"]["D"]))
                             for name in VARIANTS))
        source_coordinates = [float(expected[point][key]) for key in
                              ("latitude_deg", "longitude_deg")]
        coordinates = [float(actual[point][key]) for key in
                       ("latitude_deg", "longitude_deg")]
        if (not np.all(np.isfinite(source_coordinates + coordinates)) or
                not np.allclose(source_coordinates, coordinates, rtol=0, atol=1e-12)):
            raise ValueError("dual replay geographic coordinate changed")
        receipt = actual[point].get("quadrature_maximum_candidate_loglik_absolute_difference", {})
        if set(receipt) != set(VARIANTS) or not all(
                math.isfinite(float(value)) and float(value) >= 0 for value in receipt.values()):
            raise ValueError("dual replay quadrature receipt changed")
        quadrature_max = max(quadrature_max, *(float(value) for value in receipt.values()))
    if score_max > tolerance: raise ValueError("saved old/detection score parity failed")
    if d_max > 1e-12: raise ValueError("reception variant changed Doppler-only score")
    if quadrature_max > .001: raise ValueError("detection quadrature tolerance failed")
    return {"points": len(points), "old_detection_saved_max_absolute_difference": score_max,
            "all_variant_D_max_absolute_difference": d_max,
            "detection_quadrature_maximum_candidate_loglik_absolute_difference": quadrature_max,
            "score_tolerance": tolerance, "D_tolerance": 1e-12,
            "quadrature_tolerance": .001, "passed": True}


def select_min(rows, variant):
    return min(rows, key=lambda row: (float(row["variant_scores"][variant]["D_plus_geometry"]),
                                      float(row["east_km"]), float(row["north_km"])))


def run(index):
    started = time.monotonic(); entries, _ = balanced.inputs()
    if not 0 <= index < 4: raise IndexError("scan index out of range")
    entry = entries[index]; sid = entry["session_id"]
    target = HERE / f"dual-shared-geometry-replay-{sid}.json"
    if target.exists(): raise FileExistsError(target)
    source_path = HERE / f"shared-geometry-replay-{sid}.json"
    source_bytes = source_path.read_bytes(); source = json.loads(source_bytes)
    report_path = HERE / "shared-geometry-distances.json"
    report_bytes = report_path.read_bytes(); report = json.loads(report_bytes)
    if (not source.get("finished") or source.get("session_id") != sid or
            not report.get("complete") or
            report.get("replay_sha256", {}).get(sid) != base.digest(source_bytes)):
        raise ValueError("completed shared replay/report binding changed")
    ratio_binding, ratio_tau = ratio_effect_binding()
    detection_binding, detection_sigma = source_runner.random_effect_binding()
    bundle = mixture_geometry_models.load_geometry_bundle()
    if (ratio_binding["calibration_sha256"] != bundle.calibration_sha256 or
            ratio_binding["detection_random_effect_sha256"] != detection_binding["aggregate_sha256"] or
            ratio_binding["full_mixture_detection_sigma"] != detection_sigma or
            source.get("random_effect_binding") != detection_binding or
            source.get("calibration_sha256") != bundle.calibration_sha256):
        raise ValueError("dual calibration chain binding changed")
    oldaudit, oldsha = frozen.frozen_audit()
    frequency, old_detection, old_ratio, old_variance, bias, model_hashes = \
        frozen.frozen_models(oldaudit, oldsha)
    audit_path = HERE / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes(); audit = json.loads(audit_bytes)
    contract_sha = base.digest((HERE / "contract.json").read_bytes())
    if (source.get("contract_sha256") != contract_sha or
            source.get("calibration_source_hashes") != dict(bundle.source_hashes) or
            source.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256) or
            source.get("cache_sha256") != entry["cache_sha256"] or
            source.get("model_hashes") != model_hashes or source.get("parameters") != frequency["parameters"] or
            source.get("topology_audit_sha256") != base.digest(audit_bytes)):
        raise ValueError("source replay frozen binding changed")
    grid_path = HERE / f"local-grid-{sid}.json"; grid_bytes = grid_path.read_bytes()
    grid_report_bytes = (HERE / "local-grid-distances.json").read_bytes()
    if (source.get("source_grid_sha256") != base.digest(grid_bytes) or
            source.get("source_grid_report_sha256") != base.digest(grid_report_bytes)):
        raise ValueError("source replay grid binding changed")
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
    protocol_bytes = (HERE / "DUAL_SHARED_GEOMETRY_PROTOCOL.md").read_bytes()
    output = {"session_id": sid, "finished": False, "contract_sha256": contract_sha,
              "dual_shared_geometry_protocol_sha256": base.digest(protocol_bytes),
              "ratio_effect_binding": ratio_binding, "detection_effect_binding": detection_binding,
              "calibration_sha256": bundle.calibration_sha256,
              "calibration_sessions": list(bundle.calibration_sessions),
              "calibration_source_hashes": dict(bundle.source_hashes),
              "calibration_artifact_sha256": dict(bundle.artifact_sha256),
              "source_replay_sha256": base.digest(source_bytes),
              "source_replay_report_sha256": base.digest(report_bytes),
              "source_grid_sha256": base.digest(grid_bytes),
              "source_grid_report_sha256": base.digest(grid_report_bytes),
              "cache_sha256": entry["cache_sha256"],
              "input_manifest_sha256": prepared.input_manifest_sha256,
              "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
              "evidence_sha256": prepared.evidence_sha256, "snapshot_digest": prepared.snapshot_digest,
              "topology_audit_sha256": base.digest(audit_bytes), "model_hashes": model_hashes,
              "parameters": frequency["parameters"], "topology_receipt": receipt,
              "prediction_receipt": asdict(bank_receipt), "branches": {}}
    for prior, (latitude, longitude, _radius) in base.PRIORS.items():
        saved = source["branches"][prior]; points = prior_replay.grid_points(saved)
        evaluator = dual_core.DualSharedEffectEvaluator(
            banks, (latitude, longitude), variants, frequency["parameters"])
        evaluated = []
        for number, point in enumerate(points, 1):
            evaluated.append(evaluator.evaluate(*point))
            if number % 25 == 0 or number == len(points):
                print("DUAL_REPLAY_PROGRESS", sid, prior, number, len(points), flush=True)
        parity = parity_report(saved, evaluated)
        output["branches"][prior] = {"origin": [latitude, longitude],
            "grid_count": len(points), "parity": parity,
            "selected": {name: select_min(evaluated, name) for name in VARIANTS},
            "point_components": evaluated}
    output["finished"] = True; output["elapsed_s"] = time.monotonic() - started
    output["code_sha256"] = {name: base.digest((HERE / name).read_bytes()) for name in (
        "run_dual_shared_geometry.py", "dual_shared_effect_evaluator.py",
        "shared_effect_evaluator.py", "ratio_random_intercept.py",
        "detection_random_intercept_refined.py", "mixture_geometry_models.py",
        "paired_reception_evaluator.py", "run_shared_geometry_replay.py",
        "run_consistent_replay.py")}
    base.atomic(target, output); print("DUAL_REPLAY_DONE", sid, round(output["elapsed_s"], 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--scan-index", type=int,
                                                            required=True, choices=range(4))
    run(parser.parse_args().scan_index)
