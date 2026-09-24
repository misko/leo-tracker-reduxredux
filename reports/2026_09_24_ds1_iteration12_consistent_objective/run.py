#!/usr/bin/env python3
"""DS1 iteration 12: consistent cap-800 proposal and exact objectives."""

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
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
ITERATIONS = {
    "iteration8": ROOT / "reports/2026_09_24_ds1_iteration8_joint_groups/inference.json",
    "iteration9": ROOT / "reports/2026_09_24_ds1_iteration9_joint_refinement/inference.json",
    "iteration10": ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json",
}
ITER10_RUN = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/run.py"
JOINT = ROOT / "reports/2026_09_24_ds1_joint_rate_search/joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
GROUPS = ("20260921_00", "20260921_16")
TAUS = (-1.25, -1.0, -0.75, -0.5, -0.25)
LEVELS_KM = (0.390625, 0.1953125, 0.09765625)
TOP_BASINS = 3
EXACT_TOP_COORDINATES = 6
TOP_TAUS_PER_GROUP = 2
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
ROBUST_SCALE_HZ = 250.0
MAX_ITERATIONS = 300


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


def load_seeds(paths: dict[str, Path]) -> dict[str, dict[str, float]]:
    seeds = {}
    for name, path in paths.items():
        document = json.loads(path.read_text())
        if (
            document.get("complete") is not True
            or document.get("reference_used_for_fit") is not False
        ):
            raise ValueError(f"{name} is not a sealed reference-free inference")
        winner = document["winner"]
        if not all(
            row["exact_comparison"]["exact_sgp4_gate"]["passed"]
            for row in winner["best_exact_by_group"].values()
        ):
            raise ValueError(f"{name} winner failed its exact gate")
        seeds[name] = {
            "latitude_deg": float(winner["latitude_deg"]),
            "longitude_deg": float(winner["longitude_deg"]),
        }
    return seeds


def offset_coordinate(
    center: dict[str, float], east_km: float, north_km: float
) -> dict[str, float]:
    return {
        "latitude_deg": center["latitude_deg"] + north_km / 111.32,
        "longitude_deg": center["longitude_deg"]
        + east_km / (111.32 * math.cos(math.radians(center["latitude_deg"]))),
    }


def key(point: dict[str, Any]) -> tuple[float, float]:
    return (round(float(point["latitude_deg"]), 10), round(float(point["longitude_deg"]), 10))


def local_offsets(point: dict[str, Any], origin: dict[str, float]) -> tuple[float, float]:
    east = (
        (float(point["longitude_deg"]) - origin["longitude_deg"])
        * 111.32
        * math.cos(math.radians(origin["latitude_deg"]))
    )
    north = (float(point["latitude_deg"]) - origin["latitude_deg"]) * 111.32
    return east, north


def lattice(
    parents: list[dict[str, float]], spacing_km: float, origin: dict[str, float]
) -> list[dict[str, float]]:
    points = {}
    for parent in parents:
        for north in (-spacing_km, 0.0, spacing_km):
            for east in (-spacing_km, 0.0, spacing_km):
                point = offset_coordinate(parent, east, north)
                local_east, local_north = local_offsets(point, origin)
                point["east_km_from_iteration10"] = local_east
                point["north_km_from_iteration10"] = local_north
                points[key(point)] = point
    return list(points.values())


