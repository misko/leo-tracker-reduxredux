import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "summary.json").read_text())["rows"]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for ds, color in ((7, "#0072B2"), (8, "#D55E00"), (9, "#009E73")):
    s = [r for r in rows if r["qualified"] and r["unit"].startswith(f"DS{ds}_")]
    axes[0].scatter(
        [r["source_held_gain"] for r in s],
        [r["target_gain"] for r in s],
        color=color,
        label=f"DS{ds}",
    )
    axes[1].scatter(
        [r["baseline_error_m"] for r in s], [r["error_m"] for r in s], color=color, label=f"DS{ds}"
    )
axes[0].axhline(0, color="gray", linestyle="--")
axes[0].set(
    xlabel="Source interleaved held-score gain",
    ylabel="Whole-scan marginal-score gain",
    title="Above zero = better scan transfer",
)
limit = max(max(r["error_m"], r["baseline_error_m"]) for r in rows if r["qualified"]) * 1.05
axes[1].plot([0, limit], [0, limit], "--", color="gray")
axes[1].set(
    xlabel="Baseline four-scan error (m)",
    ylabel="Shared-slope four-scan error (m)",
    title="Below diagonal = better geographic error",
)
for ax in axes:
    ax.grid(alpha=0.2)
    ax.legend()
fig.tight_layout()
fig.savefig(HERE / "transfer.png", dpi=160)
