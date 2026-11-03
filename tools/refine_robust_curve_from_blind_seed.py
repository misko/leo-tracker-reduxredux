"""Matched local refinement from a previously sealed blind estimate, never GPS.

Both c arms receive the same earlier c=0 blind position and hardware seed. This
is explicitly a resumed search, not a new cold or globally converged result.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from evaluate_shared_satellite_phase import Experiment, protocol
from localize_merged_track_catalogue import distance_km

ROOT = Path(__file__).resolve().parents[1]


def run(case, partition, output, *, repaired, fitted_c, reference):
    recording = (
        ROOT
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
        / case
    )
    inputs = (
        ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs/DSX01-S01"
        if case.startswith("DSX")
        else Path("/tmp/ds22-shared-phase-bank-DS22-001")
    )
    seed_path = (
        ROOT
        / "reports/2026_10_17_shared_satellite_phase"
        / ("search_resumed" if case.startswith("DSX") else "search")
        / case
        / "shared_c0/fit.json"
    )
    seed_protocol = json.loads(seed_path.with_name("protocol.json").read_text())
    old = json.loads(seed_path.read_text())["endpoint"]
    experiment = Experiment(
        recording,
        inputs,
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    if seed_protocol["bank_receipt"]["bank_sha256"] != experiment.receipt["bank_sha256"]:
        raise ValueError("earlier blind estimate used a different causal sky")
    if seed_protocol["evaluation_position_used_in_search"]:
        raise ValueError("earlier seed was not blind to the evaluation position")
    original = load_tracks(recording)
    background = []
    partition_receipt = dict(
        original_points=sum(len(t["times"]) for t in original),
        curve_points=sum(len(t["times"]) for t in original),
        background_points=0,
    )
    if repaired:
        curves = json.loads((partition / "curves.json").read_text())
        for t in curves:
            t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
        background = json.loads((partition / "background.json").read_text())
        partition_receipt = experiment.set_observation_partition(
            curves, [r["observation_id"] for r in background]
        )
    common_seed = np.asarray(old["beta"][:8], float)
    common_seed[4:8] = np.clip(common_seed[4:8], -150, 150)
    # This public research configuration is an initializer, never an offset prior.
    experiment.initial = np.r_[common_seed, 0.0] if fitted_c else common_seed.copy()
    protocol(experiment, output, "resumed_shared_blind_seed_robust_partition", 16)
    center_lat, center_lon = experiment.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(center_lat))
    start = np.array(
        [(old["longitude_deg"] - center_lon) * scale, (old["latitude_deg"] - center_lat) * 111]
    )
    write(
        output / "population_protocol.json",
        dict(
            case=case,
            repaired=repaired,
            fitted_c=fitted_c,
            partition=partition_receipt,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            seed_fit_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            seed_protocol_sha256=hashlib.sha256(
                seed_path.with_name("protocol.json").read_bytes()
            ).hexdigest(),
            initial_east_north_km=start,
            common_hardware_seed=common_seed,
            seed_is_previous_blind_c0_fit=True,
            seed_uses_no_evaluation_position=True,
            initializer_is_not_calibration_truth=True,
            position_search_mode="resumed local",
            local_scales_km=[8, 2, 0.5, 0.125],
            maximum_sweeps_per_scale=2,
            local_location_budget=33,
            local_generated_seeds=8,
            exact_finalists=3,
            exact_generated_seeds=16,
            c0_fitted_c_same_initial_position_hardware_points_candidates_priors_and_budgets=True,
            no_linear_or_background_calibration=True,
            no_smoothed_measurements=True,
        ),
    )
    cache, trace = {}, []

    def evaluate(point):
        key = tuple(np.round(point, 9))
        if key not in cache:
            if len(cache) >= 33 or np.linalg.norm(point) > experiment.receipt["radius_km"]:
                return np.inf
            started = time.monotonic()
            fit = experiment.fit(
                center_lat + point[1] / 111, center_lon + point[0] / scale, 8, exact=False
            )
            cache[key] = fit
            trace.append(
                dict(
                    east_north_km=list(key),
                    score=fit["score"],
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            write(output / "progress.json", trace)
            if len(trace) % 8 == 0:
                print(
                    json.dumps(
                        dict(
                            stage="resumed_local",
                            locations=len(trace),
                            best=min(r["score"] for r in trace),
                        )
                    ),
                    flush=True,
                )
        return cache[key]["score"]

    point = start.copy()
    value = evaluate(point)
    for step in (8.0, 2.0, 0.5, 0.125):
        for _ in range(2):
            neighbors = [
                point + step * np.array(direction)
                for direction in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ]
            trial = min(neighbors, key=evaluate)
            proposed = evaluate(trial)
            if proposed >= value:
                break
            point, value = trial.copy(), proposed
    finalists = []
    for row in sorted(trace, key=lambda r: r["score"]):
        xy = np.asarray(row["east_north_km"])
        if all(np.linalg.norm(xy - np.asarray(r["east_north_km"])) >= 0.5 for r in finalists):
            fit = experiment.fit(
                center_lat + xy[1] / 111, center_lon + xy[0] / scale, 16, exact=True
            )
            finalists.append(dict(east_north_km=xy.tolist(), fit=fit))
            write(output / "finalists.json", finalists)
        if len(finalists) == 3:
            break
    best = min(finalists, key=lambda r: r["fit"]["score"])
    result = dict(
        endpoint=best["fit"],
        east_north_km=best["east_north_km"],
        initial_blind_seed_east_north_km=start,
        finalists=finalists,
        resumed_local_search=True,
        evaluation_position_used=False,
        global_optimum_proven=False,
        goal_complete=False,
    )
    write(output / "fit.json", result)
    fit_sha = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    association = population_association(experiment, best["fit"], original, background)
    write(output / "blind_association.json", association)
    # Evaluation is deliberately after saving the independent endpoint.
    error = distance_km((best["fit"]["latitude_deg"], best["fit"]["longitude_deg"]), reference)
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            within_0_5km=error < 0.5,
            fit_sha256=fit_sha,
            reference_used_only_after_fit=True,
            resumed_not_cold_search=True,
        ),
    )
    summary = dict(
        case=case,
        repaired=repaired,
        fitted_c=fitted_c,
        position_error_km=error,
        associated_points=association["compatible_points"],
        merged_tracks=association["merged_tracks"],
        background_points=len(background),
        locations=len(trace),
        score=best["fit"]["score"],
        resumed_not_cold=True,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DS22-001", "DSX01-S01"), required=True)
    p.add_argument("--partition", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repaired", action="store_true")
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--reference-latitude", type=float, required=True)
    p.add_argument("--reference-longitude", type=float, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(
        a.case,
        a.partition,
        a.output,
        repaired=a.repaired,
        fitted_c=a.fitted_c,
        reference=(a.reference_latitude, a.reference_longitude),
    )
