"""Truth-free frequency continuation against a matched final-model control."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent.parent
CONE = REPORTS / "2026_10_07_sigma1_cones"
sys.path.insert(0, str(CONE))
spec = importlib.util.spec_from_file_location("prior_cone_experiment", CONE / "experiment.py")
prior_experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior_experiment)
loader, controls = prior_experiment.loader, prior_experiment.controls


def schedule(option):
    if option == "control":
        return [(125., 40., 800)]
    if option == "anneal":
        return [(500., 8., 200), (250., 8., 200), (125., 24., 400)]
    raise ValueError(option)


def source_pool(case, old):
    rows = prior_experiment.full_scan_pool(case, old)
    frozen = json.loads((CONE / case / "polished.json").read_text())
    # All primary candidates and all final control selections are eligible.
    primary = json.loads((CONE / case / "results.json").read_text())
    rows += [dict(r, source="cone-primary-control") for r in primary["candidates"] if r["option"] == "control"]
    rows += [dict(r, source="cone-final-control") for r in frozen["selections"] if r["option"] == "control"]
    unique = {}
    for row in rows:
        if row.get("feasible", True):
            key = row["basin"], row["arm"], controls.vector_digest(row["vector"])
            unique.setdefault(key, row)
    return list(unique.values())


def choose_basins(pool):
    return sorted({min((r for r in pool if r["arm"] == arm), key=lambda r:r["selection_score"])["basin"]
                   for arm in controls.ARMS})


def inside_seed(seed, center, radius, global_radius):
    seed = np.asarray(seed, float).copy()
    for origin, r in ((center, radius), (np.zeros(2), global_radius)):
        distance = np.linalg.norm(seed[:2] - origin)
        if distance > r:
            if distance - r > 1e-5:
                raise ValueError("infeasible seed")
            seed[:2] = origin + (seed[:2] - origin) * (r - 1e-8) / distance
    return seed


def run(case):
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore

    output_path = HERE / f"{case}.json"
    if output_path.exists():
        raise FileExistsError(output_path)
    begun = time.monotonic()
    doc, old, obs, prior, bank, checkpoint, prefix = loader.load(case)
    pool = source_pool(case, old)
    basins = choose_basins(pool)
    score = replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.)
    assert score.sigma_hz == 125.
    output = dict(case=case, session_id=old["session_id"], selected_basins=basins,
                  sigma_s=1., final_sigma_hz=125., options={o:schedule(o) for o in ("control", "anneal")},
                  evidence_sha256=doc["evidence_sha256"], source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [Path(__file__), HERE/"protocol.txt", CONE/case/"results.json", CONE/case/"polished.json"]},
                  seeds={}, runs=[], candidates=[], selections=[], status="running")

    def save():
        output_path.write_text(json.dumps(output, indent=2, default=controls.encode) + "\n")

    for basin, region in old["basins"].items():
        center = np.asarray(region["center"])
        radius = region["radius_km"] if case == "1939" else max(25., 2*region["radius_km"])
        association = checkpoint.get(prefix+":"+basin+":association")["result"]
        calibration = checkpoint.get(prefix+":"+basin+":calibration")["result"]
        subset = bank.select(association["selected_indices"])
        baseline = np.asarray(calibration["receiver_baseline_hz"])
        obj = PositionObjective(obs, subset, prior, score, receiver_baseline_hz=baseline)
        saved = [r for r in pool if r["basin"] == basin]
        penalty = saved[0]["calibration_penalty"]
        minimum = max(-20., subset.nodes_s[0] - obs.times_s.min())
        maximum = min(20., subset.nodes_s[-1] - obs.times_s.max())

        def record(vector, option, arm, origin, **extra):
            value, grad, terms = obj.evaluate(np.asarray(vector))
            mass = float(terms.responsibilities.sum())
            audit = controls.audit(vector, grad, obj.basis, arm, prior.radius_km, center, radius, minimum, maximum)
            if arm == "zero-c":
                assert vector[6] == 0.
            return dict(option=option, arm=arm, basin=basin, origin=origin, vector=np.asarray(vector).tolist(),
                        objective=float(value), selection_score=float(value+penalty), calibration_penalty=penalty,
                        data_nll=float(terms.nll), timing_penalty=float(value-terms.nll), signal_mass=mass,
                        posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),
                        **audit, **extra)

        for row in saved:
            for option in ("control", "anneal"):
                r = record(row["vector"], option, row["arm"], "saved:"+row["source"])
                assert abs(r["objective"] - row["objective"]) < 1e-6
                if r["feasible"]:
                    output["candidates"].append(r)
        if basin not in basins:
            continue
        output["seeds"][basin] = {}
        for arm in controls.ARMS:
            seed = min((r for r in saved if r["arm"] == arm), key=lambda r:r["objective"])
            output["seeds"][basin][arm] = dict(source=seed["source"], vector_sha256=controls.vector_digest(seed["vector"]))
            for option in ("control", "anneal"):
                vector = inside_seed(seed["vector"], center, radius, prior.radius_km)
                for stage, (sigma, seconds, iterations) in enumerate(schedule(option)):
                    stage_obj = PositionObjective(obs, subset, prior, replace(score, sigma_hz=sigma), receiver_baseline_hz=baseline)
                    before_hash = controls.vector_digest(vector)
                    fit = fit_position(stage_obj, vector, rf_arm=arm, maximum_seconds=seconds,
                                       maximum_iterations=iterations, local_center=center, local_radius_km=radius)
                    r = record(fit.vector, option, arm, f"stage{stage}:sigma{sigma:g}",
                               stage_sigma_hz=sigma, elapsed_s=fit.elapsed_s, stop_reason=fit.stop_reason,
                               stage_objective=fit.objective, seed_sha256=before_hash, evaluations=fit.evaluations)
                    output["runs"].append(r)
                    if r["feasible"]:
                        output["candidates"].append(r)
                    vector = inside_seed(fit.vector, center, radius, prior.radius_km)
                    save()
                    print(case, basin, arm, option, sigma, round(r["selection_score"], 3), r["converged"], flush=True)
    for option in ("control", "anneal"):
        for arm in controls.ARMS:
            output["selections"].append(min((r for r in output["candidates"] if r["option"] == option and r["arm"] == arm), key=lambda r:r["selection_score"]))
    # Evaluation only after selection; never feeds the experiment.
    for row in output["candidates"]:
        lat, lon = np.radians(coordinates(prior, row["vector"][:2]))
        a, b = np.radians([doc["reference_latitude_deg"], doc["reference_longitude_deg"]])
        h = np.sin((lat-a)/2)**2 + np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row["horizontal_error_m"] = float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h, 0, 1))))
    output.update(status="complete", elapsed_s=time.monotonic()-begun,
                  fit_elapsed_s=sum(r["elapsed_s"] for r in output["runs"]))
    save()
    for row in output["selections"]:
        print("SELECTED", case, row["option"], row["arm"], row["horizontal_error_m"], row["selection_score"], row["converged"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("1939", "2139"), required=True)
    run(parser.parse_args().case)
