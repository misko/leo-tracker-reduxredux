"""Plot frozen partition membership and non-overlapping duration-window counts."""

import json
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
from matplotlib.figure import Figure


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "dataset/manifest.json").read_text())
    fig = Figure(figsize=(12, 6), layout="constrained")
    timeline, counts = fig.subplots(2, 1)
    labels = ("Training", "Retrospective validation")
    keys = ("training", "development_validation")
    for index, key in enumerate(keys):
        part = manifest["partitions"][key]
        single = part["duration_tiers"]["single_300s"]["windows"]
        times = [datetime.fromisoformat(row["start"].replace("Z", "+00:00")) for row in single]
        timeline.scatter(times, [index] * len(times), s=20, label=labels[index])
        tiers = part["duration_tiers"]
        tiers = [tiers[name] for name in ("single_300s", "about_1h", "about_3h", "about_8h")]
        counts.bar(
            [x + index * 0.35 for x in range(4)],
            [len(row["windows"]) for row in tiers],
            width=0.35,
            label=labels[index],
        )
    timeline.set_yticks([0, 1], labels)
    timeline.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
    timeline.set_xlabel("Capture start (UTC); each point is one recording")
    timeline.set_ylim(-0.5, 1.5)
    timeline.grid(axis="x", alpha=0.3)
    timeline.set_title(
        "Frozen development split · two-hour temporal embargo\n"
        "All plotted recordings were previously exposed; sealed test is unavailable"
    )
    counts.set_xticks(
        [x + 0.175 for x in range(4)],
        ["1 scan", "6 scans (~1 h)", "18 scans (~3 h)", "48 scans (~8 h)"],
    )
    counts.set_ylabel("Non-overlapping windows within each tier")
    counts.set_xlabel(
        "Elapsed durations vary; tiers reuse recordings and are not independent trials"
    )
    counts.legend()
    counts.grid(axis="y", alpha=0.3)
    fig.savefig(root / "dataset_split.png", dpi=160)


if __name__ == "__main__":
    main()
