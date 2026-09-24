#!/usr/bin/env python3
"""Truth-free fine refinement of every DS2 0.390625-km joint result."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RADII_KM = (0.5859375, 1.171875, 2.34375)
LEVELS_KM = (0.1953125, 0.09765625)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def valid(path: Path) -> bool:
    if not path.is_file():
        return False
    seals = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    return any(
        seal.is_file() and seal.read_text().strip() == hashlib.sha256(path.read_bytes()).hexdigest()
        for seal in seals
    )


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def boundary_triggered(radial_km: float, radius_km: float) -> bool:
    return radial_km >= radius_km - LEVELS_KM[0] - 1e-9


def levels_for_radius(radius_km: float) -> tuple[float, ...]:
    levels = []
    level = radius_km / 3.0
    while level > LEVELS_KM[0] + 1e-12:
        levels.append(level)
        level /= 2.0
    return (*levels, *LEVELS_KM)


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    earth_km = 6371.0088
    lat1, lat2 = map(math.radians, (left[0], right[0]))
    dlat = lat2 - lat1
    dlon = math.radians(right[1] - left[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_km * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def run_one(
    coarse_task: dict[str, Any], stage_one: dict[str, Any], cache_root: Path
) -> dict[str, Any]:
    parent_path = Path(stage_one["final_artifact"])
    if not valid(parent_path):
        raise ValueError(f"stage-one artifact is not sealed: {parent_path}")
    parent = json.loads(parent_path.read_text())
    point = parent["estimated_position"]
    label = stage_one["method"]
    rows = []
    final_path = None
    exhausted = True
    started = time.monotonic()
    for attempt, radius in enumerate(RADII_KM, 1):
        search_levels = levels_for_radius(radius)
        output = HERE / "inference_refined_fine" / f"joint-all20__{label}__r{radius:g}.json"
        task = {
            **coarse_task,
            "task_id": f"joint-all20-fine__{label}__attempt-{attempt}",
            "group_id": "ds2-sept24-all-truth-free-fine-refinement",
            "prior": {
                "name": f"sealed-{label}-refined-winner-symmetric-{radius:g}km",
                "lat": float(point["latitude_deg"]),
                "lon": float(point["longitude_deg"]),
                "radius_km": radius,
                "reference_used_for_selection": False,
            },
            "options": {
                **coarse_task["options"],
                "geographic_levels_km": list(search_levels),
                "search_levels_km": list(search_levels),
            },
            "output_path": str(output),
            "refinement_parent_sha256": digest(parent_path),
            "reference_coordinate_present": False,
        }
        task_path = HERE / "tasks_refined_fine" / f"{task['task_id']}.json"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(canonical(task))
        if not valid(output):
            env = {
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "run_portable.py"),
                    "--task",
                    str(task_path),
                    "--cache-root",
                    str(cache_root),
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            if result.returncode != 0 or not valid(output):
                raise RuntimeError(
                    f"fine refinement failed for {label} attempt {attempt}: "
                    f"{result.stderr[-4000:]}"
                )
        document = json.loads(output.read_text())
        if "selected" in document:
            east = float(document["selected"]["east_km"])
            north = float(document["selected"]["north_km"])
            radial = math.hypot(east, north)
        else:
            estimate = document["estimated_position"]
            radial = haversine_km(
                (float(point["latitude_deg"]), float(point["longitude_deg"])),
                (float(estimate["latitude_deg"]), float(estimate["longitude_deg"])),
            )
        boundary = boundary_triggered(radial, radius)
        rows.append(
            {
                "attempt": attempt,
                "radius_km": radius,
                "search_levels_km": list(search_levels),
                "winner_radial_offset_km": radial,
                "boundary_triggered": boundary,
                "artifact": str(output),
                "sha256": digest(output),
            }
        )
        final_path = output
        if not boundary:
            exhausted = False
            break
    assert final_path is not None
    return {
        "method": label,
        "stage_one_artifact": str(parent_path),
        "stage_one_sha256": digest(parent_path),
        "centre_policy": "each method's own sealed stage-one winner; no reference coordinate",
        "levels_km": list(LEVELS_KM),
        "attempts": rows,
        "edge_expansion_exhausted": exhausted,
        "final_artifact": str(final_path),
        "final_sha256": digest(final_path),
        "elapsed_s": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--stage-one", type=Path, default=HERE / "refinement-index.json")
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    stage_one = json.loads(args.stage_one.read_text())
    if stage_one.get("reference_coordinate_present") is not False:
        raise ValueError("stage-one index does not attest the reference boundary")
    tasks = {
        row["task_id"].removeprefix("joint-all20__"): row
        for row in plan["tasks"]
        if row["task_id"].startswith("joint-all20__")
    }
    arguments = [(tasks[row["method"]], row, args.cache_root) for row in stage_one["models"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda values: run_one(*values), arguments))
    document = {
        "schema": "ds2-truth-free-fine-refinement-index/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "parent_index_sha256": digest(args.stage_one),
        "symmetric_radii_km": list(RADII_KM),
        "levels_km": list(LEVELS_KM),
        "models": rows,
    }
    content = canonical(document)
    path = HERE / "fine-refinement-index.json"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(canonical({"models": len(rows), "complete": True}), end="")


if __name__ == "__main__":
    main()
