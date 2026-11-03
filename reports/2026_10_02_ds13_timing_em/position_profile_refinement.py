"""Bounded continuation of unresolved DS13 position-profile cells."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from position_profile_grid import run_profile
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable

SESSION = "scan-fw-ffa1cc19d8d7c09f"
STAGE_BUDGET_S = 8.0
WALL_BUDGET_S = 120.0
START_RESERVE_S = 9.0
MAX_WORKERS = 2
SOUTH_PRIORITY = ("S-50m", "S-100m", "S-500m")


def priority_labels(positions):
    unresolved = [
        position
        for position in positions
        if position["kind"] == "radial" and not position["ranking_resolved"]
    ]
    by_label = {position["label"]: position for position in unresolved}
    priority = [label for label in SOUTH_PRIORITY if label in by_label]
    remaining = [position for position in unresolved if position["label"] not in priority]
    remaining.sort(
        key=lambda position: (
            position["best"]["projected_nuisance_gradient_inf_norm"],
            position["radius_m"],
            position["bearing_deg"],
        )
    )
    return priority + [position["label"] for position in remaining]


def select_updated_best(original, refinements):
    candidates = [("original", original)] + [
        (f"refinement_{index + 1}", attempt)
        for index, attempt in enumerate(refinements)
        if attempt.get("objective") is not None and np.isfinite(attempt["objective"])
    ]
    return min(candidates, key=lambda item: item[1]["objective"])


def gradient_change(before, after):
    return {
        "projected_nuisance_gradient_before": before[
            "projected_nuisance_gradient_inf_norm"
        ],
        "projected_nuisance_gradient_after": after[
            "projected_nuisance_gradient_inf_norm"
        ],
        "projected_nuisance_gradient_ratio": (
            after["projected_nuisance_gradient_inf_norm"]
            / before["projected_nuisance_gradient_inf_norm"]
            if before["projected_nuisance_gradient_inf_norm"] > 0
            else None
        ),
        "free_position_gradient_before": before["free_position_gradient"],
        "free_position_gradient_after": after["free_position_gradient"],
    }


@lru_cache(maxsize=2)
def _worker_data(session):
    _source, data = load_scan(session)
    return data


def _worker(task):
    started = time.monotonic()
    try:
        result = run_profile(
            _worker_data(task["session"]),
            task["initial_parameters"],
            task["satellites"],
            task["rf_coefficient"],
            task["position"],
            start_vector=task["start_vector"],
            budget_s=STAGE_BUDGET_S,
        )
        return {
            **result,
            "refinement_pass": task["refinement_pass"],
            "start_vector": task["start_vector"],
            "worker_elapsed_s": time.monotonic() - started,
        }
    except Exception as error:
        return {
            "refinement_pass": task["refinement_pass"],
            "start_vector": task["start_vector"],
            "objective": None,
            "status": "execution_error",
            "success": False,
            "error": f"{type(error).__name__}: {error}",
            "worker_elapsed_s": time.monotonic() - started,
        }


def _compact(attempt):
    return {
        key: value
        for key, value in attempt.items()
        if key
        not in {
            "group_values",
            "group_time_s",
            "group_log_likelihood",
            "satellite_support",
        }
    }


def _task(session, original, position, pass_index, start_vector, satellites):
    return {
        "session": session,
        "label": position["label"],
        "refinement_pass": pass_index,
        "initial_parameters": np.asarray(original["positions"][0]["best"]["parameters"]),
        "satellites": np.asarray(satellites),
        "rf_coefficient": np.asarray(
            position["best"]["rf_coefficient_hz_per_ghz"]
        ),
        "position": np.asarray(position["fixed_position_km"]),
        "start_vector": np.asarray(start_vector),
    }


def _run_tasks(executor, tasks, wall_started):
    results = {}
    for start in range(0, len(tasks), MAX_WORKERS):
        if time.monotonic() - wall_started >= WALL_BUDGET_S - START_RESERVE_S:
            break
        batch = tasks[start : start + MAX_WORKERS]
        futures = [(task, executor.submit(_worker, task)) for task in batch]
        for task, future in futures:
            results[task["label"]] = future.result()
    return results


def run_case(session=SESSION):
    destination = ROOT / "position-profile-refinement" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    original_path = ROOT / "position-profile-grid" / f"{session}.json"
    protocol_path = ROOT / "position-profile-protocol.json"
    amendment_path = ROOT / "position-profile-resource-amendment.json"
    original = json.loads(original_path.read_text())
    if (
        original.get("schema") != "ds13-position-profile-grid/v1"
        or original.get("session") != session
        or original.get("complete") is not True
    ):
        raise ValueError("invalid original position-profile receipt")
    assert_snapshot_unchanged(original["source_hashes"])
    source_hashes = {
        **original["source_hashes"],
        **snapshot_files(
            [
                Path(__file__),
                original_path,
                protocol_path,
                amendment_path,
                ROOT / "position_profile_grid.py",
            ]
        ),
    }
    assert_snapshot_unchanged(source_hashes)
    positions = {position["label"]: position for position in original["positions"]}
    priority = priority_labels(original["positions"])
    satellites = np.asarray(original["satellite_indices"], dtype=int)
    wall_started = time.monotonic()
    refinements = {label: [] for label in priority}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        south_first = [
            _task(
                session,
                original,
                positions[label],
                1,
                positions[label]["best"]["vector"],
                satellites,
            )
            for label in priority
            if label in SOUTH_PRIORITY
        ]
        for label, attempt in _run_tasks(executor, south_first, wall_started).items():
            refinements[label].append(attempt)
        south_second = []
        for label in SOUTH_PRIORITY:
            if label not in refinements or not refinements[label]:
                continue
            first = refinements[label][-1]
            if not first.get("success", False) and first.get("vector") is not None:
                south_second.append(
                    _task(
                        session,
                        original,
                        positions[label],
                        2,
                        first["vector"],
                        satellites,
                    )
                )
        for label, attempt in _run_tasks(executor, south_second, wall_started).items():
            refinements[label].append(attempt)
        remaining_first = [
            _task(
                session,
                original,
                positions[label],
                1,
                positions[label]["best"]["vector"],
                satellites,
            )
            for label in priority
            if label not in SOUTH_PRIORITY
        ]
        for label, attempt in _run_tasks(executor, remaining_first, wall_started).items():
            refinements[label].append(attempt)
        second_pass = []
        for label in priority:
            if label in SOUTH_PRIORITY or not refinements[label]:
                continue
            first = refinements[label][-1]
            if not first.get("success", False) and first.get("vector") is not None:
                second_pass.append(
                    _task(
                        session,
                        original,
                        positions[label],
                        2,
                        first["vector"],
                        satellites,
                    )
                )
        for label, attempt in _run_tasks(executor, second_pass, wall_started).items():
            refinements[label].append(attempt)
    updated_positions = []
    for original_position in original["positions"]:
        label = original_position["label"]
        attempts = refinements.get(label, [])
        selected_from, best = select_updated_best(original_position["best"], attempts)
        updated_positions.append(
            {
                "label": label,
                "kind": original_position["kind"],
                "bearing_label": original_position["bearing_label"],
                "bearing_deg": original_position["bearing_deg"],
                "radius_m": original_position["radius_m"],
                "fixed_position_km": original_position["fixed_position_km"],
                "original_best": original_position["best"],
                "refinement_attempts": [_compact(attempt) for attempt in attempts],
                "selected_from": selected_from,
                "best": best,
                "gradient_change": gradient_change(original_position["best"], best),
                "ranking_resolved": bool(best.get("success", False)),
                "refinement_not_run": bool(
                    original_position["kind"] == "radial" and not attempts
                ),
            }
        )
    radial = [position for position in updated_positions if position["kind"] == "radial"]
    elapsed = time.monotonic() - wall_started
    result = {
        "schema": "ds13-position-profile-refinement/v1",
        "session": session,
        "original_receipt": str(original_path),
        "original_receipt_sha256": digest(original_path),
        "protocol_sha256": digest(protocol_path),
        "resource_amendment_sha256": digest(amendment_path),
        "source_hashes": source_hashes,
        "stage_budget_s": STAGE_BUDGET_S,
        "wall_budget_s": WALL_BUDGET_S,
        "maximum_workers": MAX_WORKERS,
        "elapsed_s": elapsed,
        "priority_order": priority,
        "positions": updated_positions,
        "refined_position_count": int(sum(bool(refinements[label]) for label in priority)),
        "refinement_attempt_count": int(sum(map(len, refinements.values()))),
        "resolved_radial_count": int(sum(position["ranking_resolved"] for position in radial)),
        "unresolved_position_labels": [
            position["label"] for position in radial if not position["ranking_resolved"]
        ],
        "not_run_position_labels": [
            position["label"] for position in radial if position["refinement_not_run"]
        ],
        "complete": bool(all(not position["refinement_not_run"] for position in radial)),
        "scope": (
            "Bounded continuation of finite nonconverged B-grid states. South 50/100/500 "
            "meter cells receive first priority and at most two eight-second continuations; "
            "other cells receive one pass, then a second only if wall budget remains. "
            "Lower finite states are retained even when nonconverged. This refines local "
            "nuisance basins only and does not certify global position rankings."
        ),
    }
    assert_snapshot_unchanged(source_hashes)
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "elapsed_s": elapsed,
        "refined_position_count": result["refined_position_count"],
        "refinement_attempt_count": result["refinement_attempt_count"],
        "resolved_radial_count": result["resolved_radial_count"],
        "not_run_position_count": len(result["not_run_position_labels"]),
    }


def main():
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    print(json.dumps(serializable(run_case())), flush=True)


if __name__ == "__main__":
    main()


__all__ = ["gradient_change", "priority_labels", "run_case", "select_updated_best"]
