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


def render(cohort, path):
    times, errors = plot_values(cohort)
    fig, axes = plt.subplots(1, 2, figsize=(10.3, 3.8), layout="constrained")
    fig.suptitle("Installed ALGO08v3 and the 20/8 ms candidate on original waveforms",
                 fontsize=14, fontweight="bold")
    for ax, values, labels, title, unit, fmt in (
        (axes[0], times, ["DS30-0107\nwithheld", "DS30-0016\nfix"], "Time through process exit", "Seconds", "%.2f"),
        (axes[1], errors, ["Fixed c = 0", "Fitted c"], "DS30-0016 horizontal error", "Metres", "%.0f"),
    ):
        for key, name, offset, color in (("stock", "Installed v3", -0.18, "#233c5c"),
                                         ("candidate", "Candidate", 0.18, "#00796a")):
            bars = ax.barh([y + offset for y in (0, 1)], values[key], height=0.32, color=color, label=name)
            ax.bar_label(bars, fmt=fmt, padding=3, fontsize=9)
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_yticks([0, 1], labels)
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        ax.set_xlim(0, 1.22 * max(max(v) for v in values.values()))
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#dbe3e8", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.19), frameon=False, ncol=2)
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    body = args.cohort.read_bytes()
    render(json.loads(gzip.decompress(body) if args.cohort.suffix == ".gz" else body), args.output)
