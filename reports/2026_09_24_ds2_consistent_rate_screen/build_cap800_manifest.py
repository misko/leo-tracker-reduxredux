#!/usr/bin/env python3
"""Freeze a bounded all-20 DS2 cap-800 replay around a sealed RF winner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FINAL = ROOT / "2026_09_24_ds2_final_manifest/manifest.json"
PLAN = ROOT / "2026_09_24_ds2_portable_evaluation/plan.json"
FINALIST = (
    ROOT
    / "2026_09_24_ds2_portable_evaluation/inference_refined_fine"
    / "joint-all20__equal-weight-joint-rate__r0.585938.json"
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def sealed(path: Path) -> dict[str, Any]:
    seals = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if not any(seal.is_file() and seal.read_text().strip() == expected for seal in seals):
        raise ValueError(f"unsealed input: {path}")
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "cap800-run-manifest.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    final = sealed(FINAL)
    plan = sealed(PLAN)
    finalist = sealed(FINALIST)
    sessions = [str(row["session_id"]) for row in final["sessions"]]
    if len(sessions) != 20 or len(set(sessions)) != 20:
        raise ValueError("final DS2 manifest must have exactly twenty unique sessions")
    source = next(
        task for task in plan["tasks"] if task["task_id"] == "joint-all20__equal-weight-joint-rate"
    )
    if list(map(str, source["session_ids"])) != sessions:
        raise ValueError("portable all-20 task does not bind the final DS2 corpus")
    groups = []
    for label, subset in (
        ("chronological-first-10", sessions[:10]),
        ("chronological-last-10", sessions[10:]),
    ):
        task = {
            **source,
            "task_id": f"ds2-cap800-{label}",
            "group_id": label,
            "session_ids": subset,
            "session_groups": {sid: "ds2" for sid in subset},
            "output_path": str(HERE / "unused.json"),
            "options": {**source["options"], "tau_grid_s": [-1.0, 0.0, 1.0]},
        }
        groups.append({"group_id": label, "weight": 0.5, "task": task})
    document = {
        "schema": "consistent-cap800-frozen-run/v1",
        "partition": "development",
        "reference_used_for_fit": False,
        "reference_coordinate_present": False,
        "dataset_manifest": {"path": str(FINAL.resolve()), "sha256": digest(FINAL)},
        "portable_cache_root": str(args.cache_root.resolve()),
        "groups": groups,
        "origin": {
            "latitude_deg": finalist["estimated_position"]["latitude_deg"],
            "longitude_deg": finalist["estimated_position"]["longitude_deg"],
            "origin_policy": "sealed reference-free all-20 250 km Sacramento winner",
        },
        "seeds": [
            {
                "latitude_deg": finalist["estimated_position"]["latitude_deg"],
                "longitude_deg": finalist["estimated_position"]["longitude_deg"],
                "source": "same sealed RF-only winner",
            }
        ],
        "tau_grid_s": [-1.0, 0.0, 1.0],
        "levels_km": [0.1953125],
        "top_basins": 2,
        "top_taus_per_group": 2,
        "exact_top_coordinates": 2,
        "modules": {
            "joint": str(
                (ROOT / "2026_09_24_ds1_joint_rate_search/joint_rate_search.py").resolve()
            ),
            "runner": str((ROOT / "2026_09_24_ds1_train_full_orbit_soft/run.py").resolve()),
            "orbit": str((ROOT / "2026_09_24_ds1_orbit_arm/run.py").resolve()),
        },
        "scope": {
            "all_sessions": sessions,
            "initial_prior": "Sacramento 250 km in the sealed parent search",
            "local_reuse": "one 3x3, 195.3125 m lattice around that sealed RF-only winner",
            "no_truth_before_postseal": True,
        },
        "parent_finalist": {"path": str(FINALIST.resolve()), "sha256": digest(FINALIST)},
    }
    content = canonical(document)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        json.dumps({"groups": len(groups), "sessions": len(sessions), "output": str(args.output)})
    )


if __name__ == "__main__":
    main()
