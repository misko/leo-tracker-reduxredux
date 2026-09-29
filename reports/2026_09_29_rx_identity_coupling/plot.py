"""Show weak and full coupling controls on separate readable scales."""

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, read  # noqa: E402

rows = read(HERE / "summary.json")["rows"]
fig, axes = plt.subplots(3, 1, figsize=(12, 9), layout="constrained", sharex=True)
x = np.arange(len(rows))
for j, rho in enumerate(("0.5", "1")):
    axes[0].bar(
        x + (j - 0.5) * 0.35, [r["primary"][rho] for r in rows], width=0.35, label="coupling " + rho
    )
    axes[j + 1].bar(x, [r["matched"][rho] - r["shuffled"][rho] for r in rows], color=f"C{j}")
    axes[j + 1].set_ylabel(f"Coupling {rho}\nselected − shuffled Δnats")
axes[0].set_ylabel("Held Δnats vs independent")
axes[0].legend()
for ax in axes:
    ax.axhline(0, color="black", linewidth=0.7)
axes[-1].set_xticks(x, [r["unit_id"].replace("_", " ") for r in rows], rotation=65, ha="right")
fig.suptitle("Identity coupling: primary scores and matched controls at unchanged locations")
for suffix in ("png", "svg"):
    fig.savefig(HERE / ("comparison." + suffix), dpi=160)
plt.close(fig)
