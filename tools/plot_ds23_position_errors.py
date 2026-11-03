"""Plot the already-evaluated DS23 positions; does not rerun inference."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"


def main():
    with (DIRECTORY / "results.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    cases = sorted({r["case"] for r in rows})
    x = np.arange(len(cases))
    fig, axes = plt.subplots(2, 1, figsize=(15, 9), sharex=True, sharey=True)
    for ax, mode, title in zip(
        axes, ("radio", "fixed150"),
        ("Radio-only estimated observation noise", "Fixed 150 Hz noise control"), strict=True
    ):
        for arm, offset, color, label in (
            ("c0", -.20, "#2869a4", "c = 0"),
            ("fitted_c", .20, "#e58b2a", "Fitted c"),
        ):
            selected = {r["case"]: float(r["error_km"]) for r in rows
                        if r["mode"] == mode and r["arm"] == arm}
            values = [selected[c] for c in cases]
            bars = ax.bar(x + offset, values, width=.38, color=color,
                          label=f"{label} — median {np.median(values):.3f} km")
            ax.bar_label(bars, fmt="%.2f", padding=4, fontsize=9)
        ax.axhline(1, c=".45", lw=1, ls="--", label="1 km")
        ax.set(title=title, ylabel="Position error (km)", ylim=(0, 5.8))
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
        ax.legend(loc="upper left", fontsize=10, ncol=3)
    formats = {r["case"]: ("adaptive" if "adaptive" in r["format"] else "fast") for r in rows}
    axes[-1].set_xticks(x, [f"{c}\n{formats[c]}" for c in cases], fontsize=10)
    axes[-1].set_xlabel("Scan, ordered chronologically by dataset label")
    fig.suptitle("DS23: position error for all 10 randomly sampled scans", fontsize=17)
    fig.text(.5, .014,
             "Errors evaluated after fitting against 37.849061591561885, −122.48574968092912; "
             "conditional on all scans sharing that reference.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .04, 1, .96))
    fig.savefig(DIRECTORY / "position_error_by_scan.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
