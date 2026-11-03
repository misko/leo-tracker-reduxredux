"""Matched cone-prior continuations of the two remaining sigma1 failures."""
import argparse
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

from cone_objective import ConeObjective, cone_bundle, CONE_BUNDLE_DIGESTS

HERE = Path(__file__).resolve().parent
ROOT_CAUSE = HERE.parent / "2026_10_07_sigma1_root_cause"
spec = importlib.util.spec_from_file_location("root_oracle_loader", ROOT_CAUSE / "oracle.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
controls = loader.CONTROLS
OPTIONS = {"control": 0., "cone050": .5, "cone100": 1.}


def full_scan_pool(case, old):
    rows = [dict(r, source="original-sigma1") for r in old["candidates"] if r["option"] == "sigma100"]
    if case == "1939":
        doc = json.loads((ROOT_CAUSE / "shared_bias/results.json").read_text())
        rows += [dict(r, source="full-scan-both-branches") for r in doc["rows"]]
    else:
        doc = json.loads((ROOT_CAUSE / "boundary/results.json").read_text())
        rows += [dict(r, source="original-expanded-domain") for r in doc["candidates"]]
        doc = json.loads((ROOT_CAUSE / "boundary/long_budget.json").read_text())
        rows += [dict(r, source="long-original-domain", origin="continued", feasible=r["independent_audit"]["feasible"])
                 for r in doc["runs"]]
    unique = {}
    for row in rows:
        if row.get("feasible", True):
            key = row["basin"], row["arm"], controls.vector_digest(row["vector"])
            unique.setdefault(key, row)
    return list(unique.values())


def run(case):
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    target = HERE / case
    target.mkdir(exist_ok=True)
    if (target / "results.json").exists():
        raise FileExistsError("Completed receipt already exists")
    begun = time.monotonic()
    doc, old, obs, prior, bank, checkpoint, prefix = loader.load(case)
    geometry = json.loads((HERE / "geometry/geometry.json").read_text())
    binding = geometry["captures"][old["session_id"]]
    assert binding["all_bindings_verified"]
    assert binding["input_sha256"] == doc["input_manifest_sha256"]
    assert binding["analysis_sha256"] == doc["analysis_manifest_sha256"]
    theta, frames, support = cone_bundle()
    pool = full_scan_pool(case, old)
    score = replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.)
    output = dict(case=case, session_id=old["session_id"], relative_sigma_s=1., options=OPTIONS,
                  seconds_per_fit=30., maximum_iterations=600, basins={}, runs=[], candidates=[], selections=[],
                  protocol_sha256=controls.digest_bytes(Path(__file__).read_bytes()),
                  objective_sha256=controls.digest_bytes((HERE / "cone_objective.py").read_bytes()),
                  cone_bundle_digests=dict(CONE_BUNDLE_DIGESTS), pose_binding_digest=binding["binding_digest"],
                  evidence_sha256=doc["evidence_sha256"], input_sha256=doc["input_manifest_sha256"],
                  analysis_sha256=doc["analysis_manifest_sha256"], status="running")

    def save():
        (target / "progress.json").write_text(json.dumps(output, indent=2, default=controls.encode) + "\n")

    for basin, region in old["basins"].items():
        center = np.asarray(region["center"])
        radius = region["radius_km"] if case == "1939" else max(25., 2 * region["radius_km"])
        association = checkpoint.get(prefix + ":" + basin + ":association")["result"]
        calibration = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
        subset = bank.select(association["selected_indices"])
        baseline = np.asarray(calibration["receiver_baseline_hz"])
        base = PositionObjective(obs, subset, prior, score, receiver_baseline_hz=baseline)
        candidates = [r for r in pool if r["basin"] == basin]
        cal_penalty = next(r["calibration_penalty"] for r in old["candidates"] if r["basin"] == basin)
        for row in candidates:
            assert abs(base.evaluate(np.asarray(row["vector"]))[0] - row["objective"]) < 1e-6
        seeds = {arm: min((r for r in candidates if r["arm"] == arm), key=lambda r:r["objective"])
                 for arm in controls.ARMS}
        output["basins"][basin] = dict(center=center.tolist(), radius_km=radius, original_radius_km=region["radius_km"],
                                       numbers=subset.numbers.tolist(), baseline_sha256=controls.vector_digest(baseline),
                                       seeds={arm: dict(vector_sha256=controls.vector_digest(row["vector"]),
                                                        source=row["source"], origin=row["origin"])
                                              for arm, row in seeds.items()}, repriced_candidates=len(candidates))
        minimum = max(-20., subset.nodes_s[0] - obs.times_s.min())
        maximum = min(20., subset.nodes_s[-1] - obs.times_s.max())
        for option, strength in OPTIONS.items():
            objective = ConeObjective(obs, subset, prior, score, receiver_baseline_hz=baseline,
                                      strength=strength, theta=theta, frames=frames, support=support)

            def record(vector, arm, origin, **extra):
                value, gradient, terms = objective.evaluate(vector)
                uniform_value, _, uniform = base.evaluate(vector)
                mass, uniform_mass = float(terms.responsibilities.sum()), float(uniform.responsibilities.sum())
                result = dict(option=option, strength=strength, arm=arm, basin=basin, origin=origin,
                              vector=np.asarray(vector).tolist(), objective=float(value), selection_score=float(value + cal_penalty),
                              calibration_penalty=cal_penalty, data_nll=float(terms.nll),
                              uniform_frequency_data_nll=float(uniform.nll), cone_score_adjustment=float(value - uniform_value),
                              timing_penalty=float(value - terms.nll), posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)),
                              uniform_posterior_rms_hz=float(np.sqrt(np.sum(uniform.responsibilities * uniform.residual_hz**2) / uniform_mass)),
                              signal_mass=mass, signal_fraction=mass / len(obs.window_ids),
                              **controls.audit(vector, gradient, objective.basis, arm, prior.radius_km, center, radius, minimum, maximum), **extra)
                if strength:
                    g = objective.last_geometry
                    np.testing.assert_allclose(g["q"].sum(axis=1), g["base_q"].sum(axis=1), rtol=1e-12, atol=1e-12)
                    result["posterior_mean_cone_support"] = float(np.sum(terms.responsibilities * g["support"]) / mass)
                return result

            for row in candidates:
                r = record(np.asarray(row["vector"]), row["arm"], "saved:" + row["source"] + ":" + row["origin"])
                if r["feasible"]:
                    output["candidates"].append(r)
            for arm in controls.ARMS:
                seed = np.asarray(seeds[arm]["vector"]).copy()
                # Repair only ulp-level excursions before calling the production solver.
                for origin, r in ((center, radius), (np.zeros(2), prior.radius_km)):
                    distance = np.linalg.norm(seed[:2] - origin)
                    if distance > r:
                        assert distance - r < 1e-5
                        seed[:2] = origin + (seed[:2] - origin) * (r - 1e-8) / distance
                fit = fit_position(objective, seed, rf_arm=arm, maximum_seconds=30., maximum_iterations=600,
                                   local_center=center, local_radius_km=radius)
                result = record(fit.vector, arm, "continued", elapsed_s=fit.elapsed_s, stop_reason=fit.stop_reason, evaluations=fit.evaluations)
                assert abs(result["objective"] - fit.objective) < 1e-6
                assert abs(result["stationarity"] - fit.stationarity) < 1e-5
                output["runs"].append(dict(option=option, basin=basin, arm=arm,
                                           seed_sha256=controls.vector_digest(seeds[arm]["vector"]), result=result))
                if result["feasible"]:
                    output["candidates"].append(result)
                save()
                print(case, basin, option, arm, round(result["selection_score"], 3), result["converged"], flush=True)
    for option in OPTIONS:
        for arm in controls.ARMS:
            output["selections"].append(min((r for r in output["candidates"] if r["option"] == option and r["arm"] == arm), key=lambda r:r["selection_score"]))
    for row in output["candidates"]:
        lat, lon = np.radians(coordinates(prior, row["vector"][:2]))
        a, b = np.radians([doc["reference_latitude_deg"], doc["reference_longitude_deg"]])
        h = np.sin((lat-a)/2)**2 + np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row["horizontal_error_m"] = float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))
    output["nested_search_gaps"] = {option:max(0., next(r["selection_score"] for r in output["selections"] if r["option"] == option and r["arm"] == "fitted-c")
                                              -next(r["selection_score"] for r in output["selections"] if r["option"] == option and r["arm"] == "zero-c")) for option in OPTIONS}
    output.update(status="complete", elapsed_s=time.monotonic() - begun)
    save()
    (target / "results.json").write_text(json.dumps(output, indent=2, default=controls.encode) + "\n")
    for row in output["selections"]:
        print("SELECTED", case, row["option"], row["arm"], row["horizontal_error_m"], row["converged"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("1939", "2139"), required=True)
    run(parser.parse_args().case)
