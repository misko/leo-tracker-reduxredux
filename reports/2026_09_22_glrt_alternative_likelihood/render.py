#!/usr/bin/env python3
"""Render matched frozen-position GLRT alternative likelihood results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    documents = [
        json.loads((HERE / "single-result.json").read_text()),
        json.loads((HERE / "set-result.json").read_text()),
    ]
    labels = ["single scan\n39 tracks", "five scans\n165 tracks"]
    aggregate = np.asarray([row["alternative_minus_selected"] for row in documents])
    common = np.asarray(
        [row["alternative_common_target_minus_selected"] for row in documents]
    )
    per_track = [
        np.asarray(
            [
                track["alternative_heldout_logbf"] - track["selected_heldout_logbf"]
                for track in document["tracks"]
            ]
        )
        for document in documents
    ]
    common_per_track = [
        np.asarray(
            [
                track["alternative_common_target_heldout_logbf"]
                - track["selected_heldout_logbf"]
                for track in document["tracks"]
            ]
        )
        for document in documents
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), constrained_layout=True)
    x = np.arange(2)
    width = 0.25
    axes[0].bar(x - width, aggregate[:, 0], width, label="training, alternative kernel")
    axes[0].bar(x, aggregate[:, 1], width, label="held-out, alternative kernel")
    axes[0].bar(
        x + width,
        common[:, 1],
        width,
        label="held-out, common selected-CFO target",
    )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("uniform alternatives − selected Δ log score")
    axes[0].set_title("Aggregate matched comparison")
    axes[0].legend()
    bins = np.linspace(
        min(values.min() for values in per_track + common_per_track),
        max(values.max() for values in per_track + common_per_track),
        35,
    )
    for label, values in zip(labels, per_track, strict=True):
        axes[1].hist(
            values,
            bins=bins,
            histtype="step",
            linewidth=1.2,
            linestyle=":",
            label=f"{label}, alternative kernel",
        )
    for label, values in zip(labels, common_per_track, strict=True):
        axes[1].hist(
            values,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            label=f"{label}, common target",
        )
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].set_xlabel("per-track held-out Δ log score")
    axes[1].set_ylabel("tracks")
    axes[1].set_title("Track contributions")
    axes[1].legend()
    fig.suptitle("Frozen-position uniform passing-GLRT alternatives diagnostic")
    fig.savefig(HERE / "glrt-alternative-likelihood.png", dpi=180)


if __name__ == "__main__":
    main()
