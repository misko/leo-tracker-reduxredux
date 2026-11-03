"""Plot persisted independent-track offsets, changing only integer alias branches."""

import csv
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from investigate_sample import SESSION, save
from selection import ROOT

ALIAS_HZ = 1 / 4.4e-6


def align_alias(offset, center=92000.0):
    return center + (offset - center + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def main():
    directory = ROOT / "scans" / SESSION
    output = ROOT / f"investigation-{SESSION}"
    diagnostics = json.loads((output / "diagnostics.json").read_text())
    metadata = {
        row["track_index"]: row
        for row in diagnostics["diagnostics"]["track_independent"]["track_points"]
    }
    fitted = json.loads((directory / "fits.json").read_text())["models"]["track_independent"]
    rows = []
    for track in fitted["tracks"]:
        if not track["accepted"]:
            continue
        row = dict(metadata[track["track_index"]])
        row["persisted_offset_hz"] = track["offset_hz"]
        row["dealiased_offset_hz"] = float(align_alias(track["offset_hz"]))
        np.testing.assert_allclose(row["dealiased_offset_hz"], row["offset_hz"], atol=1e-6)
        rows.append(row)
    figure, axes = plt.subplots(
        2, 1, figsize=(14, 9), sharex=True, sharey=True, constrained_layout=True
    )
    colors = {1: "#0072b2", 2: "#d55e00", 3: "#009e73", 4: "#cc79a7"}
    for receiver, axis in enumerate(axes):
        lane = [row for row in rows if row["rx"] == receiver]
        for channel in sorted({row["channel"] for row in lane}):
            selected = [row for row in lane if row["channel"] == channel]
            centers = np.array([row["center_s"] for row in selected])
            offsets = np.array([row["dealiased_offset_hz"] for row in selected]) / 1000
            half_duration = np.array([row["duration_s"] / 2 for row in selected])
            axis.errorbar(
                centers,
                offsets,
                xerr=half_duration,
                fmt="o",
                markersize=5,
                color=colors.get(channel, "gray"),
                alpha=0.8,
                elinewidth=1.2,
                capsize=2,
                label=f"Channel {channel}",
            )
        for row in lane:
            if row["duration_s"] >= 30 or row["track_index"] in (15, 29):
                axis.annotate(
                    str(row["catalog_number"]),
                    (row["center_s"], row["dealiased_offset_hz"] / 1000),
                    xytext=(3, 6),
                    textcoords="offset points",
                    fontsize=8,
                )
        axis.set(
            title=f"RX{receiver} — {len(lane)} independent tracks",
            ylabel="Dealiased constant offset (kHz)",
            xlim=(0, 300),
        )
        axis.grid(alpha=0.25)
        axis.legend(loc="upper right", ncol=4, fontsize=9)
    axes[-1].set_xlabel("Time from scan start (s)")
    figure.suptitle(
        SESSION + " — independent-model constant offsets\n"
        "One point per track at its midpoint; bars show track duration, not uncertainty\n"
        "Common alias branch (period 227.273 kHz); labels are candidate NORAD IDs",
        fontsize=12,
    )
    save(figure, output, "05-independent-offsets-by-rx")
    with (output / "independent-offsets-by-rx.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(output / "05-independent-offsets-by-rx.png")


if __name__ == "__main__":
    main()
