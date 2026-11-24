"""Plot the paired saved-detector clocks and cumulative errors from a sealed panel."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


HERE = Path(__file__).resolve().parent


def render(receipt, output):
    panel = json.loads(receipt.read_bytes())
    cases = panel["per_case"]
    errors = {"c0": [], "fitted_c": []}
    for case, row in cases.items():
        runs = row["geography"]["runs"]
        for arm, values in errors.items():
            value = runs["named"]["horizontal_error_km"][arm]
            if runs["candidate"]["horizontal_error_km"][arm] != value:
                raise ValueError(f"{case} has different errors between solvers")
            values.append(value)
    colors = ("#17375d", "#008573")
    fig, (runtime, error) = plt.subplots(1, 2, figsize=(10.6, 4.0))
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.25, top=0.77, wspace=0.33)
    fig.suptitle(f"ALGO08v3 and the exact solver on {len(cases)} DS30 recordings",
                 x=0.04, ha="left", fontweight="bold", fontsize=17)
    for i, row in enumerate(cases.values()):
        named, candidate = (row["clocks"][arm]["elapsed_s"] for arm in ("named", "candidate"))
        runtime.plot([candidate, named], [i, i], color="#b8c5cf", lw=2, zorder=1)
        for x, label, color in zip((named, candidate), ("ALGO08v3", "Exact solver"), colors):
            runtime.scatter(x, i, color=color, s=45, label=label if i == 0 else None, zorder=2)
    runtime.set_yticks(range(len(cases)), list(cases))
    runtime.set_ylim(len(cases) - 0.5, -0.5)
    runtime.set_xlim(left=0)
    runtime.set_xlabel("Elapsed time from saved detections through exit (s)")
    right_edge = max(max(values) for values in errors.values()) * 1.06
    for values, label, color in zip(errors.values(), ("Fixed c = 0", "Fitted c"), colors):
        xs = [0, *sorted(values), right_edge]
        ys = [n / len(values) for n in range(len(values) + 1)] + [1]
        error.step(xs, ys, where="post", color=color, lw=2, label=label)
        error.scatter(xs[1:-1], ys[1:-1], color=color, s=18)
    error.yaxis.set_major_formatter(PercentFormatter(1))
    error.set(xlim=(0, right_edge), ylim=(-0.04, 1.07), xlabel="Horizontal position error (km)")
    for axis, title in ((runtime, "Paired runtime"), (error, "Cumulative error · both solvers coincide")):
        axis.set_title(title, loc="left", fontweight="bold", fontsize=12)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="x", color="#dce3e8", alpha=0.8)
        axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=2, frameon=False)
        axis.set_axisbelow(True)
    fig.savefig(output, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render(HERE / "measurements/exact-named-saved-panel-four.json", HERE / "development/exact-named-four.png")
