#!/usr/bin/env python3
"""Plot paired joint-geometry held-record contrasts."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

CONTRASTS = ("S-D", "S-E", "T-S", "T-T_reverse")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-joint-geometry/v1" or result.get("status") != "complete":
        raise ValueError("results are not complete joint-geometry evidence")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.3), constrained_layout=True, sharey=True)
    for axis, panel_name in zip(axes, ("pilot", "confirmation"), strict=True):
        panel = result["panels"][panel_name]
        records = sorted(panel["contrasts"][CONTRASTS[0]]["records"])
        x = np.arange(len(records))
        for offset, contrast in zip(np.linspace(-0.27, 0.27, 4), CONTRASTS, strict=True):
            values = panel["contrasts"][contrast]["records"]
            axis.scatter(x + offset, [values[sid] for sid in records], label=contrast, s=35)
        axis.axhline(0, color="#444444", linewidth=0.9)
        axis.set_title(panel_name)
        axis.set_xticks(
            x, [sid.removeprefix("scan-fw-")[:7] for sid in records], rotation=35, ha="right"
        )
        axis.grid(axis="y", alpha=0.2)
        axis.legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("contrast (nats / held window)")
    figure.suptitle("Joint empirical-reference geometry contrasts")
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
