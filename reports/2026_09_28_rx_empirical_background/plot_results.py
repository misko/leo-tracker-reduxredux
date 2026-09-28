#!/usr/bin/env python3
"""Plot per-record empirical-background improvement over Poisson."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MODES = ("poisson", "joint", "joint_frequency", "rate_joint", "rate_joint_frequency")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if (
        result.get("schema") != "rx-empirical-background-selection/v1"
        or result.get("status") != "complete"
    ):
        raise ValueError("results are not complete empirical-background evidence")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")
    sessions = result["calibration_recordings"]
    x = np.arange(len(sessions))
    figure, axis = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    offsets = np.linspace(-0.27, 0.27, len(MODES))
    for offset, mode in zip(offsets, MODES, strict=True):
        values = result["versus_poisson"][mode]["by_record"]
        axis.scatter(x + offset, [values[sid] for sid in sessions], label=mode, s=35)
    axis.axhline(0, color="#444444", linewidth=0.9)
    axis.set_xticks(
        x, [sid.removeprefix("scan-fw-")[:7] for sid in sessions], rotation=35, ha="right"
    )
    axis.set_ylabel("improvement over Poisson (nats / window)")
    axis.set_title("Recording-held-out empirical background comparison")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, ncol=2)
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
