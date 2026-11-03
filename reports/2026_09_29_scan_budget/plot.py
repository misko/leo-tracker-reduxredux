import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "summary.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
for ds, color in (("DS7", "#0072B2"), ("DS8", "#D55E00"), ("DS9", "#009E73")):
    rows = [r for r in data["aggregates"] if r["dataset"] == ds and r["complete"]]
    axes[0].plot(
        [r["count"] for r in rows], [r["median_error_m"] for r in rows], "o-", color=color, label=ds
    )
    axes[1].plot(
        [r["count"] for r in rows],
        [r["held_gain_vs_eight"] for r in rows],
        "o-",
        color=color,
        label=ds,
    )
axes[0].axhline(1000, color="gray", linestyle="--")
axes[0].axhline(
    data["prior_center_error_m"], color="gray", linestyle=":", label="Prior center only"
)
axes[0].set(ylabel="Median location error (m)", title="N24 is one estimate per dataset")
axes[1].axhline(0, color="gray", linestyle="--")
axes[1].set(
    ylabel="Coverage-normalized held log-score gain", title="Relative to the eight-scan sets"
)
for ax in axes:
    ax.set(xlabel="Scans per estimate", xticks=[8, 12, 16, 24])
    ax.grid(alpha=0.2)
    ax.legend()
fig.tight_layout()
fig.savefig(HERE / "budget.png", dpi=160)
