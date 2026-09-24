#!/usr/bin/env python3
"""Post-seal evaluation and plot for DS1 iteration 18."""

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
    dlat = lat2 - lat1
    dlon = math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    qualification = json.loads(args.qualification.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    expected = "sha256:" + hashlib.sha256(args.inference.read_bytes()).hexdigest()
    if qualification.get("inference", {}).get("sha256") != expected:
        raise ValueError("qualification is not bound to inference")
    origin = inference["origin"]
    records = [
        {
            "label": "iteration-15 parent",
            "latitude_deg": origin["latitude_deg"],
            "longitude_deg": origin["longitude_deg"],
            "east_km": 0.0,
            "north_km": 0.0,
            "postseal_error_km": distance_km(origin["latitude_deg"], origin["longitude_deg"]),
        }
    ]
    geographic = inference.get("geographic")
    if geographic:
        for step in geographic["steps"]:
            winner = step["winner"]
            records.append(
                {
                    "label": f"stage {step['stage_index']} step {step['translation_index']}",
                    "latitude_deg": winner["latitude_deg"],
                    "longitude_deg": winner["longitude_deg"],
                    "east_km": winner["east_km_from_parent"],
                    "north_km": winner["north_km_from_parent"],
                    "postseal_error_km": distance_km(
                        winner["latitude_deg"], winner["longitude_deg"]
                    ),
                }
            )
    result = {
        "schema": "ds1-iteration18-timing-refresh-postseal/v1",
        "reference_role": "introduced only after inference and qualification were sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference_sha256": expected,
        "qualification_sha256": "sha256:"
        + hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
        "qualified": qualification["qualified"],
        "status": inference["status"],
        "selected_taus_s": inference["timing_refresh"]["selected_taus_s"],
        "records": records,
        "postseal_error_km": records[-1]["postseal_error_km"] if geographic else None,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output = args.output_dir / "postseal-evaluation.json"
    output.write_text(content)
    output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    timing = json.loads(Path(inference["timing_refresh"]["path"]).read_text())
    for group, color in zip(("20260921_00", "20260921_16"), ("#1f77b4", "#ff7f0e"), strict=True):
        rows = [row for step in timing["groups"][group]["steps"] for row in step["audits"]]
        unique = {float(row["tau_s"]): row for row in rows}
        ordered = [unique[tau] for tau in sorted(unique)]
        axes[0].plot(
            [row["tau_s"] for row in ordered],
            [row["rate_only"]["selection_objective"] for row in ordered],
            "o-",
            color=color,
            label=group,
        )
    axes[0].set(
        xlabel="Shared group tau (s)",
        ylabel="Selection objective",
        title="Sealed timing refresh",
    )
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    if geographic:
        axes[1].plot(
            range(len(records)), [row["postseal_error_km"] for row in records], "o-"
        )
        axes[1].axhline(1.0, color="#d62728", linestyle="--", label="1 km")
        axes[1].legend()
    else:
        axes[1].text(0.5, 0.5, "Geographic search not started", ha="center", va="center")
    axes[1].set(
        xlabel="Geographic search step",
        ylabel="Post-seal error (km)",
        title="Evaluation after seal",
    )
    axes[1].grid(alpha=0.25)
    figure.savefig(args.output_dir / "timing-refresh-basin.png", dpi=180)


if __name__ == "__main__":
    main()
