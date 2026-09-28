#!/usr/bin/env python3
"""Plot paired reception-to-held frozen geometry contrasts."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def record_contrast(fold, role, left, right):
    evaluations = fold["families"]["within"]["evaluations"]
    return (
        evaluations[left]["roles"][role]["relative_log_score_per_window"]
        - evaluations[right]["roles"][role]["relative_log_score_per_window"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-geometry-temporal-transfer/v1":
        raise ValueError("unsupported temporal-transfer result")
    if result.get("status") != "complete":
        raise ValueError("temporal-transfer result is incomplete")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")

    folds = sorted(result["folds"], key=lambda fold: fold["held_session"])
    labels = [fold["held_session"].removeprefix("scan-fw-")[:7] for fold in folds]
    contrasts = (
        ("T", "D", "T − D"),
        ("T", "S", "T − S"),
        ("T", "T_swap", "T − swap"),
        ("T", "T_reverse", "T − reverse"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True, sharex=True)
    x = np.arange(len(folds))
    for axis, (left, right, label) in zip(axes.flat, contrasts, strict=True):
        reception = [record_contrast(fold, "reception", left, right) for fold in folds]
        held = [record_contrast(fold, "held_frequency", left, right) for fold in folds]
        axis.plot(x, reception, "o", label="reception", color="#2864a8")
        axis.plot(x, held, "s", label="held frequency", color="#b44c27")
        for index in range(len(folds)):
            axis.plot(
                [x[index], x[index]],
                [reception[index], held[index]],
                color="#aaaaaa",
                zorder=0,
            )
        axis.axhline(0, color="#444444", linewidth=0.9)
        axis.set_title(label)
        axis.set_xticks(x, labels, rotation=35, ha="right")
        axis.grid(axis="y", alpha=0.2)
    axes[0, 0].legend(frameon=False)
    for axis in axes[:, 0]:
        axis.set_ylabel("contrast (nats / window)")
    figure.suptitle("Within-geometry transfer across the calibration role boundary")
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
