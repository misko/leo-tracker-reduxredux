"""Render the 12-hour research figures from archived full-publication receipts."""

import argparse
import json
from dataclasses import dataclass
from math import ceil, isfinite
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

from tools.pipeline_eval.scoring import distance_km

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
DS30 = (
    ("Conditional residual scans", "ds30-conditional-stage-inventory.json"),
    ("Full scans + collapsed solver", "full-phase-ds30-stage.json"),
    ("Terminal guard", "terminal-veto-physical-stage.json"),
    ("Wrapped spectral", "wrapped-spectral-0374-stage.json"),
)
SELECTED = "fractional-selected-stage.json"
METHODS = ("baseline", "candidate")
ARMS = ("c0", "fitted_c")
INK, MUTED, GRID = "#172a3b", "#526779", "#dce5eb"
BASE, CANDIDATE = "#596f91", "#007c72"


@dataclass(frozen=True)
class Pair:
    label: str
    elapsed_s: dict
    cpu_s: dict
    errors: dict


@dataclass(frozen=True)
class Group:
    label: str
    digest: str
    assigned: int
    pairs: tuple[Pair, ...]

    @property
    def coverage(self):
        return f"{len(self.pairs)}/{self.assigned} paired"


def read(path):
    return json.loads(path.read_bytes())


def check_times(values):
    if values.keys() != set(METHODS) or any(not isfinite(v) or v <= 0 for v in values.values()):
        raise ValueError("Each included pair needs positive matched timings")
    return values


def physical_group(label, stage, refs):
    verified = [row for row in stage["cases"] if row["state"] == "verified"]
    names = [row["case"] for row in verified]
    if (names != stage["coverage"]["verified"] or len(set(names)) != len(names)
            or len(stage["cases"]) != stage["assigned"] or not names):
        raise ValueError("The inventory disagrees with the verified recording count")
    pairs = tuple(Pair(
        row["case"], check_times(row["elapsed_s"]), check_times(row["cpu_s"]),
        {method: {arm: distance_km(row["arms"][method][arm]["latlon"], refs[row["case"]])
                  for arm in ARMS} for method in METHODS},
    ) for row in verified)
    return Group(label, stage["candidate_specification_digest"], stage["assigned"], pairs)


def simulated_group(side, pair, audit):
    for method in METHODS:
        measured, checked = pair["runs"][method], audit[method]
        if (measured["receipt"]["session_id"] != audit["session"]
                or measured["arms"] != checked["arms"]
                or any(measured[k] != checked[k] for k in ("elapsed_s", "cpu_s"))):
            raise ValueError(f"Spectral {side} timing does not bind the scored recording")
    elapsed, cpu = (check_times({method: pair["runs"][method][k] for method in METHODS})
                    for k in ("elapsed_s", "cpu_s"))
    observation = Pair(f"{side.title()} simulation", elapsed, cpu, audit["error_km"])
    return Group(f"Public {side} · spectral", pair["candidate_specification_digest"], 1,
                 (observation,))


def load_groups(report=HERE, selected=None):
    measurements = report / "measurements"
    references = read(report.parents[1] / "2026_11_21_ds30_full/reference-audit.json")
    refs = {row["dataset_label"]: (row["reference"]["latitude_deg"],
                                  row["reference"]["longitude_deg"])
            for row in references["cases"] if row["authority_eligible"]}
    physical = [physical_group(label, read(measurements / name), refs) for label, name in DS30]
    selected = measurements / SELECTED if selected is None else selected
    if selected.exists():
        physical.append(physical_group("Selected exact fractional", read(selected), refs))
    simulations = [simulated_group(
        side, read(measurements / f"spectral-terminal-{side}-inside.json"),
        read(measurements / f"spectral-terminal-{side}-audit.json"),
    ) for side in ("north", "south")]
    if len({group.digest for group in physical}) != len(physical):
        raise ValueError("Each physical chart group must name a distinct frozen build")
    if simulations[0].digest != simulations[1].digest:
        raise ValueError("The two spectral simulation controls must use the same frozen build")
    return physical, simulations


