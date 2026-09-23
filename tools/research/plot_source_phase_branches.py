"""Plot independent held-odd evidence for training-even CFO seed choices."""

import gzip
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def run():
    root = Path("reports/figures/2026_09_23_source_phase_random")
    with gzip.open(root / "frames.json.gz", "rt") as source:
        evidence = json.load(source)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, result in zip(axes, evidence["results"], strict=True):
        branch = next(b for b in result["seed_alternatives"] if len(b["seed_cfo_hz"]) == 2)
        for index, rows in enumerate(branch["frames_by_branch"]):
            held = [r for r in rows if r["partition"] == "held"]
            for offset, key, color in [
                (-0.17, "exact_coherence", "#0072B2"),
                (0.17, "control_coherence", "#D55E00"),
            ]:
                group_means = [
                    np.mean([r["frame"]["odd"][key] for r in held if r["group_id"] == group])
                    for group in sorted({r["group_id"] for r in held})
                ]
                ax.bar(
                    index + offset,
                    np.mean(group_means),
                    width=0.3,
                    color=color,
                    label="Exact pilot" if key == "exact_coherence" else "Rolled control",
                )
                ax.scatter(np.full(3, index + offset), group_means, s=12, c="black", zorder=3)
        labels = [
            f"{seed / 1000:.1f} kHz"
            + ("\nSelected on train" if i == branch["selected_branch_index"] else "\nAlternative")
            for i, seed in enumerate(branch["seed_cfo_hz"])
        ]
        ax.set(
            xticks=[0, 1],
            xticklabels=labels,
            title=(
                f"{result['selection']['sample_rate_hz'] / 1e6:g} MS/s · RX{branch['receiver_id']}"
            ),
            ylim=(0, 0.18),
        )
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Held odd-symbol pilot coherence")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles[:2], labels[:2], loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.92))
    fig.suptitle("Training-selected CFO seeds reproduce on random held groups")
    fig.text(
        0.5,
        0.015,
        (
            "Dots: three held 20 ms group means · one source-seeded dwell per rate "
            "· no satellite identity claim"
        ),
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.85))
    fig.savefig(root / "held-odd-branch-comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
