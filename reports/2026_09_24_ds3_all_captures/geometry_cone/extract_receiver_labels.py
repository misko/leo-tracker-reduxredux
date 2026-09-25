#!/usr/bin/env python3
"""Bind DS3 geometry-cache tracks to RX0/RX1 using observation IDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

SPLIT_ANALYSIS_SESSIONS = {
    "scan-fw-294be7850b76a34d",
    "scan-fw-ff02a0ba4200d0dc",
}


def load_plan(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text())
    if value.get("schema") != "ds3-lt3d-geometry-cone-plan/v1":
        raise ValueError("unexpected geometry plan schema")
    sessions = tuple(map(str, value.get("eligible_session_ids", [])))
    if len(sessions) != 5 or len(set(sessions)) != 5:
        raise ValueError("expected five unique geometry-authorized sessions")
    return sessions


def labels_for_session(
    session_id: str, store: ScannerTrackingInputStore, cache_root: Path
) -> dict[str, Any]:
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(store.load(session_id)),
        config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
    )
    by_observation: dict[str, int] = {}
    by_tracklet = {item.tracklet_id: item for item in trajectory.tracklets}
    for hypothesis in trajectory.hypotheses:
        for tracklet_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            receiver = int(by_tracklet[tracklet_id].lane_key[2])
            for row in graph.observations:
                old = by_observation.setdefault(row.observation_id, receiver)
                if old != receiver:
                    raise ValueError("observation receiver ambiguity")
    receipt = json.loads((cache_root / session_id / "cache_receipt.json").read_text())
    labels = []
    for track in receipt["prepared_evidence"]["tracks"]:
        values = {by_observation.get(identifier) for identifier in track["observation_ids"]}
        if None in values or len(values) != 1:
            raise ValueError(f"incomplete receiver join: {session_id}/{track['track_id']}")
        labels.append({"track_id": track["track_id"], "receiver_id": values.pop()})
    return {"session_id": session_id, "tracks": labels}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--split-analysis-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    sessions = load_plan(args.plan)
    standard = ScannerTrackingInputStore(args.bulk_root)
    split = ScannerTrackingInputStore(
        args.bulk_root, adaptive_analysis_root=args.split_analysis_root
    )
    try:
        rows = [
            labels_for_session(
                session_id,
                split if session_id in SPLIT_ANALYSIS_SESSIONS else standard,
                args.cache_root,
            )
            for session_id in sessions
        ]
    finally:
        standard.close()
        split.close()
    print(
        json.dumps(
            {
                "schema": "ds3-portable-track-receiver-labels/v1",
                "reference_coordinate_present": False,
                "sessions": rows,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
