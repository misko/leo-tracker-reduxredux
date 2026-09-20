"""Publish a sealed wide-search replay and evaluate it against an explicit reference."""

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from replay_regional_doppler import write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["coarse", "fine", "polish", "height", "reference", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    # Seal inference before reading the independently supplied reference.
    sources = {str(path): sha(path) for path in [a.polish / "inference.json", a.height]}
    result = json.loads((a.polish / "inference.json").read_text())
    height = json.loads(a.height.read_text())
    reference = json.loads(a.reference.read_text())
    rows = []

    def evaluate(label, row):
        lat, lon = row["latitude_deg"], row["longitude_deg"]
        lat0 = math.radians(reference["latitude_deg"])
        dlat = math.radians(lat - reference["latitude_deg"])
        dlon = math.radians(lon - reference["longitude_deg"])
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat0) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
        )
        return dict(
            label=label,
            error_m=2 * 6371008.8 * math.asin(math.sqrt(h)),
            east_km=6371.0088 * math.cos(lat0) * dlon,
            north_km=6371.0088 * dlat,
            latitude_deg=lat,
            longitude_deg=lon,
        )

    for row in result["models"]:
        rows.append(evaluate(row["label"], row))
    rows.append(evaluate("exact-clock-refit", result["exact_clock_refit"]))
    folds = [
        evaluate("fold-" + str(row["excluded_norad_mod8"]), row)
        for row in result["leave_satellite_fold_out"]
    ]
    height_rows = [
        evaluate(row["selection"] + "-height-clock-" + str(row["clock_fitted"]), row)
        for row in height["models"]
    ]
    write_json(
        a.output / "evaluation.json",
        dict(
            inference_digests=sources,
            reference_digest=sha(a.reference),
            reference=reference,
            models=rows,
            satellite_fold_checks=folds,
            height_checks=height_rows,
            goal_achieved=False,
        ),
    )
    for name in ["inference.json", "inputs.json", "exact-inputs.json", "states.npz"]:
        shutil.copy2(a.polish / name, a.output / name)
    shutil.copy2(a.height, a.output / "height-inference.json")
    for label, directory in [("coarse", a.coarse), ("fine", a.fine)]:
        destination = a.output / label
        destination.mkdir()
        for name in [
            "result.json",
            "history.json",
            "configuration.json",
            "grid.npz",
            "accumulated.npz",
        ]:
            shutil.copy2(directory / name, destination / name)
    grid = np.load(a.coarse / "grid.npz")
    score = np.load(a.coarse / "accumulated.npz")["train"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    colors = axes[0].scatter(
        grid["east_km"],
        grid["north_km"],
        c=np.clip(score.max() - score, 0, 5000),
        cmap="viridis_r",
        s=2,
        rasterized=True,
    )
    best = int(np.argmax(score))
    axes[0].plot(grid["east_km"][best], grid["north_km"][best], "r+", markersize=12)
    axes[0].set(
        xlabel="East of Denver in declared map (km)",
        ylabel="North of Denver (km)",
        title="Full 9,000 × 9,000 mile prior · 84,100 cells",
        aspect="equal",
    )
    fig.colorbar(colors, ax=axes[0], label="Training composite-score loss (clipped at 5,000)")
    for row in rows[:4]:
        axes[1].plot(
            row["east_km"], row["north_km"], "o", label=f"{row['label']}: {row['error_m']:.0f} m"
        )
    axes[1].scatter(
        [r["east_km"] for r in folds],
        [r["north_km"] for r in folds],
        marker="x",
        c="gray",
        label="Leave satellite group out",
    )
    axes[1].plot(0, 0, "k*", markersize=12, label="Antenna reference: evaluation only")
    axes[1].add_patch(plt.Circle((0, 0), 1, fill=False, linestyle="--", color="gray", label="1 km"))
    axes[1].set(
        xlabel="Approximate east displacement from antenna (km)",
        ylabel="Approximate north displacement (km)",
        title="Local fit: 1,067.7 m near miss",
        aspect="equal",
    )
    axes[1].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2)
    axes[1].grid(alpha=0.2)
    fig.savefig(a.output / "wide-to-local.png", dpi=180)
    plt.close(fig)
    write_json(
        a.output / "sha256.json",
        {
            str(path.relative_to(a.output)): sha(path)
            for path in sorted(a.output.rglob("*"))
            if path.is_file()
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
