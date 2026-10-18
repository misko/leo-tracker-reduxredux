"""Bounded cold regional search using merged-component catalogue scores.

The search function receives no evaluation coordinate. The declared region is
read from the independently prepared orbit bank. Evaluation is written only
after the fitted endpoint has been saved. This is an experimental composite
score, not a qualified posterior or a globally converged localization engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, solve_bias, write

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.track_catalogue_geometry import frequency_grid


def pattern_search(objective, *, radius_km=250.0, budget=65):
    """Fixed regional seeds and two axial sweeps per declared refinement scale."""
    cache = {}

    def evaluate(point):
        point = np.asarray(point, float)
        if np.linalg.norm(point) > radius_km:
            return np.inf
        key = tuple(np.round(point, 8))
        if key not in cache and len(cache) >= budget:
            return np.inf
        if key not in cache:
            cache[key] = float(objective(point))
        return cache[key]

    seeds = [np.array([x, y]) for x in (-100.0, 0.0, 100.0) for y in (-100.0, 0.0, 100.0)]
    point = min(seeds, key=evaluate).copy()
    score = evaluate(point)
    last_scale = None
    for scale in (64.0, 16.0, 4.0, 1.0, 0.25, 0.125):
        for _ in range(2):
            candidates = [
                point + scale * np.array(direction)
                for direction in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ]
            trial = min(candidates, key=evaluate)
            trial_score = evaluate(trial)
            if trial_score >= score:
                break
            point, score = trial, trial_score
        last_scale = scale
        if len(cache) >= budget:
            break
    return dict(
        east_north_km=point.tolist(),
        score=score,
        evaluations=len(cache),
        last_search_scale_km=last_scale,
        trace=[dict(east_north_km=list(p), score=s) for p, s in cache.items()],
    )


def discovery_subset(groups, maximum_points=8):
    """Actual time-spread observations for discovery, never interpolated marks."""
    result = []
    for key, members in groups:
        subset = []
        for track in members:
            times = track["times"]
            index = np.unique(
                np.searchsorted(
                    times, np.linspace(times[0], times[-1], min(maximum_points, len(times)))
                )
            )
            selected = dict(track, times=times[index], values=track["values"][index])
            if "observation_ids" in track:
                selected["observation_ids"] = [track["observation_ids"][j] for j in index]
            subset.append(selected)
        result.append((key, subset))
    return result


def raw_curvature(track):
    t, y = track["times"], track["values"]
    x = t - t.mean()
    centered = y - y.mean()
    residual = centered - x * (centered @ x) / max(x @ x, 1e-12)
    return bool(np.ptp(t) >= 20 and np.sqrt(np.mean(residual**2)) >= 250)


def estimate(recording, inputs, output, *, fitted_c, bias_sigma_hz=1000.0, geo_budget=65):
    receipt = json.loads((inputs / "receipt.json").read_text())
    if hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest() != receipt["bank_sha256"]:
        raise ValueError("orbit bank digest changed")
    if (
        hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest()
        != receipt["tracks_sha256"]
    ):
        raise ValueError("track population changed")
    with np.load(inputs / "bank.npz") as archive:
        sky = {key: archive[key] for key in archive.files}
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    groups = {}
    for track in tracks:
        owner = merged["result"]["ownership"][track["key"]]
        groups.setdefault(owner, []).append(track)
    groups = sorted(groups.items())
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    subsets = discovery_subset(groups)
    subset_times = np.unique(
        np.concatenate([t["times"] for _, members in subsets for t in members])
    )
    fragment_curvature = np.array([raw_curvature(t) for _, members in groups for t in members])
    component_curvature = np.array(
        [any(raw_curvature(t) for t in members) for _, members in groups]
    )
    center_lat, center_lon = receipt["regional_center"]
    longitude_scale = 111.32 * np.cos(np.deg2rad(center_lat))
    initial = np.asarray(merged["calibration"]["beta"])
    if fitted_c:
        initial = np.r_[initial, 0.0]
    details = {}
    progress = []
    output.mkdir(parents=True, exist_ok=False)
    sources = [
        Path(__file__),
        Path(__file__).with_name("associate_merged_track_catalogue.py"),
        Path(matching.__file__),
    ]
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    write(
        output / "protocol.json",
        dict(
            source_sha256=source_hashes,
            discovery_points_per_fragment=8,
            discovery_seed_budget=4,
            full_data_seed_budget=160,
            full_data_locations=4,
            region_center=receipt["regional_center"],
            evaluation_position_used_in_search=False,
        ),
    )

    def objective(east_north, full=False):
        latitude = center_lat + east_north[1] / 111.0
        longitude = center_lon + east_north[0] / longitude_scale
        requested = times if full else subset_times
        selected = groups if full else subsets
        frequency, elevation = frequency_grid(sky, requested, latitude, longitude)
        bank = dict(
            time_s=requested, doppler_0=frequency, elevation_deg=elevation, norad=sky["norad"]
        )
        stats = matching.statistics(selected, bank, {str(t["channel"]): 0.0 for t in tracks})
        stats["active"] = component_curvature.copy()
        stats["fragment_active"] = fragment_curvature.copy()
        beta, ranks = solve_bias(stats, initial, bias_sigma_hz, budget=160 if full else 4)
        terms = profile_component_bias(stats, beta, bias_sigma_hz=bias_sigma_hz)
        active = np.flatnonzero(stats["active"])
        if not len(active):
            raise ValueError("no measured curved component supports a position search")
        score = float(
            np.sum(
                np.minimum(stats["count"][active], 50)
                * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
            )
        )
        score += 150.0**2 * float(np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2))
        key = tuple(np.round(east_north, 8))
        details[key] = dict(
            latitude_deg=latitude,
            longitude_deg=longitude,
            beta=beta.tolist(),
            curved_components=len(active),
            calibration_ranks=ranks,
            candidate_norads=[int(sky["norad"][s]) for s in terms.best],
            component_rms_hz=terms.rms_hz.tolist(),
        )
        progress.append(dict(east_north_km=list(east_north), score=score, full_data=full))
        write(output / "progress.json", progress)
        return score

    result = pattern_search(objective, radius_km=receipt["radius_km"], budget=geo_budget)
    result["proxy_search_score"] = result["score"]
    finalists = sorted(result["trace"], key=lambda r: r["score"])[:4]
    full_results = [
        dict(east_north_km=row["east_north_km"], score=objective(row["east_north_km"], full=True))
        for row in finalists
    ]
    best = min(full_results, key=lambda r: r["score"])
    result["east_north_km"] = best["east_north_km"]
    result["score"] = best["score"]
    result["full_data_finalists"] = full_results
    endpoint = details[tuple(np.round(best["east_north_km"], 8))]
    result.update(
        endpoint=endpoint,
        source_id=receipt["source_id"],
        fitted_c=fitted_c,
        position_initialization="fixed regional grid, independent of evaluation GPS",
        region_center=[center_lat, center_lon],
        region_radius_km=receipt["radius_km"],
        component_bias_sigma_hz=bias_sigma_hz,
        discovery_seed_budget_per_geography=4,
        full_data_seed_budget_per_geography=160,
        discovery_points=sum(len(t["times"]) for _, members in subsets for t in members),
        full_data_location_evaluations=len(full_results),
        geography_evaluation_budget=geo_budget,
        graph_points=sum(len(t["times"]) for t in tracks),
        geometry_uses_fixed_site_associations=False,
        global_optimum_proven=False,
        qualified_local_convergence=False,
        position_target_verified=False,
    )
    result["source_sha256"] = source_hashes
    result["orbit_bank_sha256"] = receipt["bank_sha256"]
    result["tracks_sha256"] = receipt["tracks_sha256"]
    write(output / "fit.json", result)
    return result


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = np.deg2rad([*a, *b])
    h = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fit-rf-c", action="store_true")
    parser.add_argument("--component-bias-sigma-hz", type=float, default=1000.0)
    parser.add_argument("--evaluation-latitude", required=True, type=float)
    parser.add_argument("--evaluation-longitude", required=True, type=float)
    args = parser.parse_args()
    protected = Path("/mnt/qnap01")
    if args.output.resolve() == protected or protected in args.output.resolve().parents:
        parser.error("QNAP is read-only")
    result = estimate(
        args.recording,
        args.inputs,
        args.output,
        fitted_c=args.fit_rf_c,
        bias_sigma_hz=args.component_bias_sigma_hz,
    )
    # The endpoint is already frozen before the evaluation reference is consumed.
    endpoint = result["endpoint"]
    error = distance_km(
        (endpoint["latitude_deg"], endpoint["longitude_deg"]),
        (args.evaluation_latitude, args.evaluation_longitude),
    )
    diagnostic = dict(
        position_error_km=error,
        within_0_5km=error < 0.5,
        fit_sha256=hashlib.sha256((args.output / "fit.json").read_bytes()).hexdigest(),
        evaluation_position=[args.evaluation_latitude, args.evaluation_longitude],
        end_to_end_target_verified=False,
        scope="one predeclared experimental pilot",
    )
    write(args.output / "evaluation.json", diagnostic)
    print(json.dumps(diagnostic), flush=True)
