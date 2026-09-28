#!/usr/bin/env python3
"""Plot held-record within-geometry contrasts and family arm gains."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-within-geometry-cv/v1" or result.get("status") != "complete":
        raise ValueError("results are not complete within-geometry evidence")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")

    primary = result["primary"]
    records = sorted(primary["within_T-minus_D"]["records"])
    x = np.arange(len(records))
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.3), constrained_layout=True)
    for offset, (key, label) in zip(
        (-0.12, 0.12),
        (("within_T-minus_D", "within T − D"), ("within_T-minus_S", "within T − S")),
        strict=True,
    ):
        axes[0].scatter(
            x + offset,
            [primary[key]["records"][sid] for sid in records],
            s=42,
            label=label,
        )
    axes[0].axhline(0, color="#444444", linewidth=0.9)
    axes[0].set_xticks(
        x, [sid.removeprefix("scan-fw-")[:7] for sid in records], rotation=35, ha="right"
    )
    axes[0].set_ylabel("paired contrast (nats / held window)")
    axes[0].set_title("Primary within-geometry contrasts")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.2)

    arms = ("E", "S", "T")
    width = 0.35
    positions = np.arange(len(arms))
    absolute = [result["aggregates"][f"absolute_{arm}-absolute_D"]["mean"] for arm in arms]
    within = [result["aggregates"][f"within_{arm}-within_D"]["mean"] for arm in arms]
    axes[1].bar(positions - width / 2, absolute, width, label="absolute")
    axes[1].bar(positions + width / 2, within, width, label="within centered")
    axes[1].axhline(0, color="#444444", linewidth=0.9)
    axes[1].set_xticks(positions, arms)
    axes[1].set_ylabel("equal-record gain over D (nats / held window)")
    axes[1].set_title("Raw versus within-centered arm gains")
    axes[1].legend(frameon=False)
    axes[1].grid(axis="y", alpha=0.2)
    figure.suptitle("Calibration recording-held-out geometry comparison")
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
