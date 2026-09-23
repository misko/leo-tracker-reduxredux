import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
data = json.loads((HERE / "results.json").read_text())
roles = ("coarse50_rank1", "coarse50_rank2", "final_selected")
labels = ("coarse 1", "coarse 2", "final")


def fold_mean(selected, fraction):
    return np.average(
        [item["quantiles"][fraction]["held_deg"] for item in selected],
        weights=[item["held_duration_s"] for item in selected],
    )


figure, axes = plt.subplots(3, 2, figsize=(10, 10), constrained_layout=True)
for column, group in enumerate(("first_train", "second_train")):
    for row_index, fraction in enumerate(("0.5", "0.8", "0.95")):
        axis = axes[row_index, column]
        for index, role in enumerate(roles):
            rows = [
                row
                for row in data["rows"]
                if row["group"] == group and row["role"] == role and row["mapping"] == [0, 1]
            ]

            actual = fold_mean([item for item in rows if item["kind"] == "actual"], fraction)
            controls = [
                fold_mean([item for item in rows if item["permutation"] == permutation], fraction)
                for permutation in range(data["control_count"])
            ]
            axis.boxplot(controls, positions=[index], widths=0.5, showfliers=True)
            axis.scatter(index, actual, marker="*", s=110, color="tab:red", zorder=3)
        axis.set_xticks(range(3), labels)
        axis.set_title(f"{group.replace('_', ' ')} · q{float(fraction) * 100:.0f}")
        axis.set_ylabel("held-fold cone (degrees)")
        axis.grid(axis="y", alpha=0.25)
figure.suptitle("Duration-weighted fold means: actual RX labels vs 20 stratified shuffles")
figure.savefig(HERE / "held_quantile_controls.png", dpi=180)
