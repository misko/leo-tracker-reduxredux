"""Matched cold-position and association checks with explicit radio-only clutter.

The evaluation GPS is used only after the blind fit is saved. Every original
point remains in the reported denominator; background observations are explicit.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from consolidate_shared_phase_matches import consolidate_tracks
from evaluate_shared_satellite_phase import Experiment, protocol
from localize_merged_track_catalogue import distance_km
from search_merged_track_position import regional_search

ROOT = Path(__file__).resolve().parents[1]


def locate(experiment, output):
    """A declared 13-point regional grid, one refined basin and three exact fits."""
    center_lat, center_lon = experiment.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(center_lat))
    progress = []

    def evaluate(point):
        started = time.monotonic()
        lat, lon = center_lat + point[1] / 111, center_lon + point[0] / scale
        fit = experiment.fit(lat, lon, 4, exact=False)
        progress.append(
            dict(
                east_north_km=np.asarray(point).tolist(),
                score=fit["score"],
                elapsed_seconds=time.monotonic() - started,
            )
        )
        write(output / "progress.json", progress)
        if len(progress) % 20 == 0:
            print(
                json.dumps(
                    dict(
                        stage="cold_search",
                        evaluations=len(progress),
                        best_score=min(r["score"] for r in progress),
                    )
                ),
                flush=True,
            )
        return fit["score"]

    coarse = regional_search(
        evaluate, radius=experiment.receipt["radius_km"], spacing=125.0, budget=100, basins=1
    )
    finalists = []
    for row in [coarse, *sorted(coarse["trace"], key=lambda r: r["score"])]:
        point = np.asarray(row["east_north_km"])
        if all(np.linalg.norm(point - np.asarray(r["east_north_km"])) >= 2 for r in finalists):
            lat, lon = center_lat + point[1] / 111, center_lon + point[0] / scale
            started = time.monotonic()
            fit = experiment.fit(lat, lon, 32, exact=True)
            finalists.append(
                dict(
                    east_north_km=point.tolist(),
                    fit=fit,
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            write(output / "finalists.json", finalists)
        if len(finalists) == 3:
            break
    winner = min(finalists, key=lambda r: r["fit"]["score"])
    result = dict(
        endpoint=winner["fit"],
        east_north_km=winner["east_north_km"],
        coarse_search=coarse,
        exact_finalists=finalists,
        global_optimum_proven=False,
        evaluation_position_used=False,
        generated_seeds_discovery=4,
        generated_seeds_exact=32,
    )
    write(output / "fit.json", result)
    return result


def population_association(experiment, fit, original_tracks, background):
    association = experiment.associate(fit)
    mapping = {t["key"]: t for t in experiment.tracks}
    original_ids = {oid for t in original_tracks for oid in t["observation_ids"]}
    associated = {
        oid
        for r in association["rows"]
        if r["compatible"]
        for oid in mapping[r["component"]]["observation_ids"]
    }
    background_ids = {r["observation_id"] for r in background}
    if associated & background_ids or not associated <= original_ids:
        raise ValueError("association changed the fixed original population")
    if len(associated) != association["compatible_points"]:
        raise ValueError("associated point count differs from original IDs")
    merged = consolidate_tracks(
        experiment.tracks,
        experiment.sky,
        fit,
        association,
        max_gap_s=30.0,
        check_joined_residual=True,
    )
    return dict(
        original_points=len(original_ids),
        curve_points=association["points"],
        background_points=len(background_ids),
        compatible_points=len(associated),
        compatible_fraction_of_original=len(associated) / len(original_ids),
        compatible_fragments=association["compatible_fragments"],
        merged_tracks=merged["output_tracks"],
        points_per_merged_track=len(associated) / max(1, merged["output_tracks"]),
        associated_observation_ids=sorted(associated),
        explicitly_background_observation_ids=sorted(background_ids),
        all_original_points_accounted_for=True,
        association=association,
        consolidated=merged,
    )


def run(case, partition, output, *, repaired, fitted_c, reference):
    recording = (
        ROOT
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
        / case
    )
    inputs = (
        ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs/DSX01-S01"
        if case == "DSX01-S01"
        else Path("/tmp/ds22-shared-phase-bank-DS22-001")
    )
    experiment = Experiment(
        recording,
        inputs,
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    original = load_tracks(recording)
    receipt = json.loads((partition / "receipt.json").read_text())
    if receipt["original_tracks_sha256"] != experiment.receipt["tracks_sha256"]:
        raise ValueError("partition does not bind original Graph tracks")
    background = []
    partition_receipt = dict(
        original_points=sum(len(t["times"]) for t in original),
        curve_points=sum(len(t["times"]) for t in original),
        background_points=0,
    )
    if repaired:
        if (
            hashlib.sha256((partition / "curves.json").read_bytes()).hexdigest()
            != receipt["curves_sha256"]
        ):
            raise ValueError("repaired curves changed")
        if (
            hashlib.sha256((partition / "background.json").read_bytes()).hexdigest()
            != receipt["background_sha256"]
        ):
            raise ValueError("explicit background changed")
        cores = json.loads((partition / "curves.json").read_text())
        for t in cores:
            t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
        background = json.loads((partition / "background.json").read_text())
        partition_receipt = experiment.set_observation_partition(
            cores, [r["observation_id"] for r in background]
        )
    protocol(experiment, output, "matched_robust_partition_cold_search", 32)
    write(
        output / "population_protocol.json",
        dict(
            case=case,
            repaired=repaired,
            fitted_c=fitted_c,
            partition=partition_receipt,
            partition_receipt_sha256=hashlib.sha256(
                (partition / "receipt.json").read_bytes()
            ).hexdigest(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            region_center=experiment.receipt["regional_center"],
            radius_km=250,
            regional_spacing_km=125,
            discovery_location_budget=100,
            refined_basins=1,
            exact_finalists=3,
            discovery_seed_budget=4,
            exact_seed_budget=32,
            background_always_counted_unassociated=True,
            no_measurement_values_smoothed=True,
            no_reference_position_or_truth_derived_identity_initialization=True,
            no_calibration_by_linear_or_background_fragments=True,
            c0_fitted_c_matched_population_candidates_priors_and_search_budgets=True,
            one_basin_bounded_search_not_globally_converged=True,
            frequency_scores_across_partitions_have_different_curvature_support=True,
        ),
    )
    started = time.monotonic()
    cold = locate(experiment, output)
    sealed_fit_sha = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    blind_association = population_association(experiment, cold["endpoint"], original, background)
    write(output / "blind_association.json", blind_association)
    position_error = distance_km(
        (cold["endpoint"]["latitude_deg"], cold["endpoint"]["longitude_deg"]), reference
    )
    # Only now use the reference coordinates, after the cold endpoint is saved.
    write(
        output / "evaluation.json",
        dict(
            position_error_km=position_error,
            within_0_5km=position_error < 0.5,
            fit_sha256=sealed_fit_sha,
            reference_used_only_after_cold_fit=True,
            not_a_global_convergence_claim=True,
        ),
    )
    known_fit = experiment.fit(reference[0], reference[1], 32, exact=True)
    known_association = population_association(experiment, known_fit, original, background)
    write(
        output / "fixed_site.json",
        dict(
            fit=known_fit,
            association=known_association,
            use="known-position frequency diagnostic only",
        ),
    )
    summary = dict(
        case=case,
        repaired=repaired,
        fitted_c=fitted_c,
        original_points=partition_receipt["original_points"],
        background_points=partition_receipt["background_points"],
        blind_position_error_km=position_error,
        blind_associated_points=blind_association["compatible_points"],
        blind_merged_tracks=blind_association["merged_tracks"],
        fixed_site_associated_points=known_association["compatible_points"],
        fixed_site_merged_tracks=known_association["merged_tracks"],
        elapsed_seconds=time.monotonic() - started,
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
