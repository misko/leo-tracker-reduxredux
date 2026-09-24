#!/usr/bin/env python3
"""DS1 iteration 14: raw cap-800 basin closure on stable associations.

The sealed iteration-12 rate-only surface established that fixed iteration-10
identities select the same cells as the scale hierarchy.  This runner removes
the scale nuisance and continues the matched exact cap-800 objective only in
directions where the current symmetric lattice has an edge winner.  Existing
exact rate-only cells are reused; no reference coordinate is accepted.
"""

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
ITER10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
ITER12 = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/refinement.json"
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
PLAN = HERE / "plan.json"

FULL_SPACING_KM = 0.09765625
HALF_SPACING_KM = FULL_SPACING_KM / 2
MAX_FULL_EDGE_STEPS = 8
MAX_HALF_EDGE_STEPS = 4
GROUPS = ("20260921_00", "20260921_16")


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


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def coordinate_key(point: dict[str, Any]) -> tuple[float, float]:
    return round(float(point["latitude_deg"]), 11), round(float(point["longitude_deg"]), 11)


def local_coordinate(
    origin: dict[str, float], east_km: float, north_km: float
) -> dict[str, float]:
    return {
        "latitude_deg": float(origin["latitude_deg"]) + north_km / 111.32,
        "longitude_deg": float(origin["longitude_deg"])
        + east_km
        / (111.32 * math.cos(math.radians(float(origin["latitude_deg"])))),
    }


def lattice(origin: dict[str, float], spacing_km: float) -> list[dict[str, float]]:
    return [
        {
            **local_coordinate(origin, east, north),
            "east_km_from_level_origin": east,
            "north_km_from_level_origin": north,
        }
        for north in (-spacing_km, 0.0, spacing_km)
        for east in (-spacing_km, 0.0, spacing_km)
    ]


def validate_inputs(iter10_path: Path, iter12_path: Path) -> tuple[dict, dict]:
    iteration10 = json.loads(iter10_path.read_text())
    iteration12 = json.loads(iter12_path.read_text())
    if (
        iteration10.get("complete") is not True
        or iteration10.get("reference_used_for_fit") is not False
        or iteration12.get("complete") is not True
        or iteration12.get("reference_used_for_fit") is not False
    ):
        raise ValueError("inputs must be completed reference-free inferences")
    if iteration12.get("association_policy") != "same fixed iteration-10 hard supports as level 1":
        raise ValueError("iteration-12 does not attest the stable association policy")
    if set(iteration10["winner"]["best_exact_by_group"]) != set(GROUPS):
        raise ValueError("iteration-10 group support is incomplete")
    return iteration10, iteration12


def reused_rows(iteration12: dict[str, Any]) -> dict[tuple[float, float], dict[str, Any]]:
    output = {}
    for source in iteration12["baseline_rate_only_rows"]:
        row = {
            "latitude_deg": float(source["latitude_deg"]),
            "longitude_deg": float(source["longitude_deg"]),
            "balanced_exact_capped_loss": float(source["balanced_exact_capped_loss"]),
            "balanced_selection_objective": float(source["balanced_selection_objective"]),
            "all_converged": bool(source["all_converged"]),
            "source": "reused sealed iteration-12 rate-only cell",
            "group_audits": None,
        }
        output[coordinate_key(row)] = row
    if len(output) != 9:
        raise ValueError("expected the sealed iteration-12 3x3 rate-only surface")
    return output


def audit(task: tuple[dict[str, float], str, dict[str, Any]]) -> dict[str, Any]:
    point, group, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    driver = load(DRIVER, f"i13_driver_{group}_{os.getpid()}")
    model = driver._prepared_model(group, point, sealed_group)
    fit = driver.fit(model, scales_enabled=False)
    return {
        "group_id": group,
        "latitude_deg": point["latitude_deg"],
        "longitude_deg": point["longitude_deg"],
        "sample_count": len(model.data.y),
        "session_count": len(model.session_names),
        "source_count": len(model.source_names),
        "fit": fit,
    }


