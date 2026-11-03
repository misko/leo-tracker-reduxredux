"""Display per-target prediction differences without treating scans as trials."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, read  # noqa: E402

summary = read(HERE / "summary.json")
fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
for ax, dataset in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    rows = [r for r in summary["rows"] if r["dataset"] == dataset]
    assert len(rows) == 5 and all(r["qualified"] for r in rows)
    for offset, key, label, color in (
        (-0.18, "n24_minus_center", "Versus configured center", "#246d9b"),
        (0.18, "n24_minus_n8_mixture", "Versus equal N8 mixture", "#ca7135"),
    ):
        ax.bar(
            [i + offset for i in range(5)],
            [r[key] for r in rows],
            width=0.35,
            label=label,
            color=color,
        )
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set(
        title=dataset,
        xlabel="Timestamp quantile of outside scans",
        xticks=range(5),
        xticklabels=["First", "25%", "50%", "75%", "Last"],
    )
    ax.spines[["top", "right"]].set_visible(False)
axes[0].set_ylabel("Predictive log-score difference\nPositive favors fixed N24 location")
axes[0].legend(fontsize=8)
fig.suptitle("Fixed-location prediction on scans outside the 24-scan fitting pools")
fig.tight_layout()
fig.savefig(HERE / "prediction.png", dpi=170)