def november_22_1611_groups(report=HERE):
    receipts = report / "measurements"
    physical, _ = load_groups(report, selected=receipts / "fractional-selected-four-stage.json")
    # Compare the three builds that finished the same four physical recordings.
    labels = {
        "Conditional residual scans": "Conditional second scan",
        "Full scans + collapsed solver": "Two scans + collapsed solver",
        "Selected exact fractional": "Two scans + exact scores",
    }
    complete = [Group(labels[group.label], group.digest, group.assigned, group.pairs)
                for group in physical if group.label in labels and len(group.pairs) == 4]
    sides = [simulated_group(
        side, read(receipts / f"exact-curved-lookahead-{side}-inside.json"),
        read(receipts / f"exact-curved-lookahead-{side}-audit.json"),
    ) for side in ("north", "south")]
    if sides[0].digest != sides[1].digest:
        raise ValueError("A combined distribution requires the same frozen candidate")
    public = Group("Exact scores + direct solver", sides[0].digest, 2,
                   tuple(side.pairs[0] for side in sides))
    return complete, [public]


def ecdf(group, method, arm, limit):
    """Treat a missing fix as missing mass at every finite error, not as zero."""
    values = [row.errors[method][arm] for row in group.pairs]
    valid = sorted(value for value in values if value is not None)
    levels = [i / len(values) for i in range(1, len(valid) + 1)]
    return [0., *valid, limit], [0., *levels, len(valid) / len(values)]


