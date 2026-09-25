#!/usr/bin/env python3
"""Post-seal report and PNG for the whole-session selector."""

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
    a, b = map(math.radians, (REFERENCE[0], latitude))
    dlat, dlon = b - a, math.radians(longitude - REFERENCE[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
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
    if (
        inference.get("reference_used_for_fit") is not False
        or qualification.get("inference", {}).get("sha256") != expected
    ):
        raise ValueError("unsealed or mismatched inference")
    origin = inference["origin"]
    records = [
        {
            "label": "iteration15 parent",
            "east_km": 0.0,
            "north_km": 0.0,
            **origin,
            "postseal_error_km": distance_km(origin["latitude_deg"], origin["longitude_deg"]),
        }
    ]
    for step in inference["steps"]:
        row = step["winner"]
        records.append(
            {
                "label": f"stage {step['stage_index']} step {step['translation_index']}",
                "east_km": row["east_km_from_parent"],
                "north_km": row["north_km_from_parent"],
                "latitude_deg": row["latitude_deg"],
                "longitude_deg": row["longitude_deg"],
                "postseal_error_km": distance_km(row["latitude_deg"], row["longitude_deg"]),
            }
        )
    result = {
        "schema": "ds1-iteration20-session-balanced-profiled-postseal/v1",
        "reference_role": "introduced only after inference and qualification were sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference_sha256": expected,
        "qualification_sha256": "sha256:"
        + hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
        "qualified": qualification["qualified"],
        "records": records,
        "postseal_error_km": records[-1]["postseal_error_km"],
        "zero_rate_fidelity_role": "validates geographic-model propagation only",
        "widened_rate_audit_role": "diagnostic only; excluded from qualification",
        "final_widened_rate_audit": inference.get("final_widened_rate_audit", []),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "postseal-evaluation.json").write_text(content)
    (args.output_dir / "postseal-evaluation.json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    truth_north = (REFERENCE[0] - origin["latitude_deg"]) * 111.32
    truth_east = (
        (REFERENCE[1] - origin["longitude_deg"])
        * 111.32
        * math.cos(math.radians(origin["latitude_deg"]))
    )
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(
        [r["east_km"] for r in records],
        [r["north_km"] for r in records],
        "o-",
        label="RF-selected path",
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
        xlabel="East from iteration15 (km)",
        ylabel="North from iteration15 (km)",
        title="Session-balanced nominal-Doppler path",
    )
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(range(len(records)), [r["postseal_error_km"] for r in records], "o-")
    axes[1].axhline(1.0, color="#d62728", linestyle="--", label="1 km")
    axes[1].set(xlabel="Search step", ylabel="Post-seal error (km)", title="Evaluation after seal")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.savefig(args.output_dir / "session-balanced-profiled-basin.png", dpi=180)


if __name__ == "__main__":
    main()
