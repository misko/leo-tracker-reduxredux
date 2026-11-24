"""Plot the two original-input first-use runs against the same installed v3 clocks."""

import argparse
from pathlib import Path

from reports.ALGO08.v3.legacy_frame_figure import load_seal


PIN = "bcb774bb770a4ac65bdeeab5bc60b52cf0c077cc236cff456896e76b2906db01"
CASES = ("DS30-0107", "DS30-0016")


def elapsed(receipt):
    if not receipt["qualified"] or set(receipt["cases"]) != set(CASES):
        raise ValueError("Require the qualified complete physical pair")
    cases = receipt["cases"]
    return [
        [cases[k]["original"]["elapsed_s"] for k in CASES],
        [receipt["earlier_first_use"][k]["elapsed_s"] for k in CASES],
        [cases[k]["clock"]["clock"]["elapsed_s"] for k in CASES],
    ]


def render(receipt, output):
    import matplotlib.pyplot as plt

    groups = elapsed(receipt)
    reference = sum(groups[0])
    fig, ax = plt.subplots(figsize=(9.1, 4.6))
    fig.subplots_adjust(left=.225, right=.93, bottom=.24, top=.68)
    fig.suptitle("Time to analyze the same two original DS30 recordings",
                 x=.035, ha="left", fontsize=16, fontweight="bold")
    ax.set_yticks(range(3), ["Installed ALGO08v3", "Earlier first-use route", "Combined candidate"])
    for i, (withhold, fix) in enumerate(groups):
        ax.barh(i, withhold, height=.5, color="#a8bbcd", label="DS30-0107 · withheld" if i == 0 else None)
        ax.barh(i, fix, left=withhold, height=.5, color="#255a68", label="DS30-0016 · fix" if i == 0 else None)
        ax.text(withhold+fix+.12, i, f"{withhold+fix:.2f} s", va="center", fontsize=10)
    for speed, color in ((2., "#87602a"), (1.6, "#79566d")):
        x = reference/speed
        ax.axvline(x, color=color, linestyle="--", linewidth=1)
        ax.text(x, 1.035, f"{speed:g}×", transform=ax.get_xaxis_transform(), color=color,
                ha="center", fontsize=9)
    ax.legend(ncol=2, loc="lower left", bbox_to_anchor=(-.01, 1.18), frameon=False)
    ax.set_xlim(0, reference+1.15)
    ax.invert_yaxis()
    ax.set_xlabel("Summed elapsed seconds, launch through exit")
    ax.tick_params(axis="y", length=0)
    ax.spines[["right", "top", "left"]].set_visible(False)
    fig.text(.035, .07, "Each build ran on one core with resident original input. Both first-use routes built their own recording indexes.",
             fontsize=9)
    fig.savefig(output, dpi=145, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("receipt", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    render(load_seal(args.receipt, PIN), args.output)
