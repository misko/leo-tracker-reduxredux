#!/usr/bin/env python3
"""Plot frozen 1/6/16 long-TRAIN position-search results."""

import json
from pathlib import Path

from matplotlib.figure import Figure

here = Path(__file__).resolve().parent
single_path = here.parent / "2026_09_23_long_training_search/results/results.json"
single = json.loads(single_path.read_text())
multiple = json.loads((here / "results/results.json").read_text())
rows = {1: single["searches"]}
rows.update({view["scan_count"]: view["searches"] for view in multiple["views"]})
figure = Figure(figsize=(10, 4), layout="constrained")
error_axis, rms_axis = figure.subplots(1, 2)
for prior, marker in (("sacramento", "o"), ("reno", "s")):
    selected = [next(row for row in rows[count] if row["prior"] == prior) for count in (1, 6, 16)]
    values = [row["selected"] for row in selected]
    error_axis.plot(
        (1, 6, 16), [row["reference_error_km"] for row in values],
        marker=marker, label=prior,
    )
    rms_axis.plot(
        (1, 6, 16), [row["objective_rmse_hz"] for row in values],
        marker=marker, label=f"{prior} train",
    )
    rms_axis.plot(
        (1, 6, 16), [row["reserved_capped800_rmse_hz"] for row in values],
        marker=marker, linestyle="--", label=f"{prior} reserved",
    )
error_axis.set(
    xlabel="Nested TRAIN scans", ylabel="Post-seal reference error (km)",
    xticks=(1, 6, 16),
)
rms_axis.set(xlabel="Nested TRAIN scans", ylabel="Capped duration RMS (Hz)", xticks=(1, 6, 16))
error_axis.set_title("Position error (1 scan stops at 1.5625 km spacing)")
rms_axis.set_title("Training and complementary-row fit")
for axis in (error_axis, rms_axis):
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
figure.savefig(here / "nested_training_search.png", dpi=160)
