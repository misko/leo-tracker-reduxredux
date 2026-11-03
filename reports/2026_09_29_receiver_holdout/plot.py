import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "summary.json").read_text())["rows"]
fig, ax = plt.subplots(figsize=(8, 5))
for sigma, color in ((0.5, "#0072B2"), (2.0, "#D55E00")):
    selected = [r for r in rows if r["sigma"] == sigma and r["qualified"]]
    ax.scatter(
        [r["source_held_gain"] for r in selected],
        [r["target_gain"] for r in selected],
        color=color,
        label=f"Slope SD {sigma:g} Hz/s",
        alpha=0.85,
    )
ax.axhline(0, color="gray", linestyle="--")
ax.axvline(0, color="gray", linestyle="--")
ax.set(
    xlabel="Source receiver interleaved held-score gain",
    ylabel="Opposite receiver complete-track score gain",
    title="Does improved residual prediction transfer to the other receiver?",
)
ax.legend()
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(HERE / "transfer.png", dpi=160)
