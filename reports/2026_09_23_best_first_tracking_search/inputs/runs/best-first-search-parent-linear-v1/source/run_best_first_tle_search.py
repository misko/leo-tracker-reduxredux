#!/usr/bin/env python3
"""Run the bounded all-track best-first TLE location search."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import fast_coverage_inputs
import numpy as np
from best_first_tle_search import TrackResidual, best_first_search, point_evaluation
from search_multiresolution_tle_coverage import (
    CoverageEvaluator,
    build_prediction_banks,
    partition_mask,
)
from tle_parent_priority import make_parent_priority

from leo.analysis.research.regional_doppler import Region
from leo.contracts.sky import ObserverSiteV1

CITIES = {
    "sacramento": (38.5816, -121.4944),
    "reno": (39.5296, -119.8138),
}
SOURCE_NAMES = (
    "run_best_first_tle_search.py",
    "best_first_tle_search.py",
    "fast_coverage_inputs.py",
    "search_multiresolution_tle_coverage.py",
    "map_randomized_tle_coverage.py",
    "tle_parent_priority.py",
)
_WORKER_EVALUATOR = None


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def snapshot_sources(output: Path) -> dict:
    source = output / "source"
    source.mkdir()
    manifest = {}
    for name in SOURCE_NAMES:
        path = Path(__file__).with_name(name)
        shutil.copyfile(path, source / name)
        manifest[name] = digest(source / name)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = {"git_head": head, "files": manifest}
    write_json(source / "manifest.json", result)
    return result


def _initialize_worker(evaluator) -> None:
    global _WORKER_EVALUATOR
    _WORKER_EVALUATOR = evaluator


def _evaluate_worker(sites):
    return _WORKER_EVALUATOR.evaluate_residual_points(sites)


def distinct_second_weights(tracks) -> dict[str, float]:
    return {row["tracklet_id"]: float(len(np.unique(np.floor(row["times_s"])))) for row in tracks}


def exact_descendants(east: float, north: float, spacing_km: float = 12.5) -> np.ndarray:
    offsets = (np.arange(8) + 0.5) * spacing_km - 50.0
    return np.asarray(
        sorted((east + de, north + dn) for de in offsets for dn in offsets), dtype=float
    )


def residual_diagnostics(row) -> dict:
    matched = [track for track in row.tracks if track.heldout_rms_hz is not None]
    total_weight = sum(track.weight_s for track in matched)
    uncapped = (
        np.sqrt(sum(track.weight_s * track.heldout_rms_hz**2 for track in matched) / total_weight)
        if total_weight
        else None
    )
    return {
        "uncapped_matched_track_weighted_rms_hz": None if uncapped is None else float(uncapped),
        "matched_track_count": len(matched),
        "unmatched_track_count": len(row.tracks) - len(matched),
    }


def run(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    source_snapshot = snapshot_sources(args.output)
    started = time.monotonic()
    inputs = fast_coverage_inputs.load(
        args.session,
        args.evidence,
        args.bulk_root,
        args.tle_root,
        track_count=None,
        min_span_s=3.0,
        min_observations=6,
    )
    load_s = time.monotonic() - started
    weights = distinct_second_weights(inputs["tracks"])
    fixed_site = ObserverSiteV1(
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        label="best-first-fixed-partition",
    )
    evidence_tracks = []
    for row in inputs["tracks"]:
        mask, seed = partition_mask(
            row["observation_ids"],
            row["support_digest"],
            inputs["trajectory_digest"],
            fixed_site,
            mode="fixed",
        )
        evidence_tracks.append(
            {
                "rank": row["rank"],
                "tracklet_id": row["tracklet_id"],
                "support_digest": row["support_digest"],
                "observation_ids": row["observation_ids"],
                "times_s": row["times_s"].tolist(),
                "measured_hz": row["measured_hz"].tolist(),
                "span_s": row["span_s"],
                "represented_second_bins": sorted(
                    int(value) for value in np.unique(np.floor(row["times_s"]))
                ),
                "weight_s": weights[row["tracklet_id"]],
                "partition_seed": seed,
                "training_mask": mask.tolist(),
            }
        )
    evidence_path = args.output / "frozen-track-evidence.json"
    write_json(
        evidence_path,
        {
            "schema": "best-first-frozen-track-evidence/v1",
            "trajectory_digest": inputs["trajectory_digest"],
            "partition_mode": "fixed-position-independent",
            "tracks": evidence_tracks,
        },
    )
    banks, bank_metadata = build_prediction_banks(inputs)
    prepare_s = time.monotonic() - started - load_s
    evaluator = CoverageEvaluator(
        banks,
        np.arange(-5.0, 6.0),
        inputs["trajectory_digest"],
        (200.0, 800.0),
        partition_mode="fixed",
        candidate_block=args.candidate_block,
    )
    runs = []
    context = multiprocessing.get_context("fork")
    with context.Pool(
        min(args.workers, 12), initializer=_initialize_worker, initargs=(evaluator,)
    ) as pool:
        for city in args.cities:
            latitude, longitude = CITIES[city]
            region = Region(latitude, longitude, 1000.0, 1000.0)
            parent_cache = {}
            parent_priority = (
                make_parent_priority(banks, region, inputs["trajectory_digest"], weights)
                if args.priority_mode == "parent-linear"
                else None
            )

            def evaluate(points, *, cache=parent_cache, active_region=region):
                points = np.asarray(points, dtype=float).reshape(-1, 2)
                missing = [tuple(row) for row in points if tuple(row) not in cache]
                if missing:
                    sites = active_region.points(
                        np.asarray(missing)[:, 0], np.asarray(missing)[:, 1]
                    )
                    fields = (
                        "east_km",
                        "north_km",
                        "latitude_deg",
                        "longitude_deg",
                        "altitude_m",
                        "ecef_km",
                        "up",
                    )
                    worker_count = min(args.workers, len(missing))
                    indices = np.array_split(np.arange(len(missing)), worker_count)
                    shards = [
                        type(sites)(*(getattr(sites, name)[index] for name in fields))
                        for index in indices
                    ]
                    raw = [row for shard in pool.map(_evaluate_worker, shards) for row in shard]
                    for item in raw:
                        tracks = []
                        for track in item["tracks"]:
                            track_id = track["tracklet_id"]
                            rms = track["heldout_rms_hz"]
                            observation_ids = next(
                                row["observation_ids"]
                                for row in inputs["tracks"]
                                if row["tracklet_id"] == track_id
                            )
                            tracks.append(
                                TrackResidual(
                                    track_id,
                                    rms,
                                    weights[track_id],
                                    tuple(observation_ids) if rms is not None and rms < 200 else (),
                                    track["best_candidate"],
                                )
                            )
                        result = point_evaluation(
                            item["east_km"],
                            item["north_km"],
                            tracks,
                            unmatched_penalty_hz=800.0,
                            metadata={
                                "latitude_deg": item["latitude_deg"],
                                "longitude_deg": item["longitude_deg"],
                            },
                        )
                        cache[(result.east_km, result.north_km)] = result
                return [cache[tuple(row)] for row in points]

            search_started = time.monotonic()
            result = best_first_search(
                evaluate,
                radius_km=args.radius_km,
                region_size_km=1000.0,
                levels_km=(100.0, 50.0, 25.0, 12.5),
                budget_points=args.budget_points,
                estimate_priority=parent_priority,
            )
            search_s = time.monotonic() - search_started
            initial = [
                row
                for row in result.all_evaluations
                if any(
                    event.get("event") == "evaluate"
                    and event.get("depth") == 0
                    and event.get("east_km") == row.east_km
                    and event.get("north_km") == row.north_km
                    for event in result.trace
                )
            ]
            coarse = min(initial, key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km))
            reference_points = exact_descendants(coarse.east_km, coarse.north_km)
            reference_points = reference_points[
                np.linalg.norm(reference_points, axis=1) <= args.radius_km + 1e-12
            ]
            reference_started = time.monotonic()
            reference = sorted(
                evaluate(reference_points),
                key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km),
            )
            reference_s = time.monotonic() - reference_started
            reference_keys = {(row.east_km, row.north_km) for row in reference[:15]}
            reference_domain = {(row.east_km, row.north_km) for row in reference}
            visited_reference = sorted(
                (
                    row
                    for row in result.finest_evaluations
                    if (row.east_km, row.north_km) in reference_domain
                ),
                key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km),
            )
            visited_keys = {(row.east_km, row.north_km) for row in visited_reference}
            city_dir = args.output / city
            city_dir.mkdir()
            payload = {
                "schema": "best-first-tle-search-run/v1",
                "execution_complete": True,
                "search_complete": result.complete,
                "stop_reason": result.stop_reason,
                "result_guarantee": result.metrics["result_guarantee"],
                "city": city,
                "radius_km": args.radius_km,
                "workers": min(args.workers, 12),
                "budget_points": args.budget_points,
                "objective": "distinct-1s-bin-weighted capped all-track heldout MSE",
                "priority_mode": args.priority_mode,
                "priority_metrics": (
                    None if parent_priority is None else parent_priority.metrics()
                ),
                "unmatched_penalty_hz": 800.0,
                "search_s": search_s,
                "search": asdict(result),
                "global_incumbent_diagnostics": residual_diagnostics(result.best),
                "final_lattice_selection": (
                    None if not result.finest_evaluations else asdict(result.finest_evaluations[0])
                ),
                "final_lattice_diagnostics": (
                    None
                    if not result.finest_evaluations
                    else residual_diagnostics(result.finest_evaluations[0])
                ),
                "exact_validation": {
                    "selection": "12.5 km descendants of best 100 km objective cell",
                    "coarse_centre": [coarse.east_km, coarse.north_km],
                    "point_count": len(reference),
                    "elapsed_s": reference_s,
                    "winner": asdict(reference[0]),
                    "winner_diagnostics": residual_diagnostics(reference[0]),
                    "visited_local_winner_matches": (
                        bool(visited_reference)
                        and (visited_reference[0].east_km, visited_reference[0].north_km)
                        == (reference[0].east_km, reference[0].north_km)
                    ),
                    "visited_oracle_top15_coordinate_recall": len(visited_keys & reference_keys)
                    / len(reference_keys),
                    "visited_local_objective_gap_hz2": (
                        None
                        if not visited_reference
                        else visited_reference[0].weighted_mse_hz2 - reference[0].weighted_mse_hz2
                    ),
                },
            }
            write_json(city_dir / "result.json", payload)
            runs.append(
                {
                    "city": city,
                    "result_digest": digest(city_dir / "result.json"),
                    "search_s": search_s,
                    "evaluated_points": result.metrics["evaluated_point_count"],
                }
            )
    summary = {
        "schema": "best-first-tle-search-execution/v1",
        "execution_complete": True,
        "session_id": args.session,
        "timing_s": {
            "input_load": load_s,
            "prediction_bank_prepare": prepare_s,
            "total": time.monotonic() - started,
        },
        "workers": min(args.workers, 12),
        "priority_mode": args.priority_mode,
        "track_weights_distinct_second_bins": weights,
        "frozen_track_evidence_digest": digest(evidence_path),
        "track_inventory": [
            {
                "rank": row["rank"],
                "tracklet_id": row["tracklet_id"],
                "span_s": row["span_s"],
                "observation_count": row["observation_count"],
                "represented_second_bins": sorted(
                    int(value) for value in np.unique(np.floor(row["times_s"]))
                ),
                "weight_s": weights[row["tracklet_id"]],
            }
            for row in inputs["tracks"]
        ],
        "input_provenance": inputs["provenance"],
        "prediction_bank": bank_metadata,
        "source_snapshot": source_snapshot,
        "runs": runs,
    }
    write_json(args.output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="scan-fw-cf510316ae7f05d5")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--cities", nargs="+", choices=tuple(CITIES), default=tuple(CITIES))
    parser.add_argument("--radius-km", type=float, default=500.0)
    parser.add_argument("--budget-points", type=int, default=400)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--candidate-block", type=int, default=256)
    parser.add_argument(
        "--priority-mode", choices=("exact-centre", "parent-linear"), default="exact-centre"
    )
    args = parser.parse_args()
    if not 0 < args.radius_km <= 500:
        parser.error("radius must be in (0, 500]")
    if not 1 <= args.workers <= 12 or args.budget_points < 100:
        parser.error("workers must be 1..12 and budget at least 100")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
