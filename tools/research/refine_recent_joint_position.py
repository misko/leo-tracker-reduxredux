"""Refine training-selected modes while refreshing the full identity mixture.

All observations are restored, nominal states are propagated exactly once, and
every location reevaluates every region-compatible causal catalogue identity.
No reference position or previously matched identity is accepted as an input.
"""

# ruff: noqa: E402 -- bind numerical thread limits before NumPy/SciPy imports.

from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import importlib.util
import json
import resource
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
    ScoreConfig,
    centered_errors,
    logsumexp,
    score_states,
)
from leo.sky.propagation import parse_element_sets


def replay_module():
    path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("replay_regional_doppler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_acquisition(run):
    """Bind every seed-selecting input before reading numerical arrays."""
    seal = json.loads((run / "acquisition-seal.json").read_text())
    files = seal["files"]
    for name in (
        "result.json",
        "configuration.json",
        "history.json",
        "grid.npz",
        "accumulated.npz",
    ):
        if name not in files:
            raise ValueError("acquisition seal omits a required input")
    for name, expected in files.items():
        if Path(name).name != name or digest(run / name) != expected:
            raise ValueError("acquisition input seal mismatch")
    result = json.loads((run / "result.json").read_text())
    history = json.loads((run / "history.json").read_text())
    sessions = [row["session_id"] for row in history]
    if len(sessions) != len(set(sessions)) or len(sessions) != result["scan_count"]:
        raise ValueError("acquisition session accounting mismatch")
    if any(f"{session}.npz" not in files for session in sessions):
        raise ValueError("acquisition seal omits a session score map")
    if result.get("clock_s", 0) != 0 or result.get("altitude_m", 0) != 0:
        raise ValueError("this refinement requires zero clock offset and zero fixed altitude")
    return result, history, files


def refine_modes(training_score, seeds, region, *, max_evaluations=140):
    """Numerical orchestration receives training scores only, never evaluation values."""
    if max_evaluations < 4:
        raise ValueError("at least four objective evaluations required")
    bounds = [
        (-region.width_km / 2, region.width_km / 2),
        (-region.height_km / 2, region.height_km / 2),
    ]
    fits = []
    for seed in seeds:
        seed = np.asarray(seed, dtype=float)
        region.points([seed[0]], [seed[1]])
        simplex = np.tile(seed, (3, 1))
        for axis in range(2):
            direction = 10 if seed[axis] + 10 <= bounds[axis][1] else -10
            simplex[axis + 1, axis] += direction
        fit = minimize(
            lambda x: -float(training_score(x)),
            seed,
            method="Nelder-Mead",
            bounds=bounds,
            options={
                "maxfev": max_evaluations,
                "xatol": 0.02,
                "fatol": 1e-5,
                "initial_simplex": simplex,
            },
        )
        fits.append(
            {
                "east_km": float(fit.x[0]),
                "north_km": float(fit.x[1]),
                "training_score": -float(fit.fun),
                "converged": bool(fit.success),
                "evaluations": int(fit.nfev),
                "message": str(fit.message),
                "seed_east_north_km": seed.tolist(),
            }
        )
    if not fits:
        raise ValueError("at least one training-selected mode required")
    return fits


def posterior_at(arc, positions, velocities, grid, catalogue_size, config):
    """Identity probabilities conditional on this model; not calibrated correctness."""
    if len(positions) == 0:
        return np.empty(0), 1.0
    delta = positions - grid.ecef_km[0]
    distance = np.linalg.norm(delta, axis=-1)
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocities, axis=-1) / distance
    elevation = np.sum(delta * grid.up[0], axis=-1) / distance
    visible = np.min(elevation[:, arc.training], axis=-1) >= np.sin(
        np.deg2rad(config.minimum_elevation_deg)
    )
    train, _ = centered_errors(arc, prediction)
    null_train, _ = centered_errors(arc, np.zeros(len(arc.time_s)))
    n = config.effective_count
    candidate = (
        -0.5 * n * train / config.signal_sigma_hz**2
        - n * np.log(config.signal_sigma_hz)
        + np.log(config.signal_prior / catalogue_size)
    )
    candidate = np.where(visible, candidate, -np.inf)
    null = (
        -0.5 * n * null_train / config.null_sigma_hz**2
        - n * np.log(config.null_sigma_hz)
        + np.log1p(-config.signal_prior)
    )
    norm = np.logaddexp(logsumexp(candidate), null)
    return np.exp(candidate - norm), float(np.exp(null - norm))


