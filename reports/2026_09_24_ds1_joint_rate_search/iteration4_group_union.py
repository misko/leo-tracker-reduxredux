#!/usr/bin/env python3
"""Iteration-4 seed-union exact selection for DS1 prefix-6 groups.

Inference consumes only the reference-free iteration-3 screen trace.  Reno
and Sacramento create candidates, neither votes for a winner.  A predeclared
top-eight surrogate union plus both iteration-3 finalists is recomputed from
the full observations and every retained coordinate is exact-SGP4 audited.
One result per group is selected solely by exact capped full-observation loss.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITERATION3 = HERE / "iteration3-results.json"
JOINT = HERE / "joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")
TOP_K = 8
WORKERS = 4


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


def coordinate_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        round(float(row["latitude_deg"]), 8),
        round(float(row["longitude_deg"]), 8),
        round(float(row["tau_s"]), 8),
    )


def source_path(group: str) -> Path:
    # Prefix membership is group-owned, so either reference-free seed supplies
    # the same full-observation engine contract.  The Reno artifact is a
    # deterministic engine source only; it does not participate in selection.
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration4-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def load_iteration3(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-3 inference contract is invalid")
    if len(value.get("results", [])) != 4:
        raise ValueError("iteration-3 four-seed matrix is incomplete")
    return value


def shortlist(iteration3: dict[str, Any], group: str) -> list[dict[str, Any]]:
    """Fixed surrogate top-K union, retaining both prior final locations."""
    relevant = [
        row
        for row in iteration3["results"]
        if row["task_id"].startswith(f"iteration3--train-{group}--")
    ]
    if len(relevant) != 2:
        raise ValueError(f"expected two iteration-3 seeds for {group}")
    all_trace = [point for seed in relevant for point in seed["screen_trace"]]
    ordered = sorted(
        all_trace,
        key=lambda row: (
            row["selection_objective"],
            abs(row["tau_s"]),
            row["tau_s"],
            row["latitude_deg"],
            row["longitude_deg"],
        ),
    )
    chosen: dict[tuple[float, float, float], dict[str, Any]] = {}
    for row in ordered:
        key = coordinate_key(row)
        if key not in chosen:
            chosen[key] = {**row, "selection_origin": "surrogate_top_k"}
        if len(chosen) == TOP_K:
            break
    for seed in relevant:
        winner = seed["winner"]
        key = coordinate_key(winner)
        chosen.setdefault(key, {**winner, "selection_origin": "iteration3_finalist"})
    return sorted(
        chosen.values(),
        key=lambda row: (
            row["selection_objective"],
            abs(row["tau_s"]),
            row["tau_s"],
            row["latitude_deg"],
            row["longitude_deg"],
        ),
    )


def audit_candidate(group: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """One self-contained cache recomputation and exact audit, fork-safe."""
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"iteration4_joint_{group}_{os.getpid()}")
    existing = load(RUNNER, f"iteration4_existing_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"iteration4_orbit_{group}_{os.getpid()}")
    source = json.loads(source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(source_task(source)))
    begun = time.perf_counter()
    screened = joint.screen_point(
        engine,
        orbit,
        candidate["latitude_deg"],
        candidate["longitude_deg"],
        candidate["tau_s"],
        reassign_once=False,
    )
    exact = joint.exact_comparison(existing, orbit, engine, screened)
    return {
        "group_id": group,
        "latitude_deg": screened["latitude_deg"],
        "longitude_deg": screened["longitude_deg"],
        "tau_s": screened["tau_s"],
        "selection_origin": candidate["selection_origin"],
        "iteration3_surrogate_objective": candidate["selection_objective"],
        "recomputed_surrogate_fit": screened["fit"],
        "track_associations": screened["track_associations"],
        "exact_comparison": exact,
        "elapsed_s": time.perf_counter() - begun,
        "cache_bindings": engine.bindings,
    }


def _audit_task(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return audit_candidate(*task)


def run_group(iteration3: dict[str, Any], group: str, workers: int) -> dict[str, Any]:
    candidates = shortlist(iteration3, group)
    tasks = [(group, candidate) for candidate in candidates]
    if workers == 1:
        audited = [_audit_task(task) for task in tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=min(workers, len(tasks)), mp_context=multiprocessing.get_context("fork")
        ) as pool:
            audited = list(pool.map(_audit_task, tasks, chunksize=1))
    winner = min(
        audited,
        key=lambda row: (
            row["exact_comparison"]["exact_full_observation_capped_loss"],
            abs(row["tau_s"]),
            row["tau_s"],
            row["latitude_deg"],
            row["longitude_deg"],
        ),
    )
    return {
        "group_id": group,
        "candidate_count": len(candidates),
        "predeclared_top_k": TOP_K,
        "selection": "exact full-observation capped loss only",
        "candidates": audited,
        "winner": winner,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration3", type=Path, default=ITERATION3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be 1..8")
    if args.output.exists():
        raise FileExistsError(args.output)
    iteration3 = load_iteration3(args.iteration3)
    begun = time.perf_counter()
    # Candidate audits are independent across both groups and intentionally
    # parallelized.  Each worker opens immutable caches and performs no writes.
    all_tasks = [
        (group, candidate) for group in GROUPS for candidate in shortlist(iteration3, group)
    ]
    if args.workers == 1:
        audited = [_audit_task(task) for task in all_tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            audited = list(pool.map(_audit_task, all_tasks, chunksize=1))
    results = []
    for group in GROUPS:
        group_candidates = [row for row in audited if row["group_id"] == group]
        winner = min(
            group_candidates,
            key=lambda row: (
                row["exact_comparison"]["exact_full_observation_capped_loss"],
                abs(row["tau_s"]),
                row["tau_s"],
                row["latitude_deg"],
                row["longitude_deg"],
            ),
        )
        results.append(
            {
                "group_id": group,
                "candidate_count": len(group_candidates),
                "predeclared_top_k": TOP_K,
                "selection": "exact full-observation capped loss only",
                "candidates": group_candidates,
                "winner": winner,
            }
        )
    payload = {
        "schema": "ds1-iteration4-prefix6-seed-union-exact/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "candidate_generation": (
            "reference-free Reno/Sacramento iteration-3 trace union; no seed-specific winner"
        ),
        "exact_selection": "exact full-observation capped loss only",
        "elapsed_s": time.perf_counter() - begun,
        "workers": args.workers,
        "iteration3_input": {"path": str(args.iteration3), "sha256": digest(args.iteration3)},
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
            {"output": str(args.output), "elapsed_s": payload["elapsed_s"], "groups": len(results)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
