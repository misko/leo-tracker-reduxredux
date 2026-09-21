#!/usr/bin/env python3
"""Run Gaussian offset-contrast/MAP-rate fits on sealed sparse density subsets."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from leo.analysis.research.gaussian_contrast_orbit_solver import (
    GaussianContrastOrbitConfig,
    GaussianContrastOrbitData,
    fit_gaussian_contrast_orbit,
)
from leo.analysis.research.regional_doppler import Region

FRACTIONS = {1 / 8, 1 / 16, 1 / 32}
STARTS = ([0.0, 0.0], [-3000.0, 0.0], [3000.0, 0.0])


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_inputs(job):
    config = job["config"]
    states_path = Path(config["prepared_states_npz"])
    if _hash(states_path) != config["prepared_states_hash"]:
        raise ValueError("prepared state hash mismatch")
    states = np.load(states_path)
    manifest_path = Path(config["manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    ids = np.asarray([row["observation_id"] for row in manifest["observations"]])
    data = GaussianContrastOrbitData(
        y_hz=states["y_hz"],
        training=states["training"],
        segment=states["segment"],
        track=states["track"],
        source=states["source"],
        age_h=states["age_h"],
        p_km=states["p_km"],
        v_km_s=states["v_km_s"],
        phase_p_minus_km=states["phase_p_minus_km"],
        phase_v_minus_km_s=states["phase_v_minus_km_s"],
        phase_p_plus_km=states["phase_p_plus_km"],
        phase_v_plus_km_s=states["phase_v_plus_km_s"],
        time_s=states["time_s"],
        observation_id=ids,
    )
    return data, ids, Region(**config["region"]), states_path, manifest_path


def run_job(job):
    started = time.monotonic()
    common = {
        "job_id": job["job_id"],
        "subset_id": job["subset_id"],
        "seed": job["subset"]["seed"],
        "fraction": job["subset"]["fraction"],
        "method": job["subset"]["method"],
        "starts": [],
    }
    try:
        data, ids, region, states_path, manifest_path = _load_inputs(job)
        selected = np.isin(ids, job["subset"]["fitting_ids"])
        fits = []
        config = GaussianContrastOrbitConfig()
        for start in STARTS:
            try:
                fit = fit_gaussian_contrast_orbit(
                    data, region, start, config, fitting_mask=selected
                )
                fits.append(fit)
                common["starts"].append(
                    {
                        "initial_x_km": start,
                        "converged": fit.converged,
                        "negative_log_posterior": fit.negative_log_posterior,
                        "nuisance_iterations": fit.nuisance_iterations,
                        "nuisance_backtracks": fit.nuisance_backtracks,
                        "nuisance_scaled_step": fit.nuisance_scaled_step,
                    }
                )
            except Exception as error:
                common["starts"].append(
                    {
                        "initial_x_km": start,
                        "failure": type(error).__name__,
                        "reason": str(error),
                    }
                )
        if not fits:
            return {**common, "status": "failed", "seconds": time.monotonic() - started}
        best = min(fits, key=lambda fit: fit.negative_log_posterior)
        return {
            **common,
            "status": "converged" if best.converged else "nonconverged",
            "fit": dataclasses.asdict(best),
            "fitting_observations": int(np.sum(selected & data.training)),
            "seconds": time.monotonic() - started,
            "provenance": {
                "states": str(states_path),
                "states_sha256": _hash(states_path),
                "manifest": str(manifest_path),
                "manifest_sha256": _hash(manifest_path),
            },
        }
    except Exception as error:
        return {
            **common,
            "status": "failed",
            "failure": type(error).__name__,
            "reason": str(error),
            "seconds": time.monotonic() - started,
        }


def _error_m(lat, lon, truth_lat, truth_lon):
    p1, p2 = math.radians(lat), math.radians(truth_lat)
    dp, dl = p2 - p1, math.radians(truth_lon - lon)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, a)))


def _finite(value):
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2, choices=(1, 2))
    parser.add_argument("--truth-latitude-deg", type=float, required=True)
    parser.add_argument("--truth-longitude-deg", type=float, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    jobs = [
        job
        for job in plan["jobs"]
        if job["model"] == "formal-orbit-correction-v6"
        and job["subset"]["method"] == "density"
        and job["subset"]["seed"] in (0, 1, 2)
        and job["subset"]["fraction"] in FRACTIONS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, job): job for job in jobs}
        rows = []
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(row["fraction"], row["seed"], row["status"], flush=True)
    # Coordinates remain sealed until every training-only inference result exists.
    for row in rows:
        fit = row.get("fit")
        if fit is not None:
            row["horizontal_error_m"] = _error_m(
                fit["latitude_deg"],
                fit["longitude_deg"],
                args.truth_latitude_deg,
                args.truth_longitude_deg,
            )
    payload = {
        "schema": "gaussian-contrast-map-rate-benchmark-v1",
        "plan": str(args.plan),
        "plan_sha256": _hash(args.plan),
        "solver_sha256": _hash(
            Path(__file__).parents[1]
            / "src/leo/analysis/research/gaussian_contrast_orbit_solver.py"
        ),
        "inference_scope": "offsets exactly marginalized; phase rates profiled by MAP",
        "truth_applied_after_all_inference": True,
        "truth": [args.truth_latitude_deg, args.truth_longitude_deg],
        "runs": sorted(rows, key=lambda row: (row["fraction"], row["seed"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(_finite(payload), indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
