"""Audit screened candidates at exact observation-center times with SGP4."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid


def validate(path):
    record = json.loads(path.read_text())
    screen = record.get("screen")
    if not screen or screen.get("presentation_version") == 2:
        return
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = next(s for s in archive.list_snapshots() if s.digest == screen["snapshot_digest"])
    catalogue = parse_element_sets(archive.read(snapshot))
    lookup = {n: i for i, n in enumerate(catalogue.satellite_numbers)}
    site = ObserverSiteV1.model_validate(screen["observer"])
    # Frozen source report renders UTC at microsecond precision; verify the
    # capture counter UTC directly below rather than round-tripping that text.
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        capture = store.inspect(record["session_id"])
        if capture.manifest_sha256 != screen["capture_digest"]:
            raise ValueError("capture changed since screen")
        start = capture.manifest.timing.first_sample_estimate_utc_ns
    finally:
        store.close()
    differences = []
    for track in screen["tracks"]:
        y = np.asarray(track["cfo_hz"])
        split = track["training_count"]
        for field, evidence in track["fields"].items():
            for item in evidence.get("top_training", []) + evidence.get("top_heldout", []):
                times = tuple(
                    start + round((t + int(field) + item["tau_s"]) * 1e9) for t in track["time_s"]
                )
                grid = SamplingGrid(times, len(times) // 2, float(np.median(np.diff(times))) / 1e9)
                observed = observe_grid(
                    propagate_grid(catalogue, grid, [lookup[item["catalog_number"]]]), site, grid
                )
                predicted = (
                    doppler_shift_hz(11_200_000_000.0, observed.range_rate_km_s[0])
                    + item["offset_hz"]
                )
                train = float(np.sqrt(np.mean((y[:split] - predicted[:split]) ** 2)))
                held = float(np.sqrt(np.mean((y[split:] - predicted[split:]) ** 2)))
                differences.extend(
                    [abs(train - item["training_rms_hz"]), abs(held - item["heldout_rms_hz"])]
                )
                item["exact_center_validation"] = {
                    "training_rms_hz": train,
                    "heldout_rms_hz": held,
                    "minimum_elevation_deg": float(np.min(observed.elevation_deg)),
                    "maximum_elevation_deg": float(np.max(observed.elevation_deg)),
                    "propagation_usable": bool(observed.usable[0]),
                }
        if track["fields"]["0"].get("top_training"):
            winner = track["fields"]["0"]["top_training"][0]
            if winner["exact_center_validation"]["minimum_elevation_deg"] < 0:
                track["reasons"].append("candidate-below-horizon-during-some-support")
    screen["exact_center_validation"] = {
        "maximum_rms_change_hz": max(differences, default=0),
        "offset_and_tau_refitted": False,
        "note": "Exact center-time propagation; not support integration or orbital truth.",
    }
    panels = sorted(screen["tracks"], key=lambda t: -t["span_s"])[:6]
    count = max(1, len(panels))
    fig, axes = plt.subplots(count, 2, figsize=(16, 3 * count), squeeze=False)
    if not panels:
        for ax in axes[0]:
            ax.text(
                0.5, 0.5, "No track met the 20 s / 20 observation eligibility rule", ha="center"
            )
            ax.set_axis_off()
    for axis, track in zip(axes[: len(panels)], panels, strict=True):
        t = np.asarray(track["time_s"])
        y = np.asarray(track["cfo_hz"])
        split = track["training_count"]
        axis[0].plot(t, y, ".", color="black", ms=3, label="Measured GLRT")
        for item in track["fields"]["0"].get("top_training", [])[:3]:
            times = tuple(start + round((float(ti) + item["tau_s"]) * 1e9) for ti in t)
            grid = SamplingGrid(times, len(times) // 2, 1.0)
            obs = observe_grid(
                propagate_grid(catalogue, grid, [lookup[item["catalog_number"]]]), site, grid
            )
            prediction = (
                doppler_shift_hz(11_200_000_000.0, obs.range_rate_km_s[0]) + item["offset_hz"]
            )
            label = f"NORAD {item['catalog_number']}"
            axis[0].plot(t, prediction, label=label, lw=1)
            axis[1].plot(t, y - prediction, ".-", label=label, ms=2, lw=0.7)
        for ax in axis:
            ax.axvline(t[split], color="gray", ls="--", label="Heldout begins")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7)
        axis[1].axhline(0, color="black", lw=0.5)
        axis[0].set_ylabel("CFO at 11.2 GHz (Hz)")
        axis[1].set_ylabel("Measured − predicted (Hz)")
        axis[0].set_title(f"CH{track['channel']} {track['edge']} · {track['span_s']:.1f} s")
        axis[1].set_title("Training-fitted offset and time shift; no heldout refit")
    for ax in axes[-1]:
        ax.set_xlabel("Seconds since recording start")
    fig.suptitle(record["session_id"] + " · catalogue candidates, no identity claim")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(path.with_suffix(".png"), dpi=120)
    plt.close(fig)
    screen["presentation_version"] = 2
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(
        record["session_id"], screen["exact_center_validation"]["maximum_rms_change_hz"], flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if Path("/mnt/qnap01") in args.output.resolve().parents or args.output.resolve() == Path(
        "/mnt/qnap01"
    ):
        parser.error("QNAP is read-only")
    for path in sorted(args.output.glob("scan-hop-*.json")):
        validate(path)
