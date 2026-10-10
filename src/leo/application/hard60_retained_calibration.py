"""Recover ordinary retained regions whose calibration failed, without reference positions."""

import math
import time

import numpy as np

from leo.analysis.hard60_bounded_fit import fit_bounded_position
from leo.analysis.hard60_qualification import qualify, validate_fixed_calibration_fit
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_calibration import RegionalCalibration, receiver_correction
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration
from leo.application.regional_position_runner import _calibration, json_value
from leo.contracts.digests import canonical_digest


def regional_triggers(regions, *, minimum_local_radius_km=25.0):
    """Inventory all ordinary failed calibrations, deduplicated across B7 passes.

    The regions are from the same in-memory observation, prior, bank and score.
    Neither a position error nor a reference coordinate enters this inventory.
    """
    candidates, unavailable = {}, []
    for source, region in regions.items():
        spacing = {
            f"point:{row['east_km']:g}:{row['north_km']:g}": row["spacing_km"]
            for row in region["searches"]["V16"]["evaluations"]
        }
        for failure in region["failures"]:
            if failure.get("stage") != "calibration":
                continue
            key = failure["basin"]
            if not key.startswith("point:"):
                unavailable.append(
                    dict(source=source, basin=key, reason="existing-recovery-no-recursion")
                )
                continue
            receipt = region["points"].get(key)
            original = receipt.get("result") if receipt else None
            if not original or key not in spacing:
                unavailable.append(
                    dict(source=source, basin=key, reason="missing-coarse-or-spacing")
                )
                continue
            radius = max(minimum_local_radius_km, spacing[key] / math.sqrt(2))
            identity = dict(
                basin=key, original_sha256=canonical_digest(original), local_radius_km=radius
            )
            digest = canonical_digest(identity)
            if digest not in candidates:
                candidates[digest] = dict(
                    identity=identity,
                    basin=key,
                    original=original,
                    spacing_km=spacing[key],
                    source_passes=[],
                )
            candidates[digest]["source_passes"].append(source)
    return dict(candidates=[candidates[k] for k in sorted(candidates)], unavailable=unavailable)


