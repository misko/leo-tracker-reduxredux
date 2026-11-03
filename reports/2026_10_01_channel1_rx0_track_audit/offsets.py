import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent


def main(fold_alias=False):
    document = json.loads((ROOT / "offset-source.json").read_text())
    output = ROOT / "alias-folded" if fold_alias else ROOT
    output.mkdir(exist_ok=True)
    product = document["product"]
    tracks = {track["tracklet_id"]: track for track in product["tracklets"]}
    rows = []
    for review in product["track_reviews"]:
        candidate = min(review["candidates"], key=lambda item: item["rank"])
        track = tracks[review["tracklet_id"]]
        rows.append(
            dict(
                tracklet_id=review["tracklet_id"],
                channel=review["channel"],
                receiver_id=track["receiver_id"],
                start_s=review["start_s"],
                end_s=review["end_s"],
                catalog_number=candidate["catalog_number"],
                offset_hz=candidate["fitted_offset_hz"],
                evaluation_rms_hz=candidate["randomized_evaluation_rms_hz"],
                selected_tau_s=candidate["selected_tau_s"],
            )
        )
    rows.sort(key=lambda row: row["start_s"])
    for row in rows:
        spacing = (1 / 4.4e-6) * 11_200_000_000 / tracks[row["tracklet_id"]]["actual_rf_hz"]
        raw_offset = row["offset_hz"]
        branch = int(np.floor(raw_offset / spacing + 0.5)) if fold_alias else 0
        row.update(raw_offset_hz=raw_offset, alias_spacing_hz=spacing, removed_alias_branch=branch)
        row["offset_hz"] = raw_offset - branch * spacing
        assert np.isclose(row["offset_hz"] + branch * spacing, raw_offset)
        if fold_alias:
            assert -spacing / 2 <= row["offset_hz"] < spacing / 2
    assert len(rows) == product["review_count"]
    assert len({row["tracklet_id"] for row in rows}) == len(rows)
    assert all(row["start_s"] <= row["end_s"] for row in rows)
    assert all(np.isfinite(row["offset_hz"]) for row in rows)
    with (output / "constant-offsets.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    satellites = sorted({row["catalog_number"] for row in rows})
    palette = list(plt.get_cmap("tab20").colors) + list(plt.get_cmap("Set2").colors)
    if len(satellites) > len(palette):
        palette = plt.get_cmap("hsv")(np.linspace(0, 1, len(satellites), endpoint=False))
    colors = dict(zip(satellites, palette, strict=False))
    figure = plt.figure(figsize=(17, 11))
    grid = figure.add_gridspec(2, 2, width_ratios=[4, 1], hspace=0.36, wspace=0.08)
    overview = figure.add_subplot(grid[0, 0])
    histogram = figure.add_subplot(grid[0, 1], sharey=overview)
    detail = figure.add_subplot(grid[1, :])
    for row in rows:
        midpoint = (row["start_s"] + row["end_s"]) / 2
        offset = row["offset_hz"] / 1000
        color = colors[row["catalog_number"]]
        overview.hlines(offset, row["start_s"], row["end_s"], color=color, alpha=0.8)
        overview.plot(midpoint, offset, "o", color=color, markersize=4)
        if row["channel"] == 1 and row["receiver_id"] == 0:
            detail.hlines(offset, row["start_s"], row["end_s"], color=color, linewidth=4)
            detail.plot(midpoint, offset, "o", color=color)
            detail.annotate(
                f"{row['catalog_number']}\n{offset:.2f} kHz",
                (midpoint, offset),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
    histogram.hist(
        [row["offset_hz"] / 1000 for row in rows],
        bins=24,
        orientation="horizontal",
        color="#64748b",
    )
    histogram.set_xlabel("Track count")
    histogram.tick_params(labelleft=False)
    overview.set_title(f"All {len(rows)} reviewed tracks: rank-1 candidate per track")
    detail.set_title("Channel 1 / RX0 — same candidate can have different fragment offsets")
    for axis in (overview, detail):
        axis.set_xlabel("Time within scan (s; persisted review time basis)")
        axis.set_ylabel("Fitted constant frequency offset (kHz)")
        axis.set_xlim(0, 305)
        axis.grid(alpha=0.2)
        axis.margins(y=0.15)
    handles = [
        Line2D([0], [0], color=colors[satellite], marker="o", label=str(satellite))
        for satellite in satellites
    ]
    figure.legend(handles=handles, loc="lower center", ncol=9, title="Candidate catalogue number")
    label = "Alias-folded offsets (absolute branch unresolved)" if fold_alias else "Fitted offsets"
    figure.suptitle(f"{document['session_id']}: {label}", fontsize=15)
    figure.text(
        0.5,
        0.933,
        "Horizontal bars = track duration, not uncertainty. One fit per track; no interpolation. "
        "Candidate matches only — identities are not confirmed.",
        ha="center",
        fontsize=10,
    )
    figure.subplots_adjust(top=0.88, bottom=0.19)
    figure.savefig(output / "constant-offsets-vs-time.png", dpi=170)
    figure.savefig(output / "constant-offsets-vs-time.svg")
    midpoint_figure, axes = plt.subplots(3, 1, figsize=(12, 11), sharex=True, sharey=True)
    receiver_colors = {0: "#2563eb", 1: "#ea580c"}
    channel_markers = {1: "o", 2: "s", 3: "^", 4: "D"}
    for row in rows:
        receiver = row["receiver_id"]
        for axis in (axes[0], axes[receiver + 1]):
            axis.scatter(
                (row["start_s"] + row["end_s"]) / 2,
                row["offset_hz"] / 1000,
                color=receiver_colors[receiver],
                marker=channel_markers[row["channel"]],
                s=55,
                alpha=0.8,
                edgecolors="white",
                linewidths=0.5,
            )
    receiver_titles = [
        f"RX{receiver} — {sum(row['receiver_id'] == receiver for row in rows)} tracks"
        for receiver in receiver_colors
    ]
    for axis, title in zip(axes, ["Both receivers", *receiver_titles], strict=True):
        axis.set_title(title, loc="left")
        axis.set_ylabel("Constant offset (kHz)")
        axis.set_xlim(0, 300)
        axis.set_xticks(np.arange(0, 301, 25))
        axis.grid(alpha=0.2)
        axis.set_axisbelow(True)
    axes[-1].set_xlabel("Track midpoint within scan (s)")
    midpoint_handles = [
        Line2D([], [], linestyle="none", marker="o", color=color, label=f"RX{receiver}")
        for receiver, color in receiver_colors.items()
    ] + [
        Line2D([], [], linestyle="none", marker=marker, color="#555555", label=f"CH{channel}")
        for channel, marker in channel_markers.items()
    ]
    midpoint_figure.legend(handles=midpoint_handles, loc="lower center", ncol=6)
    midpoint_figure.suptitle(
        f"{document['session_id']} — {label}\n"
        f"One point per track, rank-1 candidate; all {len(rows)} reviews, not strong-only",
        fontsize=14,
    )
    midpoint_figure.tight_layout(rect=(0, 0.045, 1, 0.94))
    midpoint_figure.savefig(output / "constant-offset-midpoints-by-rx.png", dpi=160)
    midpoint_figure.savefig(output / "constant-offset-midpoints-by-rx.svg")
    print(json.dumps({"tracks": len(rows), "candidate_satellites": len(satellites)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT)
    parser.add_argument("--fold-alias", action="store_true")
    arguments = parser.parse_args()
    ROOT = arguments.directory
    main(fold_alias=arguments.fold_alias)
