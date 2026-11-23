"""Draw comparable timing stages from the two end-to-end shortcut receipts."""

import json
from math import isclose, isfinite
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
STAGES = (
    ("detection_file_s", "Launch to detections", "#476583"),
    ("detection_to_terminal_s", "Position solve", "#329488"),
    ("terminal_to_exit_s", "Publish and exit", "#D9A15E"),
)


def stage_times(run):
    times = [run[field] for field, _, _ in STAGES]
    if not all(isfinite(value) and value >= 0 for value in times):
        raise ValueError("All stage times must be finite and nonnegative")
    if not isclose(sum(times), run["elapsed_s"], abs_tol=0.001, rel_tol=0):
        raise ValueError("Stage times must cover the full elapsed clock")
    return times


def draw():
    cases = (
        ("DS30-0008", "Dense recording", "Unequal starting cache"),
        ("DS30-0016", "Weak recording", "Fully resident inputs"),
    )
    fig, axes = plt.subplots(1, 2, figsize=(10.3, 3.1))
    fig.subplots_adjust(top=.69, bottom=.26, left=.12, right=.965, wspace=.53)
    for axis, (case, description, cache) in zip(axes, cases, strict=True):
        path = HERE / "measurements" / f"bounds-{case}-pair.json"
        receipt = json.loads(path.read_bytes())
        if receipt["case"] != case:
            raise ValueError(f"Unexpected recording identity in {path}")
        arms = [receipt["runs"][name] for name in ("baseline", "bounds")]
        for y, run in zip((1, 0), arms, strict=True):
            left = 0
            for value, (_, label, color) in zip(stage_times(run), STAGES, strict=True):
                axis.barh(y, value, left=left, height=.43, color=color, label=label if y else None)
                left += value
            axis.annotate(f"{run['elapsed_s']:.2f}", (left, y), (4, 0), textcoords="offset points",
                          ha="left", va="center", fontsize=9)
        axis.axvline(arms[0]["elapsed_s"] / 2, color="#23272A", ls="--", lw=1, label="Half of v3 elapsed")
        axis.set_xlim(0, 1.24 * max(run["elapsed_s"] for run in arms))
        axis.set_ylim(-.53, 1.52)
        axis.set_yticks([1, 0], ["ALGO08v3", "#1 + #2 + #4"])
        axis.set_xlabel("Elapsed seconds")
        axis.set_title(f"{case}  ·  {description}\n{cache}", fontsize=11, loc="left", pad=9)
        axis.spines[["left", "right", "top"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
        axis.set_axisbelow(True)
        axis.grid(axis="x", alpha=.16)
    fig.suptitle("Raw I/Q through all eight position-analysis figures", x=.015, ha="left",
                 fontsize=15, fontweight="bold")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", frameon=False, ncol=4, fontsize=9)
    fig.savefig(HERE / "development/bounds-paired-runtime.png", dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    draw()
