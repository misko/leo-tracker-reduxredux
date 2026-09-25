#!/usr/bin/env python3
"""DS1 iteration 20: whole-session-balanced nominal-Doppler basin.

The geographic selector deliberately has no orbit-rate degrees of freedom.
It scores each recording independently after profiling only its track CFOs.
The final coordinate then receives, but is not selected by, a widened exact
per-NORAD-rate audit.
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

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
PARENT = ROOT / "reports/2026_09_24_ds1_iteration15_information_weighted/inference.json"
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
RATE_AUDIT = ROOT / "reports/2026_09_25_ds1_iteration19_rate_bound_audit/run.py"
ITERATION10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
GROUPS = ("20260921_00", "20260921_16")
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
TAUS = {"20260921_00": -0.75, "20260921_16": -0.50}
RATE_BOUND_S_H = 0.50
RATE_XATOL_S_H = 2e-7
BOUNDARY_MARGIN_S_H = max(5.0 * RATE_XATOL_S_H, 1e-6)


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


def key(east: float, north: float) -> tuple[float, float]:
    return (round(float(east), 10), round(float(north), 10))


def verify_inputs(parent_path: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    parent, plan = json.loads(parent_path.read_text()), json.loads(plan_path.read_text())
    if parent.get("schema") != "ds1-iteration15-information-weighted-basin/v1":
        raise ValueError("parent must be qualified iteration15 inference")
    # Iteration15 is an immutable, reference-free origin and contract source;
    # it is not evidence that its own scientific qualification remains valid.
    if not parent.get("complete"):
        raise ValueError("parent must be complete")
    if parent.get("reference_used_for_fit") is not False:
        raise ValueError("parent is not reference-free")
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("plan must prohibit reference use")
    if plan.get("group_weights") != GROUP_WEIGHTS or plan.get("group_taus_s") != TAUS:
        raise ValueError("frozen group contract mismatch")
    return parent, plan


def lattice(
    driver: Any, origin: dict[str, float], center: tuple[float, float], spacing: float
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for north_step in (-1, 0, 1):
        for east_step in (-1, 0, 1):
            east, north = center[0] + east_step * spacing, center[1] + north_step * spacing
            row = driver.local_coordinate(origin, east, north)
            row["east_km_from_parent"], row["north_km_from_parent"] = east, north
            rows.append(row)
    return rows


def on_edge(row: dict[str, Any], center: tuple[float, float], spacing: float) -> bool:
    east = round((float(row["east_km_from_parent"]) - center[0]) / spacing)
    north = round((float(row["north_km_from_parent"]) - center[1]) / spacing)
    return abs(east) == 1 or abs(north) == 1


def capped_loss(driver: Any, error: np.ndarray, model: Any, rows: np.ndarray) -> float:
    tracks = model.track_names
    total, weight = 0.0, 0.0
    for index, name in enumerate(tracks):
        selected = rows & (model.track_index == index)
        if not np.any(selected):
            continue
        rms = float(np.sqrt(np.mean(error[selected] ** 2)))
        item_weight = float(model.data.weights[str(name)])
        total += item_weight * min((rms / 800.0) ** 2, 1.0)
        weight += item_weight
    if weight <= 0:
        raise ValueError("session has no scored tracks")
    return total / weight


def nominal_session_score(driver: Any, model: Any) -> dict[str, Any]:
    """Profile CFO within each track, then give each recording one vote."""
    zero = np.zeros(len(model.source_names), float)
    error, _base, _raw = model.residual(zero, np.zeros(1 + len(model.session_names)))
    sessions = []
    for index, sid in enumerate(model.session_names):
        rows = model.session_index == index
        sessions.append(
            {
                "session_id": str(sid),
                "observation_count": int(rows.sum()),
                "track_count": int(len(np.unique(model.track_index[rows]))),
                "nominal_capped_loss": capped_loss(driver, error, model, rows),
            }
        )
    return {
        "session_scores": sessions,
        "equal_session_nominal_capped_loss": float(
            np.mean([r["nominal_capped_loss"] for r in sessions])
        ),
    }


def geographic_audit(task: tuple[str, dict[str, float], dict[str, Any]]) -> dict[str, Any]:
    group, point, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load_module(DRIVER, f"i20_driver_{group}_{os.getpid()}")
    prepared_group = dict(sealed_group)
    prepared_group["tau_s"] = TAUS[group]
    begun = time.perf_counter()
    model = driver._prepared_model(group, point, prepared_group)
    return {
        **point,
        "group_id": group,
        "tau_s": TAUS[group],
        "fixed_association_count": len(sealed_group["track_associations"]),
        "sample_count": len(model.data.y),
        "source_count": len(model.source_names),
        "nominal_session_score": nominal_session_score(driver, model),
        "elapsed_s": time.perf_counter() - begun,
    }


def combine(audits: list[dict[str, Any]], points: list[dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for point in points:
        matches = [
            r
            for r in audits
            if key(r["east_km_from_parent"], r["north_km_from_parent"])
            == key(point["east_km_from_parent"], point["north_km_from_parent"])
        ]
        if len(matches) != len(GROUPS):
            raise ValueError("incomplete group coordinate")
        by_group = {r["group_id"]: r for r in matches}
        rows.append(
            {
                **point,
                "weighted_equal_session_nominal_capped_loss": sum(
                    GROUP_WEIGHTS[g]
                    * by_group[g]["nominal_session_score"]["equal_session_nominal_capped_loss"]
                    for g in GROUPS
                ),
                "group_equal_session_nominal_capped_loss": {
                    g: by_group[g]["nominal_session_score"]["equal_session_nominal_capped_loss"]
                    for g in GROUPS
                },
            }
        )
    return sorted(
        rows,
        key=lambda r: (
            r["weighted_equal_session_nominal_capped_loss"],
            r["north_km_from_parent"],
            r["east_km_from_parent"],
        ),
    )


def widened_rate_audit(
    point: dict[str, float], sealed_groups: dict[str, Any]
) -> list[dict[str, Any]]:
    """Exact rate audit with an effective-boundary test stricter than xatol."""
    driver, orbit = load_module(DRIVER, "i20_rate_driver"), load_module(ORBIT, "i20_rate_orbit")
    rate_audit = load_module(RATE_AUDIT, "i20_rate_active_set")
    # Reuse the iteration19 active-set continuation: it first solves the
    # validated +/-0.25 control interval, then opens only the adjacent outer
    # interval when the control fit touches that guard.  A blind +/-0.5 scalar
    # search can jump between orbital-phase minima.
    rate_audit.configure_driver(driver)
    try:
        rows = []
        for group in GROUPS:
            prepared_group = dict(sealed_groups[group])
            prepared_group["tau_s"] = TAUS[group]
            model = driver._prepared_model(group, point, prepared_group)
            fit = driver.fit(model, scales_enabled=False)
            rates = np.asarray(list(fit["rates_s_h"].values()), float)
            near = int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - BOUNDARY_MARGIN_S_H))
            gate = orbit.exact_replay_gate(
                model.data,
                model.receiver,
                model.search,
                TAUS[group],
                fit["rates_s_h"],
                tolerance_hz=0.2,
            )
            rows.append(
                {
                    "group_id": group,
                    "rate_bound_s_h": RATE_BOUND_S_H,
                    "scalar_optimizer_xatol_s_h": RATE_XATOL_S_H,
                    "effective_boundary_margin_s_h": BOUNDARY_MARGIN_S_H,
                    "fit_converged": bool(fit["converged"]),
                    "effective_boundary_rate_count": near,
                    "maximum_absolute_rate_s_h": float(np.max(np.abs(rates)))
                    if len(rates)
                    else 0.0,
                    "selection_objective": float(fit["selection_objective"]),
                    "exact_full_observation_capped_loss": float(
                        fit["exact_full_observation_capped_loss"]
                    ),
                    "rates_s_h": fit["rates_s_h"],
                    "exact_sgp4_gate": gate,
                }
            )
        return rows
    finally:
        # This process-local driver is discarded after the audit.  Restoring
        # the public constant nevertheless makes direct unit use predictable.
        driver.RATE_BOUND_S_H = 0.25


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
    parent, plan = verify_inputs(args.parent, args.plan)
    driver = load_module(DRIVER, "i20_main_driver")
    sealed = driver.load_iteration10(ITERATION10)
    sealed_groups = sealed["winner"]["best_exact_by_group"]
    origin = {name: float(parent["winner"][name]) for name in ("latitude_deg", "longitude_deg")}
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[tuple[str, float, float], dict[str, Any]] = {}
    steps, center, complete = [], (0.0, 0.0), True
    begun = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        for stage_index, stage in enumerate(plan["stages"]):
            spacing, closed = float(stage["spacing_km"]), False
            for translation in range(int(stage["maximum_translations"]) + 1):
                points = lattice(driver, origin, center, spacing)
                missing = [
                    (g, p, sealed_groups[g])
                    for p in points
                    for g in GROUPS
                    if (g, *key(p["east_km_from_parent"], p["north_km_from_parent"])) not in cache
                ]
                for result in pool.map(geographic_audit, missing, chunksize=1):
                    cache[
                        (
                            result["group_id"],
                            *key(result["east_km_from_parent"], result["north_km_from_parent"]),
                        )
                    ] = result
                relevant = [
                    cache[(g, *key(p["east_km_from_parent"], p["north_km_from_parent"]))]
                    for p in points
                    for g in GROUPS
                ]
                ranked = combine(relevant, points)
                winner = ranked[0]
                edge = on_edge(winner, center, spacing)
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
                (args.checkpoint_dir / f"stage-{stage_index}-step-{translation}.json").write_text(
                    json.dumps(step, indent=2, sort_keys=True) + "\n"
                )
                center = (
                    float(winner["east_km_from_parent"]),
                    float(winner["north_km_from_parent"]),
                )
                if not edge:
                    closed = True
                    break
            if not closed:
                complete = False
                break
    winner = steps[-1]["winner"]
    rate_audits = widened_rate_audit(winner, sealed_groups) if complete else []
    rate_qualified = bool(
        rate_audits
        and all(
            r["fit_converged"]
            and r["effective_boundary_rate_count"] == 0
            and r["exact_sgp4_gate"]["passed"]
            for r in rate_audits
        )
    )
    output = {
        "schema": "ds1-iteration20-session-predictive-inference/v1",
        "complete": complete,
        "qualified": bool(complete and not steps[-1]["winner_on_edge"] and rate_qualified),
        "reference_used_for_fit": False,
        "partition": "train",
        "status": "qualified" if complete and rate_qualified else "unqualified",
        "origin": origin,
        "plan": {"path": str(args.plan), "sha256": digest(args.plan)},
        "parent": {"path": str(args.parent), "sha256": digest(args.parent)},
        "iteration10": {"path": str(ITERATION10), "sha256": digest(ITERATION10)},
        "group_weights": GROUP_WEIGHTS,
        "group_taus_s": TAUS,
        "steps": steps,
        "winner": winner,
        "unique_group_coordinate_fits": len(cache),
        "final_widened_rate_audit": rate_audits,
        "effective_boundary_rule": {
            "rate_bound_s_h": RATE_BOUND_S_H,
            "rate_xatol_s_h": RATE_XATOL_S_H,
            "margin_s_h": BOUNDARY_MARGIN_S_H,
        },
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {
            "runner": digest(Path(__file__)),
            "driver": digest(DRIVER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "complete": complete,
                "qualified": output["qualified"],
                "winner": winner,
            }
        )
    )


if __name__ == "__main__":
    main()