def aggregate(point: dict[str, float], audits: list[dict[str, Any]]) -> dict[str, Any]:
    fits = [row["fit"] for row in sorted(audits, key=lambda row: row["group_id"])]
    if len(fits) != len(GROUPS):
        raise ValueError("incomplete group audit")
    return {
        "latitude_deg": point["latitude_deg"],
        "longitude_deg": point["longitude_deg"],
        "balanced_exact_capped_loss": 0.5
        * sum(float(fit["exact_full_observation_capped_loss"]) for fit in fits),
        "balanced_selection_objective": 0.5
        * sum(float(fit["selection_objective"]) for fit in fits),
        "all_converged": bool(all(fit["converged"] for fit in fits)),
        "source": "fresh iteration-13 fixed-association exact rate fit",
        "group_audits": audits,
    }


def ranking_key(row: dict[str, Any]) -> tuple[float, float, float, float]:
    if not row["all_converged"]:
        return (math.inf, math.inf, row["latitude_deg"], row["longitude_deg"])
    return (
        row["balanced_exact_capped_loss"],
        row["balanced_selection_objective"],
        row["latitude_deg"],
        row["longitude_deg"],
    )


def is_boundary(row: dict[str, Any], origin: dict[str, float], spacing_km: float) -> bool:
    lat_step = spacing_km / 111.32
    lon_step = spacing_km / (
        111.32 * math.cos(math.radians(float(origin["latitude_deg"])))
    )
    return bool(
        abs(row["latitude_deg"] - origin["latitude_deg"]) >= lat_step - 1e-10
        or abs(row["longitude_deg"] - origin["longitude_deg"]) >= lon_step - 1e-10
    )


