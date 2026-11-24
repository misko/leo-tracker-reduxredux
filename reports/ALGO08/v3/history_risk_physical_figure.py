"""Plot the two enrolled original-waveform comparisons from the scored cohort."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_values(cohort):
    cases = cohort["cases"]
    if set(cases) != {"DS30-0107", "DS30-0016"}:
        raise ValueError("Expected the complete enrolled physical pair")
    times, errors = {}, {}
    for mode in ("stock", "candidate"):
        times[mode] = [cases[case][mode]["clock"]["elapsed_s"] for case in ("DS30-0107", "DS30-0016")]
        for arm in ("c0", "fitted_c"):
            if cases["DS30-0107"][mode]["arms"][arm]["horizontal_error_km"] is not None:
                raise ValueError("The withheld recording cannot contribute a measured position error")
        errors[mode] = [1000 * cases["DS30-0016"][mode]["arms"][arm]["horizontal_error_km"]
                        for arm in ("c0", "fitted_c")]
    return times, errors


def cairo_times(cohort, cairo):
    cases = ("DS30-0107", "DS30-0016")
    if (cairo["qualified"] is not True or not cairo["verification_0016"]["cal_arms"]
            or cairo["decisions"] != {"DS30-0107": "withheld", "DS30-0016": "complete"}):
        raise ValueError("Expected the qualified Cairo fix and withholding")
    for case in cases:
        if cairo["clocks"][case]["stock"]["elapsed_s"] != cohort["cases"][case]["stock"]["clock"]["elapsed_s"]:
            raise ValueError("The Cairo timing must share the installed comparator")
    return [cairo["clocks"][case]["candidate"]["elapsed_s"] for case in cases]


def render(cohort, path, cairo=None):
    times, errors = plot_values(cohort)
    if cairo is not None:
        times["cairo"] = cairo_times(cohort, cairo)
    fig, axes = plt.subplots(1, 2, figsize=(10.3, 3.8), layout="constrained")
    fig.suptitle("Installed ALGO08v3 and the 20/8 ms candidate on original waveforms",
                 fontsize=14, fontweight="bold")
    for ax, values, labels, title, unit, fmt in (
        (axes[0], times, ["DS30-0107\nwithheld", "DS30-0016\nfix"], "Time through process exit", "Seconds", "%.2f"),
        (axes[1], errors, ["Fixed c = 0", "Fitted c"], "DS30-0016 horizontal error", "Metres", "%.0f"),
    ):
        series = [("stock", "Installed v3", "#233c5c"), ("candidate", "20/8 ms", "#00796a")]
        if "cairo" in values:
            series.append(("cairo", "20/8 ms + Cairo", "#ab581d"))
        elif cairo is not None:
            series[1] = ("candidate", "Both 20/8 ms renderers", "#00796a")
        height = 0.70 / len(series)
        for i, (key, name, color) in enumerate(series):
            offset = (i - (len(series) - 1) / 2) * height
            bars = ax.barh([y + offset for y in (0, 1)], values[key], height=height * 0.9, color=color, label=name)
            ax.bar_label(bars, fmt=fmt, padding=3, fontsize=9)
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_yticks([0, 1], labels)
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        ax.set_xlim(0, 1.22 * max(max(v) for v in values.values()))
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#dbe3e8", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.19), frameon=False, ncol=len(series),
                  columnspacing=1, fontsize=9)
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cairo-cohort", type=Path)
    args = parser.parse_args()

    def read(path):
        body = path.read_bytes()
        return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)

    render(read(args.cohort), args.output, read(args.cairo_cohort) if args.cairo_cohort else None)
