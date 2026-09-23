#!/usr/bin/env python3
"""Recover exact receiver/lane metadata for sealed TRAIN tracks via public ports."""
import concurrent.futures
import json
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
POOLED = ROOT / "reports/2026_09_23_pooled_train_position/results/inference.json"
CACHES = (
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
)


def one(task):
    sid, cache_root = task
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(sid)
        config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        trajectory = reconstruct_persistent_hop_trajectories(
            project_scanner_candidates(source), config=config
        )
    finally:
        store.close()
    graphs = {}
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            signature = tuple(x.observation_id for x in graph.observations)
            if track_id in graphs and graphs[track_id][0] != signature:
                graphs[track_id] = None
            elif track_id not in graphs:
                graphs[track_id] = (signature, graph)
    receipt = json.loads((cache_root / sid / "cache_receipt.json").read_text())
    rows = []
    for track in receipt["prepared_evidence"]["tracks"]:
        value = graphs.get(track["track_id"])
        if value is None or tuple(track["observation_ids"]) != value[0]:
            raise ValueError(f"exact graph join failed: {sid} {track['track_id']}")
        observations = value[1].observations
        streams = {row.stream_id for row in observations}
        if len(streams) != 1:
            raise ValueError(f"mixed receiver track: {sid} {track['track_id']}")
        rows.append({
            "track_id": track["track_id"], "stream_id": next(iter(streams)),
            "observation_ids": track["observation_ids"],
            "support_start_utc_ns": min(x.support_start_utc_ns for x in observations),
            "support_end_utc_ns": max(x.support_end_utc_ns for x in observations),
        })
    return {"session_id": sid, "input_manifest": source.input_manifest_sha256,
            "analysis_manifest": source.analysis_manifest_sha256, "tracks": rows}


def main():
    pooled = json.loads(POOLED.read_text())
    tasks = [
        (sid, cache)
        for group, cache in zip(pooled["groups"], CACHES, strict=True)
        for sid in group
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, tasks))
    output = Path(__file__).with_name("metadata.json")
    output.write_text(json.dumps({"sessions": rows}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
