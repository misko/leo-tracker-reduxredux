"""Display audited opportunity coverage and paired detector outcomes."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
s = json.loads((HERE / "summary.json").read_text())
assert s["audit_passed"]
datasets = ["DS7", "DS8", "DS9"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
x = np.arange(3)
for rx, offset, color in ((0, -0.18, "#277da1"), (1, 0.18, "#f8961e")):
    values = []
    for ds in datasets:
        groups = [g for g in s["groups"] if g["dataset"] == ds and g["receiver"] == rx]
        values.append(
            100
            * sum(g["covered_seconds"] for g in groups)
            / sum(g["valid_seconds"] for g in groups)
        )
    axes[0].bar(x + offset, values, width=0.35, label=f"RX{rx}", color=color)
axes[0].set(
    xticks=x,
    xticklabels=datasets,
    ylim=(0, 100),
    ylabel="Analyzed / valid dwell time (%)",
    title="Probe coverage; gaps remain unknown",
)
axes[0].legend()
base = np.zeros(3)
for state, label, color in (
    (0, "Both empty", "#d9d9d9"),
    (1, "One RX with candidates", "#90be6d"),
    (2, "Both with candidates", "#277da1"),
):
    values = np.array(
        [
            100
            * s["datasets"][ds]["outcomes"].get(f"{state}_receivers_with_passing_candidates", 0)
            / sum(s["datasets"][ds]["outcomes"].values())
            for ds in datasets
        ]
    )
    axes[1].bar(x, values, bottom=base, label=label, color=color)
    base += values
axes[1].set(
    xticks=x,
    xticklabels=datasets,
    ylim=(0, 100),
    ylabel="Paired probe windows (%)",
    title="Detector outcomes; identities unverified",
)
axes[1].legend(loc="lower center", fontsize=8)
fig.savefig(HERE / "opportunity-coverage.png", dpi=160)
plt.close(fig)
