#!/usr/bin/env python3
"""Render descriptive membership figures; no inference or position scoring."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def describe(summary):
    members = summary["members"]
    if len(members) != summary["counts"]["members"]:
        raise ValueError("membership count differs")
    for key in ("case_id", "dataset_label", "raw_identity_sha256"):
        if len({row[key] for row in members}) != len(members):
            raise ValueError("duplicate " + key)
    daily = Counter()
    readiness = Counter()
    for row in members:
        day = datetime.fromtimestamp(row["captured_utc_ns"] / 1e9, UTC).date().isoformat()
        daily[day, row["mode"]] += 1
        readiness[row["mode"], bool(row["glrt_availability"]["available"])] += 1
    return daily, readiness


def main(args):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import numpy as np
    from matplotlib import pyplot as plt

    summary = json.loads(args.summary.read_bytes())
    daily, readiness = describe(summary)
    args.output.mkdir(parents=True, exist_ok=True)
    dates = sorted({day for day, _mode in daily})
    modes = ("fast", "adaptive")
    colors = ("#2878B5", "#E28B26")
    figure = plt.figure(figsize=(13, 8.2), constrained_layout=True)
    grid = figure.add_gridspec(2, 2)
    counts = figure.add_subplot(grid[0, 0])
    bottom = np.zeros(len(dates))
    for mode, color in zip(modes, colors, strict=True):
        values = np.array([daily[day, mode] for day in dates])
        counts.bar(range(len(dates)), values, bottom=bottom, label=mode.capitalize(), color=color)
        bottom += values
    for index, value in enumerate(bottom):
        counts.text(index, value + 0.4, str(int(value)), ha="center", fontsize=9)
    counts.set_xticks(range(len(dates)), [day[5:] for day in dates])
    counts.set(
        xlabel="Acquisition start date (UTC)",
        ylabel="Whole acquisitions",
        title="All 317 acquisitions by start date",
    )
    counts.set_ylim(0, max(bottom) * 1.15)
    counts.legend(frameon=False)

    ready = figure.add_subplot(grid[0, 1])
    available = [readiness[mode, True] for mode in modes]
    missing = [readiness[mode, False] for mode in modes]
    ready.barh(modes, available, label="Saved GLRT manifest available", color="#399765")
    ready.barh(modes, missing, left=available, label="Unavailable at inventory", color="#B84D4D")
    for index, (yes, no) in enumerate(zip(available, missing, strict=True)):
        ready.text(yes / 2, index, f"{yes} available", ha="center", va="center", color="white")
        ready.text(yes + no + 2, index, f"{no} unavailable", va="center", fontsize=9)
    ready.set(
        xlabel="Whole acquisitions (all members retained)",
        title="Saved analysis availability at inventory",
        xlim=(0, 205),
    )
    ready.legend(loc="lower left", bbox_to_anchor=(0, -0.35), frameon=False, fontsize=9)

    timeline = figure.add_subplot(grid[1, :])
    for index, (mode, color) in enumerate(zip(modes, colors, strict=True)):
        rows = [row for row in summary["members"] if row["mode"] == mode]
        times = [datetime.fromtimestamp(row["captured_utc_ns"] / 1e9, UTC) for row in rows]
        timeline.scatter(times, np.repeat(index, len(times)), marker="|", s=210, color=color)
    unavailable = [row for row in summary["members"] if not row["glrt_availability"]["available"]]
    incomplete = [row for row in summary["members"] if row["recording_state"] != "complete"]
    for rows, marker, color, label in (
        (unavailable, "o", "#B84D4D", "Unavailable saved GLRT manifest"),
        (incomplete, "x", "#222222", "Incomplete capture (retained)"),
    ):
        timeline.scatter(
            [datetime.fromtimestamp(row["captured_utc_ns"] / 1e9, UTC) for row in rows],
            [modes.index(row["mode"]) for row in rows],
            marker=marker,
            s=100,
            color=color,
            label=label,
            zorder=5,
        )
    timeline.set_yticks([0, 1], ["Fast (159)", "Adaptive (158)"])
    timeline.set(
        ylim=(-0.5, 1.5),
        xlabel="Acquisition start time (UTC)",
        title="Whole-acquisition timeline; no readiness or completeness filter",
    )
    timeline.xaxis.set_major_locator(mdates.DayLocator(tz=UTC))
    timeline.xaxis.set_major_formatter(mdates.DateFormatter("%b %d", tz=UTC))
    timeline.grid(axis="x", alpha=0.25)
    timeline.legend(loc="upper left", frameon=False, fontsize=9)
    figure.suptitle(
        "DS26: all new recordings since DS24\n2026-10-24 14:38:14 to 2026-10-30 14:42:46 UTC",
        fontsize=15,
    )
    figure.savefig(args.output / "dataset_inventory.png", dpi=160)
    figure.savefig(args.output / "dataset_inventory.pdf")
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
