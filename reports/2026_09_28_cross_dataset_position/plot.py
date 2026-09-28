"""Geographic budgets and excluded-dataset predictive differences."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
scores = json.loads((HERE / "scores.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
labels, values, colors, hatches, missing = [], [], [], [], []
for row in scores["original_panels"]:
    labels.append(row["dataset"] + "\n8 records")
    values.append(row["horizontal_error_m"] / 1000)
    colors.append("#87949b")
    hatches.append("")
for row in scores["rows"]:
    if row["state"] != "returned":
        missing.append(len(values))
        labels.append(
            "All three\n24 records"
            if row["unit_id"] == "all24"
            else row["unit_id"].replace("exclude_", "Exclude ") + "\n16 records"
        )
        values.append(0.0)
        colors.append("#bbbbbb")
        hatches.append("")
        continue
    labels.append(
        "All three\n24 records"
        if row["unit_id"] == "all24"
        else "Exclude " + row["excluded_dataset"] + "\n16 records"
    )
    values.append(row["horizontal_error_m"] / 1000)
    colors.append("#d3992e" if row["unit_id"] == "all24" else "#51758c")
    hatches.append("" if row["qualified"] else "//")
bars = axes[0].bar(range(len(values)), values, color=colors)
for bar, hatch in zip(bars, hatches, strict=True):
    bar.set_hatch(hatch)
for index in missing:
    axes[0].text(index, 0.08, "Unavailable", rotation=90, ha="center", va="bottom", fontsize=8)
axes[0].set_xticks(range(len(values)), labels, fontsize=8)
axes[0].axhline(1, color="black", linestyle=":", label="1 km")
axes[0].axhline(
    scores["coordinate_origin_error_m"] / 1000,
    color="#777777",
    linestyle="--",
    label="Inherited origin",
)
axes[0].set_ylabel("Horizontal error to unsurveyed site reference (km)")
axes[0].legend(fontsize=8)
labels, gains = [], []
for row in scores["rows"]:
    target = row.get("target_held", {})
    if target.get("state") == "returned":
        (item,) = target["datasets"]
        labels.append(item["dataset"])
        gains.append(item["held_delta_vs_original_panel"])
axes[1].bar(labels, gains, color="#51758c")
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set_ylabel(
    "Excluded dataset held score change (nats)\nvs its own eight-record position fit"
)
axes[1].set_xlabel("Fixed donor position; target training nuisance adaptation")
if not labels:
    axes[1].text(
        0.5, 0.5, "No returned target held scores", transform=axes[1].transAxes, ha="center"
    )
fig.suptitle("Shared geographic position across datasets; hatching marks unqualified source fits")
fig.savefig(HERE / "cross-dataset.png", dpi=160)
fig.savefig(HERE / "cross-dataset.svg")
