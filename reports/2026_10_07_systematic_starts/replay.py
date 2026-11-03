"""Repeatable offline regional refinement; reference locations never make starts.

Uses the tested numerical ports/solver from the earlier slope experiment.
Does not run global discovery, change frozen calibration, or publish results.
"""

import argparse
import copy
import inspect
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_07_slope_priors"
sys.path.insert(0, str(PREVIOUS))
import run as common
import polish
import numpy as np


def plan(case, methods):
    """Keep every region named by either method, even when scoring only V16."""
    basins = sorted({b for values in case["methods"].values() for b in values})
    missing = set(basins) - case["basins"].keys()
    if missing:
        raise ValueError(f"candidate regions have no frozen fixture: {sorted(missing)}")
    if not basins:
        raise ValueError("no candidate regions")
    answer = []
    for method in methods:
        if method not in case["scores"]:
            raise ValueError(f"unknown method {method}")
        for basin in basins:
            region = copy.deepcopy(case["basins"][basin])
            # This replay's solver audits the tested 25 km disk. Do not silently
            # shrink a larger source domain; a new protocol is needed for that.
            if region["local_radius_km"] > 25.:
                raise ValueError("source region exceeds this replay's 25 km domain")
            answer.append(dict(method=method, basin=basin, region=region))
    return answer


def choose(rows, require_converged=False):
    eligible = [r for r in rows if r["feasible"] and
                (not require_converged or r["converged"])]
    return min(eligible, key=lambda r: (r["selection_score"], r["basin"], r["origin"]),
               default=None)


