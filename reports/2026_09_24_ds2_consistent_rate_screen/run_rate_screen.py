#!/usr/bin/env python3
"""Bounded DS2 rate-aware screen beside a nominal-rate control.

The screen deliberately starts from a sealed, reference-free all-20 winner.
It does not re-run the 250 km prior: the parent artifact already completed
that search.  Every local point reacquires candidates from the 20 receipt-bound
caches, then the experimental arm fits causal per-NORAD rate corrections while
the control retains the same nominal hard support.  Both selected rows receive
an exact SGP4 replay gate after selection.
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
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JOINT_PATH = ROOT / "2026_09_24_ds1_joint_rate_search/joint_rate_search.py"
RUNNER_PATH = ROOT / "2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT_PATH = ROOT / "2026_09_24_ds1_orbit_arm/run.py"
DEFAULT_FINALIST = (
    ROOT
    / "2026_09_24_ds2_portable_evaluation/inference_refined_fine"
    / "joint-all20__equal-weight-joint-rate__r0.585938.json"
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_sealed(path: Path, value: Any) -> None:
    data = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sealed_finalist(path: Path) -> dict[str, Any]:
    seals = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_file() or not any(
        seal.is_file() and seal.read_text().strip() == expected for seal in seals
    ):
        raise ValueError(f"finalist is not digest sealed: {path}")
    value = json.loads(path.read_text())
    if value.get("reference_coordinate_present") is not False:
        raise ValueError("finalist does not attest the reference boundary")
    if value.get("reference_used_for_fit") is not False:
        raise ValueError("finalist was not selected reference-free")
    if len(value.get("session_ids", [])) != 20:
        raise ValueError("rate screen is restricted to the sealed all-20 DS2 result")
    return value


def point_grid(centre: dict[str, Any], spacing_km: float) -> list[dict[str, float]]:
    points = []
    for north in (-spacing_km, 0.0, spacing_km):
        for east in (-spacing_km, 0.0, spacing_km):
            lat = float(centre["latitude_deg"]) + north / 111.32
            lon = float(centre["longitude_deg"]) + east / (
                111.32 * math.cos(math.radians(float(centre["latitude_deg"])))
            )
            points.append(
                {
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                    "east_from_sealed_winner_km": east,
                    "north_from_sealed_winner_km": north,
                }
            )
    return points


def one_point(
    payload: tuple[dict[str, Any], dict[str, float], Path],
) -> dict[str, Any]:
    finalist, point, cache_root = payload
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT_PATH, f"ds2_rate_joint_{os.getpid()}")
    runner = load(RUNNER_PATH, f"ds2_rate_runner_{os.getpid()}")
    orbit = load(ORBIT_PATH, f"ds2_rate_orbit_{os.getpid()}")
    runner.CACHE_ROOTS.clear()
    runner.CACHE_ROOTS["ds2"] = cache_root
    task = joint.task_from_finalist(Path(finalist["_source_path"]))
    task["session_groups"] = {str(sid): "ds2" for sid in finalist["session_ids"]}
    engine = runner.FullObservationEngine(runner.validate_task(task))
    tau = float(finalist["global_tau_s"])
    rate = joint.screen_point(
        engine,
        orbit,
        point["latitude_deg"],
        point["longitude_deg"],
        tau,
        reassign_once=True,
    )
    control_support = joint.hard_support(
        engine, orbit, point["latitude_deg"], point["longitude_deg"], tau
    )
    control_fit = joint.fit_rate_support(control_support)
    return {
        **point,
        "tau_s": tau,
        "rate_aware": rate,
        "nominal_control": {
            "track_associations": control_support.associations,
            "selection_objective": control_fit["null_rate_full_observation_capped_loss"],
            "nominal_capped_loss": control_fit["null_rate_full_observation_capped_loss"],
            "counterfactual_rate_fit": control_fit,
        },
    }


def row_key(row: dict[str, Any], arm: str) -> tuple[float, float, float, float]:
    if arm == "rate_aware":
        score = float(row[arm]["fit"]["selection_objective"])
    else:
        score = float(row[arm]["selection_objective"])
    return (
        score,
        abs(float(row["east_from_sealed_winner_km"]))
        + abs(float(row["north_from_sealed_winner_km"])),
        float(row["north_from_sealed_winner_km"]),
        float(row["east_from_sealed_winner_km"]),
    )


def exact_gate(
    finalist: dict[str, Any], selected: dict[str, Any], arm: str, cache_root: Path
) -> dict[str, Any]:
    joint = load(JOINT_PATH, f"ds2_rate_exact_joint_{os.getpid()}")
    runner = load(RUNNER_PATH, f"ds2_rate_exact_runner_{os.getpid()}")
    orbit = load(ORBIT_PATH, f"ds2_rate_exact_orbit_{os.getpid()}")
    runner.CACHE_ROOTS.clear()
    runner.CACHE_ROOTS["ds2"] = cache_root
    task = joint.task_from_finalist(Path(finalist["_source_path"]))
    task["session_groups"] = {str(sid): "ds2" for sid in finalist["session_ids"]}
    engine = runner.FullObservationEngine(runner.validate_task(task))
    if arm == "rate_aware":
        screen = selected[arm]
    else:
        screen = {
            "latitude_deg": selected["latitude_deg"],
            "longitude_deg": selected["longitude_deg"],
            "tau_s": selected["tau_s"],
            "track_associations": selected[arm]["track_associations"],
            # This field makes the rate-aware exact comparison's surrogate
            # discrepancy explicit for the nominal control too.
            "fit": selected[arm]["counterfactual_rate_fit"],
        }
    return joint.exact_comparison(runner, orbit, engine, screen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalist", type=Path, default=DEFAULT_FINALIST)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--spacing-km", type=float, default=0.1953125)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=HERE / "rate-screen.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.spacing_km <= 0 or not 1 <= args.workers <= 8:
        raise ValueError("spacing must be positive and workers must be 1..8")
    finalist = sealed_finalist(args.finalist)
    finalist["_source_path"] = str(args.finalist.resolve())
    points = point_grid(finalist["estimated_position"], args.spacing_km)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        rows = list(pool.map(one_point, [(finalist, point, args.cache_root) for point in points]))
    winners = {arm: min(rows, key=lambda row, item=arm: row_key(row, item)) for arm in (
        "rate_aware", "nominal_control"
    )}
    exact = {arm: exact_gate(finalist, winners[arm], arm, args.cache_root) for arm in winners}
    document = {
        "schema": "ds2-rate-aware-local-screen/v1",
        "complete": True,
        "partition": "development",
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "scope": {
            "prior": "sealed 250 km Sacramento all-20 winner; bounded 3x3 local reuse",
            "reason": (
                "a fresh full 250 km rate-aware recompute is not bounded by the "
                "DS2 execution budget"
            ),
            "spacing_km": args.spacing_km,
            "point_count": len(rows),
            "all_20_sessions": True,
        },
        "rate_definition": "per-NORAD phase seconds = causal TLE age hours × fitted seconds/hour",
        "rate_aware_policy": "hard-reacquire, fit rate, one hard reassignment, refit",
        "control_policy": (
            "same geometric points; nominal hard association and no rate in selection"
        ),
        "finalist": {
            "path": str(args.finalist.resolve()),
            "sha256": digest(args.finalist),
            "estimated_position": finalist["estimated_position"],
            "global_tau_s": finalist["global_tau_s"],
        },
        "rows": rows,
        "winners": winners,
        "exact_replay": exact,
        "bindings": {
            "joint": digest(JOINT_PATH),
            "runner": digest(RUNNER_PATH),
            "orbit": digest(ORBIT_PATH),
        },
    }
    write_sealed(args.output, document)
    print(json.dumps({"output": str(args.output), "points": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
