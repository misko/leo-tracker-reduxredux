"""Plot the closed saved-detection solver comparisons without running inference."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
CALIBRATIONS = (("c0", r"Fixed zero ($c=0$)"), ("fitted_c", r"Fitted $c$"))
MODES = ("control", "repair")
COLORS = ("#53628b", "#087c67")
MARKERS = ("o", "D")


def observations():
    dense = json.loads((MEASUREMENTS / "dense-conditional-repair-0008.json").read_bytes())
    prior = json.loads((MEASUREMENTS / "collapsed-repair.json").read_bytes())["cases"]
    runs = dense["runs"]
    counts = [runs[mode]["associated"] for mode in MODES]
    yield (
        "DS30-0008",
        [runs[mode]["solver_cpu_s"] for mode in MODES],
        dense["errors_km"],
        {arm: counts[1][arm] - counts[0][arm] for arm, _ in CALIBRATIONS},
    )
    for key, label in (("DS30-0374", "DS30-0374"), ("south", "South simulation")):
        runs = prior[key]["modes"]
        yield (
            label,
            [runs[mode]["cpu_s"] for mode in MODES],
            {mode: {arm: runs[mode]["arms"][arm]["error_km"] for arm, _ in CALIBRATIONS}
             for mode in MODES},
            {arm: runs["repair"]["arms"][arm]["owners"] - runs["control"]["arms"][arm]["owners"]
             for arm, _ in CALIBRATIONS},
        )


def owner_label(deltas):
    c0, fitted = (deltas[arm] for arm, _ in CALIBRATIONS)
    if c0 != fitted:
        raise ValueError("Expected a common owner-count change across calibration arms")
    return "Same owner count" if c0 == 0 else f"{c0:+,} owners per arm".replace("-", "−")


def main():
    rows = list(observations())
    figure, (cpu, zero, fitted) = plt.subplots(
        ncols=3, sharey=True, figsize=(8.6, 3.2), layout="constrained",
        gridspec_kw={"width_ratios": (1.35, 1, 1)},
    )
    error_axes = (zero, fitted)
    levels = list(reversed(range(len(rows))))
    for level, (_, seconds, errors, _) in zip(levels, rows, strict=True):
        y = (level + 0.14, level - 0.14)
        for time, vertical, color in zip(seconds, y, COLORS, strict=True):
            bar = cpu.barh(vertical, time, height=0.22, color=color)
            cpu.bar_label(bar, fmt="%.1f", padding=4, fontsize=9)
        for axis, (arm, _) in zip(error_axes, CALIBRATIONS, strict=True):
            coordinates = [errors[mode][arm] for mode in MODES]
            axis.plot(coordinates, y, color="#a6afbb", linewidth=1.1)
            for location, vertical, color, marker in zip(coordinates, y, COLORS, MARKERS,
                                                        strict=True):
                axis.scatter(location, vertical, s=29, color=color, marker=marker, zorder=3)

    cpu.set_yticks(levels, [f"{name}\n{owner_label(deltas)}" for name, _, _, deltas in rows])
    cpu.set_ylim(-0.45, len(rows) - 0.55)
    cpu.set_xlim(0, max(max(seconds) for _, seconds, _, _ in rows) * 1.19)
    cpu.set_title("Solve and grid CPU", loc="left", fontweight="bold")
    cpu.set_xlabel("Seconds")
    maximum_error = max(error for _, _, errors, _ in rows
                        for mode_errors in errors.values() for error in mode_errors.values())
    for axis, (_, label) in zip(error_axes, CALIBRATIONS, strict=True):
        axis.set_title(label, loc="left", fontweight="bold")
        axis.set_xlim(0, maximum_error * 1.11)
        axis.set_xlabel("Horizontal error (km)")

    for axis in (cpu, *error_axes):
        axis.set_axisbelow(True)
        axis.grid(axis="x", color="#e3e7ea")
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
    legend = [Line2D([], [], color=color, marker=marker, linestyle="none", label=label)
              for color, marker, label in zip(COLORS, MARKERS,
                                              ("Matched control", "Collapsed repair"), strict=True)]
    figure.legend(handles=legend, loc="outside upper center", ncols=2, frameon=False)
    figure.savefig(HERE / "repair-dense-probe.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()
