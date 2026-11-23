"""Plot measured regional probe timings alongside the common geometry preparation."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    fig, axes = plt.subplots(1, 3, figsize=(10, 3), layout="constrained")
    for ax, case, title in zip(axes, ("physical", "south-far", "dense"),
                               ("DS30-0016", "Southern omission", "DS30-0008"), strict=True):
        row = json.loads((here / "measurements" / f"regional-track-{case}.json").read_bytes())
        base = row["shared_geometry_cpu_s"]
        arms = ("original", "native")
        ax.barh([1, 0], [base, base], color="#c8d1d8", label="Orbit geometry")
        scored = [row["mean_cpu_s"][a] for a in arms]
        ax.barh([1, 0], scored, left=base, color="#277769", label="Probe scoring")
        for y, cpu in zip([1, 0], scored, strict=True):
            ax.text(base + cpu, y, f"  {base + cpu:.2f}", va="center", fontsize=9)
        ax.set_yticks([1, 0], ["Original", "Native"])
        ax.set_xlim(0, (base + max(scored)) * 1.3)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel("CPU seconds")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.set_ylim(-.65, 1.7)
    axes[1].legend(loc="upper center", bbox_to_anchor=(.5, -.32), frameon=False, ncol=2)
    fig.suptitle("Preparing the orbits and scoring the regional probes", fontsize=14, fontweight="bold")
    fig.savefig(here / "development/regional-track-scores.png", dpi=160)
    plt.close(fig)
