"""Plot through-exit timings with separate original-waveform and saved-detector panels."""

import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def read_receipt(stem):
    with gzip.open(HERE/"measurements"/(stem+".json.gz"), "rt") as stream:
        return json.load(stream)


def panels():
    north = read_receipt("north-orbit-index-active")
    combined = read_receipt("combined-raw-north")
    medium = read_receipt("catalogue-block-portable-0316")["result"]
    if (north["diagnostic_fallback"] or combined["candidate"]["diagnostic_fallback"]
            or combined["rank"]["counts"]["admitted_ranks"] != 1 or not medium["rank_validated"]):
        raise ValueError("Panel requires a verified original region check and complete cold rank")
    return [
        ("North simulation", "Original samples through exit", [
            ("ALGO08v3", north["prior"]["named"]["clock"]["elapsed_s"]),
            ("Guarded receiver", north["prior"]["selective"]["clock"]["elapsed_s"]),
            ("Guarded + cold index", north["clock"]["elapsed_s"]),
            ("Portable + block rank", combined["candidate"]["clock"]["elapsed_s"])]),
        ("Physical DS30-0316", "Saved detections through exit", [
            ("ALGO08v3", medium["historical"]["recent_named"]["process"]["elapsed_s"]),
            ("Ordinary research solver", medium["ordinary"]["through_exit"]["elapsed_s"]),
            ("Portable index", medium["portable_only"]["through_exit"]["elapsed_s"]),
            ("Portable + block rank", medium["combined"]["through_exit"]["elapsed_s"])])]


def render(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    fig.subplots_adjust(left=.17, right=.98, bottom=.23, top=.76, wspace=.72)
    fig.suptitle("Elapsed time on one Gauss core", x=.035, ha="left", fontsize=19, fontweight="bold", y=.985)
    for ax, (name, scope, rows) in zip(axes, panels(), strict=True):
        ax.set_title(name+"\n"+scope, loc="left", fontsize=11, linespacing=1.4)
        half = rows[0][1]/2
        ax.axvline(half, color="#bd5500", ls="--", lw=1.5, zorder=1)
        for i, (label, elapsed) in enumerate(rows):
            ax.barh(i, elapsed, height=.48, color="#343f60" if i == 0 else "#168070", zorder=2)
            ax.text(elapsed+.25, i, f"{elapsed:.2f}", va="center", fontsize=9)
        ax.set_yticks(range(len(rows)), [label for label, _ in rows], fontsize=9)
        ax.set_xlim(0, 20.4)
        ax.set_xticks([0, 5, 10, 15, 20])
        ax.set_xlabel("Seconds")
        ax.invert_yaxis()
        ax.spines[["top","left","right"]].set_visible(False)
        ax.grid(axis="x", color="#dfe4e8", linewidth=.7, zorder=0)
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
    fig.text(.035, .075, "Dashed line marks half of the v3 time at each panel’s starting point.", fontsize=10)
    fig.text(.035, .025, "Each bar is one completed process. The portable index was built on an earlier recording.", fontsize=9, color="#4b5563")
    fig.savefig(output, dpi=165, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render(Path(sys.argv[1]))
