#!/usr/bin/env python3
"""Iteration-3 DS1 prefix-6 joint global-tau/cache-rate local search.

This is intentionally a report-local development runner.  It starts from four
sealed, reference-free global-time results (two independent TRAIN groups by
the Sacramento and Reno priors), then re-evaluates hard associations from all
qualified observations at every geographic/tau point.  The cache-rate
surrogate ranks those points before one exact SGP4 audit per seed.  Reference
coordinates and post-seal errors are absent from this module by contract.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
JOINT = HERE / "joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")
SEEDS = ("reno", "sacramento")
LEVELS_KM = (6.25, 3.125, 1.5625, 0.78125)
BEAM_WIDTH = 2
TAU_HALF_WIDTH_S = 0.25
EXACT_FINALISTS_PER_SEED = 1


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    seal = path.with_suffix(".sha256")
    if not path.is_file() or not seal.is_file():
        raise ValueError(f"sealed source absent: {path}")
    if digest(path).removeprefix("sha256:") != seal.read_text().strip().removeprefix("sha256:"):
        raise ValueError(f"source seal mismatch: {path}")
    value = json.loads(path.read_text())
    if value.get("reference_used_for_fit") is not False:
        raise ValueError("source must attest reference exclusion")
    if value.get("partition") != "train":
        raise ValueError("source must be TRAIN-only")
    return value


def source_path(group: str, seed: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--{seed}--global_time.json"


def global_tau(document: dict[str, Any]) -> float:
    value = document.get("fitted_parameters", {}).get("timing", {}).get("global_tau_s")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("sealed source lacks finite global tau")
    return float(value)


def tau_stencil(tau: float) -> tuple[float, float, float]:
    """Small symmetric, predeclared local timing stencil around sealed tau."""
    answer = tuple(sorted({tau - TAU_HALF_WIDTH_S, tau, tau + TAU_HALF_WIDTH_S}))
    if answer[0] < -5.0 or answer[-1] > 5.0:
        raise ValueError("iteration-3 tau stencil exceeds cache support")
    return answer  # type: ignore[return-value]


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    fit = row["fit"]
    return {
        "east_km": row["east_km"],
        "north_km": row["north_km"],
        "latitude_deg": row["latitude_deg"],
        "longitude_deg": row["longitude_deg"],
        "tau_s": row["tau_s"],
        "selection_objective": fit["selection_objective"],
        "full_observation_capped_loss": fit["full_observation_capped_loss"],
        "null_rate_full_observation_capped_loss": fit["null_rate_full_observation_capped_loss"],
        "prior_penalty": fit["prior_penalty"],
        "rate_boundary_count": fit["rate_boundary_count"],
        "track_count": len(row["track_associations"]),
    }


def _rank(rows: list[dict[str, Any]], width: int, spacing: float) -> list[dict[str, Any]]:
    selected = []
    for row in sorted(
        rows,
        key=lambda item: (
            item["fit"]["selection_objective"],
            abs(item["tau_s"]),
            item["tau_s"],
            item["east_km"],
            item["north_km"],
        ),
    ):
        if all(
            np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"])
            >= spacing - 1e-12
            for old in selected
        ):
            selected.append(row)
        if len(selected) == width:
            break
    return selected


def _task_from_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration3-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def run_seed(group: str, seed: str) -> dict[str, Any]:
    """Run one independent seed; safe to execute in a process worker."""
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"iteration3_joint_{group}_{seed}")
    existing = load(RUNNER, f"iteration3_existing_{group}_{seed}")
    orbit = load(ORBIT, f"iteration3_orbit_{group}_{seed}")
    source_file = source_path(group, seed)
    source = sealed(source_file)
    engine = existing.FullObservationEngine(existing.validate_task(_task_from_source(source)))
    centre = source["estimated_position"]
    tau_values = tau_stencil(global_tau(source))
    cache: dict[tuple[float, float, float], dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []
    started = time.perf_counter()

    def score(east: float, north: float, tau: float) -> dict[str, Any]:
        key = (round(east, 9), round(north, 9), round(tau, 9))
        if key in cache:
            return cache[key]
        latitude, longitude = engine.search.offset_coordinate(
            (centre["latitude_deg"], centre["longitude_deg"]), east, north
        )
        row = joint.screen_point(engine, orbit, latitude, longitude, tau, reassign_once=False)
        row.update({"east_km": east, "north_km": north})
        cache[key] = row
        trace.append(_public_row(row))
        return row

    first = LEVELS_KM[0]
    beam = [
        score(east, north, tau)
        for east in (-first, 0.0, first)
        for north in (-first, 0.0, first)
        for tau in tau_values
    ]
    beam = _rank(beam, BEAM_WIDTH, first)
    for level in LEVELS_KM[1:]:
        expanded = list(beam)
        for parent in beam:
            for east_delta in (-level, 0.0, level):
                for north_delta in (-level, 0.0, level):
                    for tau in tau_values:
                        expanded.append(
                            score(
                                parent["east_km"] + east_delta,
                                parent["north_km"] + north_delta,
                                tau,
                            )
                        )
        beam = _rank(expanded, BEAM_WIDTH, level)
    finalists = _rank(list(cache.values()), EXACT_FINALISTS_PER_SEED, LEVELS_KM[-1])
    exact = []
    for finalist in finalists:
        compared = joint.exact_comparison(existing, orbit, engine, finalist)
        exact.append(
            {
                **_public_row(finalist),
                "exact_comparison": compared,
                "track_associations": finalist["track_associations"],
                "fit": finalist["fit"],
            }
        )
    winner = min(
        exact,
        key=lambda row: (
            row["exact_comparison"]["exact_full_observation_capped_loss"],
            abs(row["tau_s"]),
            row["tau_s"],
            row["east_km"],
            row["north_km"],
        ),
    )
    return {
        "task_id": "iteration3--train-" + group + "--prefix-6--" + seed,
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "all_qualified_observations_used": True,
        "source_global_time_artifact": str(source_file),
        "source_global_time_sha256": digest(source_file),
        "source_position": centre,
        "source_global_tau_s": global_tau(source),
        "tau_stencil_s": tau_values,
        "search_levels_km": LEVELS_KM,
        "beam_width": BEAM_WIDTH,
        "screened_point_count": len(cache),
        "screen_elapsed_s": time.perf_counter() - started,
        "screen_trace": trace,
        "exact_finalists": exact,
        "winner": winner,
        "cache_bindings": engine.bindings,
    }


def _run_case(task: tuple[str, str]) -> dict[str, Any]:
    return run_seed(*task)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("workers must be 1..4")
    if args.output.exists():
        raise FileExistsError(args.output)
    tasks = [(group, seed) for group in GROUPS for seed in SEEDS]
    begun = time.perf_counter()
    if args.workers == 1:
        results = [run_seed(*task) for task in tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            results = list(pool.map(_run_case, tasks, chunksize=1))
    payload = {
        "schema": "ds1-iteration3-joint-global-tau-cache-rate/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "inference_inputs": "sealed global-time artifacts only; no reference coordinate or masks",
        "association": "full-observation hard reassociation at every geographic/tau point",
        "rate_model": (
            "cached tau +/- 1 s Doppler sensitivity; one bounded causal phase rate per NORAD "
            "and analytic CFO per track"
        ),
        "exact_audit": "one deterministic exact SGP4 finalist per seed",
        "runtime_budget": {"target_under_s": 3600, "workers": args.workers},
        "elapsed_s": time.perf_counter() - begun,
        "results": results,
        "bindings": {
            "driver": digest(Path(__file__)),
            "joint_screen": digest(JOINT),
            "existing_runner": digest(RUNNER),
            "exact_orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_s": payload["elapsed_s"],
                "case_count": len(results),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
