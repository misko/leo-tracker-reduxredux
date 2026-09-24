#!/usr/bin/env python3
"""Close the DS1 exact-rate basin with frozen information weights."""

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
PLAN = HERE / "plan.json"
PARENT = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/refinement.json"
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
ITERATION10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
GROUPS = ("20260921_00", "20260921_16")
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(parent_path: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    parent = json.loads(parent_path.read_text())
    plan = json.loads(plan_path.read_text())
    if parent.get("complete") is not True or parent.get("reference_used_for_fit") is not False:
        raise ValueError("parent must be complete and reference-free")
    if parent.get("portability_accepted") is not True:
        raise ValueError("parent portability gate failed")
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("plan must prohibit reference use")
    if plan.get("group_weights") != GROUP_WEIGHTS:
        raise ValueError("plan group weights do not match the runner")
    return parent, plan


def point_key(east_km: float, north_km: float) -> tuple[float, float]:
    return round(east_km, 10), round(north_km, 10)


def lattice(
    driver: Any,
    origin: dict[str, float],
    center: tuple[float, float],
    spacing_km: float,
) -> list[dict[str, float]]:
    rows = []
    for north_step in (-1, 0, 1):
        for east_step in (-1, 0, 1):
            east = center[0] + east_step * spacing_km
            north = center[1] + north_step * spacing_km
            row = driver.local_coordinate(origin, east, north)
            row["east_km_from_iteration12"] = east
            row["north_km_from_iteration12"] = north
            rows.append(row)
    return rows


def audit(task: tuple[str, dict[str, float], dict[str, Any]]) -> dict[str, Any]:
    group, point, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load_module(DRIVER, f"i13_driver_{group}_{os.getpid()}")
    begun = time.perf_counter()
    model = driver._prepared_model(group, point, sealed_group)
    fit = driver.fit(model, scales_enabled=False)
    return {
        **point,
        "group_id": group,
        "tau_s": float(sealed_group["tau_s"]),
        "fixed_association_count": len(sealed_group["track_associations"]),
        "sample_count": len(model.data.y),
        "source_count": len(model.source_names),
        "rate_only": fit,
        "elapsed_s": time.perf_counter() - begun,
    }


def combine(
    audits: list[dict[str, Any]], points: list[dict[str, float]]
) -> list[dict[str, Any]]:
    rows = []
    for point in points:
        key = point_key(
            point["east_km_from_iteration12"], point["north_km_from_iteration12"]
        )
        grouped = [
            row
            for row in audits
            if point_key(
                row["east_km_from_iteration12"], row["north_km_from_iteration12"]
            )
            == key
        ]
        if len(grouped) != len(GROUPS):
            raise ValueError("incomplete group coordinate")
        fits = {row["group_id"]: row["rate_only"] for row in grouped}
        rows.append(
            {
                **point,
                "weighted_selection_objective": sum(
                    GROUP_WEIGHTS[group] * float(fits[group]["selection_objective"])
                    for group in GROUPS
                ),
                "weighted_exact_capped_loss": sum(
                    GROUP_WEIGHTS[group]
                    * float(fits[group]["exact_full_observation_capped_loss"])
                    for group in GROUPS
                ),
                "all_converged": all(bool(fits[group]["converged"]) for group in GROUPS),
                "rate_boundary_count": sum(
                    int(fits[group]["rate_boundary_count"]) for group in GROUPS
                ),
            }
        )
    qualified = [row for row in rows if row["all_converged"]]
    if not qualified:
        raise ValueError("no converged coordinate")
    return sorted(
        qualified,
        key=lambda row: (
            row["weighted_selection_objective"],
            row["north_km_from_iteration12"],
            row["east_km_from_iteration12"],
        ),
    )


def is_edge(winner: dict[str, Any], center: tuple[float, float], spacing: float) -> bool:
    east_step = round((winner["east_km_from_iteration12"] - center[0]) / spacing)
    north_step = round((winner["north_km_from_iteration12"] - center[1]) / spacing)
    return abs(east_step) == 1 or abs(north_step) == 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=PARENT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    parent, plan = load_inputs(args.parent, args.plan)
    driver = load_module(DRIVER, "i13_driver_main")
    sealed = driver.load_iteration10(ITERATION10)
    sealed_groups = sealed["winner"]["best_exact_by_group"]
    origin = {
        name: float(parent["winner"][name]) for name in ("latitude_deg", "longitude_deg")
    }
    cache: dict[tuple[str, float, float], dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    center = (0.0, 0.0)
    complete = True
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        for stage_index, stage in enumerate(plan["stages"]):
            spacing = float(stage["spacing_km"])
            stage_closed = False
            for translation in range(int(stage["maximum_translations"]) + 1):
                points = lattice(driver, origin, center, spacing)
                missing = []
                for point in points:
                    point_id = point_key(
                        point["east_km_from_iteration12"],
                        point["north_km_from_iteration12"],
                    )
                    for group in GROUPS:
                        if (group, *point_id) not in cache:
                            missing.append((group, point, sealed_groups[group]))
                for result in pool.map(audit, missing, chunksize=1):
                    key = point_key(
                        result["east_km_from_iteration12"],
                        result["north_km_from_iteration12"],
                    )
                    cache[(result["group_id"], *key)] = result
                relevant = [
                    cache[(group, *point_key(
                        point["east_km_from_iteration12"],
                        point["north_km_from_iteration12"],
                    ))]
                    for point in points
                    for group in GROUPS
                ]
                ranked = combine(relevant, points)
                winner = ranked[0]
                edge = is_edge(winner, center, spacing)
                step = {
                    "stage_index": stage_index,
                    "translation_index": translation,
                    "spacing_km": spacing,
                    "center_east_km": center[0],
                    "center_north_km": center[1],
                    "new_group_coordinate_fits": len(missing),
                    "ranked_coordinates": ranked,
                    "winner": winner,
                    "winner_on_edge": edge,
                }
                steps.append(step)
                checkpoint = args.checkpoint_dir / f"stage-{stage_index}-step-{translation}.json"
                checkpoint.write_text(json.dumps(step, indent=2, sort_keys=True) + "\n")
                center = (
                    float(winner["east_km_from_iteration12"]),
                    float(winner["north_km_from_iteration12"]),
                )
                if not edge:
                    stage_closed = True
                    break
            if not stage_closed:
                complete = False
                break
    final = steps[-1]["winner"]
    selected_audits = [
        cache[(group, *point_key(
            final["east_km_from_iteration12"], final["north_km_from_iteration12"]
        ))]
        for group in GROUPS
    ]
    output = {
        "schema": "ds1-iteration15-information-weighted-basin/v1",
        "complete": complete,
        "qualified": complete and not steps[-1]["winner_on_edge"],
        "partition": "train",
        "reference_used_for_fit": False,
        "plan": {"path": str(args.plan), "sha256": digest(args.plan)},
        "parent": {"path": str(args.parent), "sha256": digest(args.parent)},
        "iteration10": {"path": str(ITERATION10), "sha256": digest(ITERATION10)},
        "origin": origin,
        "group_weights": GROUP_WEIGHTS,
        "steps": steps,
        "winner": final,
        "selected_group_audits": selected_audits,
        "unique_group_coordinate_fits": len(cache),
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {"runner": digest(Path(__file__)), "driver": digest(DRIVER)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "complete": complete, "winner": final}))


if __name__ == "__main__":
    main()
