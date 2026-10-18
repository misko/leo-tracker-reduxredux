"""Full-point regional grid and multiple-basin Doppler search, with no GPS seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, solve_bias, write
from localize_merged_track_catalogue import distance_km

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.track_catalogue_geometry import prepare_geometry, prepared_frequency


def regional_search(objective, *, radius=250.0, spacing=50.0, budget=250, basins=3):
    """Uniform disk coverage precedes data-ranked, separated basin refinement."""
    cache = {}

    def evaluate(point):
        point = np.asarray(point, float)
        key = tuple(np.round(point, 9))
        if np.linalg.norm(point) > radius + 1e-9:
            return np.inf
        if key not in cache:
            if len(cache) >= budget:
                return np.inf
            cache[key] = float(objective(point))
        return cache[key]

    axis = np.arange(-radius, radius + spacing * 0.5, spacing)
    seeds = [
        np.array([x, y]) for x in axis for y in axis if x * x + y * y <= radius * radius + 1e-9
    ]
    seeds.sort(key=lambda p: (float(p @ p), float(p[0]), float(p[1])))
    if len(seeds) >= budget:
        raise ValueError("budget must cover regional grid and leave refinement work")
    for point in seeds:
        evaluate(point)
    chosen = []
    for point in sorted(seeds, key=evaluate):
        if all(np.linalg.norm(point - old) >= 1.5 * spacing for old in chosen):
            chosen.append(point.copy())
        if len(chosen) == basins:
            break
    endpoints = []
    for number, start in enumerate(chosen):
        point = start.copy()
        value = evaluate(point)
        allowance = 80 if number == 0 else 44
        before = len(cache)
        minimum_scale_reached = False
        for step in (25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125, 0.09765625):
            while len(cache) - before < allowance and len(cache) < budget:
                neighbors = [point + step * np.array(v) for v in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                trial = min(neighbors, key=evaluate)
                candidate = evaluate(trial)
                if candidate >= value:
                    if step == 0.09765625:
                        minimum_scale_reached = True
                    break
                point, value = trial.copy(), candidate
            if len(cache) - before >= allowance or len(cache) >= budget:
                break
        endpoints.append(
            dict(
                east_north_km=point.tolist(),
                score=value,
                start=start.tolist(),
                new_evaluations=len(cache) - before,
                minimum_scale_stationary=minimum_scale_reached,
            )
        )
    best = min(endpoints, key=lambda r: r["score"])
    return dict(
        **best,
        coarse_evaluations=len(seeds),
        evaluations=len(cache),
        basins=endpoints,
        trace=[dict(east_north_km=list(p), score=v) for p, v in cache.items()],
    )


def run(recording, inputs, output, fitted_c, *, grouping="merged"):
    started = time.monotonic()
    receipt = json.loads((inputs / "receipt.json").read_text())
    if hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest() != receipt["bank_sha256"]:
        raise ValueError("orbit bank changed")
    if (
        hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest()
        != receipt["tracks_sha256"]
    ):
        raise ValueError("track population changed")
    with np.load(inputs / "bank.npz") as archive:
        sky = {k: archive[k] for k in archive.files}
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    groups = {}
    for track in tracks:
        key = merged["result"]["ownership"][track["key"]] if grouping == "merged" else track["key"]
        groups.setdefault(key, []).append(track)
    groups = sorted(groups.items())
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    mark = time.monotonic()
    geometry = prepare_geometry(sky, times)
    preparation_seconds = time.monotonic() - mark
    center_lat, center_lon = receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(center_lat))
    initial = np.array(merged["calibration"]["beta"])
    if fitted_c:
        initial = np.r_[initial, 0.0]
    output.mkdir(parents=True, exist_ok=False)
    sources = [
        Path(__file__),
        Path(matching.__file__),
        Path(__file__).with_name("associate_merged_track_catalogue.py"),
        Path(__file__).resolve().parents[1]
        / "src/leo/analysis/research/track_catalogue_geometry.py",
        Path(__file__).resolve().parents[1]
        / "src/leo/analysis/research/component_frequency_bias.py",
    ]
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    write(
        output / "protocol.json",
        dict(
            source_sha256=source_hashes,
            regional_spacing_km=50,
            geographic_budget=250,
            basins=3,
            all_original_points=True,
            grouping=grouping,
            discovery_seed_budget=4,
            final_seed_budget=160,
            fitted_c=fitted_c,
            bias_sigma_hz=1000,
            evaluation_position_used=False,
            region=receipt["regional_center"],
            bank_sha256=receipt["bank_sha256"],
            tracks_sha256=receipt["tracks_sha256"],
            merged_sha256=hashlib.sha256((recording / "merged.json").read_bytes()).hexdigest(),
        ),
    )
    progress = []
    details = {}

    def objective(point, final=False):
        lat = center_lat + point[1] / 111.0
        lon = center_lon + point[0] / scale
        mark = time.monotonic()
        frequency, elevation = prepared_frequency(geometry, lat, lon)
        geometry_seconds = time.monotonic() - mark
        bank = dict(time_s=times, doppler_0=frequency, elevation_deg=elevation, norad=sky["norad"])
        stats = matching.statistics(groups, bank, {str(t["channel"]): 0.0 for t in tracks})
        mark = time.monotonic()
        beta, ranks = solve_bias(stats, initial, 1000.0, 160 if final else 4)
        solve_seconds = time.monotonic() - mark
        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
        active = np.flatnonzero(stats["active"])
        score = float(
            np.sum(
                np.minimum(stats["count"][active], 50)
                * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
            )
        )
        score += 150.0**2 * float(np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2))
        key = tuple(np.round(point, 9))
        details[key] = dict(
            latitude_deg=lat,
            longitude_deg=lon,
            beta=beta.tolist(),
            candidate_norads=[int(sky["norad"][v]) for v in terms.best],
            rms_hz=terms.rms_hz.tolist(),
            calibration_ranks=ranks,
            score=score,
        )
        progress.append(
            dict(
                east_north_km=list(point),
                score=score,
                final=final,
                geometry_seconds=geometry_seconds,
                solve_seconds=solve_seconds,
            )
        )
        write(output / "progress.json", progress)
        if len(progress) % 20 == 0:
            print(
                json.dumps(dict(evaluations=len(progress), best=min(r["score"] for r in progress))),
                flush=True,
            )
        return score

    result = regional_search(objective, radius=receipt["radius_km"])
    finalists = []
    # Preserve each basin representative, then add distinct strong alternatives.
    proposals = result["basins"] + sorted(result["trace"], key=lambda r: r["score"])
    for row in proposals:
        point = np.array(row["east_north_km"])
        if all(np.linalg.norm(point - np.array(old["east_north_km"])) >= 0.2 for old in finalists):
            finalists.append(dict(east_north_km=point.tolist(), score=objective(point, final=True)))
        if len(finalists) == 8:
            break
    best = min(finalists, key=lambda r: r["score"])
    result.update(
        east_north_km=best["east_north_km"],
        score=best["score"],
        finalists=finalists,
        endpoint=details[tuple(np.round(best["east_north_km"], 9))],
        source_id=receipt["source_id"],
        fitted_c=fitted_c,
        grouping=grouping,
        points=sum(len(t["times"]) for t in tracks),
        geometry_preparation_seconds=preparation_seconds,
        elapsed_seconds=time.monotonic() - started,
        bank_sha256=receipt["bank_sha256"],
        tracks_sha256=receipt["tracks_sha256"],
        global_optimum_proven=False,
        goal_complete=False,
    )
    write(output / "fit.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fit-rf-c", action="store_true")
    p.add_argument("--grouping", choices=("merged", "fragments"), default="merged")
    p.add_argument("--evaluation-latitude", type=float, required=True)
    p.add_argument("--evaluation-longitude", type=float, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    fit = run(a.recording, a.inputs, a.output, a.fit_rf_c, grouping=a.grouping)
    endpoint = fit["endpoint"]
    error = distance_km(
        (endpoint["latitude_deg"], endpoint["longitude_deg"]),
        (a.evaluation_latitude, a.evaluation_longitude),
    )
    evaluation = dict(
        position_error_km=error,
        within_0_5km=error < 0.5,
        fit_sha256=hashlib.sha256((a.output / "fit.json").read_bytes()).hexdigest(),
        reference_used_only_after_fit=True,
        goal_complete=False,
    )
    write(a.output / "evaluation.json", evaluation)
    print(json.dumps(evaluation), flush=True)
