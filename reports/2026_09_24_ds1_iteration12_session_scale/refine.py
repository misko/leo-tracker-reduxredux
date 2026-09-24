#!/usr/bin/env python3
"""Reference-free second local level for the sealed iteration-12 scale arm."""

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
LEVEL1 = HERE / "inference.json"
DRIVER = HERE / "run.py"
SPACING_KM = 0.09765625


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


def load_level1(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("level-1 inference must be sealed and reference-free")
    winner = value.get("winner", {})
    if not winner.get("all_converged") or not winner.get("all_scale_guards_clear"):
        raise ValueError("level-1 selected fit is not portable")
    if value.get("portability_accepted") is not True:
        raise ValueError("level-1 inference is not accepted")
    return value


def key(row: dict[str, Any]) -> tuple[float, float]:
    return (
        round(float(row["east_km_from_iteration12_level1"]), 10),
        round(float(row["north_km_from_iteration12_level1"]), 10),
    )


def lattice(driver: Any, origin: dict[str, float]) -> list[dict[str, float]]:
    rows = []
    for north in (-SPACING_KM, 0.0, SPACING_KM):
        for east in (-SPACING_KM, 0.0, SPACING_KM):
            row = driver.local_coordinate(origin, east, north)
            row["east_km_from_iteration12_level1"] = east
            row["north_km_from_iteration12_level1"] = north
            rows.append(row)
    return rows


def audit(task: tuple[dict[str, float], str, dict[str, Any]]) -> dict[str, Any]:
    point, group, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load(DRIVER, f"i12_refine_{group}_{os.getpid()}")
    output = driver.audit((group, point, sealed_group))
    output["east_km_from_iteration12_level1"] = point["east_km_from_iteration12_level1"]
    output["north_km_from_iteration12_level1"] = point["north_km_from_iteration12_level1"]
    return output


def combine(audits: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    output = []
    for north in (-SPACING_KM, 0.0, SPACING_KM):
        for east in (-SPACING_KM, 0.0, SPACING_KM):
            rows = [row for row in audits if key(row) == (east, north)]
            if len(rows) != 2:
                raise ValueError("incomplete refinement coordinate")
            fits = [row[method] for row in sorted(rows, key=lambda row: row["group_id"])]
            output.append(
                {
                    "latitude_deg": rows[0]["latitude_deg"],
                    "longitude_deg": rows[0]["longitude_deg"],
                    "east_km_from_iteration12_level1": east,
                    "north_km_from_iteration12_level1": north,
                    "balanced_selection_objective": 0.5
                    * sum(float(fit["selection_objective"]) for fit in fits),
                    "balanced_exact_capped_loss": 0.5
                    * sum(float(fit["exact_full_observation_capped_loss"]) for fit in fits),
                    "all_converged": bool(all(fit["converged"] for fit in fits)),
                    "all_scale_guards_clear": bool(
                        all(not fit["scale_reaches_guard"] for fit in fits)
                    ),
                }
            )
    return sorted(
        output,
        key=lambda row: (
            row["balanced_selection_objective"],
            row["north_km_from_iteration12_level1"],
            row["east_km_from_iteration12_level1"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level1", type=Path, default=LEVEL1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    driver = load(DRIVER, "i12_refine_main")
    level1 = load_level1(args.level1)
    origin = {name: float(level1["winner"][name]) for name in ("latitude_deg", "longitude_deg")}
    iteration10 = driver.load_iteration10(Path(level1["iteration10_input"]["path"]))
    sealed_groups = iteration10["winner"]["best_exact_by_group"]
    points = lattice(driver, origin)
    begun = time.perf_counter()
    tasks = [(point, group, sealed_groups[group]) for point in points for group in driver.GROUPS]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audits = list(pool.map(audit, tasks, chunksize=1))
    baseline = combine(audits, "baseline_rate_only")
    hierarchy = combine(audits, "common_plus_session_scale")
    winner = hierarchy[0]
    selected_audits = [row for row in audits if key(row) == key(winner)]
    portable = bool(
        winner["all_converged"]
        and winner["all_scale_guards_clear"]
        and all(
            row["common_plus_session_scale"]["exact_full_observation_capped_loss"]
            <= row["baseline_rate_only"]["exact_full_observation_capped_loss"] + 1e-12
            for row in selected_audits
        )
    )
    output = {
        "schema": "ds1-iteration12-session-scale-refinement/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "level1_input": {"path": str(args.level1), "sha256": digest(args.level1)},
        "origin": origin,
        "origin_policy": "sealed portable level-1 scale winner only",
        "coordinate_policy": "symmetric 3x3 exact refinement at 97.65625 m",
        "fixed_group_taus_s": {group: sealed_groups[group]["tau_s"] for group in driver.GROUPS},
        "association_policy": "same fixed iteration-10 hard supports as level 1",
        "model": level1["model"],
        "baseline_rate_only_rows": baseline,
        "common_plus_session_scale_rows": hierarchy,
        "winner": winner,
        "selected_group_audits": selected_audits,
        "portability_accepted": portable,
        "portability_rule": level1["portability_rule"].replace(
            ", and opposite 400-ppm starts agree within 1e-6 on selection objective", ""
        ),
        "workers": args.workers,
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {"driver": digest(DRIVER), "refiner": digest(Path(__file__))},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"output": str(args.output), "elapsed_s": output["elapsed_s"], "winner": winner},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
