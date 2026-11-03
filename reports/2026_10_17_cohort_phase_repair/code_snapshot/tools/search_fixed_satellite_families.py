"""Exact-geometry local position searches on immutable blind curved families."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from localize_merged_track_catalogue import distance_km
from search_track_evidence_position import ROOT, prepare
from transfer_fixed_satellite_families import FixedFamilies


def locate(study, output):
    lat0, lon0 = study.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(lat0))
    seed = study.source_fit
    start = np.array([(seed["longitude_deg"] - lon0) * scale, (seed["latitude_deg"] - lat0) * 111])
    cache, trace = {}, []

    def evaluate(point):
        key = tuple(np.round(point, 9))
        if key not in cache:
            if len(cache) >= 73 or np.linalg.norm(point) > study.receipt["radius_km"]:
                return np.inf
            started = time.monotonic()
            fit = study.fit(lat0 + point[1] / 111, lon0 + point[0] / scale)
            cache[key] = fit
            trace.append(
                dict(
                    east_north_km=list(key),
                    score=fit["score"],
                    rms_hz=fit["detail"]["overall_rms_hz"],
                    compatible_curved_points=fit["detail"]["member_compatible_points"],
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            write(output / "progress.json", trace)
            if len(trace) % 8 == 0:
                print(
                    json.dumps(
                        dict(
                            stage="fixed_families",
                            locations=len(trace),
                            best_score=min(r["score"] for r in trace),
                        )
                    ),
                    flush=True,
                )
        return cache[key]["score"]

    grid = [start + np.array([x, y]) for x in (-16, 0, 16) for y in (-16, 0, 16)]
    point = min(grid, key=evaluate).copy()
    value = evaluate(point)
    for step in (8, 4, 2, 1, 0.5, 0.25, 0.125, 0.0625):
        for _ in range(2):
            neighbors = [point + step * np.array(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            trial = min(neighbors, key=evaluate)
            new = evaluate(trial)
            if new >= value:
                break
            point, value = trial.copy(), new
    key = min(cache, key=lambda k: cache[k]["score"])
    result = dict(
        endpoint=cache[key],
        east_north_km=list(key),
        locations=len(cache),
        evaluation_position_used_in_search=False,
        all_locations_exact_phase_geometry=True,
        labels_and_calibration_population_frozen=True,
        global_optimum_proven=False,
        resumed_local_not_cold=True,
    )
    write(output / "fit.json", result)
    return result


def run(case, fitted_c, merged, phase_floor, output):
    study = FixedFamilies(case, fitted_c, merged, phase_bound_floor_s=phase_floor)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            family_fit_source_sha256=hashlib.sha256(
                Path(__file__).with_name("transfer_fixed_satellite_families.py").read_bytes()
            ).hexdigest(),
            component_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/fixed_assignment_fit.py").read_bytes()
            ).hexdigest(),
            source_blind_fit_sha256=study.source_digest,
            source_blind_association_sha256=study.association_digest,
            observations_sha256=hashlib.sha256(
                json.dumps(study.observation_ids).encode()
            ).hexdigest(),
            case=case,
            fitted_c=fitted_c,
            merged=merged,
            calibration_points=len(study.observation_ids),
            candidate_norads=study.norads,
            fixed_labels=[study.norads[j] for j in study.labels],
            phase_bound_floor_s=phase_floor,
            phase_sigma_s=study.sigma,
            phase_bounds_s=study.bounds,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
            observation_ids_fixed=True,
            no_data_rejected_during_fitting=True,
            only_curved_members_calibrate=True,
            c0_fitted_c_same_common_c0_initialization=True,
            c0_fitted_c_same_points_candidates_priors_and_budgets=True,
            grid_offsets_km=[-16, 0, 16],
            scales_km=[8, 4, 2, 1, 0.5, 0.25, 0.125, 0.0625],
            maximum_sweeps=2,
            maximum_locations=73,
            two_initial_phase_proposals=True,
            nonlinear_iterations_per_proposal=6,
            tangent_updates=2,
            no_known_position_states_or_diagnostic_outputs_read=True,
            evaluation_position_used_in_search=False,
            gaussian_diagnostic_criterion_not_noise_gated_clutter_criterion=True,
            scores_across_merged_and_unmerged_not_directly_comparable=True,
        ),
    )
    started = time.monotonic()
    result = locate(study, output)
    digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    fit = result["endpoint"]
    # Evaluation enters only after saving an independent endpoint.
    error = distance_km(
        (fit["latitude_deg"], fit["longitude_deg"]), (37.849061591561885, -122.48574968092912)
    )
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            fit_sha256=digest,
            within_0_5km=error < 0.5,
            reference_used_only_after_fit=True,
            no_independent_satellite_identity_truth=True,
        ),
    )

    # Full-population association is a post-fit extension. It has no feedback
    # into fixed labels, constants, hardware, phases or position fitting.
    full, _, _, _, recording, background = prepare(case, fitted_c)
    phases = np.zeros(len(full.sky["norad"]))
    lookup = {int(n): j for j, n in enumerate(full.sky["norad"])}
    for n, p in zip(study.norads, fit["phases_s"], strict=True):
        phases[lookup[n]] = p
    complete_fit = dict(
        fit,
        phases_s=phases.tolist(),
        phase_norads=full.sky["norad"].tolist(),
        phase_bound_floor_s=phase_floor,
        unspecified_satellite_phases_zero=True,
    )
    write(output / "full_bank_fit.json", complete_fit)
    association = population_association(full, complete_fit, load_tracks(recording), background)
    write(output / "association.json", association)
    source_labels = {
        t["key"]: study.norads[study.labels[ci]]
        for ci, (_, members) in enumerate(study.groups)
        for t in members
    }
    relabelled = [
        r["component"]
        for r in association["association"]["rows"]
        if r["compatible"]
        and r["component"] in source_labels
        and r["candidate_norad"] != source_labels[r["component"]]
    ]
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        merged=merged,
        phase_bound_floor_s=phase_floor,
        position_error_km=error,
        score=fit["score"],
        rms_hz=fit["detail"]["overall_rms_hz"],
        fixed_curved_points=len(study.observation_ids),
        fixed_member_compatible_points=fit["detail"]["member_compatible_points"],
        fixed_family_compatible_points=fit["detail"]["family_compatible_points"],
        extended_associated_points=association["compatible_points"],
        merged_tracks=association["merged_tracks"],
        source_curved_fragments_relabelled_only_in_post_fit_extension=relabelled,
        original_graph_points=association["original_points"],
        locations=result["locations"],
        elapsed_seconds=time.monotonic() - started,
        independent_blind_search=True,
        not_a_fully_qualified_localization_result=True,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--merged", action="store_true")
    p.add_argument("--phase-bound-floor-s", type=float, default=0.0)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.merged, a.phase_bound_floor_s, a.output)
