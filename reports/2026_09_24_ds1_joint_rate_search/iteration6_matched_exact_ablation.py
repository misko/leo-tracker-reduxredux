#!/usr/bin/env python3
"""Iteration-6 matched cap-300 proposal / cap-800 exact-rank ablation.

This consumes the completed iteration-5 scan rows.  It does not rescan the
geographic or timing grid: for every group and fixed tau it retains the three
lowest *converged* cap-300 proposal rows, deduplicates that union, and adds the
iteration-4 exact winner at its original tau when necessary.  Every retained
row receives a fresh full-observation hard association and an exact SGP4 audit.
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
ITER5 = HERE / "iteration5-results.json"
ITER4 = HERE / "iteration4-results.json"
JOINT = HERE / "joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")
TOP_PER_TAU = 3


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
    return tuple(round(float(row[key]), 8) for key in ("latitude_deg", "longitude_deg", "tau_s"))  # type: ignore[return-value]


def proposal_key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(row["fit"]["selection_objective"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
        float(row["latitude_deg"]),
        float(row["longitude_deg"]),
    )


def source_path(group: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration6-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def load_iteration5(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-5 inference contract is invalid")
    if set(value.get("tau_grid_s", ())) != {
        -2.25,
        -2.0,
        -1.75,
        -1.5,
        -1.25,
        -1.0,
        -0.75,
        -0.5,
        -0.25,
    }:
        raise ValueError("unexpected fixed tau grid")
    for group in GROUPS:
        rows = [
            row
            for scan in value["spatial_scans"]
            if scan["group_id"] == group
            for row in scan["rows"]
        ]
        if not rows or not all(row["fit"]["converged"] for row in rows):
            raise ValueError(f"iteration-5 rows are incomplete or unconverged: {group}")
    return value


def iteration4_winner(iter4: dict[str, Any], group: str) -> dict[str, Any]:
    if iter4.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-4 inference contract is invalid")
    return next(row["winner"] for row in iter4["results"] if row["group_id"] == group)


def shortlist(iter5: dict[str, Any], iter4: dict[str, Any], group: str) -> list[dict[str, Any]]:
    """Return the predeclared, proposal-ranked exact audit union."""
    rows = [
        row
        for scan in iter5["spatial_scans"]
        if scan["group_id"] == group
        for row in scan["rows"]
        if row["fit"]["converged"]
    ]
    taus = tuple(iter5["tau_grid_s"])
    chosen: dict[tuple[float, float, float], dict[str, Any]] = {}
    for tau in taus:
        for rank, row in enumerate(
            sorted((row for row in rows if row["tau_s"] == tau), key=proposal_key)[:TOP_PER_TAU],
            start=1,
        ):
            key = coordinate_key(row)
            chosen.setdefault(
                key, {**row, "proposal_rank_at_tau": rank, "selection_origin": "cap300_tau_top3"}
            )
    winner = iteration4_winner(iter4, group)
    key = coordinate_key(winner)
    if key not in chosen:
        matched = next((row for row in rows if coordinate_key(row) == key), None)
        if matched is None:
            raise ValueError(f"iteration-4 winner absent from frozen iteration-5 grid: {group}")
        chosen[key] = {
            **matched,
            "proposal_rank_at_tau": None,
            "selection_origin": "iteration4_exact_winner",
        }
    return sorted(chosen.values(), key=proposal_key)


def exact_audit(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    group, proposal = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"i6_joint_{os.getpid()}")
    existing = load(RUNNER, f"i6_existing_{os.getpid()}")
    orbit = load(ORBIT, f"i6_orbit_{os.getpid()}")
    engine = existing.FullObservationEngine(
        existing.validate_task(source_task(json.loads(source_path(group).read_text())))
    )
    begun = time.perf_counter()
    screened = joint.screen_point(
        engine, orbit, proposal["latitude_deg"], proposal["longitude_deg"], proposal["tau_s"], False
    )
    exact = joint.exact_comparison(existing, orbit, engine, screened)
    return {
        "group_id": group,
        "latitude_deg": proposal["latitude_deg"],
        "longitude_deg": proposal["longitude_deg"],
        "tau_s": proposal["tau_s"],
        "selection_origin": proposal["selection_origin"],
        "proposal_rank_at_tau": proposal["proposal_rank_at_tau"],
        "cap300_proposal_fit": proposal["fit"],
        "audit_screen_fit": screened["fit"],
        "track_associations": screened["track_associations"],
        "exact_comparison": exact,
        "elapsed_s": time.perf_counter() - begun,
        "cache_bindings": engine.bindings,
    }


def exact_key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(row["exact_comparison"]["exact_full_observation_capped_loss"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
        float(row["latitude_deg"]),
        float(row["longitude_deg"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration5", type=Path, default=ITER5)
    parser.add_argument("--iteration4", type=Path, default=ITER4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("existing output or invalid workers")
    iter5, iter4 = load_iteration5(args.iteration5), json.loads(args.iteration4.read_text())
    proposals = [(group, row) for group in GROUPS for row in shortlist(iter5, iter4, group)]
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audited = list(pool.map(exact_audit, proposals, chunksize=1))
    results = []
    for group in GROUPS:
        candidates = [row for row in audited if row["group_id"] == group]
        winner = min(candidates, key=exact_key)
        i5_winner = next(row["winner"] for row in iter5["results"] if row["group_id"] == group)
        results.append(
            {
                "group_id": group,
                "reused_converged_row_count": sum(
                    1
                    for scan in iter5["spatial_scans"]
                    if scan["group_id"] == group
                    for row in scan["rows"]
                    if row["fit"]["converged"]
                ),
                "exact_candidate_count": len(candidates),
                "selection": "exact cap-800 full-observation capped loss only",
                "iteration5_exact_winner_coordinate": {
                    key: i5_winner[key] for key in ("latitude_deg", "longitude_deg", "tau_s")
                },
                "candidates": candidates,
                "winner": winner,
            }
        )
    payload = {
        "schema": "ds1-iteration6-matched-proposal-exact-rank/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "proposal_policy": (
            "reuse converged iteration-5 cap-300 rows; top three spatial rows per fixed tau"
        ),
        "iteration4_retention": ("include iteration-4 exact winner at its original tau if absent"),
        "exact_audit": (
            "fresh hard association plus existing exact SGP4 cap-800 rate fit per retained row"
        ),
        "exact_selection": "exact cap-800 full-observation capped loss only",
        "top_per_tau": TOP_PER_TAU,
        "tau_grid_s": iter5["tau_grid_s"],
        "elapsed_s": time.perf_counter() - begun,
        "workers": args.workers,
        "iteration5_input": {"path": str(args.iteration5), "sha256": digest(args.iteration5)},
        "iteration4_input": {"path": str(args.iteration4), "sha256": digest(args.iteration4)},
        "results": results,
        "bindings": {
            "driver": digest(Path(__file__)),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_s": payload["elapsed_s"],
                "candidates": len(proposals),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
