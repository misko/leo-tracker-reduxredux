"""Cold regional noise-gated association on a fixed DS22 five-scan pilot."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from audit_satellite_position_conflicts import OUTPUT, ROOT
from evaluate_robust_curve_reassociation import population_association
from localize_merged_track_catalogue import distance_km
from search_track_evidence_position import EvidenceExperiment

from leo.analysis.research.bounded_basin_search import bounded_basin_search


def run(case, fitted_c):
    entries = json.loads((OUTPUT / "frozen_inputs/manifest.json").read_text())
    entry = next(r for r in entries if r["case"] == case)
    recording, inputs = ROOT / entry["recording_path"], OUTPUT / "frozen_inputs" / case
    study = EvidenceExperiment(
        recording,
        inputs,
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1,
    )
    initial = study.initial[:8].copy()
    study.set_blind_seed(dict(beta=initial, phases_s=np.zeros(len(study.sigma))))
    arm = "fitted_c" if fitted_c else "c0"
    output = OUTPUT / "blind" / case / arm
    output.mkdir(parents=True, exist_ok=False)
    ids = sorted(
        oid for _, members in study.groups for track in members for oid in track["observation_ids"]
    )
    assert len(ids) == len(set(ids))
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            evidence_source_sha256=hashlib.sha256(
                Path(__file__).with_name("search_track_evidence_position.py").read_bytes()
            ).hexdigest(),
            basin_source_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/bounded_basin_search.py").read_bytes()
            ).hexdigest(),
            case=case,
            fitted_c=fitted_c,
            original_kind=entry["kind"],
            bank_receipt=study.receipt,
            recording_path=entry["recording_path"],
            observation_ids=ids,
            curved_calibration_fragments=len(study.groups),
            original_counts=entry["original_counts"],
            radio_only_initial_beta8=initial,
            initial_phase_s=0,
            same_points_candidate_bank_initializers_priors_and_caps_in_both_c_arms=True,
            no_known_position_fit_or_previous_geographic_endpoint_read=True,
            linear_fragments_never_estimate_or_rank_calibration=True,
            regional_center=study.receipt["regional_center"],
            radius_km=250,
            grid_spacing_km=125,
            basins=3,
            local_sweeps_per_scale=1,
            local_scales=10,
            maximum_discovery_locations=133,
            discovery_seed_budget=3,
            exact_finalists=3,
            finalist_seed_budget=8,
            exact_local_scales_km=[1, 0.25, 0.0625],
            exact_local_seed_budget=4,
            maximum_exact_local_evaluations=12,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
            common_phase_sigma_s=1,
            common_phase_bound_s=3,
            c_arms_are_controlled_but_prior_differs_from_earlier_successive_tle_001_studies=True,
            no_holdout_or_point_pruning=True,
            evaluation_position_used_in_search=False,
        ),
    )
    latitude, longitude = study.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(latitude))
    discovery, exact, trace = {}, {}, []
    started = time.monotonic()

    def evaluate(xy, final=False, budget=3):
        cache = exact if final else discovery
        key = tuple(np.round(xy, 9))
        if key not in cache:
            fit = study.fit(latitude + xy[1] / 111, longitude + xy[0] / scale, budget, exact=final)
            cache[key] = fit
            trace.append(
                dict(
                    east_north_km=list(key),
                    exact=final,
                    seed_budget=budget,
                    score=fit["score"],
                    compatible_curved_points=fit["compatible_curved_points"],
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            write(output / "progress.json", trace)
            if len(trace) % 12 == 0:
                print(
                    json.dumps(
                        dict(
                            case=case,
                            arm=arm,
                            locations=len(trace),
                            best_score=min(r["score"] for r in trace),
                        )
                    ),
                    flush=True,
                )
        return cache[key]["score"]

    search = bounded_basin_search(evaluate)
    write(output / "basins.json", search)
    for endpoint in search["endpoints"]:
        evaluate(np.asarray(endpoint["east_north_km"]), True, 8)
    current = np.asarray(min(exact, key=lambda k: exact[k]["score"]))
    for step in (1, 0.25, 0.0625):
        trials = [current + step * np.array(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        trials = [p for p in trials if np.linalg.norm(p) <= 250]
        for p in trials:
            evaluate(p, True, 4)
        current = np.asarray(min(exact, key=lambda k: exact[k]["score"]))
    fit = exact[tuple(np.round(current, 9))]
    write(
        output / "fit.json",
        dict(
            endpoint=fit,
            east_north_km=current,
            cold_regional_search=True,
            global_optimum_proven=False,
            discovery_locations=len(discovery),
            exact_locations=len(exact),
            evaluation_position_used_in_search=False,
        ),
    )
    # Geographic truth is read only after the independent endpoint is persisted.
    error = distance_km(
        (fit["latitude_deg"], fit["longitude_deg"]), (37.849061591561885, -122.48574968092912)
    )
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            fit_sha256=hashlib.sha256((output / "fit.json").read_bytes()).hexdigest(),
            reference_used_only_after_fit=True,
            within_0_5km=error < 0.5,
        ),
    )
    association = population_association(study, fit, load_tracks(recording), [])
    write(output / "association.json", association)
    summary = dict(
        case=case,
        kind=entry["kind"],
        fitted_c=fitted_c,
        position_error_km=error,
        associated_points=association["compatible_points"],
        raw_points=entry["original_counts"]["winning_points"],
        percent_raw=100
        * association["compatible_points"]
        / entry["original_counts"]["winning_points"],
        associated_fragments=association["compatible_fragments"],
        merged_tracks=association["merged_tracks"],
        points_per_merged_track=association["points_per_merged_track"],
        graph_points=association["original_points"],
        compatible_curved_points=fit["compatible_curved_points"],
        calibration_points=len(ids),
        score=fit["score"],
        discovery_locations=len(discovery),
        exact_locations=len(exact),
        elapsed_seconds=time.monotonic() - started,
        cold_not_global_optimum=True,
        no_independent_satellite_identity_truth=True,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--case",
        required=True,
        choices=["DS22-001", "DS22-034", "DS22-069", "DS22-102", "DS22-137"],
    )
    p.add_argument("--fitted-c", action="store_true")
    a = p.parse_args()
    run(a.case, a.fitted_c)
