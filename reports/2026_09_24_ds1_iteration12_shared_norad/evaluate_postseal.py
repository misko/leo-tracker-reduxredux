#!/usr/bin/env python3
"""Post-seal-only DS1 iteration-12 visual evaluation."""

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
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (*first, *second))
    h = math.sin((lat_b - lat_a) / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(
        (lon_b - lon_a) / 2
    ) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.inference.read_text())
    if data.get("reference_used_for_fit") is not False:
        raise ValueError("inference was not reference-free")
    rows = []
    for row in data["rows"]:
        rows.append(
            {
                "latitude_deg": row["latitude_deg"],
                "longitude_deg": row["longitude_deg"],
                "east_km_from_iteration10": row["east_km_from_iteration10"],
                "north_km_from_iteration10": row["north_km_from_iteration10"],
                "balanced_exact_capped_loss": row["fit"]["balanced_exact_capped_loss"],
                "postseal_error_km": distance_km(
                    (row["latitude_deg"], row["longitude_deg"]), REFERENCE
                ),
                "cross_group_shared_norad_count": row["fit"]["cross_group_shared_norad_count"],
                "selected": coordinate_key(row) == coordinate_key(data["winner"]),
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration12-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration12-postseal/v1",
                "reference_role": "post-seal only",
                "winner": next(row for row in rows if row["selected"]),
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration12-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figure, axis = plt.subplots(figsize=(5, 4), constrained_layout=True)
    scatter = axis.scatter(
        [row["east_km_from_iteration10"] for row in rows],
        [row["north_km_from_iteration10"] for row in rows],
        c=[row["balanced_exact_capped_loss"] for row in rows],
        cmap="viridis_r",
        s=110,
    )
    winner = next(row for row in rows if row["selected"])
    axis.scatter(
        winner["east_km_from_iteration10"],
        winner["north_km_from_iteration10"],
        marker="*",
        s=260,
        c="red",
        edgecolors="black",
        label="selected",
    )
    axis.set_xlabel("east from iteration-10 seed (km)")
    axis.set_ylabel("north from iteration-10 seed (km)")
    axis.set_title("Shared per-NORAD exact loss; reference shown only in CSV/JSON")
    axis.legend(loc="best")
    figure.colorbar(scatter, ax=axis, label="balanced capped loss")
    figure.savefig(args.output_dir / "iteration12-postseal.png", dpi=160)


def coordinate_key(row: dict) -> tuple[float, float]:
    return (round(float(row["latitude_deg"]), 10), round(float(row["longitude_deg"]), 10))


if __name__ == "__main__":
    main()
