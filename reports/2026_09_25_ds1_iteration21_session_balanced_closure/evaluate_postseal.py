#!/usr/bin/env python3
"""Post-seal plot for the iteration21 extension."""

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
    left, right = map(math.radians, (REFERENCE[0], latitude))
    dlat, dlon = right - left, math.radians(longitude - REFERENCE[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(left) * math.cos(right) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference, qualification = (
        json.loads(args.inference.read_text()),
        json.loads(args.qualification.read_text()),
    )
    expected = "sha256:" + hashlib.sha256(args.inference.read_bytes()).hexdigest()
    if qualification.get("inference", {}).get("sha256") != expected:
        raise ValueError("qualification is not bound to inference")
    origin = inference["origin_i20_terminal"]
    records = []
    for step in inference["steps"]:
        winner = step["winner"]
        records.append(
            {
                "stage": step["stage_index"],
                "translation": step["translation_index"],
                "east_km_from_i20_terminal": winner["east_km_from_parent"],
                "north_km_from_i20_terminal": winner["north_km_from_parent"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "postseal_error_km": distance_km(winner["latitude_deg"], winner["longitude_deg"]),
            }
        )
    result = {
        "schema": "ds1-iteration21-session-balanced-closure-postseal/v1",
        "reference_role": "introduced only after inference and qualification were sealed",
        "inference_sha256": expected,
        "qualified": qualification["qualified"],
        "records": records,
        "postseal_error_km": records[-1]["postseal_error_km"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "postseal-evaluation.json").write_text(content)
    (args.output_dir / "postseal-evaluation.json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    origin_error = distance_km(origin["latitude_deg"], origin["longitude_deg"])
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(
        [row["east_km_from_i20_terminal"] for row in records],
        [row["north_km_from_i20_terminal"] for row in records],
        "o-",
        label="RF-selected extension",
    )
    axes[0].set(
        xlabel="East from iteration20 terminal (km)",
        ylabel="North from iteration20 terminal (km)",
        title="Session-balanced extension path",
    )
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(
        [0] + list(range(1, len(records) + 1)),
        [origin_error] + [r["postseal_error_km"] for r in records],
        "o-",
    )
    axes[1].axhline(1.0, color="#d62728", linestyle="--", label="1 km")
    axes[1].set(
        xlabel="Extension step", ylabel="Post-seal error (km)", title="Evaluation after seal"
    )
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.savefig(args.output_dir / "session-balanced-closure.png", dpi=180)


if __name__ == "__main__":
    main()
