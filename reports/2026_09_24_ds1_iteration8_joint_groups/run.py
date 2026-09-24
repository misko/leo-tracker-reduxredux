#!/usr/bin/env python3
"""DS1 iteration-8: one RF-selected position for both TRAIN prefix-6 groups.

The immutable iteration-6 spatial candidate union is evaluated for *both*
independent groups on the same fixed tau grid.  A coordinate proposal is the
equal-weight mean of the two groups' best cap-300 losses.  This deliberately
does not pool observations: each group independently associates tracks and
profiles its own per-NORAD phase rates and per-track CFOs.

The bounded exact stage retains the eight lowest joint proposal coordinates
and, at each, exact-audits the two best proposal taus for each group.  The
sealed winner is the coordinate minimizing the equal-weight mean of each
group's best exact cap-800 loss.
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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER6 = ROOT / "reports/2026_09_24_ds1_joint_rate_search/iteration6-results.json"
ITER5 = ROOT / "reports/2026_09_24_ds1_joint_rate_search/iteration5_timing_refinement.py"
JOINT = ROOT / "reports/2026_09_24_ds1_joint_rate_search/joint_rate_search.py"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")
TAUS = tuple(round(-2.25 + 0.25 * number, 2) for number in range(9))
TOP_TAUS_PER_GROUP = 2
TOP_JOINT_COORDINATES = 8


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


def source_path(group: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration8-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def coordinate_key(row: dict[str, Any]) -> tuple[float, float]:
    return (round(float(row["latitude_deg"]), 8), round(float(row["longitude_deg"]), 8))


def load_iteration6(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-6 must be a completed reference-free artifact")
    if {row.get("group_id") for row in value.get("results", [])} != set(GROUPS):
        raise ValueError("iteration-6 groups do not match DS1 prefix-6")
    for result in value["results"]:
        if result.get("exact_candidate_count") != 28:
            raise ValueError("unexpected iteration-6 candidate union")
    return value


def spatial_union(iteration6: dict[str, Any]) -> list[dict[str, float]]:
    """Deduplicate only coordinates, preserving their sealed iteration-6 origins."""
    chosen: dict[tuple[float, float], dict[str, float]] = {}
    for result in iteration6["results"]:
        for row in result["candidates"]:
            key = coordinate_key(row)
            chosen.setdefault(
                key,
                {
                    "latitude_deg": float(row["latitude_deg"]),
                    "longitude_deg": float(row["longitude_deg"]),
                },
            )
    points = sorted(chosen.values(), key=lambda row: (row["latitude_deg"], row["longitude_deg"]))
    if len(points) != 16:
        raise ValueError(
            f"expected 16 immutable iteration-6 spatial coordinates, got {len(points)}"
        )
    return points


def proposal_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (float(row["fit"]["selection_objective"]), abs(float(row["tau_s"])), float(row["tau_s"]))


def joint_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["balanced_proposal_objective"]),
        float(row["latitude_deg"]),
        float(row["longitude_deg"]),
    )


def exact_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(row["exact_comparison"]["exact_full_observation_capped_loss"]),
        abs(float(row["tau_s"])),
        float(row["tau_s"]),
    )


def scan_coordinate(task: tuple[str, dict[str, float]]) -> dict[str, Any]:
    """Evaluate the fixed tau grid for one group-coordinate pair."""
    group, coordinate = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"i8_joint_{group}_{os.getpid()}")
    existing = load(RUNNER, f"i8_runner_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"i8_orbit_{group}_{os.getpid()}")
    i5 = load(ITER5, f"i8_i5_{group}_{os.getpid()}")
    source = json.loads(source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(source_task(source)))
    begun = time.perf_counter()
    previous: dict[str, float] = {}
    rows = []
    for tau in TAUS:
        support = joint.hard_support(
            engine, orbit, coordinate["latitude_deg"], coordinate["longitude_deg"], tau
        )
        fit = i5.profile_300(support, previous)
        previous = fit["rate_corrections_s_h"]
        rows.append({"tau_s": tau, "fit": fit})
    return {**coordinate, "group_id": group, "rows": rows, "elapsed_s": time.perf_counter() - begun}


def build_joint_proposals(
    scans: list[dict[str, Any]], coordinates: list[dict[str, float]]
) -> list[dict[str, Any]]:
    """Equal group weights prevent a larger observation count from voting twice."""
    proposals = []
    for coordinate in coordinates:
        per_group = {}
        for group in GROUPS:
            scan = next(
                row
                for row in scans
                if row["group_id"] == group and coordinate_key(row) == coordinate_key(coordinate)
            )
            eligible = [row for row in scan["rows"] if row["fit"]["converged"]]
            if len(eligible) < TOP_TAUS_PER_GROUP:
                raise ValueError(f"too few converged proposal rows: {group} {coordinate}")
            per_group[group] = sorted(eligible, key=proposal_key)[:TOP_TAUS_PER_GROUP]
        best00, best16 = per_group[GROUPS[0]][0], per_group[GROUPS[1]][0]
        proposals.append(
            {
                **coordinate,
                "balanced_proposal_objective": 0.5 * float(best00["fit"]["selection_objective"])
                + 0.5 * float(best16["fit"]["selection_objective"]),
                "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
                "proposal_taus": per_group,
            }
        )
    return sorted(proposals, key=joint_key)


def exact_audit(task: tuple[str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    group, coordinate, proposal = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    joint = load(JOINT, f"i8_exact_joint_{group}_{os.getpid()}")
    existing = load(RUNNER, f"i8_exact_runner_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"i8_exact_orbit_{group}_{os.getpid()}")
    engine = existing.FullObservationEngine(
        existing.validate_task(source_task(json.loads(source_path(group).read_text())))
    )
    begun = time.perf_counter()
    screened = joint.screen_point(
        engine,
        orbit,
        coordinate["latitude_deg"],
        coordinate["longitude_deg"],
        proposal["tau_s"],
        False,
    )
    exact = joint.exact_comparison(existing, orbit, engine, screened)
    return {
        **coordinate,
        "group_id": group,
        "tau_s": proposal["tau_s"],
        "cap300_proposal_fit": proposal["fit"],
        "track_associations": screened["track_associations"],
        "exact_comparison": exact,
        "elapsed_s": time.perf_counter() - begun,
    }


def select_exact(
    audits: list[dict[str, Any]], finalists: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for proposal in finalists:
        per_group = {}
        for group in GROUPS:
            options = [
                row
                for row in audits
                if row["group_id"] == group and coordinate_key(row) == coordinate_key(proposal)
            ]
            if len(options) != TOP_TAUS_PER_GROUP or not all(
                row["exact_comparison"]["exact_sgp4_gate"]["passed"] for row in options
            ):
                raise ValueError("exact audit is incomplete or failed its SGP4 gate")
            per_group[group] = min(options, key=exact_key)
        rows.append(
            {
                "latitude_deg": proposal["latitude_deg"],
                "longitude_deg": proposal["longitude_deg"],
                "balanced_proposal_objective": proposal["balanced_proposal_objective"],
                "balanced_exact_capped_loss": 0.5
                * float(
                    per_group[GROUPS[0]]["exact_comparison"]["exact_full_observation_capped_loss"]
                )
                + 0.5
                * float(
                    per_group[GROUPS[1]]["exact_comparison"]["exact_full_observation_capped_loss"]
                ),
                "group_weighting": {GROUPS[0]: 0.5, GROUPS[1]: 0.5},
                "best_exact_by_group": per_group,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["balanced_exact_capped_loss"],
            row["latitude_deg"],
            row["longitude_deg"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration6", type=Path, default=ITER6)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 8:
        raise ValueError("output already exists or workers must be 1..8")
    iteration6 = load_iteration6(args.iteration6)
    coordinates = spatial_union(iteration6)
    begun = time.perf_counter()
    scan_tasks = [(group, coordinate) for coordinate in coordinates for group in GROUPS]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        scans = list(pool.map(scan_coordinate, scan_tasks, chunksize=1))
    proposals = build_joint_proposals(scans, coordinates)
    finalists = proposals[:TOP_JOINT_COORDINATES]
    exact_tasks = [
        (group, finalist, tau_row)
        for finalist in finalists
        for group in GROUPS
        for tau_row in finalist["proposal_taus"][group]
    ]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audits = list(pool.map(exact_audit, exact_tasks, chunksize=1))
    exact_rows = select_exact(audits, finalists)
    output = {
        "schema": "ds1-iteration8-joint-prefix6-groups/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations",
        "spatial_candidate_policy": (
            "deduplicated immutable coordinate union of the completed iteration-6 exact candidates"
        ),
        "common_tau_grid_s": TAUS,
        "nuisance_policy": (
            "each group independently hard-associates tracks and fits its own tau, "
            "per-NORAD rates, and per-track CFOs"
        ),
        "balanced_objective": (
            "0.5 * group-20260921_00 loss + 0.5 * group-20260921_16 loss; "
            "no pooled-observation loss"
        ),
        "proposal_policy": (
            f"cap-300 fixed-grid screen, retain {TOP_TAUS_PER_GROUP} tau proposals "
            f"per group at each coordinate, exact-audit the {TOP_JOINT_COORDINATES} "
            "best balanced coordinates"
        ),
        "exact_selection": (
            "minimum equal-weight mean of each group's best exact cap-800 capped loss"
        ),
        "spatial_candidate_count": len(coordinates),
        "exact_finalist_count": len(finalists),
        "exact_audit_count": len(audits),
        "workers": args.workers,
        "elapsed_s": time.perf_counter() - begun,
        "iteration6_input": {"path": str(args.iteration6), "sha256": digest(args.iteration6)},
        "proposal_scans": scans,
        "joint_proposals": proposals,
        "exact_finalists": exact_rows,
        "winner": exact_rows[0],
        "bindings": {
            "driver": digest(Path(__file__)),
            "iteration5_profile": digest(ITER5),
            "joint": digest(JOINT),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_s": output["elapsed_s"],
                "exact_audits": len(audits),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
