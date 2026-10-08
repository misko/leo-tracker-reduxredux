"""Checkpointed recovery of failed coarse fits without replacing good candidates."""

from functools import partial

import numpy as np

from leo.analysis.hard60_bounded_fit import fit_bounded_position
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_calibration import RegionalCalibration, receiver_correction
from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch, distinct_basins
from leo.application.regional_position_runner import _calibration, _fit, json_value


def recover_failed_coarse(observations, bank, prior, result, *, score, config, stage):
    """Apply the qualified DS16 B policy; every operation uses the stage port.

    The baseline search/finals remain candidates. Recovery uses original
    bootstrap seeds, original constraints and priors, and no reference position.
    Best feasible states rank regions; only independently stationary fits may
    calibrate or become a final estimate. Final RF arms share association.
    """
    search = result["searches"]["V16"]
    coarse, candidates, replacements = [], {}, {}

    def key_for(point):
        return f"point:{point['east_km']:g}:{point['north_km']:g}"

    def objective_for(original):
        indices = original["bootstrap"]["satellite_indices"]
        return Hard60Objective(observations, bank.select(indices), prior, score)

    def bounded(objective, start, *, coarse=False, **options):
        fitted, diagnostics = fit_bounded_position(
            objective,
            start,
            slope_half_width_hz_s=config.slope_half_width_hz_s,
            maximum_seconds=config.coarse_fit_seconds if coarse else config.stage_fit_seconds,
            maximum_iterations=config.coarse_iterations if coarse else config.final_iterations,
            **options,
        )
        return {"fit": fitted, "diagnostics": diagnostics}

    failed = []
    for point in search["evaluations"]:
        original = result["points"][key_for(point)]["result"]
        if (
            point["spacing_km"] == config.levels_km[0]
            and original
            and not original["fits"]["V16"]["fit"]["converged"]
        ):
            failed.append(point)
    for point in sorted(failed, key=key_for):
        key = key_for(point)
        original = result["points"][key]["result"]
        receipt = stage(
            "recovery:" + key + ":coarse",
            config.coarse_fit_seconds,
            partial(
                bounded,
                objective_for(original),
                original["bootstrap"]["vector"],
                coarse=True,
                fixed_position=True,
            ),
        )
        coarse.append(
            {
                "point": key,
                "original": original["fits"]["V16"]["fit"],
                "original_optimizer": original["fits"]["V16"].get("optimizer"),
                **receipt,
            }
        )
        if receipt["result"] is None:
            continue
        best = receipt["result"]["diagnostics"]["best_feasible"]
        old = original["fits"]["V16"]["fit"]
        selected = best if best["objective"] <= old["objective"] else old
        replacements[key] = selected
        candidates[key] = original, selected["vector"]
    reranked = SpatialSearch(
        tuple(
            SpatialEvaluation(
                p["east_km"],
                p["north_km"],
                p["spacing_km"],
                replacements.get(key_for(p), {}).get("objective", p["score"]),
            )
            for p in search["evaluations"]
            if p["score"] < 1e100
        ),
        search["deferred_cells"],
        "bounded-timing-recovery",
    )
    retained = distinct_basins(
        reranked, count=config.basins, minimum_separation_km=config.basin_separation_km
    )
    basins, fit_diagnostics = [], []
    for point in retained:
        key = f"point:{point.east_km:g}:{point.north_km:g}"
        if key not in candidates:
            continue
        original, seed = candidates[key]
        objective = objective_for(original)
        recovery_key = "recovery:" + key

        def calibrate(objective=objective, seed=seed, original=original):
            attempts = []
            for name in ("coarse-best", "zero-timing"):
                start = np.array(seed, float)
                if name == "zero-timing":
                    start[7:] = 0
                attempt = {"start": name}
                attempts.append(attempt)
                try:
                    before = bounded(objective, start, fixed_position=True)
                    prefit = before["fit"]
                    attempt["prefit"] = before
                    if not prefit.converged:
                        continue
                    correction = receiver_correction(
                        observations, objective.evaluate(prefit.vector)[2]
                    )
                    corrected = Hard60Objective(
                        observations,
                        objective.bank,
                        prior,
                        score,
                        receiver_baseline_hz=correction.values_hz,
                    )
                    after = bounded(corrected, prefit.vector, fixed_position=True)
                    postfit = after["fit"]
                    attempt["postfit"] = after
                    if not postfit.converged:
                        continue
                    baseline = correction.values_hz + corrected.design[:, :4] @ postfit.vector[2:6]
                    calibration = RegionalCalibration(
                        tuple(original["bootstrap"]["satellite_indices"]),
                        prefit,
                        postfit,
                        correction,
                        baseline,
                    )
                    return {"calibration": calibration, "attempts": attempts}
                except (ValueError, TimeoutError) as error:
                    attempt["reason"] = str(error)
            return {"calibration": None, "attempts": attempts}

        receipt = stage(recovery_key + ":calibration", 4 * config.stage_fit_seconds, calibrate)
        basin = {"point": key, "score_for_ranking": point.score, "calibration": receipt}
        basins.append(basin)
        if receipt["result"] is None or receipt["result"]["calibration"] is None:
            result["failures"].append(
                {
                    "basin": recovery_key,
                    "stage": "calibration",
                    "reason": receipt["reason"] or "bounded calibration did not converge",
                }
            )
            continue
        calibrated = _calibration(receipt["result"]["calibration"])
        result["calibrations"][recovery_key] = receipt["result"]["calibration"]
        receipt = stage(
            recovery_key + ":association",
            config.association_seconds,
            partial(
                associate_calibration,
                observations,
                bank,
                prior,
                calibrated,
                maximum_seconds=config.association_seconds,
                orbit_predictor=predict_orbits,
            ),
        )
        if receipt["result"] is None:
            result["failures"].append(
                {"basin": recovery_key, "stage": "association", "reason": receipt["reason"]}
            )
            continue
        association = receipt["result"]
        final_bank = bank.select(association["selected_indices"])
        final_objective = Hard60Objective(
            observations,
            final_bank,
            prior,
            score,
            receiver_baseline_hz=calibrated.receiver_baseline_hz,
        )
        knots = calibrated.correction.knots_hz
        penalty = 0.5 * (
            float(np.sum(knots**2)) / 50**2
            + float(np.sum(np.diff(knots, n=2, axis=1) ** 2)) / 25**2
        )
        center = np.array([point.east_km, point.north_km])
        radius = max(config.minimum_local_radius_km, point.spacing_km / np.sqrt(2))
        for arm in ("fitted-c", "zero-c"):
            completed = []
            for name in config.final_starts:
                start = np.array(association["initial_vector"], float)
                if name == "zero-timing":
                    start[7:] = 0
                elif name == "own-continuation" and completed:
                    start = min(completed, key=lambda r: r.objective).vector.copy()
                for origin, bound in ((np.zeros(2), prior.radius_km), (center, radius)):
                    delta = start[:2] - origin
                    distance = np.linalg.norm(delta)
                    if bound < distance <= bound + 1e-6:
                        start[:2] = origin + delta * ((bound - 1e-8) / distance)
                receipt = stage(
                    f"{recovery_key}:{arm}:{name}",
                    config.stage_fit_seconds,
                    partial(
                        bounded,
                        final_objective,
                        start,
                        rf_arm=arm,
                        local_center=center,
                        local_radius_km=radius,
                    ),
                )
                fitted = receipt["result"]["fit"] if receipt["result"] else None
                if fitted:
                    completed.append(_fit(fitted))
                result["finals"].append(
                    {
                        "basin": recovery_key,
                        "method": "V16",
                        "arm": arm,
                        "start": name,
                        "fit": fitted,
                        "reason": receipt["reason"],
                        "calibration_penalty": penalty,
                        "satellites": final_bank.numbers.tolist(),
                        "association": association["selection"],
                    }
                )
                fit_diagnostics.append(
                    {
                        "basin": recovery_key,
                        "arm": arm,
                        "start": name,
                        "optimizer": receipt["result"]["diagnostics"]
                        if receipt["result"]
                        else None,
                    }
                )
    # Only presentation copies change; immutable baseline stage receipts remain.
    for key, selected in replacements.items():
        old = result["points"][key]
        original = old["result"]
        result["points"][key] = {
            **old,
            "result": {
                **original,
                "fits": {**original["fits"], "V16": {"fit": selected, "reason": None}},
            },
        }
    result["searches"]["V16"] = {
        **search,
        "evaluations": [
            {**p, "score": replacements.get(key_for(p), {}).get("objective", p["score"])}
            for p in search["evaluations"]
        ],
    }
    result["recovery"] = {
        "policy": config.recovery_policy,
        "attempted_points": len(coarse),
        "converged_points": sum(
            bool(r["result"] and r["result"]["fit"]["converged"]) for r in coarse
        ),
        "coarse": coarse,
        "retained_basins": json_value(retained),
        "basins": basins,
        "final_optimizers": fit_diagnostics,
    }
    return result
