"""Compare the two complete simulated replays and two physical prefix interventions."""

from gzip import open as open_gzip
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt


HERE = Path(__file__).resolve().parent


def receipt(name):
    with open_gzip(HERE / "measurements" / (name + ".json.gz"), "rt") as stream:
        return json.load(stream)


def gates(pairs):
    if not pairs or any(min(pair) <= 0 for pair in pairs):
        raise ValueError("Each timing comparison needs a positive paired elapsed time")
    return dict(median_fraction=median(b / a for a, b in pairs),
                summed_fraction=sum(b for a, b in pairs) / sum(a for a, b in pairs))


def data():
    north = receipt("eight-ms-native-live")["scientific_seal"]
    south = receipt("eight-ms-south-transfer")["documents"]
    times = {
        "North": [receipt("current-north-control")["new"]["clock"]["elapsed_s"],
                  north["historical"]["combined"]["clock"]["elapsed_s"], north["clock"]["elapsed_s"]],
        "South": [receipt("combined-raw-south")["historical_named"]["raw_elapsed_s"],
                  south["containing-score.json"]["historical_raw_clock"]["elapsed_s"], south["clock.json"]["elapsed_s"]],
    }
    dense = receipt("dense-8ms-prefix")["trial"]["geography"]["runs"]
    transfer = receipt("independent-8ms-0169")
    errors = {}
    for arm, label in (("c0", "zero"), ("fitted_c", "fitted")):
        errors["0008 · " + label] = [1000 * dense[key]["horizontal_error_km"][arm]
                                     for key in ("named", "control", "candidate")]
        sources = [transfer["named_20ms_context"], *(transfer["runs"][key]["scores"] for key in ("mixed12", "mixed8"))]
        errors["0169 · " + label] = [1000 * source[arm]["horizontal_error_km"] for source in sources]
    return times, errors


def plot(times, errors, destination):
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.5, 3.8), gridspec_kw={"width_ratios": [1, 1.24]})
    colors = ("#243855", "#bb682f", "#007c74")
    markers = ("o", "s", "D")
    for y, (key, values) in enumerate(times.items()):
        target = values[0] / 2
        left.plot([target, values[0]], [y, y], color="#dddfe4", zorder=0)
        left.scatter(target, y, marker="|", s=260, color="#363b47", label="Half-time target" if y == 0 else None)
        for idx, value in enumerate(values):
            left.scatter(value, y + (idx-1)*0.095, marker=markers[idx], s=54, color=colors[idx],
                         label=("ALGO08v3", "20/12 ms", "20/8 ms")[idx] if y == 0 else None)
        left.annotate(f"{values[0]/values[2]:.2f}×", (values[2], y+0.095), xytext=(0,-16),
                      textcoords="offset points", ha="center", fontsize=9, color=colors[2])
    left.set(yticks=range(len(times)), yticklabels=list(times), ylim=(1.55, -0.45), xlim=(6, 17),
             xlabel="Elapsed seconds through publication and exit")
    left.set_title("Complete simulated recordings", loc="left", fontweight="bold")
    for y, key in enumerate(sorted(errors)):
        named, older, newer = errors[key]
        right.plot([older, newer], [y, y], color="#b2c6c8", linewidth=2, zorder=0)
        for idx, value in enumerate((named, older, newer)):
            right.scatter(value, y+(idx-1)*0.10, marker=markers[idx], s=54, color=colors[idx])
    right.set(yticks=range(len(errors)), yticklabels=sorted(errors), ylim=(3.55, -0.6),
              xlabel="Horizontal position error, metres", xlim=(0, 1750))
    right.set_title("Physical DS30 prefix substitutions", loc="left", fontweight="bold")
    for ax in (left, right):
        ax.spines[["top","right","left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", alpha=.15)
        ax.set_axisbelow(True)
    fig.legend(*left.get_legend_handles_labels(), loc="lower left", bbox_to_anchor=(.065, -.002),
               ncol=4, frameon=False)
    fig.tight_layout(rect=(0, .12, 1, .98), w_pad=3)
    fig.savefig(destination, dpi=165)
    plt.close(fig)


if __name__ == "__main__":
    times, errors = data()
    plot(times, errors, HERE / "development" / "physical-transfer-and-raw-time.png")
    print(json.dumps(gates([(values[0], values[2]) for values in times.values()])))
