#!/usr/bin/env python3
"""Evaluate the sealed iteration-12 session-scale inference after selection."""

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


def _row(value: dict, method: str) -> dict:
    return {
        "method": method,
        "latitude_deg": value["latitude_deg"],
        "longitude_deg": value["longitude_deg"],
        "east_km_from_iteration10": value["east_km_from_iteration10"],
        "north_km_from_iteration10": value["north_km_from_iteration10"],
        "balanced_selection_objective": value["balanced_selection_objective"],
        "balanced_exact_capped_loss": value["balanced_exact_capped_loss"],
        "all_converged": value["all_converged"],
        "all_scale_guards_clear": value["all_scale_guards_clear"],
        "postseal_error_km": distance_km(
            (value["latitude_deg"], value["longitude_deg"]), REFERENCE
        ),
        "reference_role": "post-seal only",
    }


def _grid(rows: list[dict], field: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    east = sorted({float(row["east_km_from_iteration10"]) for row in rows})
    north = sorted({float(row["north_km_from_iteration10"]) for row in rows})
    values = np.asarray(
        [
            [
                next(
                    float(row[field])
                    for row in rows
                    if row["east_km_from_iteration10"] == e
                    and row["north_km_from_iteration10"] == n
                )
                for e in east
            ]
            for n in north
        ]
    )
    return np.asarray(east), np.asarray(north), values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.inference.read_text())
    if value.get("reference_used_for_fit") is not False:
        raise ValueError("inference must be sealed reference-free")
    baseline = [_row(row, "rate_only") for row in value["baseline_rate_only_rows"]]
    hierarchy = [
        _row(row, "common_plus_session_scale") for row in value["common_plus_session_scale_rows"]
    ]
    delta = []
    for base, scaled in zip(
        sorted(
            baseline,
            key=lambda row: (row["north_km_from_iteration10"], row["east_km_from_iteration10"]),
        ),
        sorted(
            hierarchy,
            key=lambda row: (row["north_km_from_iteration10"], row["east_km_from_iteration10"]),
        ),
        strict=True,
    ):
        delta.append(
            {
                "east_km_from_iteration10": base["east_km_from_iteration10"],
                "north_km_from_iteration10": base["north_km_from_iteration10"],
                "scale_minus_baseline_exact_capped_loss": (
                    scaled["balanced_exact_capped_loss"] - base["balanced_exact_capped_loss"]
                ),
            }
        )
    baseline_winner = baseline[0]
    hierarchy_winner = hierarchy[0]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(baseline[0])
    with (args.output_dir / "iteration12-postseal-grid.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(baseline + hierarchy)
    summary = {
        "schema": "ds1-iteration12-postseal/v1",
        "reference_role": "post-seal only",
        "portability_accepted": value["portability_accepted"],
        "baseline_winner": baseline_winner,
        "hierarchy_winner": hierarchy_winner,
        "hierarchy_minus_baseline_winner_error_km": (
            hierarchy_winner["postseal_error_km"] - baseline_winner["postseal_error_km"]
        ),
        "grid_rows": baseline + hierarchy,
        "loss_deltas": delta,
    }
    (args.output_dir / "iteration12-postseal.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    e, n, b = _grid(baseline, "balanced_exact_capped_loss")
    _e, _n, s = _grid(hierarchy, "balanced_exact_capped_loss")
    _e, _n, d = _grid(delta, "scale_minus_baseline_exact_capped_loss")
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.7), constrained_layout=True)
    labels = ["Rate-only exact loss", "Scale hierarchy exact loss", "Scale − rate-only loss"]
    for axis, image, label in zip(axes, (b, s, d), labels, strict=True):
        shown = axis.imshow(
            image,
            origin="lower",
            extent=(e[0], e[-1], n[0], n[-1]),
            interpolation="nearest",
            aspect="equal",
            cmap="viridis" if label != labels[2] else "coolwarm",
        )
        figure.colorbar(shown, ax=axis, label="capped loss")
        axis.set_title(label)
        axis.set_xlabel("east from iteration-10 (km)")
        axis.set_ylabel("north from iteration-10 (km)")
        axis.scatter(
            [baseline_winner["east_km_from_iteration10"]],
            [baseline_winner["north_km_from_iteration10"]],
            marker="o",
            s=45,
            facecolors="none",
            edgecolors="white",
            label="rate-only selected",
        )
        axis.scatter(
            [hierarchy_winner["east_km_from_iteration10"]],
            [hierarchy_winner["north_km_from_iteration10"]],
            marker="x",
            s=50,
            color="red",
            label="scale selected",
        )
    axes[0].legend(loc="best", fontsize=7)
    figure.savefig(args.output_dir / "iteration12-postseal-grid.png", dpi=180)


if __name__ == "__main__":
    main()
