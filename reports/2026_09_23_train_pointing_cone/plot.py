#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
data = json.loads((HERE / "results.json").read_text())
rows = [row for row in data["results"]]
roles = ("coarse50_rank1", "coarse50_rank2", "final_selected")
labels = ("coarse rank 1", "coarse rank 2", "final selected")

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True, constrained_layout=True)
for axis, group in zip(axes, ("first_train", "second_train"), strict=True):
    selected = {row["location"]["role"]: row for row in rows if row["group"] == group}
    x = np.arange(len(roles))
    for tilt, marker in ((0, "o"), (15, "s"), (30, "^")):
        values = []
        endpoint = []
        for role in roles:
            scenario = next(
                item
                for item in selected[role]["scenarios"]
                if item["maximum_tilt_deg"] == tilt and item["receiver_to_axis"] == [0, 1]
            )
            values.append(scenario["quantiles"]["0.95"]["midpoint_cone_deg"])
            endpoint.append(scenario["quantiles"]["0.95"]["endpoint_cone_deg"])
        axis.plot(x, values, marker=marker, label=f"midpoint, tilt ≤ {tilt}°")
        if tilt == 15:
            axis.plot(x, endpoint, marker=marker, linestyle="--", label="endpoints, tilt ≤ 15°")
    axis.set_xticks(x, labels, rotation=18, ha="right")
    axis.set_title(group.replace("_", " "))
    axis.grid(alpha=0.25)
axes[0].set_ylabel("weighted 95% required cone (degrees)")
axes[1].legend(fontsize=8)
fig.suptitle("Frozen TRAIN pointing-cone support requirements (mapping RX0→axis0)")
fig.savefig(HERE / "cone_q95.png", dpi=180)
plt.close(fig)

fig, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
x = np.arange(2)
width = 0.22
for offset, fraction in zip((-width, 0, width), ("0.5", "0.8", "0.95"), strict=True):
    values = []
    for group in ("first_train", "second_train"):
        row = next(
            item
            for item in rows
            if item["group"] == group and item["location"]["role"] == "final_selected"
        )
        scenario = next(
            item
            for item in row["scenarios"]
            if item["maximum_tilt_deg"] == 15 and item["receiver_to_axis"] == [0, 1]
        )
        values.append(scenario["quantiles"][fraction]["midpoint_cone_deg"])
    axis.bar(x + offset, values, width, label=f"weighted {float(fraction) * 100:.0f}%")
axis.set_xticks(x, ("first TRAIN", "second TRAIN"))
axis.set_ylabel("required midpoint cone (degrees)")
axis.set_title("Final selected locations, common tilt ≤ 15°")
axis.grid(axis="y", alpha=0.25)
axis.legend()
fig.savefig(HERE / "final_quantiles.png", dpi=180)
plt.close(fig)
