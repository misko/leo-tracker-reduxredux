#!/usr/bin/env python3
"""Evaluate sealed iteration-12 inference against the reference after selection."""

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
    parser = argparse.ArgumentParser(description=__doc__)
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
        "balanced_exact_cap800_loss": winner["balanced_exact_capped_loss"],
        "postseal_error_km": distance_km(
            (winner["latitude_deg"], winner["longitude_deg"]), REFERENCE
        ),
        "group_00_tau_s": winner["best_exact_by_group"]["20260921_00"]["tau_s"],
        "group_16_tau_s": winner["best_exact_by_group"]["20260921_16"]["tau_s"],
        "reference_role": "post-seal only",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration12-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration12-postseal/v1",
                "reference_role": "post-seal only",
                "rows": [row],
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration12-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    figure, axis = plt.subplots(figsize=(5, 3.5), constrained_layout=True)
    axis.bar(["iteration 10", "iteration 12"], [1.1792858, row["postseal_error_km"]])
    axis.axhline(1.0, linestyle="--", color="0.35", label="sub-km target")
    axis.set_ylabel("post-seal position error (km)")
    axis.set_title("DS1 joint TRAIN position error")
    axis.legend()
    figure.savefig(args.output_dir / "iteration12-postseal.png", dpi=180)
    print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
