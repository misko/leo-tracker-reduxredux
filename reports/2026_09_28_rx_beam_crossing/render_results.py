"""Render frozen results only; never fit or select a model."""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
result = json.loads((root / "corrected/result.json").read_text())
labels = {
    "geometry_free_iid": "No geometry · independent noise",
    "geometry_free_ou": "No geometry · correlated noise",
    "static_iid": "Static geometry · independent noise",
    "static_ou": "Static geometry · correlated noise",
    "temporal_ou": "Temporal geometry · correlated noise",
}
rows = []
for arm, label in labels.items():
    score = result["held_scores"][arm]
    rows.append([arm, label, score["rows"], -score["total_log_density"],
                 -score["total_log_density"] / score["rows"]])
with (root / "ablations.csv").open("w") as handle:
    writer = csv.writer(handle)
    writer.writerow(
        ["arm", "description", "held_rows", "negative_log_density_nats", "nats_per_row"]
    )
    writer.writerows(rows)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.4, 1]})
colors = ["#8c98a4", "#8c98a4", "#8c98a4", "#267e69", "#bb624b"]
axes[0].barh(list(labels.values()), [row[3] for row in rows], color=colors)
axes[0].invert_yaxis()
axes[0].set_xlabel("Held negative log density (nats; lower is better)")
axes[0].set_title("Static geometry + correlated noise performs best")
deltas = result["primary_exploratory_gate"]["per_recording_delta"]
axes[1].barh([sid.removeprefix("scan-fw-")[:8] for sid in deltas], list(deltas.values()),
             color=["#267e69" if v > 0 else "#bb624b" for v in deltas.values()])
axes[1].axvline(0, color="#555555", linewidth=0.8)
axes[1].invert_yaxis()
axes[1].set_xlabel("Temporal minus static log density (nats; higher is better)")
axes[1].set_title("Temporal addition improves 1 of 4 recordings")
fig.suptitle(
    "Conditional reused roof data · 2,099 evaluation pairs · unsupported 5 MHz level", fontsize=12
)
fig.tight_layout()
fig.savefig(root / "ablations.png", dpi=170, bbox_inches="tight")
fig.savefig(root / "ablations.svg", bbox_inches="tight")
plt.close(fig)
