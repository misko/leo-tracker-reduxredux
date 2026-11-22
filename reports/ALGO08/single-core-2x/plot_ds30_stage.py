"""Plot verified pairs from a saved DS30 stage inventory or score."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from tools.pipeline_eval.scoring import distance_km


METHODS = {"baseline": ("Deployed ALGO08v2", "#39486a"), "candidate": ("Research candidate", "#007d68")}
REFERENCES = Path(__file__).resolve().parents[2] / "2026_11_21_ds30_full/reference-audit.json"


def plot(stage, output):
    cases = [row for row in stage["cases"] if row["state"] == "verified"]
    if not cases:
        raise ValueError("No verified pairs to plot")
    public = json.loads(REFERENCES.read_bytes())
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in public["cases"] if r["authority_eligible"]}
    count = len(cases)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.3), layout="constrained")
    for ax, metric, title in zip(axes[0], ("elapsed_s", "cpu_s"),
                                 ("Raw I/Q to web publication", "Single-core CPU"), strict=True):
        for index, case in enumerate(cases):
            times = case[metric]
            ax.plot([times["baseline"], times["candidate"]], [index, index], color="#cad1d4", lw=3, zorder=1)
            for name, (label, color) in METHODS.items():
                ax.scatter(times[name], index, color=color, s=48, zorder=2, label=label if index == 0 else None)
        ax.set_yticks(range(count), [r["case"] for r in cases])
        ax.invert_yaxis()
        ax.set(xlim=(0, None), xlabel="Seconds", title=title)
        ax.margins(y=.22)
    series = {}
    for arm in ("c0", "fitted_c"):
        for method in METHODS:
            values = [distance_km(r["arms"][method][arm]["latlon"], refs[r["case"]]) for r in cases]
            series[arm, method] = sorted(v for v in values if v is not None)
    limit = 1.1 * max([1., *(v for values in series.values() for v in values)])
    for ax, arm, title in zip(axes[1], ("c0", "fitted_c"),
                              ("Fixed-zero calibration", "Fitted calibration"), strict=True):
        for method, (label, color) in METHODS.items():
            values = series[arm, method]
            fractions = [0., *[i / count for i in range(1, len(values)+1)], len(values)/count]
            ax.step([0., *values, limit], fractions, where="post", color=color,
                    ls="--" if method == "candidate" else "-", lw=2.2, label=label)
        ax.set(xlim=(0, limit), ylim=(-.04, 1.06), xlabel="Horizontal position error (km)", title=title)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
    axes[1, 0].set_ylabel("Fraction of verified recordings")
    for ax in axes.flat:
        ax.set_axisbelow(True)
        ax.grid(alpha=.16)
        ax.spines[["top", "right"]].set_visible(False)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle(f"DS30 single-core comparison · {count} of {stage['assigned']} assigned pairs verified",
                 weight="bold", fontsize=15)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot(json.loads(args.inventory.read_bytes()), args.output)
