#!/usr/bin/env python3
"""Reference-free dynamic-association replay of the sealed iteration-14 winner."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / "reports/2026_09_24_ds1_iteration12_shared_norad/run.py"
ITERATION10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
GROUPS = ("20260921_00", "20260921_16")


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


def association_map(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    return {
        f"{row['session_id']}:{row['track_id']}": (
            None if row.get("candidate_id") is None else str(row["candidate_id"])
        )
        for row in rows
    }


def compare_associations(
    fixed: list[dict[str, Any]], dynamic: list[dict[str, Any]]
) -> dict[str, Any]:
    old, new = association_map(fixed), association_map(dynamic)
    common = sorted(set(old) & set(new))
    matched = sum(old[key] == new[key] for key in common)
    return {
        "fixed_tracks": len(old),
        "dynamic_tracks": len(new),
        "common_tracks": len(common),
        "identical_candidate_tracks": matched,
        "changed_candidate_tracks": len(common) - matched,
        "common_candidate_match_fraction": matched / len(common) if common else None,
        "fixed_candidate_count": len({value for value in old.values() if value is not None}),
        "dynamic_candidate_count": len({value for value in new.values() if value is not None}),
    }


def replay_group(task: tuple[str, dict[str, float], dict[str, Any]]) -> dict[str, Any]:
    group, point, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    replay = load_module(REPLAY, f"i14_replay_{group}_{os.getpid()}")
    i8 = load_module(replay.ITER8_RUN, f"i14_i8_{group}_{os.getpid()}")
    runner = load_module(replay.RUNNER, f"i14_runner_{group}_{os.getpid()}")
    orbit = load_module(replay.ORBIT, f"i14_orbit_{group}_{os.getpid()}")
    driver = load_module(DRIVER, f"i14_driver_{group}_{os.getpid()}")
    engine = runner.FullObservationEngine(runner.validate_task(replay.source_task(i8, group)))
    tau = float(sealed_group["tau_s"])
    _loss, associations = engine.hard_association(
        point["latitude_deg"], point["longitude_deg"], tau
    )
    prepared = runner._make_exact_prepared(
        engine,
        orbit,
        point["latitude_deg"],
        point["longitude_deg"],
        tau,
        associations,
    )
    receiver, _up = engine.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    model = driver.ExactModel.build(prepared, receiver, engine.search, orbit)
    fit = driver.fit(model, scales_enabled=False)
    gate = orbit.exact_replay_gate(
        prepared, receiver, engine.search, tau, fit["rates_s_h"], tolerance_hz=0.2
    )
    return {
        "group_id": group,
        "tau_s": tau,
        "track_associations": associations,
        "fit": fit,
        "exact_sgp4_gate": gate,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False or not inference.get("qualified"):
        raise ValueError("inference must be qualified and reference-free")
    winner = inference["winner"]
    point = {
        "latitude_deg": float(winner["latitude_deg"]),
        "longitude_deg": float(winner["longitude_deg"]),
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
    }
    iteration10 = json.loads(ITERATION10.read_text())
    fixed_groups = iteration10["winner"]["best_exact_by_group"]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        group_results = list(
            pool.map(
                replay_group,
                [(group, point, fixed_groups[group]) for group in GROUPS],
                chunksize=1,
            )
        )
    dynamic = {row["group_id"]: row for row in group_results}
    comparisons = {
        group: compare_associations(
            fixed_groups[group]["track_associations"], dynamic[group]["track_associations"]
        )
        for group in GROUPS
    }
    output = {
        "schema": "ds1-iteration14-dynamic-association-replay/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "replay_driver": {"path": str(REPLAY), "sha256": digest(REPLAY)},
        "association_comparison": comparisons,
        "dynamic_result": {
            "per_group": dynamic,
            "balanced_exact_capped_loss": 0.5
            * sum(row["fit"]["exact_full_observation_capped_loss"] for row in group_results),
        },
        "passed": bool(
            all(row["fit"]["converged"] for row in group_results)
            and all(row["exact_sgp4_gate"]["passed"] for row in group_results)
        ),
    }
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "passed": output["passed"],
                "association_comparison": comparisons,
            }
        )
    )


if __name__ == "__main__":
    main()