def exact_gate(task: tuple[dict[str, Any], str, dict[str, Any]]) -> dict[str, Any]:
    winner, group, sealed_group = task
    driver = load(DRIVER, f"i13_gate_driver_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"i13_gate_orbit_{group}_{os.getpid()}")
    model = driver._prepared_model(group, winner, sealed_group)
    fit = driver.fit(model, scales_enabled=False)
    gate = orbit.exact_replay_gate(
        model.data,
        model.receiver,
        model.search,
        float(sealed_group["tau_s"]),
        fit["rates_s_h"],
        tolerance_hz=0.2,
    )
    return {"group_id": group, "fit": fit, "exact_gate": gate}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration10", type=Path, default=ITER10)
    parser.add_argument("--iteration12", type=Path, default=ITER12)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    iteration10, iteration12 = validate_inputs(args.iteration10, args.iteration12)
    plan = json.loads(PLAN.read_text())
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("plan must prohibit reference use")
    sealed_groups = iteration10["winner"]["best_exact_by_group"]
    cache = reused_rows(iteration12)
    origin = {
        key: float(iteration12["winner"][key])
        for key in ("latitude_deg", "longitude_deg")
    }
    levels = []
    phase_outcomes = []
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        for spacing, maximum_steps, phase in (
            (FULL_SPACING_KM, MAX_FULL_EDGE_STEPS, "edge-continuation"),
            (HALF_SPACING_KM, MAX_HALF_EDGE_STEPS, "half-step-confirmation"),
        ):
            for step in range(1, maximum_steps + 1):
                points = lattice(origin, spacing)
                fresh = [point for point in points if coordinate_key(point) not in cache]
                tasks = [
                    (point, group, sealed_groups[group])
                    for point in fresh
                    for group in GROUPS
                ]
                fresh_audits = list(pool.map(audit, tasks, chunksize=1))
                for point in fresh:
                    audits = [
                        row
                        for row in fresh_audits
                        if coordinate_key(row) == coordinate_key(point)
                    ]
                    cache[coordinate_key(point)] = aggregate(point, audits)
                rows = [cache[coordinate_key(point)] for point in points]
                winner = min(rows, key=ranking_key)
                boundary = is_boundary(winner, origin, spacing)
                levels.append(
                    {
                        "phase": phase,
                        "step": step,
                        "spacing_km": spacing,
                        "origin": origin,
                        "fresh_coordinate_count": len(fresh),
                        "rows": rows,
                        "winner": {
                            key: winner[key]
                            for key in (
                                "latitude_deg",
                                "longitude_deg",
                                "balanced_exact_capped_loss",
                                "balanced_selection_objective",
                                "source",
                            )
                        },
                        "winner_on_boundary": boundary,
                    }
                )
                origin = {
                    "latitude_deg": winner["latitude_deg"],
                    "longitude_deg": winner["longitude_deg"],
                }
                if not boundary:
                    break
            phase_outcomes.append(
                {
                    "phase": phase,
                    "closed_on_interior_cell": not boundary,
                    "steps_used": step,
                    "maximum_steps": maximum_steps,
                }
            )
            if boundary:
                break
        final = min(levels[-1]["rows"], key=ranking_key)
        gates = list(
            pool.map(
                exact_gate,
                [(final, group, sealed_groups[group]) for group in GROUPS],
                chunksize=1,
            )
        )
    qualified = bool(
        final["all_converged"]
        and all(row["exact_gate"]["passed"] for row in gates)
        and len(phase_outcomes) == 2
        and all(row["closed_on_interior_cell"] for row in phase_outcomes)
    )
    output = {
        "schema": "ds1-iteration14-cap800-basin/v1",
        "complete": len(phase_outcomes) == 2
        and all(row["closed_on_interior_cell"] for row in phase_outcomes),
        "partition": "train",
        "reference_used_for_fit": False,
        "truth_used_for_fit": False,
        "iteration10_input": {"path": str(args.iteration10), "sha256": digest(args.iteration10)},
        "iteration12_input": {"path": str(args.iteration12), "sha256": digest(args.iteration12)},
        "plan": {"path": str(PLAN), "sha256": digest(PLAN)},
        "association_policy": "fixed sealed iteration-10 hard identities at every coordinate",
        "objective_policy": (
            "equal-group exact full-observation cap-800 loss; rate priors fit nuisance rates "
            "but do not enter geographic ranking"
        ),
        "search_policy": {
            "initial_surface": "reuse sealed iteration-12 97.65625 m 3x3 rate-only cells",
            "full_spacing_km": FULL_SPACING_KM,
            "maximum_full_edge_steps": MAX_FULL_EDGE_STEPS,
            "half_spacing_km": HALF_SPACING_KM,
            "maximum_half_edge_steps": MAX_HALF_EDGE_STEPS,
            "edge_rule": "recenter a new symmetric 3x3 only when the winner is on its edge",
        },
        "fixed_group_taus_s": {group: sealed_groups[group]["tau_s"] for group in GROUPS},
        "levels": levels,
        "phase_outcomes": phase_outcomes,
        "unique_coordinate_count": len(cache),
        "winner": {
            key: final[key]
            for key in (
                "latitude_deg",
                "longitude_deg",
                "balanced_exact_capped_loss",
                "balanced_selection_objective",
                "all_converged",
                "source",
            )
        },
        "selected_group_audits": gates,
        "qualified": qualified,
        "qualification_rule": (
            "both nuisance fits converge, both exact replay gates pass at 0.2 Hz, and the "
            "final half-step winner is interior"
        ),
        "elapsed_s": time.monotonic() - started,
        "workers": args.workers,
        "bindings": {"driver": digest(DRIVER), "runner": digest(Path(__file__))},
    }
    content = canonical(output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        canonical(
            {
                "elapsed_s": output["elapsed_s"],
                "levels": len(levels),
                "qualified": qualified,
                "winner": output["winner"],
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