def replay(manifest_path, case_id, methods, destination):
    recipe_path = HERE / "recipe.json"
    recipe = json.loads(recipe_path.read_text())
    # The reused numerical audits assume these values; fail rather than silently
    # accepting an unsupported edited recipe.
    if (recipe["relative_sigma_s"], recipe["slope_half_width_hz_s"],
        recipe["local_radius_km"], recipe["continuations_per_region_arm"]) != (1., 60., 25., 1):
        raise ValueError("recipe differs from validated numerical configuration")
    if recipe["arms"] != list(common.ARMS) or recipe["starts"] != ["association", "zero-timing"]:
        raise ValueError("both matched arms and standard starts are required")
    if not 0 < recipe["seconds_per_fit"] <= 20 or not 0 < recipe["maximum_iterations"] <= 600:
        raise ValueError("fit budget exceeds the bounded replay protocol")
    manifest = json.loads(manifest_path.read_text())
    source_case = next(c for c in manifest["cases"] if c["case"] == case_id)
    case = {k: v for k, v in source_case.items() if k != "evaluation_reference"}
    tasks = plan(case, methods)
    destination.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), recipe_path, manifest_path, PREVIOUS / "run.py",
               PREVIOUS / "polish.py", PREVIOUS / "bounded_fit.py",
               Path(inspect.getfile(common.PositionObjective))]
    out = dict(status="running", case=case_id, session_id=case["session_id"], recipe=recipe,
               source_hashes={str(p): common.digest(p.read_bytes()) for p in sources},
               planned_regions=[{k: t[k] for k in ("method", "basin")} for t in tasks],
               seeds=[], runs=[], candidates=[], selections=[], best_feasible=[], search_gaps=[])
    begun = time.monotonic()

    def save():
        temporary = destination / "progress.tmp"
        temporary.write_text(json.dumps(out, indent=2, default=common.encode, allow_nan=False) + "\n")
        temporary.replace(destination / "progress.json")

    save()
    for task in tasks:
        method, basin, region = (task[k] for k in ("method", "basin", "region"))
        obj = common.load_objective(manifest_path.parent, case, basin, method)
        for arm in recipe["arms"]:
            local_rows = []

            def record(vector, origin, **metadata):
                row = common.candidate(obj, region, vector, "window60", arm, basin, method,
                                       origin, case=case_id, **metadata)
                out["candidates"].append(row)
                local_rows.append(row)
                return row

            def fit(seed, label, parent_origin=None):
                seed = polish.inside(seed, obj.prior.radius_km, region["center_km"])
                metadata = dict(parent_origin=parent_origin,
                                seed_sha256=common.vector_digest(seed), fixture_sha256=region["sha256"])
                out["seeds"].append(dict(method=method, basin=basin, arm=arm, label=label,
                                         vector=seed.tolist(), **metadata))
                record(seed, "initial:" + label, **metadata)
                try:
                    result = common.fit_position(
                        obj, seed.copy(), rf_arm=arm,
                        maximum_seconds=recipe["seconds_per_fit"],
                        maximum_iterations=recipe["maximum_iterations"],
                        local_center=np.asarray(region["center_km"]), local_radius_km=25.,
                        slope_half_width_hz_s=60.)
                except (ValueError, TimeoutError, ArithmeticError) as error:
                    out["runs"].append(dict(method=method, basin=basin, arm=arm, label=label,
                                            status="failed", error=str(error), **metadata))
                    save()
                    return
                row = record(result.vector, "fit:" + label, elapsed_s=result.elapsed_s,
                             status="complete", stop_reason=result.stop_reason, **metadata)
                np.testing.assert_allclose(row["objective"], result.objective, atol=1e-6, rtol=0)
                np.testing.assert_allclose(row["stationarity"], result.stationarity, atol=1e-5, rtol=0)
                out["runs"].append(row)
                save()
                print(method, basin, arm, label, round(row["selection_score"], 3),
                      row["converged"], flush=True)

            for label, seed, _ in common.seeds(region["initial_vector"], arm, 60.):
                fit(seed, label)
            parent = choose(local_rows)
            if parent is not None:
                fit(np.asarray(parent["vector"]), "own-continuation", parent["origin"])

    for method in methods:
        for arm in recipe["arms"]:
            rows = [r for r in out["candidates"] if r["method"] == method and r["arm"] == arm]
            selected, best = choose(rows, True), choose(rows)
            flags = []
            if selected is None:
                flags.append("no_converged_solution")
            else:
                center = np.asarray(case["basins"][selected["basin"]]["center_km"])
                if np.linalg.norm(np.asarray(selected["vector"][:2]) - center) >= .95 * 25:
                    flags.append("near_local_boundary_review_region_coverage")
                if selected["slope_active_bounds"]:
                    flags.append("slope_bound_active")
                if best["selection_score"] < selected["selection_score"] - 1e-6:
                    flags.append("better_unconverged_candidate")
            out["selections"].append(dict(method=method, arm=arm, result=selected, review_flags=flags))
            out["best_feasible"].append(dict(method=method, arm=arm, result=best))
        a, b = [out["selections"][-2 + i]["result"] for i in (0, 1)]
        out["search_gaps"].append(dict(method=method, fitted_c_worse_than_zero_c=
            None if a is None or b is None else max(0., b["selection_score"] - a["selection_score"])))

    # Geographic truth is introduced only after fitting and score selection.
    reference = source_case["evaluation_reference"]
    lat0, lon0 = np.radians([reference["latitude_deg"], reference["longitude_deg"]])
    prior = common.RegionalPrior(**case["prior"])
    for row in out["candidates"]:
        lat, lon = np.radians(common.coordinates(prior, row["vector"][:2]))
        h = np.sin((lat-lat0)/2)**2 + np.cos(lat)*np.cos(lat0)*np.sin((lon-lon0)/2)**2
        row["horizontal_error_m"] = float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h, 0, 1))))
    out.update(status="complete", elapsed_s=time.monotonic()-begun,
               fit_elapsed_s=sum(r.get("elapsed_s", 0.) for r in out["runs"]))
    save()
    (destination / "results.json").write_text(
        json.dumps(out, indent=2, default=common.encode, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=PREVIOUS / "inputs/manifest.json")
    parser.add_argument("--case", required=True)
    parser.add_argument("--methods", nargs="+", choices=["V16", "T1AT"], default=["V16", "T1AT"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay(args.manifest, args.case, args.methods, args.output)
