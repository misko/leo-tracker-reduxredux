"""Carry an ordinary calibration recovery through matched finals and unchanged B7."""

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.hard60_bounded_fit import _Problem, fit_bounded_position
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_calibration import RegionalCalibration, receiver_correction
from leo.analysis.regional_position_fit import PositionFit
from leo.application.hard60_b7 import regional_winners, run_joint_stages
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration
from leo.application.regional_position_inputs import prepare_position_windows
from leo.application.regional_position_runner import (
    RegionalSliceExpired,
    _calibration,
    json_value,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = HERE.parent / "2026_10_09_position_error_iter93"


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(json_value(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def load_case(document, checkpoint):
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = inputs.load(document["session_id"])
    finally:
        inputs.close()
    for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
        assert getattr(source, field) == document[field]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    evidence = canonical_digest(
        dict(
            windows=prepared.evidence_sha256,
            tle=snapshot.digest,
            candidates=[int(catalogue.satellite_numbers[i]) for i in indices],
        )
    )
    assert evidence == document["evidence_sha256"]
    prior = RegionalPrior(**document["configuration"]["prior"])
    bank, _ = build_regional_bank(
        catalogue, indices, prepared.start_utc_ns, prepared.observations, prior, maximum_seconds=180
    )
    assert bank.numbers.tolist() == document["diagnostics"]["bank"]["retained_numbers"]
    original = checkpoint["checkpoints"]["b7-shared:" + checkpoint["point_key"]]["value"]["result"]
    subset_indices = original["bootstrap"]["satellite_indices"]
    base = Hard60Objective(prepared.observations, bank.select(subset_indices), prior, HARD60_SCORE)
    old = original["fits"]["V16"]["fit"]
    np.testing.assert_allclose(
        base.evaluate(np.asarray(old["vector"]))[0], old["objective"], atol=1e-6, rtol=0
    )
    return prepared.observations, bank, prior, base, subset_indices


def select_prefit(plan, base, point):
    candidates, inventory = [], []
    for entry in plan["prefit_inventory"]:
        source = read(ROOT / entry["path"])
        fit = source
        for field in entry["fit_fields"]:
            fit = fit[field]
        vector = np.asarray(fit["vector"])
        assert np.array_equal(vector[:2], point), "Only the frozen ordinary region is allowed"
        value, gradient, _ = base.evaluate(vector)
        np.testing.assert_allclose(value, fit["objective"], atol=1e-6, rtol=0)
        problem = _Problem(base, vector, fixed_position=True, slope_half_width_hz_s=60)
        stationarity = problem.stationarity(vector, gradient)
        qualified = bool(fit["converged"] and problem.feasible(vector) and stationarity <= 0.001)
        inventory.append(
            dict(
                path=entry["path"],
                objective=float(value),
                qualified=qualified,
                stationarity=stationarity,
            )
        )
        if qualified:
            candidates.append((float(value), entry["path"], fit))
    if not candidates:
        raise ValueError("No independently qualified ordinary prefit")
    _, selected_path, selected = min(candidates, key=lambda row: (row[0], row[1]))
    vector = np.asarray(selected["vector"])
    value, gradient, terms = base.evaluate(vector)
    problem = _Problem(base, vector, fixed_position=True, slope_half_width_hz_s=60)
    mass = float(terms.responsibilities.sum())
    normalized = PositionFit(
        vector=vector.copy(),
        objective=float(value),
        posterior_rms_hz=float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        )
        if mass
        else None,
        signal_windows=mass,
        stationarity=problem.stationarity(vector, gradient),
        converged=True,
        boundary=False,
        stop_reason="qualified-saved-prefit-state",
        evaluations=int(selected.get("evaluations", 0)),
        elapsed_s=float(selected.get("elapsed_s", 0)),
    )
    return normalized, dict(
        inventory=inventory,
        selected_path=selected_path,
        normalization="Recomputed objective/KKT/RMS from saved state; no refit",
    )


def ordinary_regions(saved):
    regions = {}
    for name, source in saved["regions"].items():
        prefix, basin = source["prefix"], source["basin"]
        values = {}
        for key, row in source["checkpoints"].items():
            assert canonical_digest(row["value"]) == row["value_sha256"]
            values[key] = row["value"]
        cal = values[f"{prefix}:{basin}:calibration"]["result"]
        association = values[f"{prefix}:{basin}:association"]["result"]
        knots = np.asarray(cal["correction"]["knots_hz"])
        penalty = float(
            0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
        )
        finals = []
        for arm in ("zero-c", "fitted-c"):
            for start in Hard60Configuration().final_starts:
                receipt = values[f"{prefix}:{basin}:{arm}:{start}"]
                finals.append(
                    dict(
                        basin=basin,
                        method="V16",
                        arm=arm,
                        start=start,
                        fit=receipt["result"],
                        reason=receipt["reason"],
                        calibration_penalty=penalty,
                        satellite_indices=association["selected_indices"],
                        association=association["selection"],
                    )
                )
        regions[name] = dict(calibrations={basin: cal}, finals=finals)
    return regions


def main():
    plan_path = HERE / "protocol.json"
    plan = read(plan_path)
    assert plan["stage_fit_seconds"] == 20 and plan["stage_iterations"] == 600
    assert plan["association_seconds"] == 60 and plan["slice_seconds"] == 500
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if (HERE / "result.json").exists():
        assert read(HERE / "result.json")["protocol_sha256"] == digest
        return
    deadline = time.monotonic() + plan["slice_seconds"]
    document = read(PARENT / "published-v3.json")["manifest"]["document"]
    checkpoints = read(PARENT / "verified-checkpoints.json")
    observations, bank, prior, base, subset_indices = load_case(document, checkpoints)
    point = np.array(
        [checkpoints["selected_basin"]["east_km"], checkpoints["selected_basin"]["north_km"]]
    )
    prefit, selection = select_prefit(plan, base, point)

    def stage(key, budget, operation):
        path = HERE / "stages" / f"{canonical_digest(dict(key=key))[7:]}.json"
        if path.exists():
            receipt = read(path)
            assert receipt["protocol_sha256"] == digest and receipt["key"] == key
            return receipt["value"]
        if time.monotonic() + budget >= deadline:
            raise RegionalSliceExpired(key)
        try:
            value = dict(result=json_value(operation()), reason=None)
        except (ValueError, TimeoutError) as error:
            value = dict(result=None, reason=f"{type(error).__name__}: {error}")
        write(path, dict(protocol_sha256=digest, key=key, value=value))
        return value

    def calibrate():
        correction = receiver_correction(observations, base.evaluate(prefit.vector)[2])
        corrected = Hard60Objective(
            observations, base.bank, prior, HARD60_SCORE, receiver_baseline_hz=correction.values_hz
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
        calibration = None
        if postfit.converged:
            baseline = correction.values_hz + corrected.design[:, :4] @ postfit.vector[2:6]
            calibration = RegionalCalibration(
                tuple(subset_indices), prefit, postfit, correction, baseline
            )
        return dict(calibration=calibration, postfit=postfit, diagnostics=diagnostics)

    try:
        calibrated = stage("recovered-calibration", 20, calibrate)
        if not calibrated["result"] or calibrated["result"]["calibration"] is None:
            write(
                HERE / "result.json",
                dict(
                    protocol_sha256=digest,
                    status="calibration-unqualified",
                    prefit_selection=selection,
                    calibration=calibrated,
                ),
            )
            return
        cal = _calibration(calibrated["result"]["calibration"])
        associated = stage(
            "recovered-association",
            60,
            lambda: associate_calibration(
                observations,
                bank,
                prior,
                cal,
                maximum_seconds=60,
                orbit_predictor=predict_orbits,
            ),
        )
        if not associated["result"]:
            write(
                HERE / "result.json",
                dict(
                    protocol_sha256=digest,
                    status="association-failed",
                    prefit_selection=selection,
                    association=associated,
                ),
            )
            return
        association = associated["result"]
        final_bank = bank.select(association["selected_indices"])
        objective = Hard60Objective(
            observations,
            final_bank,
            prior,
            HARD60_SCORE,
            receiver_baseline_hz=cal.receiver_baseline_hz,
        )
        knots = cal.correction.knots_hz
        penalty = float(
            0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
        )
        finals = []
        for arm in ("zero-c", "fitted-c"):
            completed = []
            for start_name in Hard60Configuration().final_starts:
                seed = np.asarray(association["initial_vector"]).copy()
                if start_name == "zero-timing":
                    seed[7:] = 0
                elif start_name == "own-continuation" and completed:
                    seed = np.asarray(min(completed, key=lambda row: row["objective"])["vector"])

                def fit_final(seed=seed, arm=arm):
                    fit, diagnostics = fit_bounded_position(
                        objective,
                        seed.copy(),
                        rf_arm=arm,
                        local_center=point,
                        local_radius_km=25,
                        slope_half_width_hz_s=60,
                        maximum_seconds=20,
                        maximum_iterations=600,
                    )
                    return dict(fit=fit, diagnostics=diagnostics)

                receipt = stage(f"recovered-final:{arm}:{start_name}", 20, fit_final)
                fit = receipt["result"]["fit"] if receipt["result"] else None
                if fit is not None:
                    if arm == "zero-c":
                        assert fit["vector"][6] == 0
                    completed.append(fit)
                finals.append(
                    dict(
                        basin=checkpoints["point_key"],
                        method="V16",
                        arm=arm,
                        start=start_name,
                        fit=fit,
                        reason=receipt["reason"],
                        calibration_penalty=penalty,
                        satellites=final_bank.numbers.tolist(),
                        association=association["selection"],
                    )
                )
        regions = ordinary_regions(read(HERE / "ordinary-winner-checkpoints.json"))
        for region in regions.values():
            for final in region["finals"]:
                final["satellites"] = bank.numbers[final.pop("satellite_indices")].tolist()
        before = regional_winners(regions)
        baseline_operational, baseline_attempts, baseline_reasons = run_joint_stages(
            observations,
            bank,
            prior,
            regions,
            lambda key, budget, operation: stage("baseline:" + key, budget, operation),
        )
        regions["recovered-ordinary-region"] = dict(
            calibrations={checkpoints["point_key"]: calibrated["result"]["calibration"]},
            finals=finals,
        )
        after = regional_winners(regions)
        operational, attempts, reasons = run_joint_stages(
            observations,
            bank,
            prior,
            regions,
            lambda key, budget, operation: stage("candidate:" + key, budget, operation),
        )
        write(
            HERE / "result.json",
            dict(
                protocol_sha256=digest,
                status="complete",
                prefit_selection=selection,
                regional_before=before,
                regional_after=after,
                baseline_operational=baseline_operational,
                baseline_attempts=baseline_attempts,
                baseline_reasons=baseline_reasons,
                recovered_finals=finals,
                operational=operational,
                attempts=attempts,
                reasons=reasons,
                scope="Original ordinary winner retained; score-selected region then unchanged B7",
            ),
        )
    except RegionalSliceExpired as error:
        print("pending", str(error), flush=True)


if __name__ == "__main__":
    main()
