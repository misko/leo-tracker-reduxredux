#!/usr/bin/env python3
"""Refresh DS1 group timing, then close a fixed-identity exact-rate basin."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
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
PARENT = ROOT / "reports/2026_09_24_ds1_iteration15_information_weighted/inference.json"
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
ITERATION10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
GROUPS = ("20260921_00", "20260921_16")
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
INITIAL_TAUS_S = {"20260921_00": -0.75, "20260921_16": -0.50}
TIMING_SCHEMA = "ds1-iteration18-timing-refresh/v1"
INFERENCE_SCHEMA = "ds1-iteration18-timing-refresh-basin/v1"
CHECKPOINT_SCHEMA = "ds1-iteration18-checkpoint/v1"


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


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def load_inputs(parent_path: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    parent = json.loads(parent_path.read_text())
    plan = json.loads(plan_path.read_text())
    if parent.get("schema") != "ds1-iteration15-information-weighted-basin/v1":
        raise ValueError("parent must be the iteration-15 inference")
    if parent.get("complete") is not True or parent.get("qualified") is not True:
        raise ValueError("parent must be complete and qualified")
    if parent.get("reference_used_for_fit") is not False:
        raise ValueError("parent must be reference-free")
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("plan must prohibit reference use")
    if plan.get("group_weights") != GROUP_WEIGHTS:
        raise ValueError("plan group weights do not match the runner")
    if plan.get("initial_group_taus_s") != INITIAL_TAUS_S:
        raise ValueError("plan initial taus do not match the runner")
    timing = plan.get("timing_search", {})
    if timing != {
        "node_count": 9,
        "spacing_s": 0.05,
        "half_width_s": 0.2,
        "maximum_translations": 4,
        "transition_rule": (
            "recenter by 0.20 s at unchanged spacing while the winner is on an edge"
        ),
        "acceptance_rule": (
            "each group must select an interior converged timing node before geographic search"
        ),
    }:
        raise ValueError("unexpected timing-search contract")
    return parent, plan


def checkpoint_context(plan_path: Path, parent_path: Path) -> dict[str, str]:
    return {
        "plan_sha256": digest(plan_path),
        "parent_sha256": digest(parent_path),
        "iteration10_sha256": digest(ITERATION10),
    }


def validate_checkpoint(
    path: Path,
    *,
    context: dict[str, Any],
    kind: str,
    group_id: str | None = None,
    stage_index: int | None = None,
    translation_index: int,
) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("schema") != CHECKPOINT_SCHEMA or value.get("context") != context:
        raise ValueError(f"stale or malformed checkpoint: {path}")
    if value.get("kind") != kind or value.get("translation_index") != translation_index:
        raise ValueError(f"checkpoint identity mismatch: {path}")
    if group_id is not None and value.get("group_id") != group_id:
        raise ValueError(f"checkpoint group mismatch: {path}")
    if stage_index is not None and value.get("stage_index") != stage_index:
        raise ValueError(f"checkpoint stage mismatch: {path}")
    return value


def tau_key(tau_s: float) -> float:
    return round(float(tau_s), 10)


def tau_grid(center_s: float) -> list[float]:
    return [tau_key(center_s + step * 0.05) for step in range(-4, 5)]


def timing_winner(rows: list[dict[str, Any]], center_s: float) -> tuple[dict[str, Any], bool]:
    converged = [row for row in rows if row["rate_only"]["converged"]]
    if not converged:
        raise ValueError("no converged timing node")
    winner = min(
        converged,
        key=lambda row: (
            float(row["rate_only"]["selection_objective"]),
            abs(float(row["tau_s"]) - center_s),
            float(row["tau_s"]),
        ),
    )
    edge = abs(float(winner["tau_s"]) - center_s) >= 0.2 - 1e-10
    return winner, edge


def timing_audit(
    task: tuple[str, float, dict[str, float], dict[str, Any]]
) -> dict[str, Any]:
    group, tau_s, point, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load_module(DRIVER, f"i18_timing_driver_{group}_{os.getpid()}")
    refreshed = copy.deepcopy(sealed_group)
    refreshed["tau_s"] = float(tau_s)
    begun = time.perf_counter()
    model = driver._prepared_model(group, point, refreshed)
    fit = driver.fit(model, scales_enabled=False)
    return {
        "group_id": group,
        "tau_s": float(tau_s),
        "fixed_association_count": len(sealed_group["track_associations"]),
        "sample_count": len(model.data.y),
        "source_count": len(model.source_names),
        "rate_only": fit,
        "elapsed_s": time.perf_counter() - begun,
    }


def run_timing_group(
    *,
    pool: concurrent.futures.ProcessPoolExecutor,
    group: str,
    point: dict[str, float],
    sealed_group: dict[str, Any],
    checkpoint_dir: Path,
    context: dict[str, Any],
    maximum_translations: int,
) -> dict[str, Any]:
    center_s = INITIAL_TAUS_S[group]
    cache: dict[float, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    for translation in range(maximum_translations + 1):
        checkpoint = checkpoint_dir / f"timing-{group}-step-{translation}.json"
        if checkpoint.exists():
            step = validate_checkpoint(
                checkpoint,
                context=context,
                kind="timing",
                group_id=group,
                translation_index=translation,
            )
            if abs(float(step["center_tau_s"]) - center_s) > 1e-10:
                raise ValueError(f"timing checkpoint center mismatch: {checkpoint}")
            for row in step["audits"]:
                cache[tau_key(row["tau_s"])] = row
        else:
            nodes = tau_grid(center_s)
            missing = [tau for tau in nodes if tau not in cache]
            tasks = [(group, tau, point, sealed_group) for tau in missing]
            for row in pool.map(timing_audit, tasks, chunksize=1):
                cache[tau_key(row["tau_s"])] = row
            rows = [cache[tau] for tau in nodes]
            winner, edge = timing_winner(rows, center_s)
            step = {
                "schema": CHECKPOINT_SCHEMA,
                "kind": "timing",
                "context": context,
                "group_id": group,
                "translation_index": translation,
                "center_tau_s": center_s,
                "spacing_s": 0.05,
                "audits": rows,
                "new_fit_count": len(missing),
                "winner": winner,
                "winner_on_edge": edge,
            }
            write_json_atomic(checkpoint, step)
        steps.append(step)
        winner = step["winner"]
        if not step["winner_on_edge"]:
            return {
                "group_id": group,
                "complete": True,
                "qualified": True,
                "initial_tau_s": INITIAL_TAUS_S[group],
                "selected_tau_s": float(winner["tau_s"]),
                "selected_fit": winner,
                "steps": steps,
                "unique_tau_fits": len(cache),
            }
        center_s = float(winner["tau_s"])
    return {
        "group_id": group,
        "complete": True,
        "qualified": False,
        "initial_tau_s": INITIAL_TAUS_S[group],
        "selected_tau_s": None,
        "boundary_fit": steps[-1]["winner"],
        "steps": steps,
        "unique_tau_fits": len(cache),
        "reason": "timing winner remained on an edge after the translation budget",
    }


def load_timing_seal(
    path: Path, *, context: dict[str, Any]
) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file():
        raise ValueError("timing seal SHA-256 sidecar is missing")
    expected_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if sidecar.read_text().strip() != expected_digest:
        raise ValueError("timing seal SHA-256 sidecar does not match")
    value = json.loads(path.read_text())
    if value.get("schema") != TIMING_SCHEMA or value.get("context") != context:
        raise ValueError("timing seal does not match the current inputs")
    if value.get("reference_used_for_fit") is not False:
        raise ValueError("timing seal is not reference-free")
    return value


def geographic_checkpoint_context(
    context: dict[str, Any], timing_path: Path, timing: dict[str, Any]
) -> dict[str, Any]:
    return {
        **context,
        "timing_sha256": digest(timing_path),
        "selected_taus_s": timing["selected_taus_s"],
    }


def seal_timing_refresh(
    *,
    path: Path,
    pool: concurrent.futures.ProcessPoolExecutor,
    point: dict[str, float],
    sealed_groups: dict[str, Any],
    checkpoint_dir: Path,
    context: dict[str, Any],
    maximum_translations: int,
) -> dict[str, Any]:
    if path.exists():
        return load_timing_seal(path, context=context)
    begun = time.perf_counter()
    groups = {
        group: run_timing_group(
            pool=pool,
            group=group,
            point=point,
            sealed_group=sealed_groups[group],
            checkpoint_dir=checkpoint_dir,
            context=context,
            maximum_translations=maximum_translations,
        )
        for group in GROUPS
    }
    qualified = all(groups[group]["qualified"] for group in GROUPS)
    selected = (
        {group: groups[group]["selected_tau_s"] for group in GROUPS}
        if qualified
        else None
    )
    output = {
        "schema": TIMING_SCHEMA,
        "complete": True,
        "qualified": qualified,
        "reference_used_for_fit": False,
        "context": context,
        "coordinate": point,
        "association_policy": "fixed iteration-10 hard associations",
        "selection_policy": "independent per-group regularized selection objective",
        "groups": groups,
        "selected_taus_s": selected,
        "elapsed_s": time.perf_counter() - begun,
    }
    write_json_atomic(path, output)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )
    return output


def point_key(east_km: float, north_km: float) -> tuple[float, float]:
    return round(float(east_km), 10), round(float(north_km), 10)


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
            row["east_km_from_parent"] = east
            row["north_km_from_parent"] = north
            rows.append(row)
    return rows


def geographic_audit(
    task: tuple[str, dict[str, float], dict[str, Any], float]
) -> dict[str, Any]:
    group, point, sealed_group, tau_s = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load_module(DRIVER, f"i18_geo_driver_{group}_{os.getpid()}")
    refreshed = copy.deepcopy(sealed_group)
    refreshed["tau_s"] = float(tau_s)
    begun = time.perf_counter()
    model = driver._prepared_model(group, point, refreshed)
    fit = driver.fit(model, scales_enabled=False)
    return {
        **point,
        "group_id": group,
        "tau_s": float(tau_s),
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
        key = point_key(point["east_km_from_parent"], point["north_km_from_parent"])
        grouped = [
            row
            for row in audits
            if point_key(row["east_km_from_parent"], row["north_km_from_parent"]) == key
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
            row["north_km_from_parent"],
            row["east_km_from_parent"],
        ),
    )


def is_edge(winner: dict[str, Any], center: tuple[float, float], spacing: float) -> bool:
    east_step = round((winner["east_km_from_parent"] - center[0]) / spacing)
    north_step = round((winner["north_km_from_parent"] - center[1]) / spacing)
    return abs(east_step) == 1 or abs(north_step) == 1


def run_geographic_search(
    *,
    pool: concurrent.futures.ProcessPoolExecutor,
    driver: Any,
    origin: dict[str, float],
    sealed_groups: dict[str, Any],
    selected_taus: dict[str, float],
    stages: list[dict[str, Any]],
    checkpoint_dir: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    cache: dict[tuple[str, float, float], dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    center = (0.0, 0.0)
    complete = True
    for stage_index, stage in enumerate(stages):
        spacing = float(stage["spacing_km"])
        stage_closed = False
        for translation in range(int(stage["maximum_translations"]) + 1):
            checkpoint = checkpoint_dir / f"stage-{stage_index}-step-{translation}.json"
            if checkpoint.exists():
                step = validate_checkpoint(
                    checkpoint,
                    context=context,
                    kind="geographic",
                    stage_index=stage_index,
                    translation_index=translation,
                )
                if (
                    abs(float(step["center_east_km"]) - center[0]) > 1e-10
                    or abs(float(step["center_north_km"]) - center[1]) > 1e-10
                    or abs(float(step["spacing_km"]) - spacing) > 1e-12
                ):
                    raise ValueError(f"geographic checkpoint geometry mismatch: {checkpoint}")
                for row in step["group_audits"]:
                    key = point_key(row["east_km_from_parent"], row["north_km_from_parent"])
                    cache[(row["group_id"], *key)] = row
            else:
                points = lattice(driver, origin, center, spacing)
                missing = []
                for point in points:
                    point_id = point_key(
                        point["east_km_from_parent"], point["north_km_from_parent"]
                    )
                    for group in GROUPS:
                        if (group, *point_id) not in cache:
                            missing.append(
                                (group, point, sealed_groups[group], selected_taus[group])
                            )
                for row in pool.map(geographic_audit, missing, chunksize=1):
                    key = point_key(row["east_km_from_parent"], row["north_km_from_parent"])
                    cache[(row["group_id"], *key)] = row
                relevant = [
                    cache[(group, *point_key(
                        point["east_km_from_parent"], point["north_km_from_parent"]
                    ))]
                    for point in points
                    for group in GROUPS
                ]
                ranked = combine(relevant, points)
                winner = ranked[0]
                step = {
                    "schema": CHECKPOINT_SCHEMA,
                    "kind": "geographic",
                    "context": context,
                    "stage_index": stage_index,
                    "translation_index": translation,
                    "spacing_km": spacing,
                    "center_east_km": center[0],
                    "center_north_km": center[1],
                    "new_group_coordinate_fits": len(missing),
                    "group_audits": relevant,
                    "ranked_coordinates": ranked,
                    "winner": winner,
                    "winner_on_edge": is_edge(winner, center, spacing),
                }
                write_json_atomic(checkpoint, step)
            steps.append(step)
            winner = step["winner"]
            center = (
                float(winner["east_km_from_parent"]),
                float(winner["north_km_from_parent"]),
            )
            if not step["winner_on_edge"]:
                stage_closed = True
                break
        if not stage_closed:
            complete = False
            break
    final = steps[-1]["winner"]
    final_key = point_key(final["east_km_from_parent"], final["north_km_from_parent"])
    return {
        "complete": complete,
        "qualified": complete and not steps[-1]["winner_on_edge"],
        "steps": steps,
        "winner": final,
        "selected_group_audits": [cache[(group, *final_key)] for group in GROUPS],
        "unique_group_coordinate_fits": len(cache),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=PARENT)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--timing-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    parent, plan = load_inputs(args.parent, args.plan)
    driver = load_module(DRIVER, "i18_driver_main")
    iteration10 = driver.load_iteration10(ITERATION10)
    sealed_groups = iteration10["winner"]["best_exact_by_group"]
    for group in GROUPS:
        if abs(float(sealed_groups[group]["tau_s"]) - INITIAL_TAUS_S[group]) > 1e-10:
            raise ValueError(f"iteration-10 tau changed for {group}")
    origin = {
        name: float(parent["winner"][name]) for name in ("latitude_deg", "longitude_deg")
    }
    context = checkpoint_context(args.plan, args.parent)
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        timing = seal_timing_refresh(
            path=args.timing_output,
            pool=pool,
            point=origin,
            sealed_groups=sealed_groups,
            checkpoint_dir=args.checkpoint_dir,
            context=context,
            maximum_translations=int(plan["timing_search"]["maximum_translations"]),
        )
        geographic_context = geographic_checkpoint_context(
            context, args.timing_output, timing
        )
        if timing["qualified"]:
            geographic = run_geographic_search(
                pool=pool,
                driver=driver,
                origin=origin,
                sealed_groups=sealed_groups,
                selected_taus=timing["selected_taus_s"],
                stages=plan["geographic_stages"],
                checkpoint_dir=args.checkpoint_dir,
                context=geographic_context,
            )
        else:
            geographic = None
    output = {
        "schema": INFERENCE_SCHEMA,
        "complete": bool(timing["complete"] and (geographic is None or geographic["complete"])),
        "qualified": bool(timing["qualified"] and geographic and geographic["qualified"]),
        "status": (
            "timing_boundary_unqualified"
            if not timing["qualified"]
            else "geographic_complete"
            if geographic and geographic["complete"]
            else "geographic_boundary_unqualified"
        ),
        "partition": "train",
        "reference_used_for_fit": False,
        "plan": {"path": str(args.plan), "sha256": digest(args.plan)},
        "parent": {"path": str(args.parent), "sha256": digest(args.parent)},
        "iteration10": {"path": str(ITERATION10), "sha256": digest(ITERATION10)},
        "timing_refresh": {
            "path": str(args.timing_output),
            "sha256": digest(args.timing_output),
            "qualified": timing["qualified"],
            "selected_taus_s": timing["selected_taus_s"],
        },
        "origin": origin,
        "group_weights": GROUP_WEIGHTS,
        "association_policy": "fixed iteration-10 hard associations",
        "geographic_search_started": geographic is not None,
        "geographic": geographic,
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {"runner": digest(Path(__file__)), "driver": digest(DRIVER)},
    }
    write_json_atomic(args.output, output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": output["status"],
                "qualified": output["qualified"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
