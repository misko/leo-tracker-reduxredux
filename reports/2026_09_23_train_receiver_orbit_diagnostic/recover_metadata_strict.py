#!/usr/bin/env python3
"""Recover exact receiver/lane metadata for sealed TRAIN tracks via public ports."""

import concurrent.futures
import hashlib
import json
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
POOLED = ROOT / "reports/2026_09_23_pooled_train_position/results/inference.json"
CACHES = (
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
)
CHECKPOINTS = Path("/tmp/leo-train-rx-metadata-checkpoints")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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
    lanes = {row.tracklet_id: row.lane_key for row in trajectory.tracklets}
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            signature = tuple(x.observation_id for x in graph.observations)
            if track_id in graphs and graphs[track_id][0] != signature:
                graphs[track_id] = None
            elif track_id not in graphs:
                graphs[track_id] = (signature, graph)
    receipt = json.loads((cache_root / sid / "cache_receipt.json").read_text())
    cutoff = source.timing.first_sample_estimate_utc_ns - 505_000_000_000
    snapshot = TleArchiveReader(Path("/var/lib/leo/tle")).select_latest_before(cutoff)
    if snapshot.collected_utc_ns >= cutoff:
        raise ValueError(f"non-causal TLE snapshot: {sid}")
    rows = []
    for track in receipt["prepared_evidence"]["tracks"]:
        value = graphs.get(track["track_id"])
        if value is None or tuple(track["observation_ids"]) != value[0]:
            raise ValueError(f"exact graph join failed: {sid} {track['track_id']}")
        observations = value[1].observations
        channel, edge, receiver_id, actual_rf_hz = lanes[track["track_id"]]
        streams = {row.stream_id for row in observations}
        if len(streams) != 1:
            raise ValueError(f"mixed receiver track: {sid} {track['track_id']}")
        rows.append(
            {
                "track_id": track["track_id"],
                "stream_id": next(iter(streams)),
                "receiver_id": receiver_id,
                "channel": channel,
                "edge": edge.value,
                "actual_rf_hz": actual_rf_hz,
                "sample_rate_hz": source.sample_rate_hz,
                "observation_ids": track["observation_ids"],
                "support_center_utc_ns": [x.support_center_utc_ns for x in observations],
                "measured_cfo_hz": [x.measured_cfo_hz for x in observations],
                "support_start_utc_ns": min(x.support_start_utc_ns for x in observations),
                "support_end_utc_ns": max(x.support_end_utc_ns for x in observations),
            }
        )
    result = {
        "session_id": sid,
        "input_manifest": source.input_manifest_sha256,
        "analysis_manifest": source.analysis_manifest_sha256,
        "cache_receipt": digest(cache_root / sid / "cache_receipt.json"),
        "state_cache": digest(cache_root / sid / "state_cache.npz"),
        "tle_snapshot_digest": snapshot.digest,
        "tle_snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "tracks": rows,
    }
    target = CHECKPOINTS / f"{sid}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return result


def main():
    CHECKPOINTS.mkdir(exist_ok=True)
    probe = CHECKPOINTS / ".write-test"
    probe.write_text("ok\n")
    probe.unlink()
    pooled = json.loads(POOLED.read_text())
    inventory = json.loads(
        (ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json").read_text()
    )["partitions"]
    canonical_ids = pooled["groups"][0] + pooled["groups"][1]
    if canonical_ids != inventory["train"]["session_ids"]:
        raise ValueError("pooled sessions differ from frozen TRAIN inventory")
    if set(canonical_ids) & set(
        inventory["validation"]["session_ids"] + inventory["test"]["session_ids"]
    ):
        raise ValueError("TRAIN overlaps VAL/TEST")
    ordinary = [
        (sid, cache) for group, cache in zip(pooled["groups"], CACHES, strict=True) for sid in group
    ]
    priority_ids = set(pooled["groups"][0][:6] + pooled["groups"][1][:6])
    tasks = [x for x in ordinary if x[0] in priority_ids] + [
        x for x in ordinary if x[0] not in priority_ids
    ]
    first = one(tasks[0])
    if json.loads((CHECKPOINTS / f"{first['session_id']}.json").read_text()) != first:
        raise ValueError("first-session checkpoint readback differs")
    pending = tasks[1:]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, pending))
    rows = [json.loads((CHECKPOINTS / f"{sid}.json").read_text()) for sid, _ in ordinary]
    output = Path("/tmp/leo-train-rx-metadata.json")
    output.write_text(json.dumps({"sessions": rows}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
