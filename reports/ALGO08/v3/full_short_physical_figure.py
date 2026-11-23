"""Plot the completed raw pair and the two saved numerical crossovers."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent


def main():
    measurements = HERE / "measurements"
    with gzip.open(measurements / "full-short-DS30-0016-raw.json.gz", "rt") as receipt:
        runs = json.load(receipt)["runs"]
    cells = json.loads((measurements / "full-short-crossover-summary.json").read_bytes())["cells"]
    figure, (timing, error) = plt.subplots(1, 2, figsize=(12.2, 4.7))
    figure.subplots_adjust(left=.11, right=.97, top=.76, bottom=.21, wspace=.65)
    for offset, field, label, color in (
        (-.16, "elapsed_s", "Elapsed", "#29496d"), (.16, "cpu_s", "CPU", "#72a79a")
    ):
        values = [runs[arm]["process"]["clocks"][field] for arm in ("stock", "candidate")]
        bars = timing.barh([offset, 1 + offset], values, height=.28, color=color, label=label)
        timing.bar_label(bars, fmt="%.2f", padding=4, fontsize=9)
    timing.set_yticks([0, 1], ["Installed v3", "Combined"])
    timing.invert_yaxis()
    timing.set(xlim=(0, 16.8), xlabel="Seconds from launch through exit", title="Full raw recording through web figures")
    target = runs["stock"]["process"]["clocks"]["elapsed_s"] / 2
    timing.axvline(target, ls=":", color="#943f24", lw=1.2, label=f"Half time ({target:.2f} s)")
    timing.legend(loc="upper center", bbox_to_anchor=(.5, -.20), frameon=False, ncol=3, fontsize=9)
    names = ("stock-stock", "candidate-stock", "stock-candidate", "candidate-candidate")
    for row, name in enumerate(names):
        fit = cells[name]["fit"]["arms"]
        for arm, dy, color, marker, label in (
            ("c0", -.13, "#29496d", "o", "Fixed c = 0"),
            ("fitted_c", .13, "#b0592c", "D", "Fitted c")
        ):
            km = fit[arm]["error_km"]
            error.scatter(km, row + dy, color=color, marker=marker, s=33, label=label if row == 0 else None)
            error.text(km + .07, row + dy, f"{km:.2f}", va="center", fontsize=9)
    error.set_yticks(range(4), ["Installed v3", "Receiver only", "Solver only", "Combined"])
    error.set_ylim(3.5, -.5)
    error.set(xlim=(0, 2.36), xlabel="Horizontal position error (km)", title="Same recording, four receiver–solver pairings")
    error.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.20), ncol=2, fontsize=9)
    for axis in (timing, error):
        axis.set_axisbelow(True)
        axis.grid(axis="x", alpha=.18)
        axis.spines[["right", "top"]].set_visible(False)
    figure.suptitle("DS30-0016  |  One physical recording on one core", fontsize=17, fontweight="bold", y=.97)
    figure.text(.5, .86, "Installed v3 read cold input. The combined build read cached input. The two crossovers used saved detections.",
                ha="center", fontsize=10, color="#424c58")
    figure.savefig(HERE / "development/full-short-physical.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()
