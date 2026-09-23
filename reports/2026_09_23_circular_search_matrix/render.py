#!/usr/bin/env python3
"""Verify and render the self-contained circular-search matrix report."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from qualify import verify

HERE = Path(__file__).resolve().parent
CITIES = {"sacramento": 350.0, "reno": 750.0, "denver": 2500.0}
COHORTS = ("single", "quarter8")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def main():
    verified = verify()
    reference_path = HERE / "inputs/evaluation-reference.json"
    reference = read(reference_path)
    rows = []
    for cohort in COHORTS:
        for city, radius in CITIES.items():
            directory = HERE / "inputs" / f"{cohort}-{city}"
            result_path = directory / "refinement-result.json"
            receipt_path = directory / "circle-receipt.json"
            qualification_path = directory / "qualification.json"
            result, receipt = read(result_path), read(receipt_path)
            leading, gaps, null_majority = [], [], 0
            for track in result["tracks"]:
                weights = sorted([track["null_weight"], *[candidate["weight"] for candidate in track["candidates"]]], reverse=True)
                if len(weights) == 1:
                    weights.append(0.0)
                leading.append(weights[0])
                gaps.append(weights[0] - weights[1])
                null_majority += track["null_weight"] == weights[0]
            rows.append({
                "cohort": cohort, "city": city, "radius_km": radius,
                "latitude_deg": result["latitude_deg"], "longitude_deg": result["longitude_deg"],
                "evaluation_error_km": distance_km(result["latitude_deg"], result["longitude_deg"], reference["latitude_deg"], reference["longitude_deg"]),
                "training_score": result["training_score"], "heldout_score": result["heldout_score"],
                "boundary_distance_km": receipt["boundary_distance_km"],
                "track_count": result["track_count"], "observation_count": result["observation_count"],
                "null_majority_tracks": null_majority,
                "median_leading_weight": float(np.median(leading)), "median_leader_gap": float(np.median(gaps)),
                "result_digest": digest(result_path), "receipt_digest": digest(receipt_path),
                "qualification_digest": digest(qualification_path),
            })
    (HERE / "matrix.json").write_text(json.dumps({
        "schema": "circular-search-matrix-evaluation/v1",
        "position_truth_used_for_inference": False,
        "evaluation_reference_digest": digest(reference_path), "rows": rows,
    }, indent=2, sort_keys=True) + "\n")

    fig, axes = plt.subplots(2, 3, figsize=(11, 6), constrained_layout=True)
    for row in rows:
        i, j = COHORTS.index(row["cohort"]), list(CITIES).index(row["city"])
        ax = axes[i, j]
        ax.bar(["error", "boundary"], [row["evaluation_error_km"], row["boundary_distance_km"]])
        ax.set_title(f"{row['cohort']} / {row['city']}\nR={row['radius_km']:.0f} km")
        ax.set_ylabel("km")
        ax.text(0, row["evaluation_error_km"], f"{row['evaluation_error_km']:.2f}", ha="center", va="bottom")
        ax.text(1, row["boundary_distance_km"], f"{row['boundary_distance_km']:.1f}", ha="center", va="bottom")
    fig.savefig(HERE / "matrix.png", dpi=160)
    plt.close(fig)

    files = {}
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.json" and "__pycache__" not in path.parts:
            files[str(path.relative_to(HERE))] = {"sha256": digest(path), "bytes": path.stat().st_size}
    (HERE / "artifact-manifest.json").write_text(json.dumps({"schema": "report-artifact-manifest/v1", "files": files}, indent=2) + "\n")
    print(json.dumps({"verified": verified, "rows": len(rows), "manifest_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
