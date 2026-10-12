"""Explicit merged bootstrap proposals; original position observations are unchanged."""

from dataclasses import asdict, replace

import numpy as np

from leo.analysis.cfo_lines import CfoPoint
from leo.analysis.continuous_track_merge import (
    ContinuousMergeConfiguration,
    TrackSeries,
    merge_tracks,
)
from leo.application.regional_position_inputs import PositionInputUnavailable
from leo.contracts.digests import canonical_digest


def merged_position_inputs(
    prepared, trajectory, candidates, *, mode="replace", residual_guard=True
):
    if mode not in ("replace", "append"):
        raise ValueError("unknown merged proposal mode")
    by_id = {point.candidate_id: point for point in candidates}
    lookup = {point: i for i, point in enumerate(prepared.candidate_ids)}
    series = []
    config = ContinuousMergeConfiguration()
    for track in trajectory.tracklets:
        ids = tuple(p.candidate_id for p in track.points)
        if any(point not in lookup for point in ids):
            raise ValueError("trajectory contains a non-winning original candidate")
        points = [by_id[point] for point in ids]
        order = np.argsort([p.support_center_utc_ns for p in points], kind="stable")
        series.append(
            TrackSeries(
                (track.tracklet_id,),
                track.lane_key,
                tuple(ids[i] for i in order),
                tuple(points[i].source_group_id for i in order),
                np.array(
                    [(points[i].support_center_utc_ns - prepared.start_utc_ns) / 1e9 for i in order]
                ),
                np.array([track.points[i].normalized_dealiased_cfo_hz for i in order]),
                np.array(
                    [
                        CfoPoint(
                            points[i].candidate_id,
                            0,
                            0,
                            points[i].exact_score,
                            points[i].control_score,
                            points[i].margin,
                        ).weight
                        for i in order
                    ]
                ),
                (1 / 4.4e-6) * trajectory.canonical_rf_hz / track.lane_key[3],
            )
        )
    merged, decisions = merge_tracks(series, config, residual_guard=residual_guard)
    proposals = list(merged)
    if mode == "append":
        proposals.extend(series)
    tracks = set()
    for track in proposals:
        rows = tuple(sorted(lookup[point] for point in track.point_ids))
        if len(rows) >= 15 and np.ptp(prepared.observations.times_s[list(rows)]) >= 15:
            tracks.add(rows)
    selected = []
    for receiver in (0, 1):
        matches = [r for r in tracks if prepared.observations.receiver[r[0]] == receiver]
        selected.extend(
            sorted(matches, key=lambda r: (-np.ptp(prepared.observations.times_s[list(r)]), r))[:12]
        )
    if {int(prepared.observations.receiver[r[0]]) for r in selected} != {0, 1}:
        raise PositionInputUnavailable("merged bootstrap lacks both receivers")
    binding = {
        "policy": asdict(config),
        "mode": mode,
        "residual_guard": residual_guard,
        "parent_prepared_evidence_sha256": prepared.evidence_sha256,
        "bootstrap_tracks": selected,
    }
    modified = replace(
        prepared,
        bootstrap_tracks=tuple(selected),
        evidence_sha256=canonical_digest(binding),
    )
    receipt = {
        "binding": binding,
        "decisions": decisions,
        "original_segments": len(series),
        "merged_components": len(merged),
        "selected_join_count": sum(len(t.member_ids) - 1 for t in merged),
        "qualified_pair_checks": sum(d["accepted"] for d in decisions),
        "bootstrap_before": len(prepared.bootstrap_tracks),
        "bootstrap_after": len(selected),
        "bootstrap_changed": modified.bootstrap_tracks != prepared.bootstrap_tracks,
        "components": [
            {
                "member_ids": t.member_ids,
                "lane": t.lane_key,
                "points": len(t.point_ids),
                "span_s": float(np.ptp(t.times_s)),
            }
            for t in merged
            if len(t.member_ids) > 1
        ],
        "observations": "same object, IDs, CFO, RF, sample timing and original windows",
    }
    return modified, receipt
