#!/usr/bin/env python3
"""Run the frozen regional scorer on a preregistered circular 50 km grid."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from leo.analysis.research.regional_doppler import Region


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def circular_points(region, radius_km, spacing_km):
    if not np.isfinite(radius_km) or radius_km <= 0:
        raise ValueError("positive finite circle radius required")
    if 2 * radius_km > min(region.width_km, region.height_km):
        raise ValueError("circle must fit inside declared region")
    grid = region.grid(spacing_km)
    keep = np.hypot(grid.east_km, grid.north_km) <= radius_km
    if not np.any(keep):
        raise ValueError("circle contains no grid cells")
    return {"east_km": grid.east_km[keep].tolist(), "north_km": grid.north_km[keep].tolist()}


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    region = Region(args.center_lat, args.center_lon, args.region_size_km, args.region_size_km)
    points = circular_points(region, args.radius_km, args.spacing_km)
    args.output.mkdir(parents=True)
    points_path = args.output / "declared-circle-points.json"
    points_path.write_text(json.dumps(points, indent=2) + "\n")
    source = Path(args.scorer)
    spec = importlib.util.spec_from_file_location("frozen_circular_regional_scorer", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scoring_output = args.output / "scoring"
    module.run(
        SimpleNamespace(
            evidence=args.evidence,
            output=scoring_output,
            center_lat=args.center_lat,
            center_lon=args.center_lon,
            region_size_km=args.region_size_km,
            spacing_km=args.spacing_km,
            altitude_m=0.0,
            sigma_hz=250.0,
            effective_count=6.0,
            clock_s=0.0,
            max_per_partition=args.max_per_partition,
            scan_limit=args.scan_limit,
            shifted_grid=False,
            individual_sources=False,
            points=points_path,
            minimum_elevation_deg=-1.0,
        )
    )
    result = json.loads((scoring_output / "result.json").read_text())
    distance = float(np.hypot(result["east_km"], result["north_km"]))
    if distance > args.radius_km + 1e-9:
        raise RuntimeError("scorer selected a point outside the declared circle")
    receipt = {
        "schema": "circular-regional-acquisition/v1",
        "complete": True,
        "position_truth_used": False,
        "constraint_applied_before_scoring": True,
        "radius_km": args.radius_km,
        "spacing_km": args.spacing_km,
        "grid_cell_count": len(points["east_km"]),
        "selected_radius_km": distance,
        "boundary_distance_km": args.radius_km - distance,
        "evidence_inventory_digest": digest(args.evidence / "inventory.json"),
        "points_digest": digest(points_path),
        "frozen_scorer_digest": digest(source),
        "scoring_result_digest": digest(scoring_output / "result.json"),
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scorer", type=Path, required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--radius-km", type=float, required=True)
    parser.add_argument("--region-size-km", type=float, default=5000.0)
    parser.add_argument("--spacing-km", type=float, default=50.0)
    parser.add_argument("--max-per-partition", type=int, default=6)
    parser.add_argument("--scan-limit", type=int)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
