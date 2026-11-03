"""Plot final group-summed/Viterbi GLRT tracks against sealed orbit Doppler."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from group_summed_viterbi_backfill import OUTPUT_DIR, OUTPUT_PREFIX
from orbit_backfill_prototype import (
    SESSIONS,
    SOURCE_DIR,
    file_digest,
    load_archived_session,
    serializable,
)

FINAL_OUTPUT_PREFIX = "final-glrt-vs-orbit"
REQUIRED_MEMBERSHIP_FIELDS = {
    "scan_label",
    "catalog_number",
    "receiver",
    "group",
    "owner_state",
    "viterbi_row",
    "viterbi_changed",
}


def _parse_bool(value):
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"invalid boolean membership value {value!r}")


def read_membership_rows(path):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not REQUIRED_MEMBERSHIP_FIELDS.issubset(
            reader.fieldnames
        ):
            raise ValueError("final membership CSV is missing required fields")
        return list(reader)


def final_tracks(rows, arrays, scan_label):
    """Validate and organize the final Viterbi row choice for every track."""
    catalogs = np.asarray(arrays["catalog_numbers"], dtype=int)
    catalog_lookup = {int(number): column for column, number in enumerate(catalogs)}
    times = np.asarray(arrays["times_s"], dtype=float)
    groups = np.asarray(arrays["group"], dtype=int)
    receivers = np.asarray(arrays["receiver"], dtype=int)
    residuals = np.asarray(arrays["residual_hz"], dtype=float)
    grouped = defaultdict(list)
    for record in rows:
        if record["scan_label"] != scan_label:
            continue
        number = int(record["catalog_number"])
        receiver = int(record["receiver"])
        row = int(record["viterbi_row"])
        group = int(record["group"])
        if number not in catalog_lookup:
            raise ValueError(f"membership references absent NORAD {number}")
        if not 0 <= row < len(times):
            raise ValueError(f"membership row {row} is outside the archived GLRT rows")
        if groups[row] != group or receivers[row] != receiver:
            raise ValueError("membership row does not match its recorded group/receiver")
        if record["owner_state"] not in {"seed-owned", "unallocated"}:
            raise ValueError("membership has an unknown ownership state")
        grouped[(number, receiver)].append(
            {
                "row": row,
                "group": group,
                "seed_owned": record["owner_state"] == "seed-owned",
                "changed": _parse_bool(record["viterbi_changed"]),
            }
        )

    tracks = []
    claimed_rows = set()
    for (number, receiver), records in grouped.items():
        column = catalog_lookup[number]
        records.sort(key=lambda value: (times[value["row"]], value["group"]))
        selected = np.asarray([value["row"] for value in records], dtype=int)
        selected_groups = [value["group"] for value in records]
        if len(set(selected_groups)) != len(selected_groups):
            raise ValueError("final track selects a GLRT group more than once")
        overlap = claimed_rows.intersection(map(int, selected))
        if overlap:
            raise ValueError(f"final tracks collide on GLRT rows {sorted(overlap)}")
        claimed_rows.update(map(int, selected))
        values = residuals[selected, column]
        tracks.append(
            {
                "catalog_number": number,
                "receiver": receiver,
                "column": column,
                "rows": selected,
                "seed_owned": np.asarray(
                    [value["seed_owned"] for value in records], dtype=bool
                ),
                "changed": np.asarray(
                    [value["changed"] for value in records], dtype=bool
                ),
                "start_s": float(times[selected[0]]),
                "end_s": float(times[selected[-1]]),
                "duration_s": float(times[selected[-1]] - times[selected[0]]),
                "group_count": len(selected),
                "rms_residual_hz": math.sqrt(float(np.mean(values**2))),
            }
        )
    return sorted(tracks, key=lambda track: (track["start_s"], track["catalog_number"]))


def _plot_panel(figure, slot, arrays, track, scan_label):
    layout = slot.subgridspec(2, 1, height_ratios=(2.35, 1.0), hspace=0.08)
    doppler_axis = figure.add_subplot(layout[0])
    residual_axis = figure.add_subplot(layout[1], sharex=doppler_axis)
    column = track["column"]
    rows = track["rows"]
    times = np.asarray(arrays["times_s"], dtype=float)
    doppler = np.asarray(arrays["doppler_hz"], dtype=float)[:, column]
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    dense_times = np.asarray(arrays["dense_times_s"], dtype=float)
    dense = np.asarray(arrays["dense_doppler_hz"], dtype=float)[:, column]

    doppler_axis.plot(
        dense_times,
        np.asarray(arrays["unshifted_tle_doppler_hz"], dtype=float)[:, column] / 1000,
        color="0.62",
        linestyle=":",
        linewidth=0.9,
    )
    doppler_axis.plot(dense_times, dense / 1000, color="black", linewidth=1.2)
    residual_axis.plot(
        times[rows], residual[rows], color="0.55", linewidth=0.65, alpha=0.55, zorder=1
    )

    colors = {True: "#0072B2", False: "#E69F00"}
    markers = ("o", "s", "^", "D", "v", "P", "X")
    channels = np.asarray(arrays["channel"], dtype=int)
    for seed_owned in (True, False):
        for channel in np.unique(channels[rows]):
            mask = track["seed_owned"] == seed_owned
            mask &= channels[rows] == channel
            selected = rows[mask]
            if not len(selected):
                continue
            options = {
                "s": 14,
                "color": colors[seed_owned],
                "marker": markers[(int(channel) - 1) % len(markers)],
                "alpha": 0.88,
                "linewidths": 0,
                "zorder": 4,
            }
            doppler_axis.scatter(times[selected], doppler[selected] / 1000, **options)
            residual_axis.scatter(times[selected], residual[selected], **options)

    changed = rows[track["changed"]]
    if len(changed):
        options = {
            "s": 42,
            "facecolors": "none",
            "edgecolors": "#CC3311",
            "linewidths": 0.9,
            "zorder": 6,
        }
        doppler_axis.scatter(times[changed], doppler[changed] / 1000, **options)
        residual_axis.scatter(times[changed], residual[changed], **options)

    residual_axis.axhline(0, color="black", linewidth=0.65)
    for value, style, color in ((100, ":", "0.48"), (150, "--", "#CC79A7")):
        residual_axis.axhline(value, color=color, linestyle=style, linewidth=0.7)
        residual_axis.axhline(-value, color=color, linestyle=style, linewidth=0.7)
    padding = max(10_000.0, float(np.ptp(dense)) * 0.035)
    doppler_axis.set_ylim((float(np.min(dense)) - padding) / 1000, (float(np.max(dense)) + padding) / 1000)
    residual_axis.set_ylim(-180, 180)
    for axis in (doppler_axis, residual_axis):
        axis.set_xlim(0, 300)
        axis.grid(alpha=0.17)
    doppler_axis.set_title(
        f"Scan {scan_label} · NORAD {track['catalog_number']} · RX{track['receiver']} · "
        f"{track['group_count']} groups / {track['duration_s']:.1f} s · "
        f"RMS {track['rms_residual_hz']:.1f} Hz",
        fontsize=9,
    )
    doppler_axis.set_ylabel("Doppler (kHz)")
    residual_axis.set_ylabel("GLRT − orbit (Hz)")
    residual_axis.set_xlabel("Receive time since capture start (s)")
    doppler_axis.tick_params(labelbottom=False)


def render_scan(arrays, tracks, scan_label, output_stem):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    columns = 2
    rows = int(math.ceil(len(tracks) / columns))
    figure = plt.figure(figsize=(17, 3.55 * rows + 2.7))
    grid = figure.add_gridspec(
        rows,
        columns,
        left=0.065,
        right=0.985,
        bottom=0.065,
        top=0.925,
        hspace=0.46,
        wspace=0.19,
    )
    for index, track in enumerate(tracks):
        _plot_panel(figure, grid[index // columns, index % columns], arrays, track, scan_label)
    figure.suptitle(
        f"DS13 scan {scan_label} · final group-summed tracks with Viterbi peak selection\n"
        "Reference position; sealed profiled timing/RX/RF nuisance",
        y=0.988,
        fontsize=14,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="black", label="Timing-adjusted orbit Doppler"),
            Line2D([], [], color="0.62", linestyle=":", label="Pinned TLE"),
            Line2D([], [], marker="o", color="#0072B2", linestyle="", label="Seed-owned"),
            Line2D([], [], marker="o", color="#E69F00", linestyle="", label="Unallocated fill"),
            Line2D(
                [],
                [],
                marker="o",
                markerfacecolor="none",
                markeredgecolor="#CC3311",
                linestyle="",
                label="Viterbi peak changed",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=5,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.018,
        "Final membership: group-summed posterior ≥0.90, target runner-up ≤0.05, "
        "|residual| ≤150 Hz and gap ≤3 s. Viterbi changes peak identity only. "
        "Marker shape denotes calibrated channel; RMS is over one final peak per group.",
        ha="center",
        fontsize=7.5,
    )
    paths = [Path(output_stem).with_suffix(suffix) for suffix in (".png", ".svg")]
    for path in paths:
        figure.savefig(path, dpi=180)
    plt.close(figure)
    return paths


def render(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    membership_path = output_dir / f"{OUTPUT_PREFIX}-memberships.csv"
    source_backfill_receipt = output_dir / f"{OUTPUT_PREFIX}-receipt.json"
    receipt = json.loads(source_backfill_receipt.read_text())
    if receipt.get("schema") != "ds13-group-summed-viterbi-backfill/v1":
        raise ValueError("unexpected group-summed/Viterbi receipt schema")
    expected = receipt["outputs"].get(str(membership_path.resolve()))
    if expected is None or file_digest(membership_path) != expected:
        raise ValueError("final memberships do not match the backfill receipt")

    receipt_path = output_dir / f"{FINAL_OUTPUT_PREFIX}-receipt.json"
    planned = [receipt_path]
    for label in "ab":
        for suffix in (".png", ".svg"):
            planned.append(output_dir / f"{FINAL_OUTPUT_PREFIX}-scan-{label}{suffix}")
    existing = [path for path in planned if path.exists()]
    if existing:
        raise FileExistsError(", ".join(map(str, existing)))

    memberships = read_membership_rows(membership_path)
    outputs = []
    scan_records = []
    source_hashes = {
        str(membership_path.resolve()): file_digest(membership_path),
        str(source_backfill_receipt.resolve()): file_digest(source_backfill_receipt),
        str(Path(__file__).resolve()): file_digest(__file__),
    }
    for session, scan_label in zip(SESSIONS, "AB", strict=True):
        arrays, _, array_path, source_receipt = load_archived_session(session, source_dir)
        tracks = final_tracks(memberships, arrays, scan_label)
        if not tracks:
            raise ValueError(f"scan {scan_label} has no final tracks")
        paths = render_scan(
            arrays,
            tracks,
            scan_label,
            output_dir / f"{FINAL_OUTPUT_PREFIX}-scan-{scan_label.lower()}",
        )
        outputs.extend(paths)
        all_residuals = np.concatenate(
            [
                np.asarray(arrays["residual_hz"])[track["rows"], track["column"]]
                for track in tracks
            ]
        )
        scan_records.append(
            {
                "scan_label": scan_label,
                "session": session,
                "track_count": len(tracks),
                "group_count": int(sum(track["group_count"] for track in tracks)),
                "rms_residual_hz": math.sqrt(float(np.mean(all_residuals**2))),
                "tracks": [
                    {
                        key: value
                        for key, value in track.items()
                        if key
                        in {
                            "catalog_number",
                            "receiver",
                            "start_s",
                            "end_s",
                            "duration_s",
                            "group_count",
                            "rms_residual_hz",
                        }
                    }
                    for track in tracks
                ],
            }
        )
        source_hashes[str(array_path.resolve())] = file_digest(array_path)
        source_hashes[str(source_receipt.resolve())] = file_digest(source_receipt)
        arrays.close()

    output_receipt = {
        "schema": "ds13-final-glrt-vs-orbit/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "method": (
            "Plot the final Viterbi-selected row for each group-summed recovered membership "
            "against the sealed timing-adjusted orbit curve."
        ),
        "source_hashes": source_hashes,
        "scans": scan_records,
        "outputs": {str(path.resolve()): file_digest(path) for path in outputs},
    }
    receipt_path.write_text(
        json.dumps(serializable(output_receipt), indent=2, allow_nan=False) + "\n"
    )
    return outputs, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    outputs, receipt = render(args.output_dir, args.source_dir)
    print(json.dumps(serializable({"outputs": outputs, "receipt": receipt}), indent=2))


if __name__ == "__main__":
    main()
