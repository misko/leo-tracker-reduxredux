"""Plot profiled local position curvature; no accuracy bound is implied."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

here = Path(__file__).resolve().parent
data = json.loads((here / "results.json").read_text())
row = next(r for r in data["rows"] if r["prior"] == "sacramento"
           and r["tau_difference_step_s"] == 0.05)
fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained", sharey=True)
for axis, family in zip(axes, ("scan", "satellite"), strict=True):
    values = np.array([r["directional_fractions_retained"] for r in row["scenarios"]
                       if r["family"] == family]) * 100
    axis.plot(values[:, 0], "o-", label="Weakest normalized direction")
    axis.plot(values[:, 1], "s-", label="Strongest normalized direction")
    axis.set(xticks=range(4), xticklabels=["0.2 s", "1 s", "5 s", "None"],
             xlabel="Epoch regularization scale", title=f"Shared by {family}", ylim=(0, 100))
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
axes[0].set_ylabel("Local position curvature retained (%)")
fig.suptitle("First 6 TRAIN scans · fixed identities and active cap set\n"
             "Linearized objective diagnostic, not a position-accuracy bound")
fig.savefig(here / "profiled_curvature.png", dpi=160)
plt.close(fig)
