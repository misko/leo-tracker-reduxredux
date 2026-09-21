#!/usr/bin/env python3
"""Freeze a four-factor model ablation and a nested 1/8..1/32 data extension.

Run with benchmark_position_subsets.py; all variants retain identical causal
states, fixed identities, observation splits, priors and external starts.
This planner accepts no evaluation coordinate and never selects by accuracy.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

from benchmark_position_subsets import atomic_write_result, plan_jobs, read_json

from leo.analysis.research.position_subsets import canonical_hash


def factorial_models():
    models = []
    for orbit, correlation, robust, scale in itertools.product((False, True), repeat=4):
        settings = {
            "phase_rate_bound_s_h": 0.25 if orbit else 0.0,
            "ar1_rho": 0.65 if correlation else 0.0,
            "gaussian_noise": not robust,
            "infer_measurement_sigma": scale,
        }
        name = (
            f"orbit{int(orbit)}-correlation{int(correlation)}-robust{int(robust)}-scale{int(scale)}"
        )
        models.append({"name": name, "formal_orbit_config": settings})
    return models


def prepare(base_config, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    manifest = read_json(Path(base_config["manifest_path"]))
    for label, models, fractions in (
        ("factorial", factorial_models(), [1.0]),
        (
            "small-data",
            [{"name": "formal-orbit-correction-v6"}, {"name": "legacy-strict-fixed-orbit"}],
            [1 / 32, 1 / 16, 1 / 8, 1.0],
        ),
    ):
        config = {**base_config, "models": models, "fractions": fractions}
        jobs = plan_jobs(manifest, config)
        # Duration-prefix variants are a different experiment. Retain a single
        # complete-data membership and the paired seeded density/pass subsets.
        jobs = [job for job in jobs if job["subset"]["method"] != "duration"]
        plan = {
            "schema": "position-subset-plan-v1",
            "manifest_hash": manifest["manifest_hash"],
            "config_hash": canonical_hash(config),
            "jobs": jobs,
        }
        plan["plan_hash"] = canonical_hash(plan)
        atomic_write_result(output / f"{label}-config.json", config)
        atomic_write_result(output / f"{label}-plan.json", plan)
        print(label, len(jobs), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(read_json(args.config), args.output)
