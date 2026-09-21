"""Prespecified synthetic coverage characterization of the formal position fit.

This is model-checking with known synthetic truth, not a real-site accuracy
experiment. The misspecified scenario adds unmodelled per-track frequency drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.research.formal_orbit import (
    FormalOrbitConfig,
    FormalOrbitData,
    doppler_hz,
    fit_formal_orbit,
)
from leo.analysis.research.position_performance import summarize_trials
from leo.analysis.research.regional_doppler import Region


def synthetic_case(seed, misspecified=False, config=None):
    config = config or FormalOrbitConfig()
    rng = np.random.default_rng(seed)
    region = Region(35.0, -110.0, 80.0, 80.0)
    reference = region.points([0.0], [0.0]).ecef_km[0]
    truth = rng.uniform(-3, 3, 2)
    receiver = region.points([truth[0]], [truth[1]]).ecef_km[0]
    up = reference / np.linalg.norm(reference)
    east = np.cross([0.0, 0.0, 1.0], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    count, per_track = 12, 24
    p, v, tracks, sources, times, ages = [], [], [], [], [], []
    for track in range(count):
        azimuth = 2 * np.pi * track / count
        line = np.cos(azimuth) * east + np.sin(azimuth) * north
        tangent = -np.sin(azimuth) * east + np.cos(azimuth) * north
        dt = np.linspace(-30, 30, per_track)
        speed = 7.0 * tangent + 0.3 * line
        centre = reference + (600 + 40 * track) * up + 500 * line
        p.append(centre + dt[:, None] * speed)
        v.append(np.broadcast_to(speed, (per_track, 3)).copy())
        tracks.extend([track] * per_track)
        sources.extend([track % 6] * per_track)
        times.extend(dt)
        ages.extend([2.0 + track] * per_track)
    p, v = np.concatenate(p), np.concatenate(v)
    tracks, sources, times, ages = map(np.asarray, (tracks, sources, times, ages))
    step = config.phase_sensitivity_step_s
    pm, pp, vm, vp = p - step * v, p + step * v, v.copy(), v.copy()
    rates = rng.normal(0, config.phase_rate_sigma_s_h, 6)
    # Draw from the declared bounded prior instead of silently clipping atoms.
    while np.any(np.abs(rates) >= config.phase_rate_bound_s_h):
        bad = np.abs(rates) >= config.phase_rate_bound_s_h
        rates[bad] = rng.normal(0, config.phase_rate_sigma_s_h, np.sum(bad))
    y = doppler_hz(receiver, p + (ages * rates[sources])[:, None] * v, v)
    for track in range(count):
        idx = np.flatnonzero(tracks == track)
        innovations = rng.standard_t(config.robust_df, len(idx)) * config.measurement_sigma_hz
        noise = innovations.copy()
        for j in range(1, len(idx)):
            a = config.ar1_rho ** ((times[idx[j]] - times[idx[j - 1]]) / config.correlation_time_s)
            noise[j] = a * noise[j - 1] + np.sqrt(1 - a * a) * innovations[j]
        y[idx] += noise + rng.normal(0, 1000)
        if misspecified:
            y[idx] += rng.normal(0, 3.0) * times[idx]
    data = FormalOrbitData(
        y, np.ones(len(y), bool), tracks, tracks, sources, ages, p, v,
        pm, vm, pp, vp, times, np.asarray([f"synthetic-{i}" for i in range(len(y))]),
    )
    return data, region, truth


def run_trial(task):
    seed, misspecified, config_dict = task
    config = FormalOrbitConfig(**config_dict)
    data, region, truth = synthetic_case(seed, misspecified, config)
    started = time.monotonic()
    common = {"seed": seed, "scenario": "unmodelled_drift" if misspecified else "model_consistent"}
    try:
        fit = fit_formal_orbit(data, region, [0.0, 0.0], config)
        return {
            **common, "converged": bool(fit.converged),
            "error_km": (np.asarray(fit.x_km) - truth).tolist(),
            "covariance_km2": fit.position_covariance_km2,
            "fit": asdict(fit), "truth_x_km": truth.tolist(),
            "seconds": time.monotonic() - started,
        }
    except (ValueError, np.linalg.LinAlgError) as error:
        return {**common, "converged": False, "failure": str(error),
                "seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.trials < 1 or args.workers < 1:
        parser.error("positive trial/worker count required")
    args.output.mkdir(parents=True, exist_ok=False)
    config = asdict(FormalOrbitConfig())
    source = Path(__file__).read_bytes()
    protocol = {
        "config": config, "trials_per_scenario": args.trials,
        "seeds": list(range(args.trials)), "source_sha256": hashlib.sha256(source).hexdigest(),
        "model_source_sha256": hashlib.sha256(
            (Path(__file__).parents[1] / "src/leo/analysis/research/formal_orbit.py").read_bytes()
        ).hexdigest(),
        "interpretation": "Synthetic model checking; not measured real-world coverage",
    }
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    tasks = [(seed, bad, config) for bad in [False, True] for seed in range(args.trials)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = []
        for row in pool.map(run_trial, tasks):
            rows.append(row)
            if len(rows) % 20 == 0:
                print(f"Completed {len(rows)}/{len(tasks)} synthetic trials", flush=True)
    scenarios = ("model_consistent", "unmodelled_drift")
    summaries = {
        name: summarize_trials([r for r in rows if r["scenario"] == name]) for name in scenarios
    }
    output = {"protocol": protocol, "summaries": summaries, "trials": rows}
    # Identifiability condition numbers may be infinite; encode these as null.
    def finite(value):
        if isinstance(value, dict):
            return {key: finite(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [finite(item) for item in value]
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value
    (args.output / "results.json").write_text(
        json.dumps(finite(output), indent=2, allow_nan=False) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for name in scenarios:
        summary = summaries[name]
        rates = [
            summary["coverage"][str(level)]["conditional_coverage"] for level in [0.5, 0.9, 0.95]
        ]
        axes[0].plot([0.5, 0.9, 0.95], rates, marker="o", label=name.replace("_", " "))
        values = sorted(np.linalg.norm(r["error_km"]) * 1000 for r in rows
                        if r["scenario"] == name and r["converged"])
        if values:
            axes[1].plot(
                values, np.arange(1, len(values) + 1) / len(values), label=name.replace("_", " ")
            )
    axes[0].plot([0, 1], [0, 1], "k--", linewidth=1)
    axes[0].set(xlabel="Nominal region probability",
                ylabel="Measured coverage among scored regions", ylim=(0, 1.02))
    axes[1].axvline(1000, color="grey", linestyle="--")
    axes[1].set(xlabel="Synthetic horizontal error (m)",
                ylabel="Cumulative fraction of converged fits")
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    fig.suptitle("Synthetic uncertainty checks · conditional on declared model and geometry")
    fig.savefig(args.output / "coverage.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
