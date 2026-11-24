"""Render signed position errors for the two continuous-channel trials."""

import argparse
import gzip
import json
from pathlib import Path

from reports.ALGO08.v3.release_stage_budget import checked


HERE = Path(__file__).resolve().parent
PIN = "ef900f70bb8787be4a72e6ba61b59b172a238c0505d550416248d0af6366a7d9"


def observations():
    sealed = checked(HERE / "measurements/complete-rf-streams.json.gz", PIN)
    scores = json.loads(gzip.decompress(sealed))["scores"]
    rows = []
    for key, label in (("north", "North simulation"), ("weak", "DS30-0016 recording")):
        case = scores[key]
        if case["decision"] != "complete":
            raise ValueError(f"{label} has no verified fix")
        methods = (case["controls"]["named"], case["controls"]["all8"], case["candidate"])
        for arm, title in (("c0", "Fixed c = 0"), ("fitted_c", "Fitted c")):
            rows.append((label, title, [m[arm]["error_m"] for m in methods]))
    return rows


def render(output):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator, StrMethodFormatter

    rows = observations()
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 5.2), sharex=True)
    fig.subplots_adjust(left=.18, right=.96, bottom=.15, top=.77, hspace=.88)
    fig.suptitle("Position error after reducing short observations to four channels",
                 x=.04, y=.98, ha="left", fontsize=16, weight="bold")
    styles = (("Installed v3", "#38456b", "s"), ("All eight channels", "#168176", "o"),
              ("Four channels", "#b86020", "D"))
    for i, ax in enumerate(axes):
        pair = rows[2*i:2*i+2]
        ax.set_title(pair[0][0], loc="left", weight="bold", fontsize=12)
        ax.set_yticks([1, 0], [r[1] for r in pair])
        for j, (method, color, marker) in enumerate(styles):
            values = [r[2][j] for r in pair]
            y = [1.0 + .20*(1-j), .20*(1-j)]
            ax.scatter(values, y, color=color, marker=marker, s=48, label=method, zorder=3)
        ax.set_ylim(-.42, 1.45)
        ax.tick_params(axis="both", length=0, pad=6)
        ax.spines[:].set_visible(False)
        ax.grid(axis="x", color="#dce1e6")
    axes[-1].set_xlim(0, 3220)
    axes[-1].xaxis.set_major_locator(MultipleLocator(500))
    axes[-1].xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    axes[-1].set_xlabel("Horizontal position error (m)", labelpad=7)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.03,.92),
               ncol=3, frameon=False)
    fig.savefig(output, dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    render(parser.parse_args().output)
