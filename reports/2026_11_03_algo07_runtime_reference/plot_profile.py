"""Render measured nested validation calls without adding cumulative timings."""

from pathlib import Path
import pstats

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
stats = pstats.Stats(str(ROOT / "discovery-baseline/profile.pstats"))
stages = ["ALGO06", "ALGO05", "ALGO04", "ALGO03", "ALGO02"]
names = [f"fast_graph_position_v{i}.py" for i in (5, 4, 3, 2)] + ["fast_graph_position.py"]
counts = []
for name in names:
    counts.append(sum(
        values[1] for (filename, _, function), values in stats.stats.items()
        if Path(filename).name == name and function == "terminal"
    ))
fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
bars = ax.bar(stages, counts, color="#426f9a")
ax.bar_label(bars)
ax.set(ylabel="Public terminal validation calls", ylim=(0, max(counts) * 1.2),
       title="ALGO07 discovery: only three already-completed inputs")
ax.spines[["top", "right"]].set_visible(False)
ax.text(0.02, 0.96, "No new job was eligible.\nNested validation repeats at each stage.",
        transform=ax.transAxes, va="top")
fig.savefig(ROOT / "validation_calls.png", dpi=170)
plt.close(fig)
