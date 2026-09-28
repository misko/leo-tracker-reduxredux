#!/usr/bin/env python3
"""Plot paired per-record presence-geometry contrasts."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def values(panel, name):
    if name in {"S-absent", "T-absent"}:
        arm = name[0]
        return {
            sid: row["versus_absent_per_window"]
            for sid, row in panel["evaluations"][arm]["records"].items()
        }
    return panel["contrasts"][name]["records"]


def paired_axis(axis, panel, names, title):
    records = sorted(values(panel, names[0]))
    x = np.arange(len(records))
    offsets = (-0.13, 0.13)
    colors = ("#2864a8", "#c04b36")
    markers = ("o", "s")
    for offset, color, marker, name in zip(offsets, colors, markers, names, strict=True):
        row = values(panel, name)
        axis.scatter(
            x + offset, [row[sid] for sid in records], label=name, color=color, marker=marker
        )
    axis.axhline(0, color="#555555", linewidth=0.8)
    axis.set_title(title)
    axis.set_xticks(
        x, [sid.removeprefix("scan-fw-")[:6] for sid in records], rotation=45, ha="right"
    )
    axis.set_ylabel("nats / held window")
    axis.legend(frameon=False, fontsize=8)
    axis.grid(axis="y", alpha=0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    if results.get("schema") != "rx-presence-geometry/v1" or results.get("status") != "complete":
        raise ValueError("results are not complete presence-geometry evidence")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")
    figure, axes = plt.subplots(2, 2, figsize=(12, 7.5), constrained_layout=True)
    for column, panel_name in enumerate(("pilot", "confirmation")):
        panel = results["panels"][panel_name]
        paired_axis(
            axes[0, column], panel, ("S-absent", "T-absent"), f"{panel_name}: versus absence"
        )
        paired_axis(
            axes[1, column],
            panel,
            ("S-S_shift", "T-reverse"),
            f"{panel_name}: nomination and geometry controls",
        )
    figure.suptitle("Presence-state geometry: paired held-record contrasts")
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
