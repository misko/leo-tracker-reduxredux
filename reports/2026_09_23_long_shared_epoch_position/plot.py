#!/usr/bin/env python3
import json
from pathlib import Path

from matplotlib.figure import Figure

here = Path(__file__).resolve().parent
data = json.loads((here / "results/results.json").read_text())
figure = Figure(figsize=(10, 4), layout="constrained")
error_axis, rms_axis = figure.subplots(1, 2)
for view in data["views"]:
    for prior, marker in (("sacramento", "o"), ("reno", "s")):
        arms = [row for row in view["arms"] if row["prior"] == prior]
        label = f"{view['scan_count']} scans, {prior}"
        error_axis.plot(
            [row["scale_s"] for row in arms],
            [row["reference_error_km"] for row in arms], marker=marker, label=label,
        )
        rms_axis.plot(
            [row["scale_s"] for row in arms],
            [row["training_capped800_rmse_hz"] for row in arms], marker=marker,
            label=label + " train",
        )
        rms_axis.plot(
            [row["scale_s"] for row in arms],
            [row["reserved_capped800_rmse_hz"] for row in arms], marker=marker,
            linestyle="--", label=label + " reserved",
        )
error_axis.set(xlabel="Regularization scale (s)", ylabel="Post-seal error (km)")
rms_axis.set(xlabel="Regularization scale (s)", ylabel="Capped duration RMS (Hz)")
for axis in (error_axis, rms_axis):
    axis.set_xscale("log")
    axis.set_xticks([0.2, 1.0, 5.0], labels=["0.2", "1", "5"])
    axis.minorticks_off()
    axis.grid(alpha=0.25)
    axis.legend(fontsize=7)
figure.savefig(here / "shared_epoch_results.png", dpi=160)
