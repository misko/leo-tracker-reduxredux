#!/usr/bin/env python3
import json
from pathlib import Path

from matplotlib.figure import Figure

here = Path(__file__).resolve().parent
data = json.loads((here / "results/results.json").read_text())
figure = Figure(figsize=(10, 4), layout="constrained")
error_axis, rms_axis = figure.subplots(1, 2)
for prior, marker in (("sacramento", "o"), ("reno", "s")):
    arms = [row for row in data["arms"] if row["prior"] == prior]
    scales = [row["scale_s"] for row in arms]
    error_axis.plot(scales, [row["reference_error_km"] for row in arms], marker=marker, label=prior)
    rms_axis.plot(
        scales,
        [row["training_capped800_rmse_hz"] for row in arms],
        marker=marker,
        label=prior + " train",
    )
    rms_axis.plot(
        scales,
        [row["reserved_capped800_rmse_hz"] for row in arms],
        marker=marker,
        linestyle="--",
        label=prior + " reserved",
    )
error_axis.set(xlabel="Regularization scale (s)", ylabel="Post-seal error (km)")
rms_axis.set(xlabel="Regularization scale (s)", ylabel="Capped duration RMS (Hz)")
for axis in (error_axis, rms_axis):
    axis.set_xscale("log")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
figure.savefig(here / "satellite_epoch_results.png", dpi=160)
