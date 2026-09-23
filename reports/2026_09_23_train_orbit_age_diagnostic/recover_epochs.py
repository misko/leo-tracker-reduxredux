#!/usr/bin/env python3
"""Read exact candidate epochs from digest-bound public TLE snapshots."""

import hashlib
import json
from pathlib import Path

import numpy as np

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
PAIRS = ROOT / "reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.json"
FIRST = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json"
SECOND = ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
OUTPUT = Path("/tmp/leo-train-orbit-epochs.json")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inference = json.loads(PAIRS.read_text())
    metadata = json.loads(METADATA.read_text())["sessions"]
    if len(metadata) != 151 or len({row["session_id"] for row in metadata}) != 151:
        raise ValueError("strict metadata is not exactly 151 unique TRAIN sessions")
    by_session = {row["session_id"]: row for row in metadata}
    parents = [json.loads(FIRST.read_text()), json.loads(SECOND.read_text())]
    parent_arms = [
        next(
            row
            for row in parents[0]["arms"]
            if row["prior"] == "sacramento" and row["scale_s"] == 5.0
        ),
        next(
            row
            for row in parents[1]["arms"]
            if row["prior"] == "sacramento"
            and row["scale_s"] == 5.0
            and row["model"] == "scan"
            and row["view_scan_count"] == 79
        ),
    ]
    required = sorted(
        (row["session_id"], row["track_id"], row["candidate_id"])
        for arm in parent_arms
        for row in arm["fixed_tracks"]
    )
    if len(required) != inference["support"]["fixed_track_count"]:
        raise ValueError("fixed parent track count differs from sealed paired support")
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = {(item.digest, item.collected_utc_ns): item for item in reader.list_snapshots()}
    parsed = {}
    rows = []
    for session_id, track_id, candidate_id in required:
        meta = by_session[session_id]
        snapshot_digest = meta["tle_snapshot_digest"]
        snapshot = snapshots.get((snapshot_digest, meta["tle_snapshot_collected_utc_ns"]))
        if snapshot is None:
            raise ValueError(f"bound snapshot unavailable: {session_id} {snapshot_digest}")
        snapshot_key = (snapshot_digest, snapshot.collected_utc_ns)
        if snapshot_key not in parsed:
            catalogue = parse_element_sets(reader.read(snapshot))
            numbers = np.asarray(catalogue.satellite_numbers, dtype=np.int64)
            epochs = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)
            if len(numbers) != len(set(numbers.tolist())):
                raise ValueError(f"duplicate catalogue number in {snapshot_digest}")
            parsed[snapshot_key] = dict(zip(numbers.tolist(), epochs.tolist(), strict=True))
        number = int(candidate_id)
        if number not in parsed[snapshot_key]:
            raise ValueError(f"candidate absent: {session_id} {candidate_id}")
        rows.append(
            {
                "session_id": session_id,
                "track_id": track_id,
                "candidate_id": candidate_id,
                "snapshot_digest": snapshot_digest,
                "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
                "element_epoch_utc_ns": parsed[snapshot_key][number],
            }
        )
    output = {
        "schema": "train-orbit-epochs/v1",
        "train_session_count": len(metadata),
        "fixed_track_count": len(required),
        "rows": rows,
        "bindings": {
            "paired_inference": digest(PAIRS),
            "strict_metadata": digest(METADATA),
            "fixed_track_parents": [digest(FIRST), digest(SECOND)],
        },
    }
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
