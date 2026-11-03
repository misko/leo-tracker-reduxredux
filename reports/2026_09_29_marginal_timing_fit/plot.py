import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "summary.json").read_text())["rows"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
for ds, color in ((7, "#0072B2"), (8, "#D55E00"), (9, "#009E73")):
    selected = [r for r in rows if r["qualified"] and r["unit"].startswith(f"DS{ds}_")]
    axes[0].scatter(
        [r["movement_m"] for r in selected],
        [r["target_gain"] for r in selected],
        color=color,
        label=f"DS{ds}",
    )
    axes[1].scatter(
        [r["movement_m"] for r in selected],
        [r["baseline_error_m"] - r["error_m"] for r in selected],
        color=color,
        label=f"DS{ds}",
    )
axes[0].set(
    xlabel="Location movement (m)", ylabel="Whole-scan log-score gain", title="Prediction transfer"
)
axes[1].set(
    xlabel="Location movement (m)",
    ylabel="Geographic error reduction (m)",
    title="Geographic effect",
)
for ax in axes:
    ax.axhline(0, color="gray", linestyle="--")
    ax.grid(alpha=0.2)
    ax.legend()
fig.tight_layout()
fig.savefig(HERE / "comparison.png", dpi=160)
