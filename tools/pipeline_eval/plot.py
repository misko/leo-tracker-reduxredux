"""Plot the fraction of all attempts returning a position within a given error."""

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter

from .scoring import ROLES


def make_plot(refs, root, arm, methods, destination):
    destination = Path(destination).resolve()
    if destination.is_relative_to("/mnt/qnap01"):
        raise ValueError("choose a local plot destination outside the read-only archive")
    groups = sorted({(r["group"], r["condition"]) for r in refs})
    curves = {k: defaultdict(list) for k in groups}
    for r in refs:
        key = r["group"], r["condition"]
        for method in (
            *ROLES,
            "grid_four"
            if r["condition"] == "missing" or "grid_one" not in r["reference"]
            else "grid_one",
        ):
            arms = r["reference"].get(method, {})
            if arms:
                result = arms.get(arm, arms.get("shape"))
                curves[key][method].append(result["error_km"])

    folders = sorted(p for p in root.glob("*") if p.is_dir())
    count = 0
    for folder in folders:
        method = folder.name
        if methods and method not in methods:
            continue
        path = folder / "current" / "errors.csv"
        if not path.is_file():
            path = folder / "errors.csv"
        if not path.is_file():
            continue
        with path.open() as stream:
            recorded = [r for r in csv.DictReader(stream) if r["arm"] == arm]
        if not any(r["position_method"] == "True" for r in recorded):
            continue
        if {r["id"] for r in refs} != {r["id"] for r in recorded}:
            raise ValueError(f"{method} and the plotted roster differ")
        for r in recorded:
            key = r["group"], r["condition"]
            curves[key][method].append(float(r["error_km"]) if r["error_km"] else None)
        count += 1
    if methods and not count:
        raise ValueError("no selected positioning results are available in this output directory")

    columns = min(2, len(groups))
    fig, axes = plt.subplots(
        math.ceil(len(groups) / columns),
        columns,
        squeeze=False,
        figsize=(6 * columns, 3.5 * math.ceil(len(groups) / columns) + 0.9),
    )
    labels = {
        "baseline": "v5, no repair",
        "selective-gap": "v5, selective gap",
        "omitted-track-one": "v5, one omitted",
        "omitted-tracks": "v5, two omitted",
        "grid_one": "Regional grid, one tile",
        "grid_four": "Regional grid, four tiles",
    }
    palette = dict(zip(ROLES, ("#192f54", "#526884", "#76869e", "#91a4bf"), strict=True))
    handles = {}
    for ax, group in zip(axes.flat, groups, strict=False):
        entries = curves[group]
        hi = max([10.0] + [v for values in entries.values() for v in values if v is not None])
        for name, values in entries.items():
            if not values:
                continue
            ordered = sorted(v for v in values if v is not None)
            y = [0.0] + [(i + 1) / len(values) for i in range(len(ordered))]
            (line,) = ax.step(
                [0.0, *ordered, 1.12 * hi],
                [*y, y[-1]],
                where="post",
                label=labels.get(name, name.replace("_", " ")),
                lw=1.7,
                color=palette.get(name),
                linestyle="--" if name in ROLES[1:] else "-",
            )
            handles.setdefault(name, line)
        ax.set_xscale("symlog", linthresh=0.25)
        ax.set_xlim(0, hi * 1.1)
        ticks = [x for x in (0, 0.25, 1, 2, 5, 10, 30, 100, 300, 1000, 3000, 10000) if x < hi * 1.1]
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
        ax.set_ylim(-0.025, 1.04)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title(f"{group[0]} · true region {group[1]}", loc="left", fontweight="bold")
        ax.set_xlabel("Horizontal position error (km)")
        ax.set_ylabel("Fraction of all attempts")
        ax.grid(alpha=0.2)
    for ax in list(axes.flat)[len(groups) :]:
        ax.set_visible(False)
    fig.suptitle(f"Receiver error distributions · {arm.replace('_', ' ')}", fontsize=16)
    fig.legend(handles=handles.values(), loc="lower center", ncol=min(4, len(handles)), fontsize=8)
    fig.tight_layout(rect=(0, min(0.22, 0.07 + len(handles) * 0.007), 1, 0.95))
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=145)
    plt.close(fig)
