import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "summary.json").read_text())["rows"]
assert len(rows) == 3 and all(r["qualified"] for r in rows)
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for offset, key, label, color in (
    (-0.18, "baseline_error_m", "N24 baseline", "#ca7135"),
    (0.18, "curvature_error_m", "N24 curvature", "#246d9b"),
):
    axes[0].bar(
        [i + offset for i in range(3)], [r[key] for r in rows], width=0.35, label=label, color=color
    )
axes[0].set(
    ylabel="Error to inherited reference (m)",
    title="Geographic change is mixed",
    xticks=range(3),
    xticklabels=[r["dataset"] for r in rows],
)
axes[0].legend()
for offset, key, label, color in (
    (-0.18, "curvature_minus_baseline", "Versus N24 baseline", "#246d9b"),
    (0.18, "curvature_minus_n8_mixture", "Versus N8 mixture", "#ca7135"),
):
    axes[1].bar(
        [i + offset for i in range(3)], [r[key] for r in rows], width=0.35, label=label, color=color
    )
axes[1].axhline(0, color="#888888", linewidth=0.8)
axes[1].set(
    ylabel="Outside-scan predictive log-score difference",
    title="Prediction does not consistently improve",
    xticks=range(3),
    xticklabels=[r["dataset"] for r in rows],
)
axes[1].legend(fontsize=8)
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Fixed curvature prior: 24 source scans and five excluded targets per dataset")
fig.tight_layout()
fig.savefig(HERE / "comparison.png", dpi=170)
