#!/usr/bin/env python3
"""Reference-free, symmetric local refinement of the sealed iteration-8 joint fit."""

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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER8 = ROOT / "reports/2026_09_24_ds1_iteration8_joint_groups/inference.json"
ITER8_RUN = ROOT / "reports/2026_09_24_ds1_iteration8_joint_groups/run.py"
GROUPS = ("20260921_00", "20260921_16")
TAUS = (-1.25, -1.0, -0.75, -0.5, -0.25)
LEVELS_KM = (0.78125, 0.390625, 0.1953125)
TOP_BASINS = 3
EXACT_TOP_COORDINATES = 8
TOP_TAUS_PER_GROUP = 2


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


def load_iteration8(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-8 must be sealed reference-free inference")
    winner = value.get("winner", {})
    if set(winner.get("best_exact_by_group", {})) != set(GROUPS):
        raise ValueError("iteration-8 shared winner is incomplete")
    if not all(
        row["exact_comparison"]["exact_sgp4_gate"]["passed"]
        for row in winner["best_exact_by_group"].values()
    ):
        raise ValueError("iteration-8 winner did not pass exact gates")
    return value


def offset_coordinate(
    center: dict[str, float], east_km: float, north_km: float
) -> dict[str, float]:
    """Local tangent-plane displacement; all points are within 1.2 km."""
    latitude = float(center["latitude_deg"]) + north_km / 111.32
    longitude = float(center["longitude_deg"]) + east_km / (
        111.32 * math.cos(math.radians(float(center["latitude_deg"])))
    )
    return {
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "east_km_from_iteration8": east_km,
        "north_km_from_iteration8": north_km,
    }


def key(point: dict[str, Any]) -> tuple[float, float]:
    return (round(float(point["latitude_deg"]), 10), round(float(point["longitude_deg"]), 10))


def lattice(
    parent: dict[str, float], spacing_km: float, origin: dict[str, float]
) -> list[dict[str, float]]:
    rows = []
    for north in (-spacing_km, 0.0, spacing_km):
        for east in (-spacing_km, 0.0, spacing_km):
            point = offset_coordinate(parent, east, north)
            point["east_km_from_iteration8"] = (
                (float(point["longitude_deg"]) - origin["longitude_deg"])
                * 111.32
                * math.cos(math.radians(origin["latitude_deg"]))
            )
            point["north_km_from_iteration8"] = (
                float(point["latitude_deg"]) - origin["latitude_deg"]
            ) * 111.32
            rows.append(point)
    return rows


def proposal_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (float(row["fit"]["selection_objective"]), abs(float(row["tau_s"])), float(row["tau_s"]))


def exact_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["exact_comparison"]["exact_full_observation_capped_loss"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
    )


def joint_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["balanced_proposal_objective"]),
        float(row["north_km_from_iteration8"]),
        float(row["east_km_from_iteration8"]),
    )


def scan(task: tuple[str, dict[str, float]]) -> dict[str, Any]:
    group, point = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    i8 = load(ITER8_RUN, f"i9_i8_{group}_{os.getpid()}")
    i8.TAUS = TAUS
    return i8.scan_coordinate((group, point))