def _recover_calibration(observations, bank, prior, trigger):
    original = trigger["original"]
    indices = original["bootstrap"]["satellite_indices"]
    objective = Hard60Objective(observations, bank.select(indices), prior, HARD60_SCORE)
    fit = original["fits"]["V16"]["fit"]
    point = np.asarray([float(x) for x in trigger["basin"].split(":")[1:]])
    value = objective.evaluate(np.asarray(fit["vector"], float))[0]
    if not np.isclose(value, fit["objective"], rtol=0, atol=1e-6):
        raise ValueError("retained coarse fit differs from the physical model")
    prefit_qualification = None
    if not fit["converged"]:
        prefit_qualification = qualify(
            objective,
            np.asarray(fit["vector"], float),
            fit["objective"],
            retained=True,
            stage="calibration-prefit",
            independently_qualified=False,
            maximum_rounds=2,
            maximum_evaluations=100,
        )
        if not prefit_qualification["qualified"]:
            return dict(
                status="prefit-unqualified",
                prefit_qualification=prefit_qualification,
                calibration=None,
            )
        fit = prefit_qualification["fit"]
    prefit = validate_fixed_calibration_fit(objective, fit, point)
    begun = time.monotonic()
    receipt = dict(
        correction=None,
        calibration=None,
        postfit=None,
        qualification=None,
        prefit_qualification=prefit_qualification,
        direct_prefit=json_value(prefit),
    )
    try:
        correction = receiver_correction(observations, objective.evaluate(prefit.vector)[2])
        receipt["correction"] = json_value(correction)
        corrected = Hard60Objective(
            observations,
            objective.bank,
            prior,
            HARD60_SCORE,
            receiver_baseline_hz=correction.values_hz,
        )
        postfit, diagnostics = fit_bounded_position(
            corrected,
            prefit.vector.copy(),
            fixed_position=True,
            rf_arm="fitted-c",
            slope_half_width_hz_s=60,
            maximum_seconds=20,
            maximum_iterations=600,
        )
        receipt.update(postfit=json_value(postfit), diagnostics=json_value(diagnostics))
        selected = receipt["postfit"]
        if not postfit.converged:
            attempt = qualify(
                corrected,
                postfit.vector,
                postfit.objective,
                retained=True,
                stage="calibration-postfit",
                independently_qualified=False,
                maximum_rounds=2,
                maximum_evaluations=100,
            )
            receipt["qualification"] = json_value(attempt)
            if not attempt["qualified"]:
                receipt.update(status="calibration-unqualified", elapsed_s=time.monotonic() - begun)
                return receipt
            selected = attempt["fit"]
        validated = validate_fixed_calibration_fit(corrected, selected, prefit.vector[:2])
        baseline = correction.values_hz + corrected.design[:, :4] @ validated.vector[2:6]
        calibration = RegionalCalibration(tuple(indices), prefit, validated, correction, baseline)
        receipt.update(status="qualified", calibration=json_value(calibration))
    except (ValueError, TimeoutError, AssertionError) as error:
        receipt.update(status="calibration-failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - begun
    return receipt


def recovered_region(observations, bank, prior, trigger, stage):
    """Bounded, checkpointed calibration/association/finals for one saved basin."""
    basin = trigger["basin"]
    prefix = "retained-calibration:" + canonical_digest(trigger["identity"])[7:] + ":"
    calibrated = stage(
        prefix + "calibration",
        90,
        lambda: _recover_calibration(observations, bank, prior, trigger),
    )
    if not calibrated["result"] or calibrated["result"]["calibration"] is None:
        return dict(calibrations={}, finals=[], recovery=calibrated)
    calibration = calibrated["result"]["calibration"]
    parsed = _calibration(calibration)
    associated = stage(
        prefix + "association",
        60,
        lambda: associate_calibration(
            observations, bank, prior, parsed, maximum_seconds=60, orbit_predictor=predict_orbits
        ),
    )
    if not associated["result"]:
        return dict(
            calibrations={basin: calibration},
            finals=[],
            recovery=calibrated,
            association=associated,
        )
    selected = associated["result"]
    subset = bank.select(selected["selected_indices"])
    model = Hard60Objective(
        observations,
        subset,
        prior,
        HARD60_SCORE,
        receiver_baseline_hz=parsed.receiver_baseline_hz,
    )
    knots = parsed.correction.knots_hz
    penalty = float(
        0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
    )
    center = np.asarray([float(x) for x in basin.split(":")[1:]])
    radius = trigger["identity"]["local_radius_km"]
    finals = []
    for arm in ("zero-c", "fitted-c"):
        completed = []
        for name in Hard60Configuration().final_starts:
            seed = np.asarray(selected["initial_vector"], float).copy()
            if name == "zero-timing":
                seed[7:] = 0
            elif name == "own-continuation" and completed:
                seed = np.asarray(min(completed, key=lambda row: row["objective"])["vector"]).copy()
            for origin, bound in ((np.zeros(2), prior.radius_km), (center, radius)):
                delta = seed[:2] - origin
                distance = np.linalg.norm(delta)
                if bound < distance <= bound + 1e-6:
                    seed[:2] = origin + delta * ((bound - 1e-8) / distance)

            effective_seed = seed.copy()

            def fit(seed=effective_seed, arm=arm):
                fitted, diagnostics = fit_bounded_position(
                    model,
                    seed,
                    rf_arm=arm,
                    local_center=center,
                    local_radius_km=radius,
                    slope_half_width_hz_s=60,
                    maximum_seconds=20,
                    maximum_iterations=600,
                )
                return dict(fit=fitted, diagnostics=diagnostics)

            receipt = stage(prefix + arm + ":" + name, 20, fit)
            fitted = receipt["result"]["fit"] if receipt["result"] else None
            if fitted is not None:
                if arm == "zero-c" and fitted["vector"][6] != 0:
                    raise ValueError("zero-c recovery fit unlocked c")
                completed.append(fitted)
            finals.append(
                dict(
                    basin=basin,
                    method="V16",
                    arm=arm,
                    start=name,
                    fit=fitted,
                    reason=receipt["reason"],
                    calibration_penalty=penalty,
                    satellites=subset.numbers.tolist(),
                    association=selected["selection"],
                )
            )
    return dict(
        calibrations={basin: calibration},
        finals=finals,
        recovery=calibrated,
        association=associated,
    )
