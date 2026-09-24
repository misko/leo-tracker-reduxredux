#!/usr/bin/env python3
"""Iteration-5 fixed-spatial tau/convergence refinement for DS1 prefix-6."""

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
HERE = Path(__file__).resolve().parent
ITER4 = HERE / "iteration4-results.json"
JOINT = HERE / "joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
TAUS = tuple(round(-2.25 + 0.25 * n, 2) for n in range(9))
CAP_HZ, SIGMA, BOUND, SCALE, MAXITER = 300.0, 0.09176615913014215, 0.25, 250.0, 300
PRIOR_WEIGHT, EXACT_TOP_K, SPATIAL_SEPARATION_KM = 0.001, 12, 1.5


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


def source_path(group: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration5-" + source["task_id"],
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def labels(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(values.astype(str), return_inverse=True)


def profile_300(support: Any, initial: dict[str, float]) -> dict[str, Any]:
    """CFO-profiled cap-300 fit with an analytic gradient and continuation."""
    sources, si = labels(support.source)
    tracks, ti = labels(support.track)
    raw = support.measured - support.nominal
    feature = support.sensitivity_hz_s * support.age_h
    design = np.zeros((len(raw), len(sources)))
    design[np.arange(len(raw)), si] = feature
    centered_y, centered_x = raw.copy(), design.copy()
    for n in range(len(tracks)):
        rows = ti == n
        centered_y[rows] -= np.mean(centered_y[rows])
        centered_x[rows] -= np.mean(centered_x[rows], axis=0)
    x0 = np.asarray([initial.get(str(key), 0.0) for key in sources])

    def fun(rate: np.ndarray) -> float:
        e = centered_y - centered_x @ rate
        z = e / SCALE
        return float(np.sum(np.sqrt(1 + z * z) - 1) + 0.5 * np.sum((rate / SIGMA) ** 2))

    def jac(rate: np.ndarray) -> np.ndarray:
        e = centered_y - centered_x @ rate
        d = e / (SCALE**2 * np.sqrt(1 + (e / SCALE) ** 2))
        return -centered_x.T @ d + rate / SIGMA**2

    fit = minimize(
        fun,
        x0,
        jac=jac,
        method="L-BFGS-B",
        bounds=[(-BOUND, BOUND)] * len(sources),
        options={"maxiter": MAXITER, "ftol": 1e-12, "gtol": 1e-7},
    )
    rate = np.asarray(fit.x)
    residual = raw - feature * rate[si]
    cfo = np.asarray([np.mean(residual[ti == n]) for n in range(len(tracks))])
    err = residual - cfo[ti]
    loss = sum(
        support.weights[str(name)]
        * min((float(np.sqrt(np.mean(err[ti == n] ** 2))) / CAP_HZ) ** 2, 1.0)
        for n, name in enumerate(tracks)
    ) / sum(support.weights.values())
    prior = PRIOR_WEIGHT * 0.5 * float(np.sum((rate / SIGMA) ** 2))
    return {
        "selection_objective": float(loss + prior),
        "full_observation_capped_loss": float(loss),
        "prior_penalty": prior,
        "converged": bool(fit.success),
        "iterations": int(fit.nit),
        "message": str(fit.message),
        "rate_corrections_s_h": {str(k): float(v) for k, v in zip(sources, rate, strict=True)},
        "track_cfo_hz": {str(k): float(v) for k, v in zip(tracks, cfo, strict=True)},
        "rate_boundary_count": int(np.sum(np.abs(rate) >= BOUND - 1e-8)),
    }


def frozen_candidates(iter4: dict[str, Any], group: str) -> list[dict[str, Any]]:
    result = next(row for row in iter4["results"] if row["group_id"] == group)
    return [
        {
            "latitude_deg": c["latitude_deg"],
            "longitude_deg": c["longitude_deg"],
            "spatial_origin": c["selection_origin"],
        }
        for c in result["candidates"]
    ]


def scan_spatial(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    group, spatial = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"i5_joint_{os.getpid()}")
    existing = load(RUNNER, f"i5_existing_{os.getpid()}")
    orbit = load(ORBIT, f"i5_orbit_{os.getpid()}")
    engine = existing.FullObservationEngine(
        existing.validate_task(source_task(json.loads(source_path(group).read_text())))
    )
    previous: dict[str, float] = {}
    rows = []
    begun = time.perf_counter()
    for tau in TAUS:
        support = joint.hard_support(
            engine, orbit, spatial["latitude_deg"], spatial["longitude_deg"], tau
        )
        fit = profile_300(support, previous)
        previous = fit["rate_corrections_s_h"]
        rows.append(
            {
                "latitude_deg": spatial["latitude_deg"],
                "longitude_deg": spatial["longitude_deg"],
                "tau_s": tau,
                "spatial_origin": spatial["spatial_origin"],
                "fit": fit,
            }
        )
    return {
        "group_id": group,
        "spatial": spatial,
        "rows": rows,
        "elapsed_s": time.perf_counter() - begun,
    }


def haversine(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians, (a["latitude_deg"], a["longitude_deg"], b["latitude_deg"], b["longitude_deg"])
    )
    x = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(x))


def shortlist(scans: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    eligible = [
        row
        for scan in scans
        if scan["group_id"] == group
        for row in scan["rows"]
        if row["fit"]["converged"]
    ]
    if not eligible:
        raise ValueError(f"no converged rows: {group}")

    def key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
        return (
            row["fit"]["selection_objective"],
            abs(row["tau_s"]),
            row["tau_s"],
            row["latitude_deg"],
            row["longitude_deg"],
        )

    chosen = {}
    for tau in TAUS:
        rows = [r for r in eligible if r["tau_s"] == tau]
        if rows:
            row = min(rows, key=key)
            chosen[
                (round(row["latitude_deg"], 8), round(row["longitude_deg"], 8), row["tau_s"])
            ] = row
    for row in sorted(eligible, key=key):
        if len(chosen) >= EXACT_TOP_K:
            break
        if all(haversine(row, old) >= SPATIAL_SEPARATION_KM for old in chosen.values()):
            chosen[
                (round(row["latitude_deg"], 8), round(row["longitude_deg"], 8), row["tau_s"])
            ] = row
    return sorted(chosen.values(), key=key)


def exact_audit(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    group, row = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"i5ej_{os.getpid()}")
    existing = load(RUNNER, f"i5ee_{os.getpid()}")
    orbit = load(ORBIT, f"i5eo_{os.getpid()}")
    engine = existing.FullObservationEngine(
        existing.validate_task(source_task(json.loads(source_path(group).read_text())))
    )
    screened = joint.screen_point(
        engine, orbit, row["latitude_deg"], row["longitude_deg"], row["tau_s"], False
    )
    return {
        "group_id": group,
        "latitude_deg": row["latitude_deg"],
        "longitude_deg": row["longitude_deg"],
        "tau_s": row["tau_s"],
        "cap300_surrogate_fit": row["fit"],
        "exact_comparison": joint.exact_comparison(existing, orbit, engine, screened),
        "track_associations": screened["track_associations"],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("existing output or invalid workers")
    i4 = json.loads(ITER4.read_text())
    if i4.get("reference_used_for_fit") is not False:
        raise ValueError("iteration4 is not reference-free")
    spatial = [(g, c) for g in ("20260921_00", "20260921_16") for c in frozen_candidates(i4, g)]
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        scans = list(pool.map(scan_spatial, spatial, chunksize=1))
    exact_tasks = [(g, row) for g in ("20260921_00", "20260921_16") for row in shortlist(scans, g)]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        exact = list(pool.map(exact_audit, exact_tasks, chunksize=1))
    groups = []
    for group in ("20260921_00", "20260921_16"):
        candidates = [r for r in exact if r["group_id"] == group]
        winner = min(
            candidates,
            key=lambda r: (
                r["exact_comparison"]["exact_full_observation_capped_loss"],
                abs(r["tau_s"]),
                r["tau_s"],
                r["latitude_deg"],
                r["longitude_deg"],
            ),
        )
        groups.append(
            {
                "group_id": group,
                "frozen_spatial_candidate_count": len(frozen_candidates(i4, group)),
                "converged_tau_rows": sum(
                    r["fit"]["converged"]
                    for s in scans
                    if s["group_id"] == group
                    for r in s["rows"]
                ),
                "shortlist": candidates,
                "winner": winner,
            }
        )
    out = {
        "schema": "ds1-iteration5-fixed-spatial-tau-convergence/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "tau_grid_s": TAUS,
        "cap_hz": CAP_HZ,
        "rate_max_iterations": MAXITER,
        "exact_selection": "exact full-observation capped loss only",
        "elapsed_s": time.perf_counter() - begun,
        "workers": args.workers,
        "iteration4_input": {"path": str(ITER4), "sha256": digest(ITER4)},
        "spatial_scans": scans,
        "results": groups,
        "bindings": {
            "driver": digest(Path(__file__)),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "elapsed_s": out["elapsed_s"]}))


if __name__ == "__main__":
    main()
