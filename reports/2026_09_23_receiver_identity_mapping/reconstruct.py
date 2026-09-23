"""Derive exact receiver identity joins through public trajectory contracts."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def join_observations(records, wanted):
    mapping = {}
    for observation_id, stream_id, receiver_path_id in records:
        value = {"stream_id": stream_id, "receiver_path_id": receiver_path_id}
        if observation_id in mapping and mapping[observation_id] != value:
            raise ValueError("conflicting receiver identity for observation")
        mapping[observation_id] = value
    missing = set(wanted) - mapping.keys()
    if missing:
        raise ValueError(f"missing {len(missing)} cached observations")
    return {key: mapping[key] for key in sorted(set(wanted))}


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        persistent_hop_tracklet_graph,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    manifest = here.parent / "2026_09_23_position_random_group_split/manifest.json"
    if args.session not in json.loads(manifest.read_text())["partitions"]["train"]["session_ids"]:
        raise ValueError("training partition only")
    cache = json.loads(args.evidence.read_text())
    if cache["session_id"] != args.session:
        raise ValueError("cache session mismatch")
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(args.session)
    finally:
        store.close()
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    candidates = project_scanner_candidates(source)
    trajectory = reconstruct_persistent_hop_trajectories(candidates, config=config)
    records = []
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            records.extend(
                (o.observation_id, o.stream_id, o.receiver_path_id) for o in graph.observations
            )
    wanted = [oid for track in cache["tracks"] for oid in track["observation_ids"]]
    mapping = join_observations(records, wanted)
    result = {
        "sample_session_id": args.session,
        "mapping_available": True,
        "matched_count": len(mapping),
        "cached_observation_count": len(wanted),
        "projected_candidates": len(candidates),
        "hypotheses": len(trajectory.hypotheses),
        "stream_counts": dict(Counter(value["stream_id"] for value in mapping.values())),
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "trajectory_config_digest": config.digest,
        "cached_evidence_sha256": hashlib.sha256(args.evidence.read_bytes()).hexdigest(),
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "partition_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "mapping": mapping,
        "scope": (
            "Exact public-contract reconstruction, training recording only; "
            "no IQ or position outcome used"
        ),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
