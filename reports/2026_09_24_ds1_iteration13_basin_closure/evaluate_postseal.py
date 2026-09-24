#!/usr/bin/env python3
"""Evaluate a sealed iteration-13 basin closure against the surveyed site."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (*first, *second))
    haversine = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(haversine))


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    if not inference.get("steps"):
        raise ValueError("inference has no completed search steps")

    rows = []
    parent = inference["origin"]
    rows.append(
        {
            "label": "iteration-12 parent",
            "stage_index": -1,
            "translation_index": -1,
            "spacing_km": None,
            "latitude_deg": parent["latitude_deg"],
            "longitude_deg": parent["longitude_deg"],
            "postseal_error_km": distance_km(
                (parent["latitude_deg"], parent["longitude_deg"]), REFERENCE
            ),
            "winner_on_edge": True,
        }
    )
    for step in inference["steps"]:
        winner = step["winner"]
        rows.append(
            {
                "label": f"stage {step['stage_index']} step {step['translation_index']}",
                "stage_index": step["stage_index"],
                "translation_index": step["translation_index"],
                "spacing_km": step["spacing_km"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "postseal_error_km": distance_km(
                    (winner["latitude_deg"], winner["longitude_deg"]), REFERENCE
                ),
                "winner_on_edge": step["winner_on_edge"],
            }
        )
    raw_rows = []
    for step in inference["steps"]:
        winner = min(
            step["ranked_coordinates"],
            key=lambda row: (
                row["balanced_exact_capped_loss"],
                row["north_km_from_iteration12"],
                row["east_km_from_iteration12"],
            ),
        )
        raw_rows.append(
            {
                "label": f"stage {step['stage_index']} step {step['translation_index']}",
                "stage_index": step["stage_index"],
                "translation_index": step["translation_index"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "east_km_from_iteration12": winner["east_km_from_iteration12"],
                "north_km_from_iteration12": winner["north_km_from_iteration12"],
                "postseal_error_km": distance_km(
                    (winner["latitude_deg"], winner["longitude_deg"]), REFERENCE
                ),
                "role": "post-seal diagnostic; did not steer the planned path",
            }
        )
    final = rows[-1]
    output = {
        "schema": "ds1-iteration13-basin-closure-postseal/v1",
        "reference_role": "introduced only after inference was sealed",
        "reference_coordinate": {
            "latitude_deg": REFERENCE[0],
            "longitude_deg": REFERENCE[1],
        },
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "qualified": bool(inference.get("qualified")),
        "records": rows,
        "raw_cap800_diagnostic_records": raw_rows,
        "headline": {
            "parent_error_km": rows[0]["postseal_error_km"],
            "final_error_km": final["postseal_error_km"],
            "improvement_km": rows[0]["postseal_error_km"] - final["postseal_error_km"],
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    json_path = args.output_dir / "postseal-evaluation.json"
    json_path.write_text(content)
    json_path.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    with (args.output_dir / "postseal-trajectory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    east = [0.0] + [step["winner"]["east_km_from_iteration12"] for step in inference["steps"]]
    north = [0.0] + [step["winner"]["north_km_from_iteration12"] for step in inference["steps"]]
    errors = [row["postseal_error_km"] for row in rows]
    raw_east = [0.0] + [row["east_km_from_iteration12"] for row in raw_rows]
    raw_north = [0.0] + [row["north_km_from_iteration12"] for row in raw_rows]
    truth_north = (REFERENCE[0] - parent["latitude_deg"]) * 111.32
    truth_east = (
        (REFERENCE[1] - parent["longitude_deg"])
        * 111.32
        * math.cos(math.radians(parent["latitude_deg"]))
    )
    axes[0].plot(east, north, "o-", color="#2878b5")
    axes[0].plot(
        raw_east,
        raw_north,
        "x--",
        color="#e76f51",
        alpha=0.8,
        label="raw cap-800 diagnostic",
    )
    axes[0].scatter([east[0]], [north[0]], marker="s", color="#666666", label="parent")
    axes[0].scatter([east[-1]], [north[-1]], marker="*", s=150, color="#d62728", label="final")
    axes[0].scatter(
        [truth_east],
        [truth_north],
        marker="*",
        s=170,
        color="#f4b400",
        edgecolor="black",
        label="surveyed reference (post-seal)",
    )
    axes[0].set(
        xlabel="East from iteration-12 winner (km)",
        ylabel="North from iteration-12 winner (km)",
        title="RF-selected paths and post-seal reference",
    )
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(
        range(len(rows)), errors, "o-", color="#2a9d8f", label="planned regularized path"
    )
    axes[1].plot(
        range(1, len(raw_rows) + 1),
        [row["postseal_error_km"] for row in raw_rows],
        "x--",
        color="#e76f51",
        label="raw cap-800 diagnostic",
    )
    axes[1].axhline(1.0, color="#d62728", linestyle="--", label="1 km")
    axes[1].set(
        xlabel="Completed search step",
        ylabel="Post-seal error (km)",
        title="Evaluation after inference seal",
    )
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.savefig(args.output_dir / "basin-closure.png", dpi=180)


if __name__ == "__main__":
    main()
