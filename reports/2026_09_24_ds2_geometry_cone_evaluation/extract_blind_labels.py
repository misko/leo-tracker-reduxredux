#!/usr/bin/env python3
"""Bind each portable full-catalogue track to its recorded receiver path.

Run as ``leo``.  The join key is the immutable observation ID, never a
site-assisted candidate identity or a receiver coordinate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

SESSIONS = (
    "scan-fw-f3ce5fe73aa40506",
    "scan-fw-9f3d5067d149118e",
    "scan-fw-cfcf667726e80735",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    inputs = ScannerTrackingInputStore(args.bulk_root)
    try:
        scans = []
        for session_id in SESSIONS:
            trajectory = reconstruct_persistent_hop_trajectories(
                project_scanner_candidates(inputs.load(session_id)),
                config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
            )
            by_observation = {}
            by_tracklet = {item.tracklet_id: item for item in trajectory.tracklets}
            for hypothesis in trajectory.hypotheses:
                for tracklet_id in hypothesis.tracklet_ids:
                    graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
                    receiver = by_tracklet[tracklet_id].lane_key[2]
                    for row in graph.observations:
                        old = by_observation.setdefault(row.observation_id, receiver)
                        if old != receiver:
                            raise ValueError("observation receiver ambiguity")
            receipt = json.loads((args.cache_root / session_id / "cache_receipt.json").read_text())
            labels = []
            for track in receipt["prepared_evidence"]["tracks"]:
                values = {by_observation.get(identifier) for identifier in track["observation_ids"]}
                if None in values or len(values) != 1:
                    raise ValueError(f"incomplete receiver join: {session_id}/{track['track_id']}")
                labels.append({"track_id": track["track_id"], "receiver_id": values.pop()})
            scans.append({"session_id": session_id, "tracks": labels})
        print(
            json.dumps(
                {"schema": "ds2-portable-track-receiver-labels/v1", "sessions": scans},
                sort_keys=True,
            )
        )
    finally:
        inputs.close()


if __name__ == "__main__":
    main()
