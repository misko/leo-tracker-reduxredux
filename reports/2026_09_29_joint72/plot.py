import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "summary.json").read_text())
assert not data["failures"]
rows = [r for r in data["aggregates"] if r["dataset"] != "all"]
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for offset, key, label, color in (
    (-0.18, "joint_minus_n24", "Joint 72-scan fit", "#246d9b"),
    (0.18, "mean_minus_n24", "Mean of three N24 fits", "#ca7135"),
):
    axes[0].bar(
        [i + offset for i in range(3)], [r[key] for r in rows], width=0.35, label=label, color=color
    )
axes[0].set(
    xticks=range(3),
    xticklabels=[r["dataset"] for r in rows],
    ylabel="Outside-target log-score gain vs per-dataset N24",
    title="Fixed locations on excluded scans",
)
axes[0].axhline(0, color="#888888", linewidth=0.8)
axes[0].legend(fontsize=8)
axes[1].bar(
    ["Joint 72", "Mean N24"],
    [data["joint_error_m"], data["mean_error_m"]],
    color=["#246d9b", "#ca7135"],
)
axes[1].set(ylabel="Error to inherited reference (m)", title="One shared estimate per method")
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Assumed stationary receiver across DS7–DS9; no target refitting")
fig.tight_layout()
fig.savefig(HERE / "comparison.png", dpi=170)
