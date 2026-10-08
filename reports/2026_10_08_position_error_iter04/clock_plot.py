"""Visualize the smooth nuisance correction separately from position accuracy."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

root = Path(__file__).resolve().parent
document = json.loads((root / "probes/S24.json").read_text())
nodes = np.asarray(document["calibration"]["nodes_s"])
fig, axes = plt.subplots(2, 1, figsize=(10, 7), layout="constrained")
for row in document["candidates"]:
    if row["arm"] != "fitted-c" or row["variant"] == "joint-tight":
        continue
    knots = np.asarray(row["knots_hz"])
    for rx, ax in enumerate(axes):
        ax.plot(nodes, knots[rx], "o-", label=f"{row['variant']}: {row['error_km']:.2f} km")
        ax.set(xlabel="Seconds into scan", ylabel="Smooth correction (Hz)", title=f"RX{rx}")
        ax.grid(alpha=.2)
        ax.legend()
fig.suptitle("S24: refitting the clock correction moves the displaced optimum\n"
             "Gauge-fixed smooth component only; affine clock terms are separate")
fig.savefig(root / "S24-clock-correction.png", dpi=160)
plt.close(fig)
