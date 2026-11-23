"""Compare full raw timings and graph-only position results on the same dense recording."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def read(name):
    return json.loads((DATA / name).read_bytes())


def main():
    controls = read("dense-control-clocks.json")["controls"]
    raw = json.loads(gzip.decompress((DATA / "dense-full-short-raw.json.gz").read_bytes()))
    crossover = read("dense-full-short-crossover-summary.json")["runs"]
    degree = read("degree-only-dense.json")["against_stock"]
    fig, (timing, error) = plt.subplots(1, 2, figsize=(11.1, 4.55))
    fig.subplots_adjust(left=.18, right=.98, bottom=.23, top=.79, wspace=.65)
    cases = [controls["named_launcher"], controls["qualification"], raw["process"]]
    for offset, key, color, label in [(-.16, "elapsed_s", "#364d72", "Elapsed"), (.16, "cpu_s", "#85ad9d", "CPU")]:
        bars = timing.barh([n + offset for n in range(3)], [r[key] for r in cases], .29, color=color, label=label)
        timing.bar_label(bars, fmt="%.1f", fontsize=9, padding=3)
    timing.set_yticks(range(3), ["Named v3\n76.7% cached", "Frozen v3\n100% cached", "Short + quadratic\n2.8% cached"])
    timing.invert_yaxis()
    timing.set(xlim=(0,173), xlabel="Seconds, launch through exit", title="Raw recording through eight figures")
    timing.legend(loc="upper center", bbox_to_anchor=(.5, -.20), frameon=False, ncol=2, fontsize=9)
    for arm, delta, color, marker, label in (("c0", -.13, "#364d72", "o", "Fixed c = 0"),
                                             ("fitted_c", .13, "#b85d2e", "D", "Fitted c")):
        values = [crossover["short_quadratic"]["arms"][arm]["horizontal_error_km"],
                  degree[arm]["error_km"], crossover["short_installed"]["arms"][arm]["horizontal_error_km"]]
        y = [i + delta for i in range(len(values))]
        error.scatter(values, y, c=color, marker=marker, label=label)
        for x, line in zip(values,y,strict=True):
            error.text(x+.035,line,f"{x:.3f}",va="center",fontsize=9)
    error.set_yticks(range(3), ["Degree ≤2, 6 points", "Degree ≤2, 8 points", "Installed graph"])
    error.set(ylim=(2.5,-.5), xlim=(0,1.65), xlabel="Horizontal position error (km)",
              title="Same 12 ms receiver measurements")
    error.legend(loc="upper center", bbox_to_anchor=(.5, -.20), frameon=False, ncol=2, fontsize=9)
    for ax in (timing,error):
        ax.set_axisbelow(True)
        ax.grid(axis="x",alpha=.18)
        ax.spines[["right","top"]].set_visible(False)
    fig.suptitle("DS30-0008 · one dense physical recording on one Gauss core", y=.95,
                 fontsize=15, fontweight="bold")
    fig.savefig(HERE / "development/dense-real-transfer.png",dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
