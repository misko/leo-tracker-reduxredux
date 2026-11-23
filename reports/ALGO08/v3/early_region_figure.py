"""Plot the sealed coverage ablation and time to the missing-region decision."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent


def main():
    crossed = json.loads((HERE / "measurements/mixed-aperture-crossed.json").read_bytes())["cases"]
    early = json.loads((HERE / "measurements/early-region.json").read_bytes())["cases"]
    fig, axes = plt.subplots(1, 3, figsize=(11.6, 4.1), layout="constrained")
    colors = ("#324572", "#00816c")
    for ax, (case, title) in zip(axes[:2], (("DS30-0016", "DS30-0016 · physical"), ("south-containing", "Southern simulation")), strict=True):
        for prefix, offset, label, style in (("all", -.075, "All visit times", "-"),
                                            ("reduced", .075, "5 of 8 visit times", "--")):
            for arm, marker, color in zip(("c0", "fitted_c"), ("o", "D"), colors, strict=True):
                values = [crossed[case][f"{prefix}-{policy}"]["scores"]["matched"]["arms"][arm]["error_km"]
                          for policy in ("both", "primary")]
                ax.plot([offset, 1 + offset], values, marker=marker, color=color, ls=style, lw=1.6,
                        label=f"{label} · " + ("zero c" if arm == "c0" else "fitted c"))
        ax.set_xticks([0, 1], ["Either rank", "Primary between\nanchors"])
        ax.set_xlim(-.23, 1.23)
        ax.set(title=title, ylabel="Horizontal error (km)")
        ax.set_ylim(bottom=0)
    axes[0].legend(loc="lower left", fontsize=8, frameon=False)
    sites = ("DS30-0016", "south-containing", "south-far")
    for i, (field, label, color) in enumerate((("original_cpu_s", "Usual order", "#64748b"),
                                                ("cpu_s", "Check region first", "#00816c"))):
        axes[2].bar([n+(i-.5)*.36 for n in range(3)], [early[k][field] for k in sites], width=.34,
                    color=color, label=label)
    axes[2].set_xticks(range(3), ["Physical\ninside", "South\ninside", "South\nomitted"])
    axes[2].set(title="Time to the regional decision", ylabel="Saved solve CPU (s)")
    axes[2].legend(frameon=False, fontsize=8, loc="upper left")
    for ax in axes:
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=.17)
    fig.suptitle("Position from saved full-aperture measurements", fontsize=15, fontweight="bold")
    fig.savefig(HERE / "development/mixed-aperture-region.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
