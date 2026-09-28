"""Plot record-level causal-reference refit comparisons."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "results.json").read_text())
    aggregate = result["aggregate_equal_record"]
    panels = [
        ("Refitted models above causal reference", [
            (f"{arm}-causal_reference", arm) for arm in ("D", "E", "S", "T")]),
        ("Tilt comparisons and controls", [
            ("T-D", "T − D"), ("T-S", "T − S"), ("T-T_swap", "T − swapped"),
            ("T-T_reverse", "T − reversed"), ("T-T_shift", "T − shifted")]),
        ("Effect of refitting", [
            (f"refit-{arm}-minus-frozen-{arm}-full", arm) for arm in ("D", "S", "T")]),
    ]
    for role, title, color in (("reception", "Reception", "#2563eb"),
                               ("held_frequency", "Later windows", "#d97706")):
        fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
        for ax, (panel_title, comparisons) in zip(axes, panels, strict=True):
            for i, (key, _) in enumerate(comparisons):
                row = aggregate[f"{role}:{key}"]
                points = list(row["records"].values())
                ax.scatter(i + np.linspace(-0.07, 0.07, len(points)), points,
                           color=color, alpha=0.5, s=30)
                ax.scatter(i, row["mean"], color=color, marker="D", s=65,
                           edgecolor="white", linewidth=0.5, zorder=5)
            ax.axhline(0, color="#334155", linewidth=0.8)
            ax.set_xticks(range(len(comparisons)), [label for _, label in comparisons],
                          rotation=25, ha="right")
            ax.set_title(panel_title)
            ax.set_ylabel("nats per paired window")
            ax.grid(axis="y", alpha=0.2)
        fig.suptitle(f"{title}: geometry fitted against causal frequency continuity", fontsize=16)
        fig.text(0.5, 0.02,
                 "Dots: six omitted recordings. Diamonds: equal-record means. "
                 "Fits use only other-record reception data. "
                 "These are reused development recordings.",
                 ha="center", fontsize=10)
        fig.tight_layout(rect=(0, 0.07, 1, 0.94))
        for suffix in ("png", "svg"):
            fig.savefig(HERE / f"causal-refit-{role}.{suffix}", dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
