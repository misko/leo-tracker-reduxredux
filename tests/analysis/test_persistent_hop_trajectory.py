from __future__ import annotations

from dataclasses import replace

import pytest

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryConfig,
    PersistentHopTrajectoryInputError,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge

_BASE_UTC_NS = 1_788_400_000_000_000_000
_MANIFEST = canonical_digest({"manifest": "long-scan"})
_AUTHORITY = canonical_digest({"authority": "long-scan"})


def _candidate(
    *,
    lane: int,
    point: int,
    normalized_rate_hz_per_s: float,
    normalized_intercept_hz: float,
    alias_index: int,
) -> PersistentHopCfoCandidate:
    actual_rf_hz = (10_709_687_500.0, 11_690_312_500.0)[lane]
    canonical_rf_hz = 11_200_000_000.0
    scale = canonical_rf_hz / actual_rf_hz
    time_s = point + 0.25 * lane
    normalized_alias_spacing_hz = (1.0 / 4.4e-6) * scale
    normalized_cfo_hz = (
        normalized_intercept_hz
        + normalized_rate_hz_per_s * time_s
        + alias_index * normalized_alias_spacing_hz
    )
    measured_cfo_hz = normalized_cfo_hz / scale
    center_ns = _BASE_UTC_NS + round(time_s * 1e9)
    source_start = lane * 10_000_000 + point * 100_000
    identity = {
        "lane": lane,
        "point": point,
        "center_ns": center_ns,
    }
    return PersistentHopCfoCandidate(
        candidate_id=canonical_digest({"candidate": identity}),
        source_group_id=canonical_digest({"source": identity}),
        candidate_rank=0,
        session_id="scan-hop-synthetic-long",
        input_manifest_digest=_MANIFEST,
        raw_recording_authority_digest=_AUTHORITY,
        radio_id="radio-pluto-test",
        stream_generation="iio-0000000000000001",
        receiver_id=lane,
        visit_index=point * 8 + lane,
        probe_index=0,
        channel=(1, 4)[lane],
        edge=(StarlinkEdge.LOWER, StarlinkEdge.UPPER)[lane],
        actual_rf_hz=actual_rf_hz,
        source_sample_start=source_start,
        source_sample_end=source_start + 50_000,
        support_start_utc_ns=center_ns - 10_000_000,
        support_center_utc_ns=center_ns,
        support_end_utc_ns=center_ns + 10_000_000,
        measured_cfo_hz=measured_cfo_hz,
        standard_uncertainty_hz=400.0,
        factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
        exact_score=0.13,
        control_score=0.05,
        margin=0.08,
    )


def test_reconstructs_and_cross_links_normalized_alias_trajectories() -> None:
    candidates = tuple(
        _candidate(
            lane=lane,
            point=point,
            normalized_rate_hz_per_s=(-2_000.0, -1_950.0)[lane],
            normalized_intercept_hz=(50_000.0, -80_000.0)[lane],
            alias_index=1 if point >= 15 else 0,
        )
        for lane in range(2)
        for point in range(31)
    )

    result = reconstruct_persistent_hop_trajectories(candidates)

    assert result.tle_blind
    assert result.identity_claimed is False
    assert len(result.tracklets) == 2
    assert len(result.physical_groups) == 1
    assert len(result.physical_groups[0].tracklet_ids) == 2
    assert result.used_candidate_count == len(candidates)
    assert len(result.graph.episodes) == 2
    assert len(result.graph.observations) == len(candidates)
    assert {item.replica_group_id for item in result.graph.episodes} == {
        result.physical_groups[0].group_id
    }
    assert all(
        abs(track.normalized_rate_hz_per_s - expected) < 1.0
        for track, expected in zip(result.tracklets, (-2_000.0, -1_950.0), strict=True)
    )
    assert any(
        point.relative_alias_index == 1
        for track in result.tracklets
        for point in track.points
    )
    first_tracklet_graph = persistent_hop_tracklet_graph(
        result.hypotheses[0], result.tracklets[0].tracklet_id
    )
    assert len(first_tracklet_graph.episodes) == 1
    assert len(first_tracklet_graph.observations) == 31
    assert first_tracklet_graph.episodes[0].replica_group_id is None


def test_keeps_incompatible_normalized_rates_as_separate_physical_groups() -> None:
    candidates = tuple(
        _candidate(
            lane=lane,
            point=point,
            normalized_rate_hz_per_s=(-2_000.0, 1_000.0)[lane],
            normalized_intercept_hz=(50_000.0, -80_000.0)[lane],
            alias_index=0,
        )
        for lane in range(2)
        for point in range(20)
    )

    result = reconstruct_persistent_hop_trajectories(candidates)

    assert len(result.tracklets) == 2
    assert len(result.physical_groups) == 2
    assert all(len(item.tracklet_ids) == 1 for item in result.physical_groups)
    assert all(item.replica_group_id is None for item in result.graph.episodes)


def test_rejects_a_source_group_that_does_not_bind_one_observation() -> None:
    first = _candidate(
        lane=0,
        point=0,
        normalized_rate_hz_per_s=-2_000.0,
        normalized_intercept_hz=50_000.0,
        alias_index=0,
    )
    second = _candidate(
        lane=1,
        point=0,
        normalized_rate_hz_per_s=-2_000.0,
        normalized_intercept_hz=-80_000.0,
        alias_index=0,
    )
    second = replace(second, source_group_id=first.source_group_id)

    with pytest.raises(
        PersistentHopTrajectoryInputError,
        match="does not bind one RF observation",
    ):
        reconstruct_persistent_hop_trajectories((first, second))


def test_preserves_competing_per_probe_paths_as_source_disjoint_hypotheses() -> None:
    primary = tuple(
        _candidate(
            lane=0,
            point=point,
            normalized_rate_hz_per_s=-2_000.0,
            normalized_intercept_hz=50_000.0,
            alias_index=0,
        )
        for point in range(20)
    )
    alternative = tuple(
        replace(
            item,
            candidate_id=canonical_digest(
                {"alternative": item.source_group_id}
            ),
            candidate_rank=1,
            measured_cfo_hz=item.measured_cfo_hz + 70_000.0,
            exact_score=0.12,
            margin=0.07,
        )
        for item in primary
    )

    result = reconstruct_persistent_hop_trajectories(primary + alternative)

    assert len(result.tracklets) == 2
    assert len(result.hypotheses) == 2
    for hypothesis in result.hypotheses:
        source_group_ids = tuple(
            item.source_group_id
            for item in primary + alternative
            if item.candidate_id
            in {
                point.candidate_id
                for tracklet in result.tracklets
                if tracklet.tracklet_id in hypothesis.tracklet_ids
                for point in tracklet.points
            }
        )
        assert len(source_group_ids) == len(set(source_group_ids)) == 20


def test_work_limit_fails_closed() -> None:
    candidate = _candidate(
        lane=0,
        point=0,
        normalized_rate_hz_per_s=-2_000.0,
        normalized_intercept_hz=50_000.0,
        alias_index=0,
    )

    with pytest.raises(PersistentHopTrajectoryInputError, match="positive"):
        reconstruct_persistent_hop_trajectories(
            (candidate,),
            config=PersistentHopTrajectoryConfig(maximum_input_points=0),
        )
