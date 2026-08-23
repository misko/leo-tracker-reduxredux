#!/usr/bin/env python3
"""Render the fixed-window operational summary from the audited CSV evidence."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
START = datetime.fromisoformat("2026-08-23T07:03:41+00:00")
END = datetime.fromisoformat("2026-08-23T15:03:41+00:00")
CAPTURE_ENABLED = datetime.fromisoformat("2026-08-23T07:32:32+00:00")


def time(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    operations = rows("acquisition-operations.csv")
    standard = rows("standard-runs.csv")
    research = rows("research-runs.csv")
    scheduled_by_session: dict[str, datetime] = {}
    for operation in operations:
        match = re.search(r"capture (cap-[^ ]+) committed", operation.get("outcome") or "")
        scheduled = time(operation["scheduled_for"])
        if match and scheduled:
            scheduled_by_session[match.group(1)] = scheduled

    fig, axes = plt.subplots(3, 1, figsize=(14, 10.5), constrained_layout=True, sharex=True)

    ax = axes[0]
    ax.axvspan(START, CAPTURE_ENABLED, color="#c7c7c7", alpha=0.35, label="capture disabled")
    styles = {
        ("scheduled_recording", "succeeded"): (2, "o", "#238b45", "dwell succeeded"),
        ("scheduled_recording", "cancelled"): (2, "x", "#cb181d", "dwell coalesced"),
        ("scanner_sweep", "succeeded"): (1, ".", "#2171b5", "scanner succeeded"),
    }
    seen: set[str] = set()
    for operation in operations:
        key = (operation["kind"], operation["state"])
        if key not in styles:
            continue
        y, marker, color, label = styles[key]
        scheduled = time(operation["scheduled_for"])
        if scheduled is None:
            continue
        ax.scatter(
            scheduled,
            y,
            marker=marker,
            s=34 if marker != "." else 22,
            color=color,
            linewidths=1.6,
            label=label if label not in seen else None,
            zorder=3,
        )
        seen.add(label)
    ax.axvline(CAPTURE_ENABLED, color="#636363", linestyle="--", linewidth=1)
    ax.set_yticks((1, 2), ("scanner", "dwell"))
    ax.set_ylim(0.5, 2.5)
    ax.set_title("A · Three-minute intent coverage")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(loc="upper right", ncol=4, fontsize=9)

    ax = axes[1]
    for lane, lane_rows, color in (
        ("Standard", standard, "#238b45"),
        ("Research", research, "#756bb1"),
    ):
        for state, marker in (("succeeded", "o"), ("failed", "X")):
            values = []
            for run in lane_rows:
                if run["state"] != state:
                    continue
                started = time(run["created_at"])
                sealed = time(run["sealed_at"])
                scheduled = scheduled_by_session.get(run["session_id"], started)
                if started and sealed and scheduled:
                    values.append((scheduled, (sealed - started).total_seconds() / 60))
            if values:
                ax.scatter(
                    [item[0] for item in values],
                    [item[1] for item in values],
                    color="#cb181d" if state == "failed" else color,
                    marker=marker,
                    s=48 if marker == "X" else 28,
                    alpha=0.85,
                    label=f"{lane} {state}",
                )
    ax.set_yscale("log")
    ax.set_ylabel("created-to-sealed runtime (min, log)")
    ax.set_title("B · Analysis runtime and terminal failures")
    ax.grid(alpha=0.22)
    ax.legend(loc="upper right", ncol=2, fontsize=9)

    ax = axes[2]
    research_sorted = sorted(research, key=lambda row: row["created_at"])
    for index, run in enumerate(research_sorted, start=1):
        started = time(run["started_at"])
        sealed = time(run["sealed_at"])
        if not started or not sealed:
            continue
        color = "#cb181d" if run["state"] == "failed" else "#756bb1"
        ax.plot((started, sealed), (index, index), color=color, linewidth=5, solid_capstyle="butt")
    cancelled_after_enable = [
        time(row["scheduled_for"])
        for row in operations
        if row["kind"] == "scheduled_recording"
        and row["state"] == "cancelled"
        and time(row["scheduled_for"])
        and time(row["scheduled_for"]) >= CAPTURE_ENABLED
    ]
    ax.scatter(
        cancelled_after_enable,
        [0] * len(cancelled_after_enable),
        color="#cb181d",
        marker="|",
        s=130,
        label="coalesced after enable",
    )
    ax.set_ylabel("Research assignment (chronological)")
    ax.set_title("C · Research occupancy and post-enable coverage loss")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(START, END)
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("UTC on 2026-08-23")

    fig.suptitle(
        "Eight-hour production dwell/scanner operational evidence", fontsize=16, weight="bold"
    )
    fig.savefig(ROOT / "eight-hour-operational-cadence.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
