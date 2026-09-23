"""Export public per-observation quality for one long training session."""

import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        persistent_hop_tracklet_graph,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    sid = "scan-hop-85afa91453f8847b"
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            sid, inputs=store, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
        )
        candidates = project_scanner_candidates(store.load(sid))
        trajectory = reconstruct_persistent_hop_trajectories(
            candidates, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        )
    finally:
        store.close()
    candidate = {row.candidate_id: row for row in candidates}
    tracklet = {row.tracklet_id: row for row in trajectory.tracklets}
    by_id = {}
    for hypothesis in trajectory.hypotheses:
        binding = {row.episode_id: row.tracklet_id for row in hypothesis.tracklet_episode_bindings}
        for track_id in hypothesis.tracklet_ids:
            points = {row.candidate_id: row for row in tracklet[track_id].points}
            for row in persistent_hop_tracklet_graph(hypothesis, track_id).observations:
                if binding[row.episode_id] != track_id:
                    raise ValueError("episode binding differs")
                matches = [
                    candidate[pid]
                    for pid, point in points.items()
                    if candidate[pid].source_group_id == row.source_group_id
                    and abs(point.normalized_dealiased_cfo_hz - row.measured_cfo_hz) < 1e-6
                ]
                if (
                    len(matches) != 1
                    or matches[0].support_center_utc_ns != row.support_center_utc_ns
                ):
                    raise ValueError("quality candidate does not uniquely bind observation")
                item = matches[0]
                value = {
                    "standard_uncertainty_hz": row.standard_uncertainty_hz,
                    "exact_score": item.exact_score,
                    "control_score": item.control_score,
                    "margin": item.margin,
                    "actual_rf_hz": item.actual_rf_hz,
                }
                if row.observation_id in by_id and by_id[row.observation_id] != value:
                    raise ValueError("conflicting quality")
                by_id[row.observation_id] = value
    wanted = [oid for t in prepared.track_evidence for oid in t["observation_ids"]]
    rows = [{"observation_id": oid, **by_id[oid]} for oid in wanted]
    u = np.array([r["standard_uncertainty_hz"] for r in rows])
    print(
        json.dumps(
            {
                "session_id": sid,
                "matched_observations": len(rows),
                "summary": {
                    "uncertainty_hz": {
                        "min": float(u.min()),
                        "median": float(np.median(u)),
                        "max": float(u.max()),
                    },
                    "rf_hz": sorted(set(r["actual_rf_hz"] for r in rows)),
                },
                "weights": rows,
                "provenance": {
                    "evidence_sha256": prepared.evidence_sha256,
                    "snapshot_digest": prepared.snapshot_digest,
                    "export_sha256": "sha256:"
                    + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                },
        "proposal": (
            "standard uncertainty is mainly shared timing/RF scaling, not calibrated SNR; "
            "do not add inverse-variance weighting without a training-only holdout protocol"
        ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
