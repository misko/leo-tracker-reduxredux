#!/usr/bin/env python3
"""Adapt sealed RF-only track shards to the regional Doppler replay contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from leo.operations.tle_archive import TleArchiveReader


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _create(path: Path, value) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(path)
        return
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(shard_paths, output: Path, archive: TleArchiveReader):
    snapshots = {
        (item.digest, item.collected_utc_ns): item for item in archive.list_snapshots()
    }
    scans = []
    for shard_path in sorted(shard_paths):
        raw = shard_path.read_bytes()
        shard = json.loads(raw)
        session_id = shard["session"]["session_id"]
        reference_ns = int(shard["session"]["capture_start_utc_ns"])
        snapshot_ref = shard["catalogue_snapshot"]
        snapshot = snapshots.get((snapshot_ref["digest"], snapshot_ref["collected_utc_ns"]))
        if snapshot is None:
            raise ValueError("exported causal TLE snapshot is unavailable or changed")
        tle = archive.read(snapshot).encode()
        tle_name = snapshot.digest.removeprefix("sha256:") + ".tle"
        tle_path = output / "evidence" / tle_name
        tle_path.parent.mkdir(parents=True, exist_ok=True)
        if tle_path.exists() and tle_path.read_bytes() != tle:
            raise FileExistsError(tle_path)
        if not tle_path.exists():
            tle_path.write_bytes(tle)
        series, episodes = [], []
        for track in shard["tracks"]:
            rows = track["observations"]
            series.append(
                {
                    "tracklet_id": track["tracklet_id"],
                    "channel": track["lane"]["channel"],
                    "receiver_id": track["lane"]["receiver_id"],
                    "actual_rf_hz": track["lane"]["actual_rf_hz"],
                    "candidate_ids": [row["observation_id"] for row in rows],
                    "paired_visit_ids": [row["source_group_id"] for row in rows],
                    "t_s": [
                        (row["support_center_utc_ns"] - reference_ns) / 1e9 for row in rows
                    ],
                    "y_hz": [row["measured_cfo_hz"] for row in rows],
                }
            )
            episodes.append(
                {
                    "episode_id": track["tracklet_id"],
                    "members": [track["tracklet_id"]],
                    "channel": track["lane"]["channel"],
                }
            )
        inventory = {
            "session_id": session_id,
            "reference_utc_ns": reference_ns,
            "tle_collected_ns": snapshot.collected_utc_ns,
            "tle_file": tle_name,
            "tle_digest": _digest_bytes(tle),
            "source_shard_digest": _digest_bytes(raw),
            "partition": "chronological",
            "fixed_candidates": {},
            "known_position_used": False,
        }
        _create(
            output / "evidence" / f"{session_id}.json",
            {"inventory": inventory, "series": series, "episodes": episodes},
        )
        scans.append(
            {
                "session_id": session_id,
                "reference_utc_ns": reference_ns,
                "included": True,
                "track_count": len(series),
                "observation_count": sum(len(row["t_s"]) for row in series),
            }
        )
    inventory = {
        "schema": "recent-regional-rf-inventory-v1",
        "scans": sorted(scans, key=lambda row: row["reference_utc_ns"]),
        "prior_matched_norads_used": False,
        "known_position_used": False,
        "receiver_copy_policy": "separate-track-arcs; paired visit IDs retained for diagnostics",
    }
    _create(output / "inventory.json", inventory)
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", action="append", required=True)
    args = parser.parse_args()
    paths = [args.shards / f"{session_id}.json" for session_id in args.session]
    print(json.dumps(prepare(paths, args.output, TleArchiveReader(args.tle_root)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
