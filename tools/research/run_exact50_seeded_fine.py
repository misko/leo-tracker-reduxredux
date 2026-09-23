#!/usr/bin/env python3
"""Refine exact 50 km coverage finalists on 25 and 12.5 km lattices."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import fast_coverage_inputs
import numpy as np
import search_multiresolution_tle_coverage as search

from leo.analysis.research.regional_doppler import Region

CITIES = {
    "sacramento": (38.5816, -121.4944),
    "reno": (39.5296, -119.8138),
    "denver": (39.7392, -104.9903),
}
SEARCH_BOX_KM = 1000.0
MAXIMUM_RADIUS_KM = 500.0


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_exact_seeds(
    path: Path, *, session: str, city: str, radius_km: float = MAXIMUM_RADIUS_KM
) -> tuple[np.ndarray, dict]:
    result = json.loads(path.read_text())
    full_uniform = result.get("partially_scored_pruned_points") == 0 and len(
        result.get("scores", ())
    ) == result.get("requested_points")
    if (
        result.get("schema", "fast-coverage-search-run/v1") != "fast-coverage-search-run/v1"
        or result.get("complete") is not True
        or result.get("session_id") != session
        or result.get("city") != city
        or result.get("mode") != "uniform"
        or result.get("spacing_km") != 50.0
        or result.get("partition_mode") != "fixed"
        or result.get("primary_threshold_hz") != 200.0
        or result.get("radius_km") != radius_km
        or ("schema" in result and result.get("search_box_km") != SEARCH_BOX_KM)
        or (result.get("uniform_policy") != "exact-topk" and not full_uniform)
        or len(result.get("top_cells", ())) < 15
    ):
        raise ValueError("exact 50 km seed result contract mismatch")
    seeds = np.asarray(
        [[row["east_km"], row["north_km"]] for row in result["top_cells"][:15]], dtype=float
    )
    if seeds.shape != (15, 2) or not np.all(np.isfinite(seeds)):
        raise ValueError("invalid exact seed coordinates")
    return seeds, result


def run(args) -> dict:
    if not 0 < args.radius_km <= MAXIMUM_RADIUS_KM:
        raise ValueError("radius must be positive and no greater than 500 km")
    requested_cities = [str(city) for city, _ in args.exact]
    if (
        not requested_cities
        or len(requested_cities) != len(set(requested_cities))
        or any(city not in CITIES for city in requested_cities)
    ):
        raise ValueError("one unique supported city required per exact root")
    started = time.monotonic()
    source_paths = {
        "engine_digest": Path(search.__file__),
        "loader_digest": Path(fast_coverage_inputs.__file__),
        "runner_digest": Path(__file__),
    }
    source_before = {name: digest(path) for name, path in source_paths.items()}
    inputs = fast_coverage_inputs.load(args.session, args.evidence, args.bulk_root, args.tle_root)
    banks, metadata = search.build_prediction_banks(inputs)
    evaluator = search.CoverageEvaluator(
        banks,
        np.arange(-5.0, 6.0),
        inputs["trajectory_digest"],
        (200.0, 500.0, 800.0),
        partition_mode="fixed",
    )
    receipt = {
        "schema": "exact50-seeded-fine-coverage/v1",
        "complete": True,
        "truth_accessed": False,
        "scientific_status": (
            "exact 50 km top-15 seeds followed by heuristic local 25/12.5 km "
            "refinement; no global fine-grid guarantee"
        ),
        "radius_km": args.radius_km,
        "search_box_km": SEARCH_BOX_KM,
        **source_before,
        "prediction_bank": metadata,
        "cities": {},
    }
    for city, exact_root in args.exact:
        latitude, longitude = CITIES[city]
        radius = args.radius_km
        result_path = exact_root / f"{city}-uniform-50km" / "result.json"
        seeds, _ = load_exact_seeds(result_path, session=args.session, city=city, radius_km=radius)
        region = Region(latitude, longitude, SEARCH_BOX_KM, SEARCH_BOX_KM)

        def evaluate(points, region=region):
            return evaluator.evaluate_points(region.points(points[:, 0], points[:, 1]))

        city_started = time.monotonic()
        ranked, trace = search.refine_from_centres(
            evaluate,
            seeds,
            initial_spacing_km=50.0,
            radius_km=radius,
            region_size_km=SEARCH_BOX_KM,
            levels_km=(25.0, 12.5),
            basins=(32, 32),
            threshold_hz=200.0,
        )
        top = ranked[:15]
        finalists = evaluator.evaluate_finalists(
            region.points([row.east_km for row in top[:5]], [row.north_km for row in top[:5]])
        )
        receipt["cities"][city] = {
            "exact50_result_digest": digest(result_path),
            "seed_count": len(seeds),
            "elapsed_s": time.monotonic() - city_started,
            "trace": trace,
            "top_cells": [asdict(row) for row in top],
            "top_five_finalists": finalists,
        }
    receipt["elapsed_s"] = time.monotonic() - started
    if {name: digest(path) for name, path in source_paths.items()} != source_before:
        raise ValueError("research source changed during seeded refinement")
    args.output.mkdir(parents=True)
    (args.output / "result.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="scan-fw-cf510316ae7f05d5")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--radius-km", type=float, default=MAXIMUM_RADIUS_KM)
    parser.add_argument(
        "--exact",
        nargs=2,
        action="append",
        metavar=("CITY", "RESULT_ROOT"),
        required=True,
        type=lambda value: Path(value) if "/" in value else value,
    )
    args = parser.parse_args()
    args.exact = [(str(city), Path(root)) for city, root in args.exact]
    if (
        not args.exact
        or len(args.exact) != len(set(city for city, _ in args.exact))
        or any(city not in CITIES for city, _ in args.exact)
    ):
        raise ValueError("one unique supported city required per exact root")
    if not 0 < args.radius_km <= MAXIMUM_RADIUS_KM:
        raise ValueError("radius must be positive and no greater than 500 km")
    if args.output.exists():
        raise FileExistsError(args.output)
    print(json.dumps(run(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
