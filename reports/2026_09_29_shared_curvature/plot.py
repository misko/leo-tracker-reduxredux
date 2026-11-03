import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "summary.json").read_text())
assert not data["failures"]
fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    rows = [r for r in data["rows"] if r["dataset"] == ds]
    for i, row in enumerate(rows):
        ax.plot(
            [i - 0.15, i + 0.15],
            [row["baseline_error_m"], row["curvature_error_m"]],
            color="#999999",
        )
        ax.scatter(
            i - 0.15, row["baseline_error_m"], color="#ca7135", label="Baseline" if i == 0 else None
        )
        ax.scatter(
            i + 0.15,
            row["curvature_error_m"],
            color="#246d9b",
            label="Curvature" if i == 0 else None,
        )
    ax.axhline(1000, linestyle="--", color="#888888", linewidth=0.8)
    ax.set(title=ds, xticks=range(3), xticklabels=["Early", "Middle", "Late"], ylim=(0, 4000))
    ax.spines[["top", "right"]].set_visible(False)
axes[0].set_ylabel("Error to inherited reference (m)")
axes[0].legend()
fig.suptitle("Fixed 0.1 Hz/s² shared-curvature prior: 6/9 improve, 2/9 remain sub-km")
fig.tight_layout()
fig.savefig(HERE / "geographic.png", dpi=170)
