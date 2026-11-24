"""Plot complete saved-packet worker clocks and errors on their original offers."""

import argparse
import gzip
import json
from pathlib import Path

from reports.ALGO08.v3.release_stage_budget import checked


HERE = Path(__file__).resolve().parent


def row(case, cohort, installed_s, candidate_s, geographic):
    errors = {}
    for calibration in ("c0", "fitted_c"):
        errors[calibration] = [
            arm["horizontal_error_km"] if (arm := geographic[worker][calibration]) is not None else None
            for worker in ("installed", "routed")
        ]
    return dict(case=case, cohort=cohort, elapsed_s=[installed_s, candidate_s], **errors)


def read_receipt(name, pin):
    return json.loads(gzip.decompress(checked(HERE / "measurements" / name, pin)))


def observations():
    dev = read_receipt("nomination-handoff-0255.json.gz",
                       "52597f4dddbe7b6de19d2dbc990916578578c7a4378021b8c594aff99a631817")
    rows = [row("DS30-0255", "development", dev["controls"]["installed"]["elapsed_s"],
                dev["clock"]["elapsed_s"], dev["original_geographic"])]
    for case, pin in (("0419", "acd745a32eedcaad14560e1f32da7b0e761419811780a9ca9dcdfb9eb797e4a1"),
                      ("0289", "78d36df4d6cea5a851ffb344803b965e09f1814c6d068f69c538875359c993fe")):
        trial = read_receipt(f"nomination-handoff-{case}-local.json.gz", pin)
        if trial["case"] != "DS30-" + case or not trial["checks"]["same_input_and_offer"]:
            raise ValueError("The comparison requires the assigned case and matching inputs")
        timed = trial["time"]["elapsed_s"]
        rows.append(row(trial["case"], "blind", timed["installed"], timed["routed"], trial["geographic"]))
    return rows


def render(rows, output):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator

    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.85), sharey=True)
    fig.subplots_adjust(left=.21, right=.975, top=.66, bottom=.20, wspace=.19)
    fig.suptitle("Runtime and position error on the same saved detections",
                 ha="left", x=.025, y=.97, weight="bold", fontsize=16)
    colors = ["#415677", "#007c6b"]
    handles = [
        Line2D([], [], marker="o", linestyle="none", markeredgecolor=colors[0],
               markerfacecolor="white", markersize=9, markeredgewidth=1.7),
        Line2D([], [], marker="o", linestyle="none", color=colors[1], markersize=5),
    ]
    fig.legend(handles, ["Installed ALGO08v3", "Frozen candidate"], frameon=False,
               loc="upper left", bbox_to_anchor=(.018,.89), ncol=2)
    error_max = max((x for r in rows for arm in ("c0", "fitted_c") for x in r[arm]
                     if x is not None), default=1.)
    for ax, key, title, unit in zip(axes, ("elapsed_s", "c0", "fitted_c"),
                                    ("Worker runtime", "Fixed c = 0", "Fitted c"),
                                    ("seconds", "horizontal error (km)", "horizontal error (km)"), strict=True):
        for i, item in enumerate(rows):
            values = item[key]
            if all(v is not None for v in values):
                ax.plot(values, [i, i], color="#a9b1bb", lw=1.8, zorder=1)
            for j, value in enumerate(values):
                if value is not None:
                    ax.scatter(value, i, s=79 if j == 0 else 34, linewidth=1.6,
                               facecolor="white" if j == 0 else colors[1], edgecolor=colors[j], zorder=2+j)
        xmax = max(max(r[key]) for r in rows) if key == "elapsed_s" else error_max
        ax.set_xlim(0, max(xmax*1.11, .1))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=2))
        ax.set_title(title, fontsize=11, loc="left", weight="bold")
        ax.set_xlabel(unit, fontsize=10)
        ax.grid(axis="x", color="#dce2e8")
        ax.tick_params(axis="both", length=0, pad=5)
        ax.spines[:].set_visible(False)
    axes[0].set_yticks(range(len(rows)), [f"{r['case']}  ·  {r['cohort']}" for r in rows])
    axes[0].set_ylim(len(rows)-.55, -.55)
    fig.text(.025,.037, "Clocks include publication and exit on one core. Installed v3 withheld on DS30-0289.",
             fontsize=9, color="#415064")
    fig.savefig(output, facecolor="white", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    render(observations(), parser.parse_args().output)