def _labels(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(values.astype(str), return_inverse=True)


def profile_consistent(support: Any) -> dict[str, Any]:
    """Fit nuisance rates as exact does; publish exact's cap-800 selection loss."""
    sources, source_index = _labels(support.source)
    tracks, track_index = _labels(support.track)
    raw = support.measured - support.nominal
    feature = support.sensitivity_hz_s * support.age_h
    design = np.zeros((len(raw), len(sources)), dtype=float)
    design[np.arange(len(raw)), source_index] = feature
    centered_y, centered_x = raw.copy(), design.copy()
    for index in range(len(tracks)):
        rows = track_index == index
        centered_y[rows] -= np.mean(centered_y[rows])
        centered_x[rows] -= np.mean(centered_x[rows], axis=0)

    def objective(rate: np.ndarray) -> float:
        error = centered_y - centered_x @ rate
        z = error / ROBUST_SCALE_HZ
        return float(
            np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * np.sum((rate / RATE_SIGMA_S_H) ** 2)
        )

    def gradient(rate: np.ndarray) -> np.ndarray:
        error = centered_y - centered_x @ rate
        derivative = error / (ROBUST_SCALE_HZ**2 * np.sqrt(1.0 + (error / ROBUST_SCALE_HZ) ** 2))
        return -centered_x.T @ derivative + rate / RATE_SIGMA_S_H**2

    optimized = minimize(
        objective,
        np.zeros(len(sources)),
        jac=gradient,
        method="L-BFGS-B",
        bounds=[(-RATE_BOUND_S_H, RATE_BOUND_S_H)] * len(sources),
        options={"maxiter": MAX_ITERATIONS, "ftol": 1e-11, "gtol": 1e-7},
    )

    def evaluate(rate: np.ndarray) -> tuple[float, np.ndarray]:
        residual = raw - feature * rate[source_index]
        cfo = np.asarray([np.mean(residual[track_index == index]) for index in range(len(tracks))])
        error = residual - cfo[track_index]
        loss = sum(
            support.weights[str(name)]
            * min(
                (float(np.sqrt(np.mean(error[track_index == index] ** 2))) / CAP_HZ) ** 2,
                1.0,
            )
            for index, name in enumerate(tracks)
        ) / sum(support.weights.values())
        return float(loss), cfo

    rate = np.asarray(optimized.x, dtype=float)
    loss, cfo = evaluate(rate)
    null_loss, null_cfo = evaluate(np.zeros_like(rate))
    rejected = loss > null_loss + 1e-12
    if rejected:
        rate = np.zeros_like(rate)
        loss, cfo = null_loss, null_cfo
    return {
        "selection_objective": loss,
        "full_observation_capped_loss": loss,
        "full_observation_capped_rms_hz": CAP_HZ * math.sqrt(loss),
        "null_rate_full_observation_capped_loss": null_loss,
        "rate_fit_rejected_by_full_observation_loss": rejected,
        "converged": bool(optimized.success),
        "iterations": int(optimized.nit),
        "message": str(optimized.message),
        "rate_corrections_s_h": {
            str(name): float(value) for name, value in zip(sources, rate, strict=True)
        },
        "rate_boundary_count": int(np.sum(np.abs(rate) >= RATE_BOUND_S_H - 1e-8)),
        "track_cfo_hz": {str(name): float(value) for name, value in zip(tracks, cfo, strict=True)},
    }


def scan(task: tuple[str, dict[str, float]]) -> dict[str, Any]:
    group, point = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    iteration10 = load(ITER10_RUN, f"i12_i10_{group}_{os.getpid()}")
    iteration9 = load(iteration10.ITER9_RUN, f"i12_i9_{group}_{os.getpid()}")
    iteration8 = load(iteration9.ITER8_RUN, f"i12_i8_{group}_{os.getpid()}")
    iteration8.TAUS = TAUS
    joint = load(JOINT, f"i12_joint_{group}_{os.getpid()}")
    existing = load(RUNNER, f"i12_runner_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"i12_orbit_{group}_{os.getpid()}")
    source = json.loads(iteration8.source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(iteration8.source_task(source)))
    begun = time.perf_counter()
    rows = []
    for tau in TAUS:
        support = joint.hard_support(
            engine, orbit, point["latitude_deg"], point["longitude_deg"], tau
        )
        rows.append({"tau_s": tau, "fit": profile_consistent(support)})
    return {**point, "group_id": group, "rows": rows, "elapsed_s": time.perf_counter() - begun}


def proposal_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (float(row["fit"]["selection_objective"]), abs(float(row["tau_s"])), float(row["tau_s"]))


def joint_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["balanced_proposal_objective"]),
        float(row["north_km_from_iteration10"]),
        float(row["east_km_from_iteration10"]),
    )


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
    iteration10 = load(ITER10_RUN, f"i12_exact_{group}_{os.getpid()}")
    result = iteration10.exact((group, point, tau_row))
    result["cap800_proposal_fit"] = result.pop("cap300_proposal_fit")
    return result


def exact_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["exact_comparison"]["exact_full_observation_capped_loss"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
    )


def select(audits: list[dict[str, Any]], finalists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for point in finalists:
        group_rows = {}
        for group in GROUPS:
            rows = [row for row in audits if row["group_id"] == group and key(row) == key(point)]
            if len(rows) != TOP_TAUS_PER_GROUP or not all(
                row["exact_comparison"]["exact_sgp4_gate"]["passed"] for row in rows
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
                        "east_km_from_iteration10",
                        "north_km_from_iteration10",
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
        key=lambda row: (
            row["balanced_exact_capped_loss"],
            row["north_km_from_iteration10"],
            row["east_km_from_iteration10"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("existing output or workers must be 1..8")
    seeds = load_seeds(ITERATIONS)
    origin = seeds["iteration10"]
    parents = [origin]
    levels = []
    begun = time.perf_counter()
    for level, spacing in enumerate(LEVELS_KM):
        points = lattice(parents, spacing, origin)
        if level == 0:
            # The three sealed seeds are only 0.10--0.38 km apart.  Add their
            # coordinates to one shared lattice rather than evaluating three
            # almost-overlapping 3x3 lattices.
            points_by_key = {key(point): point for point in points}
            for seed in seeds.values():
                east, north = local_offsets(seed, origin)
                points_by_key[key(seed)] = {
                    **seed,
                    "east_km_from_iteration10": east,
                    "north_km_from_iteration10": north,
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
        "schema": "ds1-iteration12-consistent-objective/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "seed_policy": (
            "one shared iteration-10-centered lattice plus sealed reference-free "
            "iteration 8, 9, and 10 winner coordinates"
        ),
        "seeds": seeds,
        "origin": origin,
        "shared_coordinate_policy": "one coordinate selected by equal-weight group objective",
        "group_nuisance_policy": (
            "independent hard associations, tau, per-NORAD rates, and per-track CFOs"
        ),
        "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
        "proposal_objective": (
            "cap-800 all-qualified-observation capped loss after regularized nuisance fit"
        ),
        "exact_objective": (
            "cap-800 all-qualified-observation capped loss after exact SGP4 nuisance fit"
        ),
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
        "bindings": {
            "driver": digest(Path(__file__)),
            "iteration10_driver": digest(ITER10_RUN),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
            **{name: digest(path) for name, path in ITERATIONS.items()},
        },
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
