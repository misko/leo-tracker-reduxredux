#!/usr/bin/env python3
"""Prepare and run a truth-blind causal-geometry sparse position experiment."""
from __future__ import annotations

import argparse
import math
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
from benchmark_position_subsets import (
    _subset_metrics,
    atomic_write_result,
    canonical_hash,
    file_hash,
    read_json,
    run_plan,
    summarize_plan,
)

from leo.analysis.research.position_geometry_subsets import geometry_packet_order
from leo.analysis.research.position_subsets import Observation, PositionSubset
from leo.analysis.research.regional_doppler import Region


def prepare(source_plan: Path, output: Path, seeds=(0, 1, 2)):
    plan = read_json(source_plan)
    original = next(j for j in plan["jobs"] if j["model"] == "shape3-formal")
    manifest = read_json(Path(original["config"]["manifest_path"]))
    rows = tuple(Observation(**r) for r in manifest["observations"])
    by_id = {r.observation_id: r for r in rows}
    ids = np.asarray([r.observation_id for r in rows])
    states = np.load(original["config"]["prepared_states_npz"])
    if len(ids) != len(states["training"]):
        raise ValueError("manifest/state row mismatch")
    region = Region(**original["config"]["region"])
    axis = (-3000.0, 0.0, 3000.0)
    xx, yy = np.meshgrid(axis, axis)
    receiver_grid = region.points(xx.ravel(), yy.ravel()).ecef_km
    count = sum(r.fitting for r in rows)
    evaluation = tuple(sorted(r.observation_id for r in rows if not r.fitting))
    all_tracks = {r.track_id for r in rows if r.fitting}
    jobs = []
    root = Path(__file__).parents[1]
    for seed in seeds:
        order = geometry_packet_order(
            ids, states["training"], states["track"], states["time_s"], states["age_h"],
            states["p_km"], states["v_km_s"], states["phase_p_minus_km"],
            states["phase_v_minus_km_s"], states["phase_p_plus_km"],
            states["phase_v_plus_km_s"], receiver_grid, seed=seed, candidate_limit=9,
            max_count=math.floor(count/8))
        for fraction in (1/32, 1/16, 1/8):
            fitting_ids = tuple(sorted(order[:math.floor(count*fraction)]))
            tracks = {by_id[x].track_id for x in fitting_ids}
            subset = PositionSubset(
                "density", fraction, seed, fitting_ids, evaluation,
                tuple(x for x in evaluation if by_id[x].track_id not in tracks),
                tuple(sorted(all_tracks-tracks)), "geometry-fisher-packet3-v1")
            job = deepcopy(original)
            job.pop("job_id", None)
            job.update(
                model="geometry-fisher-formal", model_config={}, subset=asdict(subset),
                subset_id=subset.subset_id, subset_aliases=[],
                subset_metrics=_subset_metrics(subset, by_id, count),
                numerical_source_hash=file_hash(root/"src/leo/analysis/research/formal_orbit.py"),
                sampling_source_hash=file_hash(root/"src/leo/analysis/research/position_geometry_subsets.py"))
            job["job_id"] = canonical_hash(job)
            jobs.append(job)
    result = {
        "schema":"position-subset-plan-v1", "jobs":jobs,
        "manifest_hash":manifest["manifest_hash"],
        "config_hash":canonical_hash({"design":"geometry-fisher-packet3-v1", "seeds":list(seeds)}),
        "experiment":"causal-orbit-geometry-fisher",
        "selection_contract": {
            "responses_used": False, "truth_used": False, "future_tles_used": False,
            "receiver_grid_km": [[x,y] for y in axis for x in axis],
            "nuisance_projection": "per-track constant plus causal orbit-phase-rate direction",
        },
    }
    result["plan_hash"] = canonical_hash(result)
    atomic_write_result(output, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("prepare")
    q.add_argument("--source-plan", type=Path, required=True)
    q.add_argument("--output", type=Path, required=True)
    q.add_argument("--seed-count", type=int, default=3)
    q = sub.add_parser("run")
    q.add_argument("--plan", type=Path, required=True)
    q.add_argument("--result-dir", type=Path, required=True)
    q.add_argument("--workers", type=int, default=2)
    q = sub.add_parser("summarize")
    q.add_argument("--plan", type=Path, required=True)
    q.add_argument("--result-dir", type=Path, required=True)
    q.add_argument("--output", type=Path, required=True)
    q.add_argument("--figure", type=Path, required=True)
    q.add_argument("--truth-latitude-deg", type=float, required=True)
    q.add_argument("--truth-longitude-deg", type=float, required=True)
    a = p.parse_args()
    if a.command == "prepare":
        if not 1 <= a.seed_count <= 3:
            p.error("seed-count must be 1..3")
        prepare(a.source_plan, a.output, tuple(range(a.seed_count)))
    elif a.command == "run":
        run_plan(read_json(a.plan), "benchmark_position_subsets:formal_fixed_identity_adapter",
                 a.result_dir, a.workers)
    else:
        summarize_plan(read_json(a.plan), a.result_dir, a.output, a.figure,
                       a.truth_latitude_deg, a.truth_longitude_deg)


if __name__ == "__main__":
    main()
