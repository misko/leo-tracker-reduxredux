"""Plot published completed-cohort comparisons; no fitting or outcome selection."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
# Rounded published means: iterations65 and82 RESULTS/README tables.
labels = ["DS16 (63)", "DS17 (51)", "DS18 (34)", "All (148)"]
series = {
    "Saved hard60 baseline": [5.964450, 4.477043, 4.422188, 5.097594],
    "Expanded regions, slope sigma 0.25": [1.017307, 0.864203, 2.739331, 1.360148],
    "Expanded regions, slope sigma 0.5": [0.979007, 0.819111, 2.691656, 1.317354],
}
fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
x = np.arange(len(labels))
for i, (label, values) in enumerate(series.items()):
    bars = ax.bar(x + (i - 1) * 0.25, values, 0.25, label=label)
    ax.bar_label(bars, fmt="%.2f", fontsize=9)
ax.axhline(1, color="black", linestyle="--", linewidth=1, label="1 km goal")
ax.set_xticks(x, labels)
ax.set_ylabel("Mean position error (km), fitted-c")
ax.set_ylim(0, 7.8)
ax.set_title("Completed full-membership development comparisons\n"
             "No isolated diagnostic rescue inserted; production unchanged")
ax.legend(fontsize=9, ncol=2)
fig.savefig(HERE / "comparison.png", dpi=160)
