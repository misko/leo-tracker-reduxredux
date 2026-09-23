"""Plot saved held-frame circular DD means; no new fit or phase alignment."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thresholds", nargs=2, type=float, default=[0.9, 0.8])
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    out = Path("reports/figures/2026_09_23_relaxed_adaptive_coherence")
    parts = sorted(out.glob("results-part-*.json"))
    cache = out / "all-dwell-pair-means.json"
    if parts:
        rows = [r for p in parts for r in json.loads(p.read_text())["rows"]]
        assert len(rows) == len({r["visit_index"] for r in rows}) == 301
        data = []
        for r in rows:
            for p in r["pairs"]:
                data.append(
                    dict(
                        visit=r["visit_index"],
                        time_s=r["time_s"] + 0.06,
                        channel=r["channel"],
                        arm=p["arm"],
                        anchors=p["anchors"],
                        R=p["weighted_R"],
                        phase_deg=float(np.degrees(p["phase_rad"])),
                        pilot_supported=p["both_sources_pilot_supported"],
                        held_pairs=p["count"],
                        failure=p["failure"],
                        wrong_time_R=p["wrong_time_control"]["weighted_R"],
                    )
                )
        cache.write_text(json.dumps(data, indent=2) + "\n")
    else:
        data = json.loads(cache.read_text())
    with (out / "all-dwell-pair-means.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)
    colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
    fig, axs = plt.subplots(
        2, 2, figsize=(15, 9), sharex=True, sharey=True, constrained_layout=True
    )
    counts = []
    for row, threshold in enumerate(args.thresholds):
        for arm in [0, 1]:
            ax = axs[row, arm]
            selected = [
                p
                for p in data
                if p["arm"] == arm
                and p["pilot_supported"]
                and not p["failure"]
                and p["R"] > threshold
            ]
            counts.append(
                dict(
                    arm=arm,
                    threshold=threshold,
                    pairs=len(selected),
                    dwells=len({p["visit"] for p in selected}),
                )
            )
            for channel, color in colors.items():
                points = [p for p in selected if p["channel"] == channel]
                ax.scatter(
                    [p["time_s"] for p in points],
                    [p["phase_deg"] for p in points],
                    c=color,
                    s=42,
                    alpha=0.8,
                    edgecolors="white",
                    linewidths=0.4,
                    label=f"Channel {channel} ({len(points)})",
                )
            ax.set_title(
                f"RX{arm}-anchored · R > {threshold:.1f} · "
                f"{len(selected)} pairs / {counts[-1]['dwells']} dwells"
            )
            ax.set(xlim=(0, 300), ylim=(-180, 180), yticks=[-180, -90, 0, 90, 180])
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8, loc="lower right")
    fig.suptitle(
        "Adaptive scan: mean two-source receiver-phase difference per dwell\n"
        "Held-frame weighted circular mean · both sources pilot-supported · "
        "before separate rate removal"
    )
    fig.supxlabel("Time since scan start (s; dwell midpoint)")
    fig.supylabel("Wrapped mean source B−A receiver-phase difference (degrees)")
    fig.savefig(out / f"dwell-mean-phase-300s{args.suffix}.png", dpi=170)
    (out / f"dwell-mean-phase-counts{args.suffix}.json").write_text(
        json.dumps(counts, indent=2) + "\n"
    )
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
