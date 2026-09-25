#!/usr/bin/env python3
"""Post-seal evaluation and visualization for DS1 iteration 19."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(latitude: float, longitude: float) -> float:
    earth = 6371.0088
    lat1, lat2 = map(math.radians, (REFERENCE[0], latitude))
    dlat, dlon = lat2 - lat1, math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    parent = inference["origin"]
    records = [
        {
            "label": "iteration-15 parent",
            "latitude_deg": parent["latitude_deg"],
            "longitude_deg": parent["longitude_deg"],
            "east_km": 0.0,
            "north_km": 0.0,
            "postseal_error_km": distance_km(parent["latitude_deg"], parent["longitude_deg"]),
        }
    ]
    for step in inference["steps"]:
        winner = step["winner"]
        records.append(
            {
                "label": f"stage {step['stage_index']} step {step['translation_index']}",
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "east_km": winner["east_km_from_iteration12"],
                "north_km": winner["north_km_from_iteration12"],
                "postseal_error_km": distance_km(
                    winner["latitude_deg"], winner["longitude_deg"]
                ),
            }
        )
    result = {
        "schema": "ds1-iteration19-widened-rate-bound-postseal/v1",
        "reference_role": "introduced only after inference was sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference_sha256": "sha256:" + hashlib.sha256(args.inference.read_bytes()).hexdigest(),
        "qualified": inference["qualified"],
        "records": records,
        "postseal_error_km": records[-1]["postseal_error_km"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output = args.output_dir / "postseal-evaluation.json"
    output.write_text(content)
    output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    truth_north = (REFERENCE[0] - parent["latitude_deg"]) * 111.32
    truth_east = (
        (REFERENCE[1] - parent["longitude_deg"])
        * 111.32
        * math.cos(math.radians(parent["latitude_deg"]))
    )
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(
        [row["east_km"] for row in records],
        [row["north_km"] for row in records],
        "o-",
        label="widened-rate-bound path",
    )
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
        xlabel="East from parent (km)",
        ylabel="North from parent (km)",
        title="RF-selected path",
    )
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(
        range(len(records)), [row["postseal_error_km"] for row in records], "o-"
    )
    axes[1].axhline(1.0, color="#d62728", linestyle="--", label="1 km")
    axes[1].set(
        xlabel="Search step",
        ylabel="Post-seal error (km)",
        title="Evaluation after seal",
    )
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.savefig(args.output_dir / "widened-rate-bound-basin.png", dpi=180)


if __name__ == "__main__":
    main()
