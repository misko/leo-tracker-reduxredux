"""Audit live pilot time anchors against exact public causal-cutoff inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
CACHES = (
    Path("/tmp/leo-long-training-cache-first16"),
    Path("/tmp/leo-long-training-cache-second8h"),
)
OFFSET_NS = 505_000_000_000


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    partitions = json.loads(MANIFEST.read_text())["partitions"]
    groups = (partitions["train"]["session_ids"][:6], partitions["train"]["session_ids"][72:78])
    session_ids = [session_id for group in groups for session_id in group]
    if len(session_ids) != 12 or len(set(session_ids)) != 12:
        raise ValueError("expected exactly two disjoint first-six TRAIN views")
    metadata = {row["session_id"]: row for row in json.loads(METADATA.read_text())["sessions"]}
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    rows = []
    try:
        for session_id, cache_root in zip(groups, CACHES, strict=True):
            for sid in session_id:
                source = store.load(sid)
                first_sample = int(source.timing.first_sample_estimate_utc_ns)
                cutoff = first_sample - OFFSET_NS
                meta = metadata[sid]
                receipt = json.loads((cache_root / sid / "cache_receipt.json").read_text())
                evidence = {row["track_id"]: row for row in receipt["prepared_evidence"]["tracks"]}
                tracks = []
                for recovered in meta["tracks"]:
                    track = evidence.get(recovered["track_id"])
                    if track is None:
                        continue
                    if recovered["observation_ids"] != track["observation_ids"]:
                        raise ValueError(
                            f"observation-ID order differs: {sid}/{recovered['track_id']}"
                        )
                    centers = np.asarray(recovered["support_center_utc_ns"], dtype=np.int64)
                    times = np.asarray(track["times_s"], dtype=float)
                    if len(centers) != len(times):
                        raise ValueError(f"support length differs: {sid}/{recovered['track_id']}")
                    anchor = int(centers[0]) - int(round(float(times[0]) * 1e9))
                    deviations = centers - (anchor + np.rint(times * 1e9).astype(np.int64))
                    tracks.append(
                        {
                            "track_id": recovered["track_id"],
                            "observation_id_count": len(recovered["observation_ids"]),
                            "derived_anchor_utc_ns": anchor,
                            "maximum_relative_time_deviation_ns": int(np.max(np.abs(deviations))),
                            "anchor_minus_first_sample_ns": anchor - first_sample,
                            "live_anchor_cutoff_minus_exact_cutoff_ns": anchor - first_sample,
                        }
                    )
                if not tracks:
                    raise ValueError(f"no receipt/metadata tracks joined: {sid}")
                rows.append(
                    {
                        "session_id": sid,
                        "first_sample_estimate_utc_ns": first_sample,
                        "exact_causal_cutoff_utc_ns": cutoff,
                        "metadata_snapshot_digest": meta["tle_snapshot_digest"],
                        "metadata_snapshot_collected_utc_ns": meta["tle_snapshot_collected_utc_ns"],
                        "snapshot_strictly_before_exact_cutoff": (
                            meta["tle_snapshot_collected_utc_ns"] < cutoff
                        ),
                        "tracks": tracks,
                    }
                )
    finally:
        store.close()
    result = {
        "schema": "leo.train-orbit-phase-cutoff-audit/v1",
        "read_only_public_input_store": True,
        "session_count": len(rows),
        "track_count": sum(len(row["tracks"]) for row in rows),
        "maximum_absolute_anchor_minus_first_sample_ns": max(
            abs(track["anchor_minus_first_sample_ns"]) for row in rows for track in row["tracks"]
        ),
        "maximum_relative_time_deviation_ns": max(
            track["maximum_relative_time_deviation_ns"] for row in rows for track in row["tracks"]
        ),
        "all_snapshots_strictly_causal": all(
            row["snapshot_strictly_before_exact_cutoff"] for row in rows
        ),
        "rows": rows,
        "bindings": {
            "tool": digest(Path(__file__)),
            "manifest": digest(MANIFEST),
            "strict_metadata": digest(METADATA),
            "strict_recovery_source": digest(
                ROOT
                / "reports/2026_09_23_train_receiver_orbit_diagnostic"
                / "recover_metadata_strict.py"
            ),
            "cache_receipts": [
                {
                    "session_id": sid,
                    "receipt": digest(cache / sid / "cache_receipt.json"),
                }
                for group, cache in zip(groups, CACHES, strict=True)
                for sid in group
            ],
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
