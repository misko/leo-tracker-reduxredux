#!/usr/bin/env python3
"""Post-seal comparison of DS1 iteration-12 level one and its refinement."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (*first, *second))
    h = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _grid(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    east = sorted({float(row["east_km_from_iteration12_level1"]) for row in rows})
    north = sorted({float(row["north_km_from_iteration12_level1"]) for row in rows})
    values = np.asarray(
        [
            [
                next(
                    float(row["balanced_exact_capped_loss"])
                    for row in rows
                    if row["east_km_from_iteration12_level1"] == e
                    and row["north_km_from_iteration12_level1"] == n
                )
                for e in east
            ]
            for n in north
        ]
    )
    return np.asarray(east), np.asarray(north), values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level1", type=Path, required=True)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    level1 = json.loads(args.level1.read_text())
    refined = json.loads(args.refinement.read_text())
    if (
        level1.get("reference_used_for_fit") is not False
        or refined.get("reference_used_for_fit") is not False
    ):
        raise ValueError("only sealed reference-free inferences may be evaluated")
    records = []
    for label, value in (("level1", level1), ("refinement", refined)):
        winner = value["winner"]
        records.append(
            {
                "level": label,
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "balanced_exact_capped_loss": winner["balanced_exact_capped_loss"],
                "balanced_selection_objective": winner["balanced_selection_objective"],
                "postseal_error_km": distance_km(
                    (winner["latitude_deg"], winner["longitude_deg"]), REFERENCE
                ),
                "reference_role": "post-seal only",
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "iteration12-refinement-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    e, n, loss = _grid(refined["common_plus_session_scale_rows"])
    figure, axes = plt.subplots(1, 2, figsize=(8, 3.4), constrained_layout=True)
    image = axes[0].imshow(
        loss,
        origin="lower",
        extent=(e[0], e[-1], n[0], n[-1]),
        interpolation="nearest",
        aspect="equal",
    )
    figure.colorbar(image, ax=axes[0], label="exact capped loss")
    axes[0].set(
        title="Level-2 scale hierarchy",
        xlabel="east from level-1 winner (km)",
        ylabel="north from level-1 winner (km)",
    )
    axes[0].scatter(
        [refined["winner"]["east_km_from_iteration12_level1"]],
        [refined["winner"]["north_km_from_iteration12_level1"]],
        marker="x",
        color="red",
        s=50,
    )
    axes[1].bar([row["level"] for row in records], [row["postseal_error_km"] for row in records])
    axes[1].set(title="Post-seal error", ylabel="error (km)")
    figure.savefig(args.output_dir / "iteration12-refinement-postseal.png", dpi=180)
    output = {
        "schema": "ds1-iteration12-refinement-postseal/v1",
        "reference_role": "post-seal only",
        "records": records,
        "refinement_minus_level1_error_km": (
            records[1]["postseal_error_km"] - records[0]["postseal_error_km"]
        ),
    }
    (args.output_dir / "iteration12-refinement-postseal.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
