"""Plot the longest tightly associated GLRT tracks against sealed orbit Doppler."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from plot_all_glrt_doppler_overlay import (
    DEFAULT_OUTPUT_DIR,
    SESSIONS,
    SOURCE_DIR,
    file_digest,
    load_archived_session,
    serializable,
)

POSTERIOR_MINIMUM = 0.90
RUNNER_UP_MAXIMUM = 0.05
RESIDUAL_MAXIMUM_HZ = 150.0
MAX_GAP_S = 3.0
WINDOW_PADDING_S = 5.0
MAIN_RESIDUAL_WINDOW_HZ = 2_000.0
RESIDUAL_DISPLAY_HZ = 400.0
SELECTED_CATALOGS = {
    SESSIONS[0]: (64361, 64013, 67889),
    SESSIONS[1]: (65686, 59199, 63926),
}
OUTPUT_PREFIX = "tight-track-glrt-vs-orbit"


def tight_association_mask(
    posterior,
    residual_hz,
    column,
    *,
    posterior_minimum=POSTERIOR_MINIMUM,
    runner_up_maximum=RUNNER_UP_MAXIMUM,
    residual_maximum_hz=RESIDUAL_MAXIMUM_HZ,
):
    posterior = np.asarray(posterior, dtype=float)
    residual_hz = np.asarray(residual_hz, dtype=float)
    if (
        posterior.ndim != 2
        or residual_hz.shape != posterior.shape
        or not 0 <= column < posterior.shape[1]
    ):
        raise ValueError("posterior and residual arrays must be aligned row/satellite matrices")
    competitors = np.delete(posterior, column, axis=1)
    runner_up = np.max(competitors, axis=1) if competitors.shape[1] else np.zeros(len(posterior))
    return (
        (posterior[:, column] >= posterior_minimum)
        & (runner_up <= runner_up_maximum)
        & (np.abs(residual_hz[:, column]) <= residual_maximum_hz)
    )


def contiguous_segments(times_s, receiver, mask, *, max_gap_s=MAX_GAP_S):
    times_s = np.asarray(times_s, dtype=float)
    receiver = np.asarray(receiver)
    mask = np.asarray(mask, dtype=bool)
    if (
        times_s.ndim != 1
        or receiver.shape != times_s.shape
        or mask.shape != times_s.shape
        or np.any(~np.isfinite(times_s))
        or max_gap_s <= 0
    ):
        raise ValueError("invalid aligned track segmentation inputs")
    segments = []
    for rx in np.unique(receiver):
        rows = np.flatnonzero(mask & (receiver == rx))
        rows = rows[np.argsort(times_s[rows], kind="stable")]
        cuts = np.flatnonzero(np.diff(times_s[rows]) > max_gap_s) + 1
        for segment in np.split(rows, cuts):
            if len(segment):
                segments.append((int(rx), segment))
    return segments


def longest_tight_track(arrays, column):
    mask = tight_association_mask(arrays["posterior"], arrays["residual_hz"], column)
    segments = contiguous_segments(arrays["times_s"], arrays["receiver"], mask)
    if not segments:
        raise ValueError("satellite has no tightly associated contiguous track")

    def ranking(item):
        _, rows = item
        duration = float(arrays["times_s"][rows[-1]] - arrays["times_s"][rows[0]])
        return duration, len(rows), -float(arrays["times_s"][rows[0]])

    receiver, rows = max(segments, key=ranking)
    groups = arrays["group"][rows]
    if len(np.unique(groups)) != len(groups):
        raise ValueError("tight track contains multiple peaks from the same GLRT group")
    residual = np.abs(arrays["residual_hz"][rows, column])
    posterior = arrays["posterior"][rows, column]
    competitors = np.delete(arrays["posterior"][rows], column, axis=1)
    runner_up = np.max(competitors, axis=1) if competitors.shape[1] else np.zeros(len(rows))
    return {
        "receiver": receiver,
        "rows": rows,
        "start_s": float(arrays["times_s"][rows[0]]),
        "end_s": float(arrays["times_s"][rows[-1]]),
        "duration_s": float(arrays["times_s"][rows[-1]] - arrays["times_s"][rows[0]]),
        "point_count": len(rows),
        "residual_median_hz": float(np.median(residual)),
        "residual_p95_hz": float(np.quantile(residual, 0.95)),
        "posterior_minimum": float(np.min(posterior)),
        "runner_up_maximum": float(np.max(runner_up)),
    }


def plot_track_panel(figure, slot, arrays, column, track, scan_label):
    layout = slot.subgridspec(2, 1, height_ratios=[2.5, 1.15], hspace=0.08)
    main = figure.add_subplot(layout[0])
    residual_axis = figure.add_subplot(layout[1], sharex=main)
    start = max(0.0, track["start_s"] - WINDOW_PADDING_S)
    end = min(300.0, track["end_s"] + WINDOW_PADDING_S)
    times = arrays["times_s"]
    window = (times >= start) & (times <= end)
    dense_times = arrays["dense_times_s"]
    dense_window = (dense_times >= start) & (dense_times <= end)
    curve = arrays["dense_doppler_hz"][dense_window, column]

    main.scatter(
        times[window],
        arrays["doppler_hz"][window, column] / 1000,
        s=4,
        color="0.65",
        alpha=0.16,
        linewidths=0,
        rasterized=True,
    )
    residual_axis.scatter(
        times[window],
        arrays["residual_hz"][window, column],
        s=4,
        color="0.65",
        alpha=0.16,
        linewidths=0,
        rasterized=True,
    )
    associated = window & arrays["accepted"][:, column]
    main.scatter(
        times[associated],
        arrays["doppler_hz"][associated, column] / 1000,
        s=10,
        color="0.35",
        alpha=0.48,
        linewidths=0,
    )
    residual_axis.scatter(
        times[associated],
        arrays["residual_hz"][associated, column],
        s=10,
        color="0.35",
        alpha=0.48,
        linewidths=0,
    )
    main.plot(
        dense_times[dense_window],
        arrays["unshifted_tle_doppler_hz"][dense_window, column] / 1000,
        color="0.6",
        linestyle=":",
        linewidth=1,
    )
    main.plot(
        dense_times[dense_window],
        curve / 1000,
        color="black",
        linewidth=1.4,
    )

    colors = {0: "#0072B2", 1: "#D55E00"}
    markers = ("o", "s", "^", "D", "v", "P", "X")
    selected_rows = track["rows"]
    for channel in np.unique(arrays["channel"][selected_rows]):
        rows = selected_rows[arrays["channel"][selected_rows] == channel]
        options = {
            "s": 22,
            "color": colors.get(track["receiver"], "#009E73"),
            "marker": markers[(int(channel) - 1) % len(markers)],
            "alpha": 0.86,
            "linewidths": 0,
            "zorder": 5,
        }
        main.scatter(times[rows], arrays["doppler_hz"][rows, column] / 1000, **options)
        residual_axis.scatter(times[rows], arrays["residual_hz"][rows, column], **options)

    residual_axis.axhline(0, color="black", linewidth=0.7)
    for limit, style, color in ((100, ":", "0.5"), (150, "--", "#CC79A7")):
        residual_axis.axhline(limit, color=color, linestyle=style, linewidth=0.8)
        residual_axis.axhline(-limit, color=color, linestyle=style, linewidth=0.8)
    main.set_xlim(start, end)
    main.set_ylim(
        (float(np.min(curve)) - MAIN_RESIDUAL_WINDOW_HZ) / 1000,
        (float(np.max(curve)) + MAIN_RESIDUAL_WINDOW_HZ) / 1000,
    )
    residual_axis.set_ylim(-RESIDUAL_DISPLAY_HZ, RESIDUAL_DISPLAY_HZ)
    number = int(arrays["catalog_numbers"][column])
    main.set_title(
        f"Scan {scan_label} · NORAD {number} · RX{track['receiver']} · "
        f"{track['duration_s']:.1f} s / {track['point_count']} groups · "
        f"residual p95 {track['residual_p95_hz']:.0f} Hz",
        fontsize=10,
    )
    main.set_ylabel("Orbit Doppler (kHz)")
    residual_axis.set_ylabel("GLRT − orbit (Hz)")
    residual_axis.set_xlabel("Receive time since capture start (s)")
    main.tick_params(labelbottom=False)
    for axis in (main, residual_axis):
        axis.grid(alpha=0.18)


def decorate(figure, scan_label):
    from matplotlib.lines import Line2D

    figure.suptitle(
        f"DS13 scan {scan_label} · longest tightly associated GLRT tracks\n"
        "Reference position; sealed profiled timing/RX/RF nuisance",
        y=0.995,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="black", label="Timing-adjusted orbit Doppler"),
            Line2D([], [], color="0.6", linestyle=":", label="Pinned TLE"),
            Line2D([], [], marker="o", color="0.65", linestyle="", label="Nearby GLRT"),
            Line2D([], [], marker="o", color="0.35", linestyle="", label="Posterior≥0.8"),
            Line2D([], [], marker="o", color="#0072B2", linestyle="", label="Selected RX0"),
            Line2D([], [], marker="o", color="#D55E00", linestyle="", label="Selected RX1"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=6,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.012,
        "Selection: satellite posterior ≥0.90, runner-up ≤0.05, |residual| ≤150 Hz; "
        "receiver-specific segments split at gaps >3 s; longest segment retained.\n"
        "All stored GLRT rows in each displayed time window are faint; rows beyond the "
        "±2 kHz Doppler and ±400 Hz residual display windows are clipped. No refitting.",
        ha="center",
        fontsize=8,
    )


def render_session(session, scan_label, output_dir=DEFAULT_OUTPUT_DIR, source_dir=SOURCE_DIR):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arrays, metadata, array_path, receipt_path = load_archived_session(session, source_dir)
    lookup = {int(number): column for column, number in enumerate(arrays["catalog_numbers"])}
    requested = SELECTED_CATALOGS[session]
    missing = [number for number in requested if number not in lookup]
    if missing:
        raise ValueError(f"selected track catalogues are missing: {missing}")
    tracks = [(lookup[number], longest_tight_track(arrays, lookup[number])) for number in requested]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"{OUTPUT_PREFIX}-scan-{scan_label.lower()}"
    outputs = [stem.with_suffix(extension) for extension in (".png", ".svg")]
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"tight-track outputs already exist: {', '.join(existing)}")
    figure = plt.figure(figsize=(14, 12.5))
    grid = figure.add_gridspec(
        len(tracks),
        1,
        left=0.08,
        right=0.98,
        bottom=0.09,
        top=0.90,
        hspace=0.43,
    )
    for row, (column, track) in enumerate(tracks):
        plot_track_panel(figure, grid[row], arrays, column, track, scan_label)
    decorate(figure, scan_label)
    for output in outputs:
        figure.savefig(output, dpi=170)
    plt.close(figure)

    result_tracks = []
    for column, track in tracks:
        result_tracks.append(
            {
                "catalog_number": int(arrays["catalog_numbers"][column]),
                **{key: value for key, value in track.items() if key != "rows"},
            }
        )
    result = {
        "session": session,
        "scan_label": scan_label,
        "source_profile": metadata["source_profile"],
        "source_hashes": {
            str(array_path.resolve()): file_digest(array_path),
            str(receipt_path.resolve()): file_digest(receipt_path),
        },
        "tracks": result_tracks,
        "outputs": {str(path.resolve()): file_digest(path) for path in outputs},
    }
    arrays.close()
    return result


def render(output_dir=DEFAULT_OUTPUT_DIR, source_dir=SOURCE_DIR):
    results = [
        render_session(session, "AB"[index], output_dir=output_dir, source_dir=source_dir)
        for index, session in enumerate(SESSIONS)
    ]
    receipt_path = Path(output_dir) / f"{OUTPUT_PREFIX}-receipt.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt = {
        "schema": "ds13-tight-track-glrt-orbit-plot/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "selection": {
            "posterior_minimum": POSTERIOR_MINIMUM,
            "runner_up_maximum": RUNNER_UP_MAXIMUM,
            "absolute_residual_maximum_hz": RESIDUAL_MAXIMUM_HZ,
            "maximum_contiguous_gap_s": MAX_GAP_S,
            "ranking": "duration, then group count, then earliest start",
        },
        "semantics": "Focused visualization of the six previously identified longest tight "
        "tracks. Orbit predictions and nuisance parameters are sealed; no refitting.",
        "scans": results,
    }
    receipt_path.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
    return results, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    results, receipt = render(output_dir=args.output_dir, source_dir=args.source_dir)
    print(json.dumps(serializable({"scans": results, "receipt": receipt}), indent=2))


if __name__ == "__main__":
    main()
