from types import SimpleNamespace

import numpy as np
import pytest

from leo.application.continuous_merge_inputs import merged_position_inputs
from leo.application.regional_position_inputs import PreparedPositionWindows
from leo.contracts.regional_position import PositionObservations


def inputs():
    candidates, tracks, original, times, values, receivers = [], [], [], [], [], []
    origin = 10**18
    for rx in (0, 1):
        for segment, t in enumerate((np.arange(0, 24, 0.5), np.arange(25, 46, 0.5))):
            pts, indexes = [], []
            for i, time in enumerate(t):
                identity = f"{rx}:{segment}:{i}"
                value = 100000 - 2000 * time + 15 * time**2 + 0.03 * time**3
                if segment:
                    value += 1 / 4.4e-6
                p = SimpleNamespace(
                    candidate_id=identity,
                    source_group_id=identity,
                    support_center_utc_ns=origin + int(time * 1e9),
                    exact_score=0.5,
                    control_score=0.02,
                    margin=0.48,
                )
                candidates.append(p)
                pts.append(
                    SimpleNamespace(
                        candidate_id=identity,
                        normalized_dealiased_cfo_hz=value,
                    )
                )
                indexes.append(len(times))
                times.append(time)
                values.append(value)
                receivers.append(rx)
            original.append(tuple(indexes))
            tracks.append(
                SimpleNamespace(
                    tracklet_id=f"track-{rx}-{segment}",
                    lane_key=(1, "lower", rx, 11.2e9),
                    points=tuple(pts),
                )
            )
    n = len(times)
    observations = PositionObservations(
        tuple(p.source_group_id for p in candidates),
        np.array(times),
        np.array(values),
        np.full(n, 11.2e9),
        np.array(receivers),
        np.ones(n, int),
        np.full(n, 0.48),
    )
    prepared = PreparedPositionWindows(
        observations,
        tuple(p.candidate_id for p in candidates),
        tuple(original),
        origin,
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
    )
    trajectory = SimpleNamespace(tracklets=tracks, canonical_rf_hz=11.2e9)
    return prepared, trajectory, tuple(candidates)


def test_merge_only_changes_bootstrap_proposals_and_evidence_binding():
    prepared, trajectory, candidates = inputs()
    merged, receipt = merged_position_inputs(prepared, trajectory, candidates)
    assert merged.observations is prepared.observations
    assert merged.candidate_ids == prepared.candidate_ids
    assert merged.start_utc_ns == prepared.start_utc_ns
    assert merged.evidence_sha256 != prepared.evidence_sha256
    assert receipt["selected_join_count"] == 2
    assert len(merged.bootstrap_tracks) == 2
    assert sum(map(len, merged.bootstrap_tracks)) == len(prepared.candidate_ids)


def test_append_ablation_keeps_original_track_proposals():
    prepared, trajectory, candidates = inputs()
    merged, _ = merged_position_inputs(prepared, trajectory, candidates, mode="append")
    assert set(prepared.bootstrap_tracks) <= set(merged.bootstrap_tracks)
    assert len(merged.bootstrap_tracks) == 6


def test_nonwinning_trajectory_candidates_are_rejected():
    prepared, trajectory, candidates = inputs()
    trajectory.tracklets[0].points[0].candidate_id = "foreign"
    with pytest.raises(ValueError, match="non-winning"):
        merged_position_inputs(prepared, trajectory, candidates)