def style_axis(ax, *, y_grid=False):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=.7)
    if y_grid:
        ax.grid(axis="y", color=GRID, linewidth=.7)
    ax.spines[["left", "right", "top"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(color=GRID, labelcolor=MUTED, labelsize=9)


def heading(fig, title, subtitle, *, error=False):
    fig.text(.055, .963, title, fontsize=21, fontweight="bold", color=INK, va="top")
    fig.text(.055, .923 if error else .914, subtitle, fontsize=10.5, color=MUTED, va="top")


def legend(fig, *, error=False):
    handles = [
        Line2D([], [], color=BASE, marker="o" if not error else None, linewidth=2.5 if error else 0,
               label="Deployed ALGO08v2"),
        Line2D([], [], color=CANDIDATE, marker="D" if not error else None,
               linewidth=1.8 if error else 0, linestyle="--" if error else "-",
               label="Research build"),
    ]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(.977, .941 if error else .94),
               ncol=1, frameon=False, fontsize=9, labelcolor=INK)


def seconds_axis(ax, groups, metric, *, label_visibility):
    y, ticks, labels, titles = 0., [], [], []
    max_value = max(getattr(row, metric)[method]
                    for group in groups for row in group.pairs for method in METHODS)
    for group in groups:
        ax.axhspan(y - .46, y + .46, color="#edf3f7", zorder=0)
        ticks.append(y)
        titles.append(len(labels))
        labels.append(f"{group.label}  ·  {group.coverage}")
        y += 1
        for row in group.pairs:
            base, candidate = (getattr(row, metric)[method] for method in METHODS)
            ax.plot([base, candidate], [y, y], lw=2.2, color="#a8b8c1", zorder=2)
            ax.scatter(base, y, s=36, marker="o", color=BASE, zorder=3)
            ax.scatter(candidate, y, s=33, marker="D", color=CANDIDATE, zorder=4)
            ax.annotate(f"{base / candidate:.2f}×", (max(base, candidate), y),
                        xytext=(7, 0), textcoords="offset points", va="center",
                        color=MUTED, fontsize=8)
            ticks.append(y)
            labels.append(row.label)
            y += .88
        y += .28
    ax.set(xlim=(0, max_value * 1.18), ylim=(y - .66, -.53), xlabel="Seconds")
    if label_visibility:
        for idx, item in enumerate(ax.set_yticks(ticks, labels)):
            label = item.label1
            if idx in titles:
                label.set(fontweight="bold", color=INK)
    else:
        ax.set_yticks([])
    ax.tick_params(axis="y", length=0, pad=8)
    style_axis(ax)
    if label_visibility:
        for idx in titles:
            ax.get_yticklabels()[idx].set_color(INK)


def timing_figure(physical, simulations, output):
    fig, axes = plt.subplots(2, 2, figsize=(13.3, 9.6),
                             gridspec_kw={"height_ratios": (len(physical) * 3.4, 5)})
    fig.subplots_adjust(left=.265, right=.97, top=.859, bottom=.103, hspace=.33, wspace=.23)
    heading(fig, "Time from sealed I/Q to publication",
            "Matched wall and charged CPU time on one core. Labels show deployed ÷ research time.")
    legend(fig)
    metrics = (("elapsed_s", "Wall time"), ("cpu_s", "Single-core CPU"))
    for col, (metric, label) in enumerate(metrics):
        seconds_axis(axes[0, col], physical, metric, label_visibility=col == 0)
        seconds_axis(axes[1, col], simulations, metric, label_visibility=col == 0)
        axes[0, col].set_title(label, loc="left", color=INK, fontsize=12, fontweight="bold", pad=9)
    for row, title in ((0, "DS30 PHYSICAL  ·  ONE ROOF"), (1, "PUBLIC SIMULATED CONTROLS")):
        axes[row, 0].text(-.66, 1.04, title, transform=axes[row, 0].transAxes,
                          color=MUTED, fontsize=9, fontweight="bold", clip_on=False)
    fig.text(.055, .025,
             "DS30 recordings recur across builds. North and south are distinct simulated "
             "controls. Ratios compare the two runs on the same row.", color=MUTED, fontsize=9)
    fig.savefig(output, dpi=155, facecolor="white")
    plt.close(fig)


def error_figure(physical, simulations, output):
    groups = [*physical, *simulations]
    valid_errors = (value for group in groups for row in group.pairs
                    for arms in row.errors.values() for value in arms.values() if value is not None)
    max_value = max(valid_errors, default=0.)
    limit = max(.5, ceil((max_value + .05) * 2) / 2)
    fig, axes = plt.subplots(len(groups), 2, figsize=(13.3, 2.0 + 1.35 * len(groups)), sharex=True)
    fig.subplots_adjust(left=.268, right=.97, top=.847 if len(groups) <= 4 else .866,
                        bottom=.102, hspace=.47, wspace=.2)
    heading(fig, "Horizontal position error",
            "Share of matched recordings at or below each error. Near-equal curves overlap.",
            error=True)
    legend(fig, error=True)
    for row, group in enumerate(groups):
        for col, arm in enumerate(ARMS):
            ax = axes[row, col]
            for method, color, width, ls in (
                ("baseline", BASE, 2.9, "-"), ("candidate", CANDIDATE, 1.85, "--"),
            ):
                x, y = ecdf(group, method, arm, limit)
                ax.step(x, y, where="post", color=color, linewidth=width, linestyle=ls)
            ax.set(xlim=(0, limit), ylim=(-.10, 1.12), yticks=[0, .5, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            style_axis(ax, y_grid=True)
            if row == 0:
                title = ("Fixed zero (c = 0)", "Fitted calibration")[col]
                ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=10)
            if row == len(groups) - 1:
                ax.set_xlabel("Horizontal error (km)", color=INK)
        scope = "Public simulation" if row >= len(physical) else "DS30 same roof"
        ax = axes[row, 0]
        ax.text(-.62, .72, group.label, transform=ax.transAxes, color=INK,
                fontsize=10.3, weight="bold", ha="left", va="center")
        ax.text(-.62, .38, f"{group.coverage}  ·  {scope}", transform=ax.transAxes, color=MUTED,
                fontsize=8.3, ha="left", va="center")
    fig.text(.055, .031,
             "Panels use the matched recordings for that build. A withheld fix would leave its "
             "curve below 100%. DS30 labels show verified coverage.",
             color=MUTED, fontsize=9)
    fig.savefig(output, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-inventory", type=Path)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--snapshot", choices=("1532", "1611"), default="1532")
    args = parser.parse_args()
    if args.snapshot == "1611":
        if args.selected_inventory:
            parser.error("The 16:11 snapshot uses the archived four-case inventory")
        physical_groups, simulation_groups = november_22_1611_groups()
        stem = "progress_1611"
    else:
        physical_groups, simulation_groups = load_groups(selected=args.selected_inventory)
        stem = "progress_12h"
    timing_figure(physical_groups, simulation_groups, args.output_dir / f"{stem}_timing.png")
    error_figure(physical_groups, simulation_groups, args.output_dir / f"{stem}_error.png")
