"""Plot frozen causal-reference contrasts with recording-level support."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "results.json").read_text())
    values = result["aggregate_equal_record"]
    panels = [
        ("Causal frequency reference gain", [
            ("causal_reference-uniform_reference", "Causal − uniform reference")]),
        ("Satellite models above causal reference", [
            (f"causal_{arm}-causal_reference", arm) for arm in ("D", "S", "T")]),
        ("Geometry and frequency controls", [
            ("causal_T-D", "T − D"), ("causal_T-S", "T − S"),
            ("causal_T-T_swap", "T − swapped"),
            ("causal_T-T_reverse", "T − reversed"),
            ("causal_T-T_shift", "T − shifted")]),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.4), gridspec_kw={"width_ratios": [1, 1.3, 1.8]})
    for ax, (title, comparisons) in zip(axes, panels, strict=True):
        for role, offset, color, label in (
            ("reception", -0.13, "#2563eb", "Reception"),
            ("held_frequency", 0.13, "#d97706", "Later"),
        ):
            for i, (comparison, _) in enumerate(comparisons):
                row = values[f"{role}:{comparison}"]
                points = list(row["records"].values())
                ax.scatter(i + offset + np.linspace(-0.055, 0.055, len(points)), points,
                           s=23, alpha=0.45, color=color)
                ax.scatter(i + offset, row["mean"], marker="D", s=60, color=color,
                           edgecolor="white", linewidth=0.5,
                           label=label if i == 0 else None, zorder=5)
        ax.axhline(0, color="#334155", linewidth=0.8)
        ax.set_xticks(range(len(comparisons)), [label for _, label in comparisons],
                      rotation=30, ha="right")
        ax.set_title(title)
        ax.set_ylabel("nats per paired window")
        ax.grid(axis="y", alpha=0.2)
    axes[0].legend(frameon=False)
    fig.suptitle("Frozen geometry against a causal frequency predictor", fontsize=16)
    fig.text(0.5, 0.015,
             "Dots: six recordings; diamonds: equal-record means. Frozen coefficients, no refit. "
             "Predictive evidence does not establish satellite identity.",
             ha="center", fontsize=10)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"causal-geometry.{suffix}", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, (title, comparisons) in zip(axes, panels[1:], strict=True):
        for i, (comparison, _) in enumerate(comparisons):
            row = values[f"held_frequency:{comparison}"]
            points = list(row["records"].values())
            ax.scatter(i + np.linspace(-0.08, 0.08, len(points)), points,
                       s=35, alpha=0.5, color="#d97706")
            ax.scatter(i, row["mean"], marker="D", s=65, color="#b45309", zorder=5)
        ax.axhline(0, color="#334155", linewidth=0.8)
        ax.set_xticks(range(len(comparisons)), [label for _, label in comparisons],
                      rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel("nats per paired window")
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Later windows: small incremental geometry effects", fontsize=15)
    fig.text(0.5, 0.02, "Six recording-level dots; diamonds show equal-record means. "
             "Positive contrasts between models do not imply reliable association.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"causal-geometry-later.{suffix}", dpi=160)


if __name__ == "__main__":
    main()
