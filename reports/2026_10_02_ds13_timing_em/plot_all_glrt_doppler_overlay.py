"""Plot every stored GLRT row against each selected satellite Doppler curve."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SESSIONS = ("scan-fw-911c4e5db9243281", "scan-fw-ffa1cc19d8d7c09f")
SOURCE_DIR = ROOT / "tle-doppler-overlay"
DEFAULT_OUTPUT_DIR = ROOT / "pruned-position-profile-evaluation"
OUTPUT_PREFIX = "all-glrt-vs-satellite-curves"
REQUIRED_ARRAYS = {
    "times_s",
    "receiver",
    "channel",
    "catalog_numbers",
    "dense_times_s",
    "dense_doppler_hz",
    "unshifted_tle_doppler_hz",
    "posterior",
    "accepted",
    "doppler_hz",
    "residual_hz",
}


def serializable(value):
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_plot_arrays(arrays):
    missing = REQUIRED_ARRAYS.difference(arrays.files)
    if missing:
        raise ValueError(f"archived plot data is missing {sorted(missing)}")
    row_count = len(arrays["times_s"])
    satellite_count = len(arrays["catalog_numbers"])
    if row_count == 0 or satellite_count == 0:
        raise ValueError("archived plot data must contain rows and satellites")
    row_vectors = ("receiver", "channel")
    row_satellite_matrices = ("posterior", "accepted", "doppler_hz", "residual_hz")
    dense_matrices = ("dense_doppler_hz", "unshifted_tle_doppler_hz")
    if any(np.asarray(arrays[name]).shape != (row_count,) for name in row_vectors):
        raise ValueError("archived row vectors are not aligned")
    if any(
        np.asarray(arrays[name]).shape != (row_count, satellite_count)
        for name in row_satellite_matrices
    ):
        raise ValueError("archived row/satellite matrices are not aligned")
    dense_count = len(arrays["dense_times_s"])
    if any(
        np.asarray(arrays[name]).shape != (dense_count, satellite_count) for name in dense_matrices
    ):
        raise ValueError("archived dense curves are not aligned")
    numeric = (
        "times_s",
        "dense_times_s",
        "dense_doppler_hz",
        "unshifted_tle_doppler_hz",
        "doppler_hz",
        "residual_hz",
    )
    if any(np.any(~np.isfinite(arrays[name])) for name in numeric):
        raise ValueError("archived plot data contains non-finite display values")
    accepted = np.asarray(arrays["accepted"])
    if accepted.dtype != np.bool_:
        raise ValueError("archived accepted mask must be boolean")
    return row_count, satellite_count


def lane_masks(receiver, channel):
    """Partition every row exactly once by receiver and channel."""
    receiver = np.asarray(receiver)
    channel = np.asarray(channel)
    if receiver.ndim != 1 or channel.shape != receiver.shape or not len(receiver):
        raise ValueError("receiver and channel must be aligned nonempty vectors")
    masks = []
    for rx in np.unique(receiver):
        for lane in np.unique(channel):
            mask = (receiver == rx) & (channel == lane)
            if mask.any():
                masks.append((int(rx), int(lane), mask))
    coverage = np.sum([mask for _, _, mask in masks], axis=0)
    if not np.array_equal(coverage, np.ones(len(receiver), dtype=int)):
        raise ValueError("receiver/channel lanes do not partition all GLRT rows")
    return masks


def load_archived_session(session, source_dir=SOURCE_DIR):
    source_dir = Path(source_dir)
    receipt_path = source_dir / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != "ds13-tle-doppler-overlay/v1":
        raise ValueError("unexpected source overlay receipt schema")
    array_path = source_dir / f"{session}-plot-data.npz"
    expected = receipt["artifact_sha256"].get(str(array_path.resolve()))
    if expected is None or file_digest(array_path) != expected:
        raise ValueError("archived plot data does not match its sealed digest")
    metadata = [row for row in receipt["scans"] if row.get("session") == session]
    if len(metadata) != 1:
        raise ValueError("source receipt does not identify the requested session exactly once")
    arrays = np.load(array_path)
    validate_plot_arrays(arrays)
    if not np.array_equal(arrays["catalog_numbers"], metadata[0]["catalog_numbers"]):
        raise ValueError("source receipt catalogue mapping changed")
    return arrays, metadata[0], array_path, receipt_path


def satellite_panel(figure, slot, arrays, column, title):
    layout = slot.subgridspec(2, 1, height_ratios=[2.5, 1.2], hspace=0.10)
    main = figure.add_subplot(layout[0])
    residual_axis = figure.add_subplot(layout[1], sharex=main)
    dense_times = arrays["dense_times_s"]
    main.plot(
        dense_times,
        arrays["unshifted_tle_doppler_hz"][:, column] / 1000,
        color="0.65",
        linestyle=":",
        linewidth=1,
    )
    main.plot(
        dense_times,
        arrays["dense_doppler_hz"][:, column] / 1000,
        color="black",
        linewidth=1.15,
    )
    markers = ("o", "s", "^", "D", "v", "P", "X")
    colors = {0: "#0072B2", 1: "#D55E00"}
    lanes = lane_masks(arrays["receiver"], arrays["channel"])
    for receiver, channel, mask in lanes:
        options = {
            "s": 3,
            "color": colors.get(receiver, "0.35"),
            "marker": markers[(channel - 1) % len(markers)],
            "alpha": 0.12,
            "linewidths": 0,
            "rasterized": True,
        }
        main.scatter(arrays["times_s"][mask], arrays["doppler_hz"][mask, column] / 1000, **options)
        residual_axis.scatter(
            arrays["times_s"][mask], arrays["residual_hz"][mask, column], **options
        )
        associated = mask & arrays["accepted"][:, column]
        highlight = {
            **options,
            "s": 9,
            "alpha": 0.72,
            "rasterized": False,
        }
        main.scatter(
            arrays["times_s"][associated],
            arrays["doppler_hz"][associated, column] / 1000,
            **highlight,
        )
        residual_axis.scatter(
            arrays["times_s"][associated],
            arrays["residual_hz"][associated, column],
            **highlight,
        )
    residual_axis.axhline(0, color="black", linewidth=0.6)
    residual_axis.axhline(100, color="0.55", linestyle=":", linewidth=0.6)
    residual_axis.axhline(-100, color="0.55", linestyle=":", linewidth=0.6)
    residual_axis.set_yscale("symlog", linthresh=250, linscale=0.8)
    maximum = max(1000.0, float(np.max(np.abs(arrays["residual_hz"][:, column]))) * 1.04)
    residual_axis.set_ylim(-maximum, maximum)
    residual_axis.set_yticks(
        [-100_000, -1_000, 0, 1_000, 100_000],
        labels=["−100k", "−1k", "0", "1k", "100k"],
    )
    all_count = len(arrays["times_s"])
    associated_count = int(arrays["accepted"][:, column].sum())
    main.set_title(
        f"{title} · {all_count:,} total / {associated_count:,} posterior≥0.8",
        fontsize=10,
    )
    main.set_ylabel("Doppler (kHz)")
    residual_axis.set_ylabel("O−M (Hz, symlog)")
    residual_axis.set_xlabel("Receive time since capture start (s)")
    main.tick_params(labelbottom=False)
    for axis in (main, residual_axis):
        axis.set_xlim(0, 300)
        axis.grid(alpha=0.18)


def decorate(figure, title):
    from matplotlib.lines import Line2D

    figure.suptitle(
        title + "\nReference position; sealed profiled timing/RX/RF nuisance",
        y=0.995,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="black", label="Timing-adjusted TLE Doppler"),
            Line2D([], [], color="0.6", linestyle=":", label="Pinned TLE, zero timing shift"),
            Line2D(
                [],
                [],
                color="#0072B2",
                marker="o",
                linestyle="",
                alpha=0.35,
                label="All RX0 GLRT",
            ),
            Line2D(
                [],
                [],
                color="#D55E00",
                marker="o",
                linestyle="",
                alpha=0.35,
                label="All RX1 GLRT",
            ),
            Line2D(
                [],
                [],
                color="0.25",
                marker="o",
                linestyle="",
                label="Posterior≥0.8 overlay",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=5,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.012,
        "Every stored GLRT row is shown in every panel, lifted to the nearest alias of that "
        "satellite and colored by receiver; this reuse is nonexclusive, not an assignment.\n"
        "Larger points retain the original posterior≥0.8 association overlay. RX line + RF "
        "coefficient removed; scaled to 11.085 GHz; channel marker shapes differ.\n"
        "Residuals use the timing-adjusted curve and a symmetric-log axis (linear within "
        "±250 Hz); dotted guides are ±100 Hz. No new parameters fitted.",
        ha="center",
        fontsize=8,
    )


def render_session(session, scan_label, output_dir=DEFAULT_OUTPUT_DIR, source_dir=SOURCE_DIR):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arrays, metadata, array_path, receipt_path = load_archived_session(session, source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"{OUTPUT_PREFIX}-scan-{scan_label.lower()}"
    outputs = [stem.with_suffix(extension) for extension in (".png", ".svg")]
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"all-point overlay outputs already exist: {', '.join(existing)}")
    count = len(arrays["catalog_numbers"])
    rows = int(np.ceil(count / 2))
    figure = plt.figure(figsize=(15, 3.6 * rows + 2))
    grid = figure.add_gridspec(
        rows,
        2,
        left=0.07,
        right=0.98,
        bottom=0.085,
        top=0.92,
        hspace=0.48,
        wspace=0.22,
    )
    for column, number in enumerate(arrays["catalog_numbers"]):
        satellite_panel(
            figure,
            grid[column // 2, column % 2],
            arrays,
            column,
            f"Scan {scan_label} · NORAD {number}",
        )
    decorate(figure, f"DS13 scan {scan_label} · all GLRT rows vs {count} selected satellites")
    for output in outputs:
        figure.savefig(output, dpi=160)
    plt.close(figure)
    source_hashes = {
        str(array_path.resolve()): file_digest(array_path),
        str(receipt_path.resolve()): file_digest(receipt_path),
    }
    result = {
        "session": session,
        "scan_label": scan_label,
        "total_glrt_rows_per_satellite": len(arrays["times_s"]),
        "selected_satellite_count": count,
        "catalog_numbers": arrays["catalog_numbers"],
        "source_profile": metadata["source_profile"],
        "source_hashes": source_hashes,
        "outputs": {str(path.resolve()): file_digest(path) for path in outputs},
    }
    arrays.close()
    return result


def render(output_dir=DEFAULT_OUTPUT_DIR, source_dir=SOURCE_DIR, sessions=SESSIONS):
    labels = {session: "AB"[index] for index, session in enumerate(SESSIONS)}
    results = [
        render_session(session, labels[session], output_dir=output_dir, source_dir=source_dir)
        for session in sessions
    ]
    receipt_path = Path(output_dir) / f"{OUTPUT_PREFIX}-receipt.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt = {
        "schema": "ds13-all-glrt-doppler-overlay/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "semantics": "Every stored GLRT row is plotted nonexclusively against every selected "
        "satellite after nearest-alias lifting with the sealed reference-position nuisance fit. "
        "The stronger overlay retains the original posterior>=0.8 association. No refitting.",
        "scans": results,
    }
    receipt_path.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
    return results, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--session", choices=SESSIONS, action="append")
    args = parser.parse_args(argv)
    results, receipt = render(
        output_dir=args.output_dir,
        source_dir=args.source_dir,
        sessions=tuple(args.session or SESSIONS),
    )
    print(json.dumps(serializable({"scans": results, "receipt": receipt}), indent=2))


if __name__ == "__main__":
    main()
