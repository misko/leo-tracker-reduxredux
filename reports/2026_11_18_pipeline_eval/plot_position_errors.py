"""Show every published roof position and the coverage of each position estimator."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tools.pipeline_eval.__main__ import read_predictions, references
from tools.pipeline_eval.scoring import score

HERE = Path(__file__).resolve().parent
METHODS = (
    ("baseline", "Original v5", "#243a5b"),
    ("v5_lean", "v5 without rendering", "#007f69"),
    ("orbit_interp", "Reuse orbital states", "#246e99"),
    ("shape_score", "Horizon screening", "#398ca3"),
    ("track_reduce", "Track compression", "#906027"),
    ("track_link", "Causal track linking", "#ac7737"),
    ("projected_fit", "Projected position fit", "#78698d"),
    ("iq_position", "Bounded IQ replay", "#716978"),
)


def main():
    _, refs = references("roof16", None)
    data = {"baseline": {r["id"]: r["reference"]["baseline"]["fitted_c"]["error_km"] for r in refs}}
    for method, _, _ in METHODS[1:]:
        source = HERE / "predictions" / "roof16" / f"{method}.jsonl.gz"
        _, rows = score(refs, read_predictions(source))
        data[method] = {r["id"]: r["error_km"] for r in rows if r["arm"] == "fitted_c"}
    fig, axes = plt.subplots(1, 2, figsize=(11.3, 4.9), sharex=True)
    fig.subplots_adjust(left=0.185, right=0.97, top=0.79, bottom=0.19, wspace=0.22)
    for k, (ax, group) in enumerate(zip(axes, ("DS26", "DS29"), strict=True)):
        ids = [r["id"] for r in refs if r["group"] == group]
        ax.set_title(f"{group} · {len(ids)} recordings", loc="left", fontweight="bold")
        labels = []
        for i, (name, label, color) in enumerate(METHODS):
            values = [
                (j, data[name][case]) for j, case in enumerate(ids) if data[name][case] is not None
            ]
            labels.append(
                f"{label}   {len(values)}/{len(ids)}" if not k else f"{len(values)}/{len(ids)}"
            )
            ax.scatter(
                [v for _, v in values],
                [i + (j - 3.5) * 0.052 for j, _ in values],
                color=color,
                alpha=0.64,
                s=34,
                linewidth=0,
            )
            if values:
                med = np.median([v for _, v in values])
                ax.scatter(
                    med,
                    i,
                    marker="D",
                    facecolors="white",
                    edgecolors=color,
                    s=40,
                    linewidth=1.5,
                    zorder=4,
                )
        ax.set_yticks(range(len(METHODS)), labels)
        ax.set_ylim(len(METHODS) - 0.5, -0.5)
        ax.set_xlim(-0.1, 7.5)
        ax.set_xlabel("Horizontal position error (km)")
        ax.grid(axis="x", color="#dce1e3", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.spines[:].set_visible(False)
        ax.tick_params(length=0)
    fig.suptitle(
        "Position error on matched roof recordings",
        x=0.035,
        y=0.97,
        ha="left",
        fontsize=18,
        fontweight="bold",
    )
    fig.text(
        0.035,
        0.045,
        "One dot per published position. Diamonds mark medians. Fractions count "
        "all eight attempts. v5 uses fitted calibration.",
        size=9,
    )
    fig.savefig(HERE / "roof-errors.png", dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    main()
