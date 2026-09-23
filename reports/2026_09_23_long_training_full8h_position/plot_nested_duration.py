#!/usr/bin/env python3
"""Render the fixed nested TRAIN duration/error comparison through full 8h."""

import json
from pathlib import Path

from matplotlib.figure import Figure

HERE = Path(__file__).resolve().parent
SINGLE = HERE.parent / "2026_09_23_long_training_search/results/results.json"
MULTI = HERE.parent / "2026_09_23_long_training_search_multi/results/results.json"
FULL = HERE / "results/results.json"


def main() -> None:
    single = json.loads(SINGLE.read_text())
    multi = json.loads(MULTI.read_text())
    full = json.loads(FULL.read_text())
    rows = {1: single["searches"], 72: full["searches"]}
    rows.update({view["scan_count"]: view["searches"] for view in multi["views"]})
    counts = (1, 6, 16, 72)
    duration_minutes = tuple(count * 5 for count in counts)
    figure = Figure(figsize=(7, 4), layout="constrained")
    axis = figure.subplots()
    for prior, marker in (("sacramento", "o"), ("reno", "s")):
        selected = [next(row for row in rows[count] if row["prior"] == prior) for count in counts]
        axis.plot(
            duration_minutes,
            [row["selected"]["reference_error_km"] for row in selected],
            marker=marker,
            label=prior,
        )
    axis.set(
        xlabel="Nominal nested TRAIN capture duration (minutes)",
        ylabel="Post-seal reference error (km)",
        xticks=duration_minutes,
        title="Frozen tau-zero search: 1, 6, 16, and 72 TRAIN scans",
    )
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(HERE / "nested_duration_error.png", dpi=160)


if __name__ == "__main__":
    main()
