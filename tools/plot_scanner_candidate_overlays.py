"""Render measured-CFO, TLE-candidate, and residual panels for every reviewed track."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.storage.adaptive_hop import AdaptiveHopIqStore

_RF_HZ = 11_200_000_000.0
_TRACKS_PER_PAGE = 6


def track_pages(tracks, page_size=_TRACKS_PER_PAGE):
    """Return deterministic chronological pages without dropping tracks."""
    if page_size < 1:
        raise ValueError("page size must be positive")
    ordered = sorted(
        tracks,
        key=lambda track: (
            track["time_s"][0],
            track["channel"],
            track["edge"],
            track["tracklet_id"],
        ),
    )
    return [ordered[offset : offset + page_size] for offset in range(0, len(ordered), page_size)]


def prediction(track, candidate, *, start_utc_ns, catalogue, lookup, site):
    times_s = np.asarray(track["time_s"], dtype=float)
    times = tuple(
        start_utc_ns + round((float(value) + candidate["tau_s"]) * 1e9) for value in times_s
    )
    grid = SamplingGrid(times, len(times) // 2, 1.0)
    observed = observe_grid(
        propagate_grid(catalogue, grid, [lookup[candidate["catalog_number"]]]),
        site,
        grid,
    )
    if not observed.usable[0]:
        raise ValueError(f"unusable shortlisted candidate {candidate['catalog_number']}")
    return doppler_shift_hz(_RF_HZ, observed.range_rate_km_s[0]) + candidate["offset_hz"]


def render_page(*, record, tracks, page_number, start, catalogue, lookup, site, destination):
    rows = len(tracks)
    fig, axes = plt.subplots(rows, 2, figsize=(16, 3 * rows), squeeze=False)
    for axis, track in zip(axes, tracks, strict=True):
        times = np.asarray(track["time_s"], dtype=float)
        measured = np.asarray(track["cfo_hz"], dtype=float)
        split = track["training_count"]
        axis[0].plot(times, measured, ".", color="black", ms=3, label="Measured GLRT")
        for candidate in track["fields"]["0"].get("top_training", [])[:3]:
            curve = prediction(
                track,
                candidate,
                start_utc_ns=start,
                catalogue=catalogue,
                lookup=lookup,
                site=site,
            )
            label = f"NORAD {candidate['catalog_number']}"
            axis[0].plot(times, curve, label=label, lw=1)
            axis[1].plot(times, measured - curve, ".-", label=label, ms=2, lw=0.7)
        for ax in axis:
            ax.axvline(times[split], color="gray", ls="--", label="Heldout begins")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7)
        axis[1].axhline(0, color="black", lw=0.5)
        axis[0].set_ylabel("CFO at 11.2 GHz (Hz)")
        axis[1].set_ylabel("Measured − predicted (Hz)")
        axis[0].set_title(
            f"CH{track['channel']} {track['edge']} · "
            f"{times[0]:.1f}–{times[-1]:.1f} s · {track['span_s']:.1f} s span"
        )
        axis[1].set_title("Training-fitted offset and time shift; no heldout refit")
    for ax in axes[-1]:
        ax.set_xlabel("Seconds since recording start")
    fig.suptitle(
        f"{record['session_id']} · all-track catalogue candidates · page {page_number}\n"
        "Top 3 training-ranked candidates per track · no identity claim"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    filename = f"{record['session_id']}-{page_number:02d}.png"
    fig.savefig(destination / filename, dpi=120)
    plt.close(fig)
    return filename


def render(root, *, capture_root=Path("/srv/bulk/leo"), tle_root=Path("/var/lib/leo/tle")):
    destination = root / "all-track-overlays"
    destination.mkdir(exist_ok=True)
    archive = TleArchiveReader(tle_root)
    snapshots = {snapshot.digest: snapshot for snapshot in archive.list_snapshots()}
    captures = AdaptiveHopIqStore(capture_root, read_only=True)
    records = sorted(
        (
            json.loads(gzip.decompress(path.read_bytes()))
            for path in root.glob("scan-hop-*.json.gz")
        ),
        key=lambda record: record["capture_start_utc"],
    )
    inventory = []
    index_rows = []
    try:
        for record in records:
            screen = record["screen"]
            capture = captures.inspect(record["session_id"])
            if capture.manifest_sha256 != screen["capture_digest"]:
                raise ValueError("capture changed since screen: " + record["session_id"])
            snapshot = snapshots[screen["snapshot_digest"]]
            catalogue = parse_element_sets(archive.read(snapshot))
            lookup = {number: i for i, number in enumerate(catalogue.satellite_numbers)}
            site = ObserverSiteV1.model_validate(screen["observer"])
            start = capture.manifest.timing.first_sample_estimate_utc_ns
            pages = []
            for number, tracks in enumerate(track_pages(screen["tracks"]), 1):
                filename = render_page(
                    record=record,
                    tracks=tracks,
                    page_number=number,
                    start=start,
                    catalogue=catalogue,
                    lookup=lookup,
                    site=site,
                    destination=destination,
                )
                pages.append((filename, tracks))
                inventory.append(
                    {
                        "file": filename,
                        "session_id": record["session_id"],
                        "tracklet_ids": [track["tracklet_id"] for track in tracks],
                    }
                )
            sid = record["session_id"]
            page_path = root / f"{sid}-all-tracks.md"
            page_path.write_text(
                f"# All track overlays: {sid}\n\n"
                f"Recorded **{record['capture_start_utc']}**, RX0, 10 MS/s. "
                f"All **{len(screen['tracks'])} eligible tracks** are shown in "
                "chronological order.\n\n"
                f"[Recording assessment]({sid}.md) · "
                f"[Candidate RMS and gains]({sid}-candidates.md)\n\n"
                "Each row matches the requested view: measured GLRT CFO and the top three "
                "training-ranked TLE curves on the left, residuals on the right. Offset and "
                "time shift are fitted only on the first 60%; the last 40% is held out. "
                "These are candidate diagnostics, not satellite identifications.\n\n"
                + "\n\n".join(
                    f"## Page {page}\n\n![All-track TLE overlays, page {page}]"
                    f"(all-track-overlays/{filename})"
                    for page, (filename, _) in enumerate(pages, 1)
                )
                + "\n"
            )
            index_rows.append(
                f"| {record['capture_start_utc']} | [{sid}](../{sid}-all-tracks.md) | "
                f"{len(screen['tracks'])} | {len(pages)} |"
            )
    finally:
        captures.close()
    (destination / "manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
    (destination / "README.md").write_text(
        "# All-track measured CFO and TLE overlays\n\n"
        "Every eligible track in every reviewed RX0 10 MS/s scanner session. Figures contain "
        "up to six track rows each, with measured/TLE overlays and held-out residuals.\n\n"
        "| UTC recording start | Session figures | Tracks | Pages |\n"
        "|---|---|---:|---:|\n" + "\n".join(index_rows) + "\n"
    )
    print(
        f"Rendered {len(inventory)} PNGs for "
        f"{sum(len(item['tracklet_ids']) for item in inventory)} tracks in {len(records)} sessions"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root == Path("/mnt/qnap01") or Path("/mnt/qnap01") in root.parents:
        parser.error("QNAP is read-only")
    render(root)
