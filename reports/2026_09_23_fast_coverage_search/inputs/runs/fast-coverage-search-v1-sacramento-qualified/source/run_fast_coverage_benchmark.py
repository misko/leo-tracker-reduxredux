#!/usr/bin/env python3
"""Run fixed-grid and multiresolution coverage searches from one state bank."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import fast_coverage_inputs
import numpy as np
from search_multiresolution_tle_coverage import (
    CoverageEvaluator,
    build_prediction_banks,
    multiresolution_search,
    rank_coverage_cells,
    regional_circle_offsets,
)

from leo.analysis.research.regional_doppler import Region

CITIES = {
    "sacramento": (38.5816, -121.4944, 350.0),
    "reno": (39.5296, -119.8138, 750.0),
    "denver": (39.7392, -104.9903, 2500.0),
}
SOURCE_PATHS = (
    Path(__file__),
    Path(__file__).with_name("fast_coverage_inputs.py"),
    Path(__file__).with_name("search_multiresolution_tle_coverage.py"),
    Path(__file__).with_name("map_randomized_tle_coverage.py"),
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_numbers(value: str, cast=float) -> tuple:
    result = tuple(cast(item) for item in value.split(",") if item)
    if not result:
        raise argparse.ArgumentTypeError("at least one comma-separated value required")
    return result


def json_safe(value):
    """Represent unavailable numeric diagnostics as JSON null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n")


def write_gzip_json(path: Path, value) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(json_safe(value), stream, separators=(",", ":"), allow_nan=False)
        stream.write("\n")


def site_grid(region: Region, points: np.ndarray):
    return region.points(points[:, 0], points[:, 1])


def score_rows(scores) -> list[dict]:
    return [asdict(score) for score in scores]


