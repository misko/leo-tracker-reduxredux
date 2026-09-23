#!/usr/bin/env python3
"""Plot the sealed Astropy Doppler-oracle result."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def run(source: Path, output: Path):
    result = json.loads(source.read_text())
    sessions = result["session_metrics"]
    labels = [row["session_id"].removeprefix("scan-hop-")[:5] for row in sessions]
    position = [row["position_norm_difference_m"]["rms"] for row in sessions]
    doppler = [row["centered_doppler_difference_hz"]["rms"] for row in sessions]
    track_rms = np.asarray(
        [row["centered_doppler_rms_difference_hz"] for row in result["tracks"]]
    )

    figure, axes = plt.subplots(1, 3, figsize=(12.4, 3.7), constrained_layout=True)
    x = np.arange(len(sessions))
    axes[0].bar(x, position, color="#4477aa")
    axes[0].set_xticks(x, labels, rotation=35, ha="right")
    axes[0].set_ylabel("RMS position difference (m)")
    axes[0].set_title("Repository vs Astropy ITRS")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(x, doppler, color="#228833")
    axes[1].set_xticks(x, labels, rotation=35, ha="right")
    axes[1].set_ylabel("CFO-centered Doppler RMS (Hz)")
    axes[1].set_title("Per TRAIN session")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].hist(track_rms, bins=24, color="#cc6677", edgecolor="white")
    aggregate = result["aggregate_metrics"]["centered_doppler_difference_hz"]["rms"]
    axes[2].axvline(aggregate, color="black", linestyle="--", label=f"all rows {aggregate:.3f} Hz")
    axes[2].set_xlabel("Per-track centered Doppler RMS (Hz)")
    axes[2].set_ylabel("Tracks")
    axes[2].set_title("476 fixed baseline identities")
    axes[2].legend(frameon=False)
    axes[2].grid(axis="y", alpha=0.25)

    figure.suptitle("Direct-SGP4 TEME frame oracle · arbitrary receiver 38°, −122°")
    figure.savefig(output, dpi=170)
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.source, arguments.output)
