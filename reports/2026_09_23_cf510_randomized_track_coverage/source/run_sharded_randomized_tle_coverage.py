#!/usr/bin/env python3
"""Run the frozen randomized TLE coverage grid in disjoint deterministic slices."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import map_randomized_tle_coverage as kernel
import numpy as np


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _worker(args: argparse.Namespace) -> None:
    original = kernel.Region.grid

    def sliced(region, spacing_km):
        grid = original(region, spacing_km)
        keep = np.arange(len(grid)) % args.shards == args.worker_index
        return region.points(grid.east_km[keep], grid.north_km[keep])

    kernel.Region.grid = sliced
    values = json.loads(args.kernel_arguments)
    for name in ("output", "evidence", "bulk_root", "tle_root"):
        values[name] = Path(values[name])
    kernel.run(SimpleNamespace(**values))


def _merge(args: argparse.Namespace, kernel_args: dict, elapsed_s: float) -> None:
    region = kernel.Region(
        kernel_args["center_lat"], kernel_args["center_lon"],
        kernel_args["region_size_km"], kernel_args["region_size_km"],
    )
    square = region.grid(kernel_args["spacing_km"])
    keep = np.hypot(square.east_km, square.north_km) <= kernel_args["radius_km"]
    full = region.points(square.east_km[keep], square.north_km[keep])
    coordinate_to_index = {
        (float(e), float(n)): i
        for i, (e, n) in enumerate(zip(full.east_km, full.north_km, strict=True))
    }
    cells: list[dict | None] = [None] * len(full)
    seeds = np.empty((10, len(full)), dtype="U128")
    candidate_tmp = args.output / "candidates.jsonl.gz.tmp"
    args.output.mkdir(parents=True)
    first = None
    with gzip.open(candidate_tmp, "wt") as target:
        for shard in range(args.shards):
            root = args.output.parent / f"{args.output.name}.shards" / f"{shard:02d}"
            result = json.loads((root / "result.json").read_text())
            first = first or result
            for name in (
                "source_digest", "snapshot_digest", "snapshot_collected_utc_ns",
                "observer_label", "track_inventory", "candidate_catalogue_count",
                "threshold_hz_strict_less_than", "radius_km", "spacing_km", "session_id",
            ):
                if result[name] != first[name]:
                    raise ValueError(f"shard invariant differs: {name}")
            local_to_global = {}
            for local, cell in enumerate(result["cells"]):
                global_index = coordinate_to_index[(cell["east_km"], cell["north_km"])]
                if cells[global_index] is not None:
                    raise ValueError("duplicate sharded cell")
                cell["index"] = global_index
                cells[global_index] = cell
                local_to_global[local] = global_index
            with np.load(root / "map.npz") as arrays:
                for local, global_index in local_to_global.items():
                    seeds[:, global_index] = arrays["partition_seeds"][:, local]
            with gzip.open(root / "candidates.jsonl.gz", "rt") as source:
                for line in source:
                    row = json.loads(line)
                    row["cell_index"] = local_to_global[row["cell_index"]]
                    target.write(json.dumps(row) + "\n")
    if any(cell is None for cell in cells):
        raise ValueError("shards do not cover the original grid")
    candidate_path = args.output / "candidates.jsonl.gz"
    candidate_tmp.replace(candidate_path)
    complete_cells = list(cells)
    order = sorted(
        range(len(complete_cells)),
        key=lambda i: (
            -complete_cells[i]["qualifying_track_count"],
            complete_cells[i]["clipped_best_rms_sum_hz"],
            complete_cells[i]["east_km"], complete_cells[i]["north_km"],
        ),
    )
    result = dict(first)
    result.update({
        "cells": complete_cells,
        "top_five_cells": [complete_cells[i] for i in order[:5]],
        "maximum_count_tie_cells": sum(
            cell["qualifying_track_count"]
            == complete_cells[order[0]]["qualifying_track_count"]
            for cell in complete_cells
        ),
        "candidate_inventory_digest": _digest(candidate_path),
        "elapsed_s": elapsed_s,
        "sharded_execution": {
            "shards": args.shards,
            "kernel_source_digest": first["source_digest"],
            "wrapper_source_digest": _digest(Path(__file__)),
            "exact_original_grid_partition": "square-grid index modulo shards",
        },
    })
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    np.savez_compressed(
        args.output / "map.npz", east_km=full.east_km, north_km=full.north_km,
        latitude_deg=full.latitude_deg, longitude_deg=full.longitude_deg,
        count=np.asarray([cell["qualifying_track_count"] for cell in complete_cells]),
        tie_score=np.asarray([cell["clipped_best_rms_sum_hz"] for cell in complete_cells]),
        partition_seeds=seeds,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shards", type=int, default=12)
    parser.add_argument("--worker-index", type=int)
    parser.add_argument("--kernel-arguments", help=argparse.SUPPRESS)
    args, rest = parser.parse_known_args()
    if args.worker_index is not None:
        _worker(args)
        return
    kernel_parser = argparse.ArgumentParser()
    kernel_parser.add_argument("--session", required=True)
    kernel_parser.add_argument("--evidence", type=Path, required=True)
    kernel_parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    kernel_parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    kernel_parser.add_argument("--center-lat", type=float, required=True)
    kernel_parser.add_argument("--center-lon", type=float, required=True)
    kernel_parser.add_argument("--radius-km", type=float, required=True)
    kernel_parser.add_argument("--region-size-km", type=float, default=5000)
    kernel_parser.add_argument("--spacing-km", type=float, default=50)
    kernel_parser.add_argument("--threshold-hz", type=float, default=800)
    kernel_parser.add_argument("--track-count", type=int, default=10)
    kernel_parser.add_argument("--observer-label", required=True)
    kernel_parser.add_argument("--single-observer", action="store_true")
    values = vars(kernel_parser.parse_args(rest))
    shard_root = args.output.parent / f"{args.output.name}.shards"
    if args.output.exists() or shard_root.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    shard_root.mkdir(parents=True)
    processes = []
    for shard in range(args.shards):
        worker_values = {
            name: str(value) if isinstance(value, Path) else value
            for name, value in values.items()
        }
        worker_values["output"] = str(shard_root / f"{shard:02d}")
        command = [
            sys.executable, str(Path(__file__)), "--output", str(args.output),
            "--shards", str(args.shards), "--worker-index", str(shard),
            "--kernel-arguments", json.dumps(worker_values),
        ]
        processes.append(subprocess.Popen(command))
    for process in processes:
        if process.wait() != 0:
            raise RuntimeError("coverage shard failed")
    values["output"] = args.output
    _merge(args, values, time.monotonic() - started)


if __name__ == "__main__":
    main()