def combine(points: list[dict[str, float]], scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined = []
    for point in points:
        per_group = {}
        for group in GROUPS:
            scan_row = next(
                row for row in scans if row["group_id"] == group and key(row) == key(point)
            )
            eligible = sorted(
                (row for row in scan_row["rows"] if row["fit"]["converged"]), key=proposal_key
            )
            if len(eligible) < TOP_TAUS_PER_GROUP:
                raise ValueError("insufficient converged tau proposals")
            per_group[group] = eligible[:TOP_TAUS_PER_GROUP]
        combined.append(
            {
                **point,
                "balanced_proposal_objective": 0.5
                * per_group[GROUPS[0]][0]["fit"]["selection_objective"]
                + 0.5 * per_group[GROUPS[1]][0]["fit"]["selection_objective"],
                "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
                "proposal_taus": per_group,
            }
        )
    return sorted(combined, key=joint_key)


def exact(task: tuple[str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    group, point, tau_row = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    i8 = load(ITER8_RUN, f"i9_exact_{group}_{os.getpid()}")
    return i8.exact_audit((group, point, tau_row))


def select(audits: list[dict[str, Any]], finalists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for point in finalists:
        group_rows = {}
        for group in GROUPS:
            rows = [r for r in audits if r["group_id"] == group and key(r) == key(point)]
            if len(rows) != TOP_TAUS_PER_GROUP or not all(
                r["exact_comparison"]["exact_sgp4_gate"]["passed"] for r in rows
            ):
                raise ValueError("failed exact gate or incomplete audit")
            group_rows[group] = min(rows, key=exact_key)
        output.append(
            {
                **{
                    name: point[name]
                    for name in (
                        "latitude_deg",
                        "longitude_deg",
                        "east_km_from_iteration8",
                        "north_km_from_iteration8",
                        "balanced_proposal_objective",
                    )
                },
                "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
                "balanced_exact_capped_loss": 0.5
                * group_rows[GROUPS[0]]["exact_comparison"]["exact_full_observation_capped_loss"]
                + 0.5
                * group_rows[GROUPS[1]]["exact_comparison"]["exact_full_observation_capped_loss"],
                "best_exact_by_group": group_rows,
            }
        )
    return sorted(
        output,
        key=lambda r: (
            r["balanced_exact_capped_loss"],
            r["north_km_from_iteration8"],
            r["east_km_from_iteration8"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration8", type=Path, default=ITER8)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("existing output or invalid worker count")
    i8 = load_iteration8(args.iteration8)
    origin = {name: float(i8["winner"][name]) for name in ("latitude_deg", "longitude_deg")}
    parents = [origin]
    levels = []
    begun = time.perf_counter()
    for level, spacing in enumerate(LEVELS_KM):
        points_by_key = {
            key(row): row for parent in parents for row in lattice(parent, spacing, origin)
        }
        points = list(points_by_key.values())
        tasks = [(group, point) for point in points for group in GROUPS]
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            scans = list(pool.map(scan, tasks, chunksize=1))
        proposals = combine(points, scans)
        retained = proposals[:TOP_BASINS]
        levels.append(
            {
                "level": level,
                "spacing_km": spacing,
                "parent_count": len(parents),
                "coordinate_count": len(points),
                "proposal_scans": scans,
                "proposals": proposals,
                "retained_basins": retained,
            }
        )
        parents = [
            {name: float(row[name]) for name in ("latitude_deg", "longitude_deg")}
            for row in retained
        ]
    finalists = levels[-1]["proposals"][:EXACT_TOP_COORDINATES]
    tasks = [
        (group, point, tau)
        for point in finalists
        for group in GROUPS
        for tau in point["proposal_taus"][group]
    ]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audits = list(pool.map(exact, tasks, chunksize=1))
    exact_rows = select(audits, finalists)
    payload = {
        "schema": "ds1-iteration9-symmetric-joint-refinement/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "iteration8_input": {"path": str(args.iteration8), "sha256": digest(args.iteration8)},
        "origin": origin,
        "shared_coordinate_policy": "one coordinate selected by equal-weight group objective",
        "group_nuisance_policy": (
            "independent hard associations, tau, per-NORAD rates, and per-track CFOs"
        ),
        "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
        "common_tau_grid_s": TAUS,
        "symmetric_levels_km": LEVELS_KM,
        "basin_policy": f"retain {TOP_BASINS} proposal basins at each level",
        "exact_policy": (
            f"exact-audit {EXACT_TOP_COORDINATES} final coordinates and "
            f"{TOP_TAUS_PER_GROUP} taus/group"
        ),
        "exact_audit_count": len(audits),
        "workers": args.workers,
        "elapsed_s": time.perf_counter() - begun,
        "levels": levels,
        "exact_finalists": exact_rows,
        "winner": exact_rows[0],
        "bindings": {"driver": digest(Path(__file__)), "iteration8_driver": digest(ITER8_RUN)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"output": str(args.output), "elapsed_s": payload["elapsed_s"], "audits": len(audits)}
        )
    )


if __name__ == "__main__":
    main()
