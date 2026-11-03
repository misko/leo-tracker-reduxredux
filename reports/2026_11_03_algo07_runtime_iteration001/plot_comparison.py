"""Plot matched discovery timing; neither panel is end-to-end localization."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "matched-summary.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout="constrained")
for ax, metric, title in zip(
    axes, ["discovery_seconds", "wall_seconds"],
    ["Discovery in a running process", "Including interpreter startup"], strict=True
):
    for i, mode in enumerate(("legacy", "pending")):
        values = [r[metric] for r in data["rows"] if r["mode"] == mode]
        median = data["medians"][mode][metric]
        ax.bar(i, median, color=["#b25245", "#3a8194"][i], alpha=.7)
        ax.scatter([i-.08, i, i+.08], values, color="#222222", s=24, zorder=3)
        ax.text(i, max(values)+.6, f"{median:.2f} s", ha="center")
    ax.set(xticks=[0, 1], xticklabels=["Original", "Skip finished jobs"],
           ylabel="Seconds", title=title, ylim=(0, 28))
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Three fixed completed inputs · three runs each · identical eligibility")
fig.savefig(ROOT / "matched_discovery.png", dpi=170)
plt.close(fig)
