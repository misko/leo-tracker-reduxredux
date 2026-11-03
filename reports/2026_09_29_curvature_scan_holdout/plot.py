import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "summary.json").read_text())
data["rows"] = [r for r in data["rows"] if r["qualified"]]
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
colors = dict(DS7="#246d9b", DS8="#ca7135", DS9="#44884c")
for ds, color in colors.items():
    rows = [r for r in data["rows"] if r["dataset"] == ds]
    axes[0].scatter(
        [r["baseline_error_m"] for r in rows],
        [r["curvature_error_m"] for r in rows],
        color=color,
        label=ds,
    )
    axes[1].scatter(
        [r["baseline_error_m"] - r["curvature_error_m"] for r in rows],
        [r["target_gain"] for r in rows],
        color=color,
        label=ds,
    )
limit = max(max(r["baseline_error_m"], r["curvature_error_m"]) for r in data["rows"]) * 1.05
axes[0].plot([0, limit], [0, limit], color="#888888", linestyle="--")
axes[0].set(
    xlabel="Baseline geographic error (m)",
    ylabel="Curvature geographic error (m)",
    title="Below diagonal: geographic improvement",
    xlim=(0, limit),
    ylim=(0, limit),
)
axes[0].legend()
axes[1].axhline(0, color="#888888", linewidth=0.8)
axes[1].axvline(0, color="#888888", linewidth=0.8)
axes[1].set(
    xlabel="Geographic error reduction (m)",
    ylabel="Whole-target log-score gain",
    title="Upper right: both measures improve",
)
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle(f"Four source scans → four disjoint target scans; {len(data['rows'])} qualified pairs")
fig.tight_layout()
fig.savefig(HERE / "holdout.png", dpi=170)