def run(args):
    if (
        not 1 <= args.modes <= 12
        or not np.isfinite(args.budget_seconds)
        or args.budget_seconds <= 0
    ):
        raise ValueError("one to twelve modes and a positive finite time budget required")
    replay = replay_module()
    global_result, history, acquisition_files = verify_acquisition(args.run)
    if (
        not global_result.get("complete")
        or global_result.get("position_truth_used") is not False
        or global_result.get("prior_matched_norads_used", False)
    ):
        raise ValueError("completed blind acquisition required")
    if args.output.exists():
        raise ValueError("fresh output required")
    region = Region(**global_result["region"])
    config = ScoreConfig(**global_result["score"])
    inventory = json.loads((args.evidence / "inventory.json").read_text())
    if inventory.get("prior_matched_norads_used", False):
        raise ValueError("site-selected evidence is not allowed")
    if digest(args.evidence / "inventory.json") != global_result["inventory_digest"]:
        raise ValueError("acquisition evidence digest changed")
    sessions = [row["session_id"] for row in history]
    expected_sessions = {row["session_id"] for row in inventory["scans"] if row["included"]}
    if set(sessions) != expected_sessions:
        raise ValueError("acquisition does not cover the declared evidence inventory")
    if args.single_session:
        if args.single_session not in sessions:
            raise ValueError("single session is not in the acquisition")
        sessions = [args.single_session]
    with np.load(args.run / "grid.npz") as saved:
        grid_arrays = {key: saved[key] for key in saved.files}
    coarse_score = np.zeros(len(grid_arrays["east_km"]))
    cache, provenance = [], {}
    started = time.monotonic()

    def guard():
        if time.monotonic() - started > args.budget_seconds:
            raise TimeoutError("bounded refinement budget exhausted")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 1_800_000:
            raise MemoryError("refinement RSS exceeds 1.8GB")

    args.output.mkdir(parents=True)
    for session in sessions:
        guard()
        path = args.evidence / "evidence" / f"{session}.json"
        document = json.loads(path.read_text())
        authority = next(row for row in history if row["session_id"] == session)
        if digest(path) != authority["source_digest"]:
            raise ValueError("RF evidence changed after acquisition")
        metadata = document["inventory"]
        if metadata["tle_collected_ns"] >= metadata["reference_utc_ns"] - 5_000_000_000:
            raise ValueError("noncausal orbit input")
        if Path(metadata["tle_file"]).name != metadata["tle_file"]:
            raise ValueError("TLE must be an evidence-local basename")
        tle_path = path.parent / metadata["tle_file"]
        if digest(tle_path) != metadata["tle_digest"]:
            raise ValueError("orbit source digest changed")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, metadata["reference_utc_ns"], region
        )
        arcs = replay.load_observations(document, max_per_partition=0)
        evaluated_support = []
        for episode, arc in arcs:
            guard()
            p, v, retained = replay.state_arrays(
                catalogue, indices, metadata["reference_utc_ns"], arc.time_s
            )
            evaluated_norads = np.asarray(catalogue.satellite_numbers)[retained]
            evaluated_support.append(
                {
                    "episode_id": episode,
                    "evaluated_candidate_count": len(retained),
                    "propagation_or_radius_exclusion_count": len(indices) - len(retained),
                    "evaluated_norad_digest": "sha256:"
                    + hashlib.sha256(np.sort(evaluated_norads).astype("<i8").tobytes()).hexdigest(),
                }
            )
            cache.append(
                (
                    session,
                    episode,
                    arc,
                    p,
                    v,
                    evaluated_norads,
                    population,
                )
            )
        provenance[session] = {
            "rf_digest": digest(path),
            "tle_digest": digest(tle_path),
            "track_count": len(arcs),
            "full_catalogue_count": population,
            "regional_candidate_count": len(indices),
            "regional_prefilter_exclusion_count": population - len(indices),
            "evaluated_support": evaluated_support,
        }
        with np.load(args.run / f"{session}.npz") as archive:
            coarse_score += np.sum(archive["train_logbf"], axis=0)
        print(f"Cached {session}: {len(arcs)} full-observation tracks", flush=True)
    seeds = []
    for index in np.argsort(-coarse_score, kind="stable"):
        point = np.array([grid_arrays["east_km"][index], grid_arrays["north_km"][index]])
        if all(np.linalg.norm(point - previous) >= 200 for previous in seeds):
            seeds.append(point)
        if len(seeds) == args.modes:
            break
    evaluations = 0

    def score(point, details=False):
        nonlocal evaluations
        guard()
        grid = region.points([point[0]], [point[1]])
        total, heldout, rows = 0.0, 0.0, []
        for session, episode, arc, p, v, norads, population in cache:
            result = score_states(arc, p, v, grid, population, config)
            total += float(result["train_logbf"][0])
            heldout += float(result["heldout_logbf"][0])
            if details:
                weights, null = posterior_at(arc, p, v, grid, population, config)
                order = np.argsort(-weights)[:8]
                rows.append(
                    {
                        "session_id": session,
                        "episode_id": episode,
                        "observations": len(arc.time_s),
                        "null_weight": null,
                        "candidates": [
                            {"norad": int(norads[i]), "weight": float(weights[i])}
                            for i in order
                            if weights[i] > 0
                        ],
                        "omitted_identity_weight": float(1 - null - np.sum(weights[order])),
                        "training_score": float(result["train_logbf"][0]),
                        "heldout_score": float(result["heldout_logbf"][0]),
                    }
                )
        evaluations += 1
        with (args.output / "checkpoint.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "evaluation": evaluations,
                        "elapsed_s": time.monotonic() - started,
                        "east_km": float(point[0]),
                        "north_km": float(point[1]),
                        "training_score": total,
                    }
                )
                + "\n"
            )
        return (total, heldout, rows) if details else total

    fits = refine_modes(score, seeds, region, max_evaluations=args.max_evaluations)
    selected = max(fits, key=lambda fit: fit["training_score"])
    point = [selected["east_km"], selected["north_km"]]
    total, heldout, rows = score(point, details=True)
    latitude, longitude = region.coordinates(*point)
    result = {
        "complete": True,
        "scientific_status": "diagnostic; not calibrated uncertainty",
        "qualification": "diagnostic" if selected["converged"] else "insufficient-unconverged",
        "position_truth_used": False,
        "identity_refreshed_at_every_position": True,
        "nominal_exact_orbits": True,
        "geometry_pair_factor_used": False,
        "run": str(args.run),
        "source_result_digest": digest(args.run / "result.json"),
        "source_code_digest": digest(Path(__file__)),
        "replay_source_digest": digest(Path(replay.__file__)),
        "numerical_source_digest": digest(
            Path(__file__).parents[2] / "src/leo/analysis/research/regional_doppler.py"
        ),
        "acquisition_file_digests": acquisition_files,
        "provenance": provenance,
        "region": global_result["region"],
        "sessions": sessions,
        "fits": fits,
        "selected": selected,
        "latitude_deg": float(latitude),
        "longitude_deg": float(longitude),
        "training_score": total,
        "heldout_score": heldout,
        "tracks": rows,
        "track_count": len(cache),
        "observation_count": sum(len(row[2].time_s) for row in cache),
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
    (args.output / "result.json").write_text(payload)
    (args.output / "result.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
    print(json.dumps({key: result[key] for key in ("latitude_deg", "longitude_deg", "elapsed_s")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single-session")
    parser.add_argument("--modes", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=140)
    parser.add_argument("--budget-seconds", type=float, default=900)
    run(parser.parse_args())
