#!/usr/bin/env python3
"""Post-seal-only truth comparison for the fixed iteration-8 winner."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def contains_truth(value: Any) -> bool:
    if isinstance(value, dict):
        forbidden = {"reference_coordinate", "reference_error_km", "truth"}
        return bool(forbidden & value.keys()) or any(
            contains_truth(item) for item in value.values()
        )
    return any(contains_truth(item) for item in value) if isinstance(value, list) else False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False or contains_truth(inference):
        raise ValueError("inference artifact is not sealed from truth")
    winner = inference["winner"]
    error = distance_km((winner["latitude_deg"], winner["longitude_deg"]), REFERENCE)
    row = {
        "latitude_deg": winner["latitude_deg"],
        "longitude_deg": winner["longitude_deg"],
        "postseal_error_km": error,
        "balanced_exact_capped_loss": winner["balanced_exact_capped_loss"],
        "group_00_tau_s": winner["best_exact_by_group"]["20260921_00"]["tau_s"],
        "group_16_tau_s": winner["best_exact_by_group"]["20260921_16"]["tau_s"],
        "reference_role": "post-seal only",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration8-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration8-postseal/v1",
                "reference_role": "post-seal only",
                "rows": [row],
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration8-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    fig, axis = plt.subplots(figsize=(5, 3), constrained_layout=True)
    axis.bar(["joint shared position"], [error], color="#3b82a0")
    axis.set_ylabel("post-seal error (km)")
    axis.set_title("DS1 iteration-8 joint position")
    fig.savefig(args.output_dir / "iteration8-postseal.png", dpi=160)
    print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
