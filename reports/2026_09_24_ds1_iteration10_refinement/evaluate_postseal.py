#!/usr/bin/env python3
"""Evaluate sealed iteration-10 inference after selection is complete."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    latitude_a, longitude_a, latitude_b, longitude_b = map(math.radians, (*first, *second))
    haversine = (
        math.sin((latitude_b - latitude_a) / 2) ** 2
        + math.cos(latitude_a)
        * math.cos(latitude_b)
        * math.sin((longitude_b - longitude_a) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(haversine))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.inference.read_text())
    if data.get("reference_used_for_fit") is not False:
        raise ValueError("unsealed inference")
    winner = data["winner"]
    row = {
        "latitude_deg": winner["latitude_deg"],
        "longitude_deg": winner["longitude_deg"],
        "east_km_from_iteration9": winner["east_km_from_iteration9"],
        "north_km_from_iteration9": winner["north_km_from_iteration9"],
        "balanced_exact_capped_loss": winner["balanced_exact_capped_loss"],
        "postseal_error_km": distance_km(
            (winner["latitude_deg"], winner["longitude_deg"]), REFERENCE
        ),
        "group_00_tau_s": winner["best_exact_by_group"]["20260921_00"]["tau_s"],
        "group_16_tau_s": winner["best_exact_by_group"]["20260921_16"]["tau_s"],
        "reference_role": "post-seal only",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration10-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration10-postseal/v1",
                "reference_role": "post-seal only",
                "rows": [row],
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration10-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    figure, axis = plt.subplots(figsize=(4, 3), constrained_layout=True)
    axis.bar(["joint refinement"], [row["postseal_error_km"]])
    axis.set_ylabel("post-seal error (km)")
    figure.savefig(args.output_dir / "iteration10-postseal.png", dpi=160)
    print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
