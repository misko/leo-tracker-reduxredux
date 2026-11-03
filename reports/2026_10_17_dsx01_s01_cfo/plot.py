"""Plot frozen DSX01 S01 winning GLRT CFO measurements without model edits."""

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "2026_10_16_dsx01_fast_association_losses"
COLORS = {1: "#0072B2", 2: "#D55E00"}


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    hashes = {}
    for name in ("context-observations.jsonl", "sources.json"):
        digest = "sha256:" + hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        expected = next(f["sha256"] for f in manifest["files"] if f["path"] == name)
        assert digest == expected, f"Frozen input changed: {name}"
        hashes[name] = digest
    source = next(s for s in json.loads((DATA / "sources.json").read_text())
                  if s["source_id"] == "S01")
    with (DATA / "context-observations.jsonl").open() as stream:
        rows = [r for line in stream if (r := json.loads(line))["source_id"] == "S01"]
    rows.sort(key=lambda r: (r["time_s"], r["receiver"], r["channel"]))
    assert len(rows) == source["observation_count"] == 4797
    assert len({r["observation_id"] for r in rows}) == len(rows)
    assert {r["channel"] for r in rows} == set(range(1, 9))
    assert {r["receiver"] for r in rows} == {1, 2}
    assert all(math.isfinite(r[k]) for r in rows for k in ("time_s", "measured_cfo_hz"))

    fields = ["observation_id", "time_s", "receiver", "channel", "actual_rf_hz",
              "measured_cfo_hz", "original_associated"]
    with (ROOT / "s01-glrt-cfo.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold"})
    handles = [Line2D([], [], color=COLORS[rx], marker="o", linestyle="",
                      markersize=6, label=f"RX{rx}") for rx in (1, 2)]
    low = math.floor(min(r["measured_cfo_hz"] for r in rows) / 100000) * 100
    high = math.ceil(max(r["measured_cfo_hz"] for r in rows) / 100000) * 100
    counts = []
    for split in (False, True):
        fig, axes = plt.subplots(8 if split else 4, 2, figsize=(16, 24 if split else 14),
                                 sharex=True, sharey=True)
        plotted = 0
        for channel in range(1, 9):
            group = [r for r in rows if r["channel"] == channel]
            rf = sorted({r["actual_rf_hz"] for r in group})
            assert len(rf) == 1
            count = Counter(r["receiver"] for r in group)
            if not split:
                counts.append({"channel": channel, "actual_rf_hz": rf[0],
                               "rx1_count": count[1], "rx2_count": count[2]})
            for rx in (1, 2):
                ax = axes[channel - 1, rx - 1] if split else axes.flat[channel - 1]
                subset = [r for r in group if r["receiver"] == rx]
                ax.scatter([r["time_s"] for r in subset],
                           [r["measured_cfo_hz"] / 1000 for r in subset],
                           s=9, color=COLORS[rx], alpha=0.65, linewidths=0,
                           rasterized=True)
                plotted += len(subset)
                suffix = f"RX{rx}: {count[rx]} points" if split else (
                    f"RX1: {count[1]}  |  RX2: {count[2]}")
                ax.set_title(f"CH{channel}  ·  {rf[0] / 1e9:.5f} GHz  ·  {suffix}",
                             fontsize=10, loc="left")
                ax.set_xlim(0, 300)
                ax.set_ylim(low, high)
                ax.set_xticks(range(0, 301, 50))
                ax.grid(alpha=0.2)
                ax.set_axisbelow(True)
        assert plotted == len(rows)
        fig.suptitle("DSX01 · S01 · GLRT CFO versus time\n"
                     + source["recording_id"], fontsize=17, y=0.988)
        fig.legend(handles=handles, loc="upper center", ncol=2,
                   bbox_to_anchor=(0.5, 0.951 if split else 0.934), frameon=False)
        fig.supxlabel("Time since recording first-sample estimate (s)", y=0.035)
        fig.supylabel("Measured GLRT CFO (kHz)", x=0.015)
        fig.text(0.5, 0.012, "All 4,797 original winning observations; associated and unassociated. "
                 "No calibration, alias unwrapping, orbit fit, or track linking applied.",
                 ha="center", fontsize=10)
        fig.subplots_adjust(left=0.065, right=0.985, bottom=0.075 if not split else 0.06,
                            top=0.90 if not split else 0.93, hspace=0.28, wspace=0.08)
        stem = "s01-glrt-cfo-by-receiver" if split else "s01-glrt-cfo-all-channels"
        for extension in ("png", "pdf"):
            fig.savefig(ROOT / f"{stem}.{extension}", dpi=170)
        plt.close(fig)

    summary = {"source_id": "S01", "recording_id": source["recording_id"],
               "first_sample_estimate_utc": source["first_sample_estimate_utc"],
               "input_sha256": hashes, "observation_count": len(rows),
               "time_range_s": [min(r["time_s"] for r in rows), max(r["time_s"] for r in rows)],
               "measured_cfo_range_hz": [min(r["measured_cfo_hz"] for r in rows),
                                         max(r["measured_cfo_hz"] for r in rows)],
               "channels": counts,
               "selection": "Every frozen S01 winning observation, both receivers; no filtering or fitting",
               "validation": "Frozen input hashes, unique IDs, source count, finite coordinates, all eight channels, "
                             "both receivers, and plotted point counts checked"}
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
