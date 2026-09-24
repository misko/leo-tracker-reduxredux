#!/usr/bin/env python3
"""Plot the sealed raw cap-800 path and its post-seal evaluation."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main() -> None:
    inference = json.loads((HERE / "inference.json").read_text())
    evaluation = json.loads((HERE / "postseal-evaluation.json").read_text())
    origin = json.loads(
        (
            HERE.parent
            / "2026_09_24_ds1_iteration12_session_scale"
            / "refinement.json"
        ).read_text()
    )["winner"]
    reference = evaluation["reference_coordinate"]
    points = [level["winner"] for level in inference["levels"]]
    east = [0.0]
    north = [0.0]
    for point in points:
        north.append((point["latitude_deg"] - origin["latitude_deg"]) * 111.32)
        east.append(
            (point["longitude_deg"] - origin["longitude_deg"])
            * 111.32
            * math.cos(math.radians(origin["latitude_deg"]))
        )
    truth_north = (reference["latitude_deg"] - origin["latitude_deg"]) * 111.32
    truth_east = (
        (reference["longitude_deg"] - origin["longitude_deg"])
        * 111.32
        * math.cos(math.radians(origin["latitude_deg"]))
    )
    losses = [level["winner"]["balanced_exact_capped_loss"] for level in inference["levels"]]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    axes[0].plot(east, north, "o-", color="#e76f51", label="raw cap-800 path")
    axes[0].scatter([0], [0], marker="s", color="#666666", label="iteration-12 parent")
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
        title="Raw objective remains on the search edge",
        xlabel="East from iteration-12 winner (km)",
        ylabel="North from iteration-12 winner (km)",
    )
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(range(1, len(losses) + 1), losses, "o-", color="#2878b5")
    axes[1].set(
        title="RF objective keeps improving",
        xlabel="Edge-translation step",
        ylabel="Balanced exact cap-800 loss",
    )
    axes[1].grid(alpha=0.25)
    figure.savefig(HERE / "cap800-open-basin.png", dpi=180)


if __name__ == "__main__":
    main()