def snapshot_sources(output: Path) -> dict:
    """Freeze executable sources before any timed numerical work begins."""
    source_dir = output / "source"
    source_dir.mkdir()
    manifest = {}
    for path in SOURCE_PATHS:
        destination = source_dir / path.name
        shutil.copyfile(path, destination)
        manifest[path.name] = digest(destination)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    value = {"git_head": head, "files": manifest}
    write_json(source_dir / "manifest.json", value)
    return value


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
        track_count=10,
    )
    loaded_s = time.monotonic() - started
    banks, bank_metadata = build_prediction_banks(inputs)
    prepared_s = time.monotonic() - started - loaded_s
    thresholds = tuple(sorted(set(args.thresholds_hz)))
    shared_evaluators = {}

    def make_evaluator(city: str):
        cache_key = "fixed" if args.partition_mode == "fixed" else city
        if args.cache_policy == "shared" and cache_key in shared_evaluators:
            return shared_evaluators[cache_key]
        created = CoverageEvaluator(
            banks,
            np.arange(-5.0, 6.0),
            inputs["trajectory_digest"],
            thresholds,
            partition_mode=args.partition_mode,
            observer_label=(
                "randomized-coverage-grid-v1"
                if args.partition_mode == "legacy"
                else "fast-coverage-cell"
            ),
            candidate_block=args.candidate_block,
        )
        if args.cache_policy == "shared":
            shared_evaluators[cache_key] = created
        return created

    summary_runs = []
    for city in args.cities:
        latitude, longitude, radius = CITIES[city]
        region = Region(latitude, longitude, 5000.0, 5000.0)
        if args.mode in {"uniform", "both"}:
            for spacing in args.spacings_km:
                evaluator = make_evaluator(city)
                run_started = time.monotonic()
                points = regional_circle_offsets(5000.0, radius, spacing)
                if args.single_point is not None:
                    points = np.asarray([args.single_point], dtype=float)
                before = len(evaluator.cache)
                scores = evaluator.evaluate_points(site_grid(region, points))
                search_s = time.monotonic() - run_started
                ranked = rank_coverage_cells(scores, args.primary_threshold_hz)
                run_id = f"{city}-uniform-{spacing:g}km"
                directory = args.output / run_id
                directory.mkdir()
                finalist_started = time.monotonic()
                finalist_points = np.asarray(
                    [[row.east_km, row.north_km] for row in ranked[: args.top_k]]
                )
                finalists = evaluator.evaluate_finalists(site_grid(region, finalist_points))
                finalist_s = time.monotonic() - finalist_started
                write_gzip_json(directory / "finalists.json.gz", finalists)
                result = {
                    "schema": "fast-coverage-search-run/v1",
                    "complete": True,
                    "session_id": args.session,
                    "city": city,
                    "mode": "uniform",
                    "spacing_km": spacing,
                    "radius_km": radius,
                    "partition_mode": args.partition_mode,
                    "thresholds_hz": thresholds,
                    "primary_threshold_hz": args.primary_threshold_hz,
                    "cache_policy": args.cache_policy,
                    "timing_s": {
                        "search": search_s,
                        "finalist_recompute": finalist_s,
                    },
                    "requested_points": len(points),
                    "newly_scored_points": len(evaluator.cache) - before,
                    "cache_hits": len(points) - (len(evaluator.cache) - before),
                    "scores": score_rows(scores),
                    "top_cells": score_rows(ranked[: args.top_k]),
                    "evaluator_metrics": evaluator.metrics(),
                    "finalists_digest": digest(directory / "finalists.json.gz"),
                }
                write_json(directory / "result.json", result)
                summary_runs.append(
                    {
                        "run_id": run_id,
                        "result_digest": digest(directory / "result.json"),
                        "evaluated_points": len(points),
                        "newly_scored_points": result["newly_scored_points"],
                        "search_s": search_s,
                    }
                )
        if args.mode in {"adaptive", "both"}:
            evaluator = make_evaluator(city)
            run_started = time.monotonic()
            before = len(evaluator.cache)

            def evaluate(points, *, active=evaluator, active_region=region):
                return active.evaluate_points(site_grid(active_region, points))

            ranked, trace = multiresolution_search(
                evaluate,
                radius_km=radius,
                region_size_km=5000.0,
                levels_km=args.levels_km,
                basins=args.basins,
                threshold_hz=args.primary_threshold_hz,
            )
            search_s = time.monotonic() - run_started
            run_id = f"{city}-adaptive"
            directory = args.output / run_id
            directory.mkdir()
            write_json(directory / "trace.json", trace)
            finalist_started = time.monotonic()
            finalist_points = np.asarray(
                [[row.east_km, row.north_km] for row in ranked[: args.top_k]]
            )
            finalists = evaluator.evaluate_finalists(site_grid(region, finalist_points))
            finalist_s = time.monotonic() - finalist_started
            write_gzip_json(directory / "finalists.json.gz", finalists)
            result = {
                "schema": "fast-coverage-search-run/v1",
                "complete": True,
                "session_id": args.session,
                "city": city,
                "mode": "adaptive",
                "levels_km": args.levels_km,
                "basins": args.basins,
                "radius_km": radius,
                "partition_mode": args.partition_mode,
                "thresholds_hz": thresholds,
                "primary_threshold_hz": args.primary_threshold_hz,
                "cache_policy": args.cache_policy,
                "timing_s": {"search": search_s, "finalist_recompute": finalist_s},
                "requested_points": sum(row["new_cell_count"] for row in trace),
                "newly_scored_points": len(evaluator.cache) - before,
                "cache_hits": sum(row["new_cell_count"] for row in trace)
                - (len(evaluator.cache) - before),
                "top_cells": score_rows(ranked[: args.top_k]),
                "evaluator_metrics": evaluator.metrics(),
                "finalists_digest": digest(directory / "finalists.json.gz"),
                "trace_digest": digest(directory / "trace.json"),
            }
            write_json(directory / "result.json", result)
            summary_runs.append(
                {
                    "run_id": run_id,
                    "result_digest": digest(directory / "result.json"),
                    "evaluated_points": result["requested_points"],
                    "newly_scored_points": result["newly_scored_points"],
                    "search_s": search_s,
                }
            )
    summary = {
        "schema": "fast-coverage-benchmark-execution/v1",
        "complete": True,
        "session_id": args.session,
        "partition_mode": args.partition_mode,
        "cache_policy": args.cache_policy,
        "thresholds_hz": thresholds,
        "primary_threshold_hz": args.primary_threshold_hz,
        "timing_s": {
            "input_load": loaded_s,
            "prediction_bank_prepare": prepared_s,
            "total": time.monotonic() - started,
        },
        "prediction_bank": bank_metadata,
        "source_snapshot": source_snapshot,
        "input_provenance": inputs["provenance"],
        "runs": summary_runs,
    }
    write_json(args.output / "benchmark-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="scan-fw-cf510316ae7f05d5")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument(
        "--cities",
        type=lambda value: parse_numbers(value, str),
        default=tuple(CITIES),
        choices=None,
    )
    parser.add_argument("--mode", choices=("uniform", "adaptive", "both"), default="both")
    parser.add_argument("--spacings-km", type=parse_numbers, default=(200.0, 100.0, 50.0))
    parser.add_argument("--levels-km", type=parse_numbers, default=(200.0, 100.0, 50.0, 25.0, 12.5))
    parser.add_argument(
        "--basins", type=lambda value: parse_numbers(value, int), default=(8, 32, 128, 128, 128)
    )
    parser.add_argument("--thresholds-hz", type=parse_numbers, default=(200.0, 500.0, 800.0))
    parser.add_argument("--primary-threshold-hz", type=float, default=200.0)
    parser.add_argument("--candidate-block", type=int, default=256)
    parser.add_argument("--partition-mode", choices=("fixed", "legacy"), default="fixed")
    parser.add_argument(
        "--cache-policy",
        choices=("cold-per-search", "shared"),
        default="cold-per-search",
        help="reuse prediction banks always; optionally reuse scored physical cells",
    )
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument(
        "--single-point",
        type=lambda value: parse_numbers(value, float),
        help="smoke-test one east,north point instead of each requested uniform grid",
    )
    args = parser.parse_args()
    if any(city not in CITIES for city in args.cities):
        parser.error(f"cities must be drawn from {tuple(CITIES)}")
    if args.primary_threshold_hz not in args.thresholds_hz:
        parser.error("primary threshold must be included in thresholds")
    if args.single_point is not None and len(args.single_point) != 2:
        parser.error("single point must contain exactly east,north")
    if args.single_point is not None and args.mode != "uniform":
        parser.error("single point is supported only in uniform mode")
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
