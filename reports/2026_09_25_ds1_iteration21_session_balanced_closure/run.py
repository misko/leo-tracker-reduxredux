#!/usr/bin/env python3
"""Extend the sealed iteration20 nominal-Doppler boundary without new data."""

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
PARENT = ROOT / "reports/2026_09_25_ds1_iteration20_session_predictive/inference.json"
I20_RUNNER = ROOT / "reports/2026_09_25_ds1_iteration20_session_predictive/run.py"
GROUPS = ("20260921_00", "20260921_16")
WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
TAUS = {"20260921_00": -0.75, "20260921_16": -0.50}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def point_key(point: dict[str, Any]) -> tuple[float, float]:
    return round(float(point["east_km_from_parent"]), 10), round(
        float(point["north_km_from_parent"]), 10
    )


def load_inputs(parent_path: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    parent, plan = json.loads(parent_path.read_text()), json.loads(plan_path.read_text())
    if parent.get("reference_used_for_fit") is not False or not parent.get("steps"):
        raise ValueError("parent must be a complete reference-free inference")
    if parent.get("complete") is not False or not parent["steps"][-1].get("winner_on_edge"):
        raise ValueError("iteration21 may extend only a sealed terminal boundary")
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("plan must prohibit reference use")
    if plan.get("group_weights") != WEIGHTS or plan.get("group_taus_s") != TAUS:
        raise ValueError("frozen group contract mismatch")
    return parent, plan


def lattice(
    driver: Any, origin: dict[str, float], center: tuple[float, float], spacing: float
) -> list[dict[str, float]]:
    rows = []
    for north_step in (-1, 0, 1):
        for east_step in (-1, 0, 1):
            east, north = center[0] + east_step * spacing, center[1] + north_step * spacing
            row = driver.local_coordinate(origin, east, north)
            # Keep i20's input field names so the shared exact scorer remains
            # unchanged; the output documents this as relative to i20 terminal.
            row["east_km_from_parent"], row["north_km_from_parent"] = east, north
            rows.append(row)
    return rows


def edge(row: dict[str, Any], center: tuple[float, float], spacing: float) -> bool:
    east = round((float(row["east_km_from_parent"]) - center[0]) / spacing)
    north = round((float(row["north_km_from_parent"]) - center[1]) / spacing)
    return abs(east) == 1 or abs(north) == 1


def audit(task: tuple[str, dict[str, float], dict[str, Any]]) -> dict[str, Any]:
    """Call the unchanged i20 exact nominal session scorer in a child process."""
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    helper = load(I20_RUNNER, f"i21_i20_{os.getpid()}")
    result = helper.geographic_audit(task)
    return result


def combine(
    helper: Any, audits: list[dict[str, Any]], points: list[dict[str, float]]
) -> list[dict[str, Any]]:
    return helper.combine(audits, points)


def deletion_influence(
    final_step: dict[str, Any], cache: dict[tuple[str, float, float], dict[str, Any]]
) -> list[dict[str, Any]]:
    """Exact delete-one-session re-rank over the sealed final 3x3 stencil."""
    candidates = final_step["ranked_coordinates"]
    baseline = final_step["winner"]
    output = []
    sessions = []
    first = candidates[0]
    for group in GROUPS:
        audit = cache[(group, *point_key(first))]
        sessions.extend(
            (group, row["session_id"]) for row in audit["nominal_session_score"]["session_scores"]
        )
    for deleted_group, deleted_session in sessions:
        ranked = []
        for point in candidates:
            loss = 0.0
            for group in GROUPS:
                score_rows = cache[(group, *point_key(point))]["nominal_session_score"][
                    "session_scores"
                ]
                values = [
                    r["nominal_capped_loss"]
                    for r in score_rows
                    if not (group == deleted_group and r["session_id"] == deleted_session)
                ]
                loss += WEIGHTS[group] * sum(values) / len(values)
            ranked.append({**point, "deleted_session_score": loss})
        winner = min(
            ranked,
            key=lambda r: (
                r["deleted_session_score"],
                r["north_km_from_parent"],
                r["east_km_from_parent"],
            ),
        )
        output.append(
            {
                "deleted_group_id": deleted_group,
                "deleted_session_id": deleted_session,
                "stencil_size": len(candidates),
                "baseline_winner": {
                    "east_km": baseline["east_km_from_parent"],
                    "north_km": baseline["north_km_from_parent"],
                },
                "deleted_winner": {
                    "east_km": winner["east_km_from_parent"],
                    "north_km": winner["north_km_from_parent"],
                },
                "winner_changed": point_key(winner) != point_key(baseline),
                "deleted_session_objective": winner["deleted_session_score"],
            }
        )
    return output


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
    helper = load(I20_RUNNER, "i21_i20_main")
    origin = {key: float(parent["winner"][key]) for key in ("latitude_deg", "longitude_deg")}
    cache: dict[tuple[str, float, float], dict[str, Any]] = {}
    steps, center, complete = [], (0.0, 0.0), True
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    begun = time.perf_counter()
    # i20 has already validated its hard association/tau contract.  Reconstruct
    # the same sealed groups here to make each artifact self-describing.
    driver = load(helper.DRIVER, "i21_i20_driver")
    sealed_groups = driver.load_iteration10(helper.ITERATION10)["winner"]["best_exact_by_group"]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        for stage_index, stage in enumerate(plan["stages"]):
            spacing, closed = float(stage["spacing_km"]), False
            for translation in range(int(stage["maximum_translations"]) + 1):
                points = lattice(driver, origin, center, spacing)
                missing = []
                for point in points:
                    for group in GROUPS:
                        cache_key = (group, *point_key(point))
                        if cache_key not in cache:
                            missing.append((group, point, sealed_groups[group]))
                for result in pool.map(audit, missing, chunksize=1):
                    cache[(result["group_id"], *point_key(result))] = result
                relevant = [
                    cache[(group, *point_key(point))] for point in points for group in GROUPS
                ]
                ranked = combine(helper, relevant, points)
                winner = ranked[0]
                winner_on_edge = edge(winner, center, spacing)
                step = {
                    "stage_index": stage_index,
                    "translation_index": translation,
                    "spacing_km": spacing,
                    "center_east_km_from_i20_terminal": center[0],
                    "center_north_km_from_i20_terminal": center[1],
                    "new_group_coordinate_fits": len(missing),
                    "ranked_coordinates": ranked,
                    "winner": winner,
                    "winner_on_edge": winner_on_edge,
                }
                steps.append(step)
                (args.checkpoint_dir / f"stage-{stage_index}-step-{translation}.json").write_text(
                    json.dumps(step, indent=2, sort_keys=True) + "\n"
                )
                center = float(winner["east_km_from_parent"]), float(winner["north_km_from_parent"])
                if not winner_on_edge:
                    closed = True
                    break
            if not closed:
                complete = False
                break
    final = steps[-1]
    session_scores = []
    for (_group, _east, _north), value in sorted(cache.items()):
        session_scores.append(
            {
                "group_id": value["group_id"],
                "east_km_from_i20_terminal": value["east_km_from_parent"],
                "north_km_from_i20_terminal": value["north_km_from_parent"],
                "session_scores": value["nominal_session_score"]["session_scores"],
            }
        )
    result = {
        "schema": "ds1-iteration21-session-balanced-closure-inference/v1",
        "complete": complete,
        "qualified": False,
        "reference_used_for_fit": False,
        "status": "pending_zero_rate_fidelity" if complete else "unqualified_boundary",
        "parent": {"path": str(args.parent), "sha256": digest(args.parent)},
        "plan": {"path": str(args.plan), "sha256": digest(args.plan)},
        "objective_source": {"path": str(I20_RUNNER), "sha256": digest(I20_RUNNER)},
        "origin_i20_terminal": origin,
        "group_weights": WEIGHTS,
        "group_taus_s": TAUS,
        "steps": steps,
        "winner": final["winner"],
        "unique_group_coordinate_fits": len(cache),
        "per_session_scores_by_coordinate": session_scores,
        "session_deletion_influence": deletion_influence(final, cache) if complete else [],
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {"runner": digest(Path(__file__)), "iteration20_runner": digest(I20_RUNNER)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "complete": complete, "winner": final["winner"]}))


if __name__ == "__main__":
    main()
