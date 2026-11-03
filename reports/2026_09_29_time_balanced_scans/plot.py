import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
prefix = "grid_" if len(sys.argv) > 1 and sys.argv[1] == "grid" else ""
rows = json.loads((HERE / f"{prefix}summary.json").read_text())["rows"]
fig, ax = plt.subplots(figsize=(9, 5))
for ds, color in (("DS7", "#0072B2"), ("DS8", "#D55E00"), ("DS9", "#009E73")):
    for arm, marker in (("contiguous", "o"), ("balanced", "^")):
        s = [r for r in rows if r["qualified"] and r["dataset"] == ds and r["arm"] == arm]
        ax.scatter(
            [r["start_span_hours"] for r in s],
            [r["error_m"] for r in s],
            color=color,
            marker=marker,
            label=f"{ds} {arm}",
            s=55,
            alpha=0.8,
        )
ax.axhline(1000, color="gray", linestyle="--", label="1 km")
ax.set(
    xlabel="Elapsed span between first and last scan starts (hours)",
    ylabel="Eight-scan location error (m)",
    title="Same scan count and overall corpus; different elapsed time",
)
ax.grid(alpha=0.2)
ax.legend(ncol=2)
fig.tight_layout()
fig.savefig(HERE / f"{prefix}comparison.png", dpi=160)
