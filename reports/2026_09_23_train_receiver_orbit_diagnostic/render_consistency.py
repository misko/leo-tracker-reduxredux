#!/usr/bin/env python3
"""Render prespecified consistency strata from the sealed diagnostic JSON."""

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "results/inference.json"
OUTPUT = HERE / "results/consistency.png"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(rows):
    labels, means, low, high = [], [], [], []
    for label, row in rows.items():
        effect = row["differential_slope_hz_s"]
        labels.append(label)
        means.append(effect["mean"])
        low.append(effect["mean"] - effect["ci95"][0])
        high.append(effect["ci95"][1] - effect["mean"])
    return labels, means, [low, high]


def main():
    result = json.loads(SOURCE.read_text())
    strata = result["consistency_strata"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis, title, rows in (
        (axes[0], "TRAIN block", strata["train_group"]),
        (axes[1], "RF lane", strata["lane"]),
    ):
        labels, means, errors = values(rows)
        axis.errorbar(means, range(len(labels)), xerr=errors, fmt="o", capsize=3)
        axis.axvline(0, color="black", linewidth=0.8)
        axis.set_yticks(range(len(labels)), labels)
        axis.set_xlabel("Mean RX0−RX1 residual slope (Hz/s), 95% group-bootstrap CI")
        axis.set_title(title)
        axis.grid(axis="x", alpha=0.25)
    figure.suptitle("Differential slope is inconsistent across frozen TRAIN strata")
    figure.tight_layout()
    figure.savefig(OUTPUT, dpi=180)
    plt.close(figure)
    OUTPUT.with_suffix(".sha256").write_text(digest(OUTPUT) + "\n")


if __name__ == "__main__":
    main()
