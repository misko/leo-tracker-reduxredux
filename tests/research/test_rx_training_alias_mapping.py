from types import SimpleNamespace

import pytest

from tools.rx_training_alias_mapping import (
    ALIAS_SPACING_HZ,
    calibrate_receiver_biases,
    candidate_window_index,
    export_selected_tracks,
    paired_epoch_distance_ns,
    unique_track_graph_observations,
    wrapped_difference,
)


def candidate(identifier, receiver, cfo, epoch, *, channel=2, rf=10_960_000_000.0):
    return SimpleNamespace(
        candidate_id=identifier,
        session_id="session",
        receiver_id=receiver,
        channel=channel,
        edge="lower",
        actual_rf_hz=rf,
        measured_cfo_hz=cfo,
        support_center_utc_ns=epoch,
        source_group_id=f"source-{identifier}",
        visit_index=0,
        probe_index=0,
    )


def test_selected_track_exports_exact_public_alias_coordinates() -> None:
    scale = 11_200_000_000.0 / 10_960_000_000.0
    projected = (
        candidate("a", 1, 100_000.0, 10),
        candidate("b", 1, 100_100.0, 20),
    )
    points = tuple(
        SimpleNamespace(
            candidate_id=item.candidate_id,
            relative_alias_index=index,
            normalized_raw_cfo_hz=item.measured_cfo_hz * scale,
            normalized_dealiased_cfo_hz=item.measured_cfo_hz * scale
            - index * ALIAS_SPACING_HZ * scale,
        )
        for index, item in enumerate(projected)
    )
    tracklet = SimpleNamespace(
        tracklet_id="track", lane_key=(2, "lower", 1, 10_960_000_000.0), points=points
    )
    observations = tuple(
        SimpleNamespace(
            observation_id=f"graph-{item.candidate_id}", source_group_id=item.source_group_id
        )
        for item in projected
    )
    episode = SimpleNamespace(
        episode_id="episode", observation_ids=tuple(item.observation_id for item in observations)
    )
    hypothesis = SimpleNamespace(
        graph=SimpleNamespace(episodes=(episode,), observations=observations),
        tracklet_episode_bindings=(
            SimpleNamespace(tracklet_id="track", episode_id="episode"),
        ),
    )
    trajectory = SimpleNamespace(tracklets=(tracklet,), hypotheses=(hypothesis,))

    rows = export_selected_tracks(
        "session",
        [{"track_id": "track", "training_observation_ids": ["graph-a", "graph-b"]}],
        trajectory,
        projected,
        {"a": "wa", "b": "wb"},
    )

    assert rows[0]["receiver_id"] == 1
    assert rows[0]["canonical_scale"] == pytest.approx(scale)
    assert rows[0]["training_alias_points"][1]["relative_alias_index"] == 1
    assert rows[0]["training_alias_points"][0]["observation_id"] == "graph-a"
    assert rows[0]["training_alias_points"][0]["candidate_id"] == "a"
    assert rows[0]["maximum_coordinate_verification_error_hz"] <= 1e-6


def test_selected_track_rejects_any_frozen_observation_drift() -> None:
    trajectory = SimpleNamespace(
        tracklets=(SimpleNamespace(tracklet_id="track", points=()),),
        hypotheses=(
            SimpleNamespace(
                graph=SimpleNamespace(
                    episodes=(SimpleNamespace(episode_id="episode", observation_ids=()),),
                    observations=(),
                ),
                tracklet_episode_bindings=(
                    SimpleNamespace(tracklet_id="track", episode_id="episode"),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="exactly reconstruct"):
        export_selected_tracks(
            "session",
            [{"track_id": "track", "training_observation_ids": ["missing"]}],
            trajectory,
            (),
            {},
        )


def test_selected_track_rejects_candidate_collapse_to_one_graph_observation() -> None:
    projected = (
        candidate("a", 1, 100_000.0, 10),
        candidate("b", 1, 100_100.0, 20),
    )
    projected[1].source_group_id = projected[0].source_group_id
    points = tuple(
        SimpleNamespace(
            candidate_id=item.candidate_id,
            relative_alias_index=0,
            normalized_raw_cfo_hz=item.measured_cfo_hz,
            normalized_dealiased_cfo_hz=item.measured_cfo_hz,
        )
        for item in projected
    )
    tracklet = SimpleNamespace(
        tracklet_id="track", lane_key=(2, "lower", 1, 11_200_000_000.0), points=points
    )
    observation = SimpleNamespace(observation_id="graph", source_group_id="source-a")
    episode = SimpleNamespace(episode_id="episode", observation_ids=("graph",))
    trajectory = SimpleNamespace(
        tracklets=(tracklet,),
        hypotheses=(
            SimpleNamespace(
                graph=SimpleNamespace(episodes=(episode,), observations=(observation,)),
                tracklet_episode_bindings=(
                    SimpleNamespace(tracklet_id="track", episode_id="episode"),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="collapse to one graph observation"):
        export_selected_tracks(
            "session",
            [{"track_id": "track", "training_observation_ids": ["graph"]}],
            trajectory,
            projected,
            {"a": "wa", "b": "wb"},
        )


def test_candidate_window_index_rejects_duplicate_public_probe_locator() -> None:
    raw = SimpleNamespace(session_id="session", sample_rate_hz=10_000_000)
    common = {
        "visit_index": 1,
        "receiver_id": 0,
        "probe_index": 2,
        "valid_start_counter": 100,
        "channel": 1,
        "edge": "lower",
        "actual_rf_hz": 10_710_000_000.0,
    }
    filtered = SimpleNamespace(
        probes=(
            SimpleNamespace(**common, probe_start_ms=0),
            SimpleNamespace(**common, probe_start_ms=20),
        )
    )
    with pytest.raises(ValueError, match="duplicate public probe locator"):
        candidate_window_index(raw, filtered, ())


def test_receiver_calibration_uses_one_wrapped_vote_per_training_window() -> None:
    points = []
    windows = {}
    for index in range(12):
        window = f"w{index}"
        left = candidate(f"l{index}", 0, 20_000.0 + index, index * 10_000)
        right = candidate(
            f"r{index}",
            1,
            21_000.0 + index + (ALIAS_SPACING_HZ if index % 2 else 0.0),
            index * 10_000 + 2_000,
        )
        points.extend((left, right))
        windows[left.candidate_id] = windows[right.candidate_id] = window
        # A second rx1 candidate must not create a second window vote.
        decoy = candidate(
            f"d{index}", 1, right.measured_cfo_hz + 40_000.0, right.support_center_utc_ns
        )
        points.append(decoy)
        windows[decoy.candidate_id] = window

    row = calibrate_receiver_biases(tuple(points), windows)[0]

    assert row["bias_rx1_minus_rx0_hz"] == pytest.approx(1_000.0)
    assert row["distinct_training_windows"] == 12
    assert [item["source_window_id"] for item in row["training_window_votes"]] == sorted(
        {f"w{index}" for index in range(12)}
    )
    assert all(
        item["wrapped_rx1_minus_rx0_hz"] == pytest.approx(1_000.0)
        for item in row["training_window_votes"]
    )
    assert row["qualified"] is True
    assert row["mad_hz"] == pytest.approx(0.0, abs=1e-9)


def test_receiver_calibration_does_not_pair_across_window_or_epoch_gate() -> None:
    points = (
        candidate("l", 0, 0.0, 0),
        candidate("r-late", 1, 1_000.0, 2_201),
        candidate("r-other-window", 1, 1_000.0, 2_000),
    )
    rows = calibrate_receiver_biases(
        points, {"l": "one", "r-late": "one", "r-other-window": "two"}
    )
    assert rows[0]["candidate_pair_count"] == 0
    assert rows[0]["bias_rx1_minus_rx0_hz"] is None
    assert rows[0]["training_window_votes"] == []
    assert rows[0]["qualified"] is False


def test_wrapping_uses_known_4p4_microsecond_alias_period() -> None:
    assert wrapped_difference(ALIAS_SPACING_HZ + 321.0) == pytest.approx(321.0)


def test_epoch_compatibility_is_modulo_the_750_hz_period() -> None:
    period = round(1_000_000_000 / 750)
    assert paired_epoch_distance_ns(10_000, 10_000 + period + 2_000) < 2_200


def test_installed_public_projection_and_tracklet_fields_exist() -> None:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTracklet,
        PersistentHopTrackPoint,
        PersistentHopTrajectoryConfig,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates

    assert callable(project_scanner_candidates)
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    assert config.canonical_rf_hz == 11_200_000_000.0
    assert set(PersistentHopTrackPoint.__dataclass_fields__) >= {
        "candidate_id",
        "relative_alias_index",
        "normalized_raw_cfo_hz",
        "normalized_dealiased_cfo_hz",
    }
    assert set(PersistentHopTracklet.__dataclass_fields__) >= {"tracklet_id", "lane_key", "points"}


def test_installed_reconstruction_binds_graph_observations_to_source_candidates() -> None:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopCfoCandidate,
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )

    from leo.contracts.digests import canonical_digest
    from leo.contracts.states import StarlinkEdge

    start = 1_800_000_000_000_000_000
    candidates = tuple(
        PersistentHopCfoCandidate(
            candidate_id=canonical_digest({"candidate": index}),
            source_group_id=canonical_digest({"source": index}),
            candidate_rank=0,
            session_id="session",
            input_manifest_digest=canonical_digest({"manifest": 1}),
            raw_recording_authority_digest=canonical_digest({"raw": 1}),
            radio_id="radio",
            stream_generation="generation",
            receiver_id=0,
            visit_index=index,
            probe_index=0,
            channel=1,
            edge=StarlinkEdge.LOWER,
            actual_rf_hz=11_200_000_000.0,
            source_sample_start=index * 200_000,
            source_sample_end=index * 200_000 + 100_000,
            support_start_utc_ns=start + index * 1_000_000_000,
            support_center_utc_ns=start + index * 1_000_000_000 + 10_000_000,
            support_end_utc_ns=start + index * 1_000_000_000 + 20_000_000,
            measured_cfo_hz=10_000.0 + index * 100.0,
            standard_uncertainty_hz=400.0,
            factorial_support_moments_s=(1.0, 0.0, 1e-6, 0.0),
            exact_score=0.2,
            control_score=0.1,
            margin=0.1,
        )
        for index in range(6)
    )
    trajectory = reconstruct_persistent_hop_trajectories(
        candidates,
        config=PersistentHopTrajectoryConfig(
            minimum_span_s=3.0,
            minimum_support=6,
            slope_bins=101,
            intercept_bins=64,
            peak_candidates=8,
        ),
    )
    tracklet = next(item for item in trajectory.tracklets if len(item.points) == 6)
    graph_sources = unique_track_graph_observations(trajectory)[str(tracklet.tracklet_id)]
    graph_ids = {str(item.observation_id) for item in graph_sources.values()}
    candidate_ids = {str(item.candidate_id) for item in candidates}
    assert graph_ids.isdisjoint(candidate_ids)

    rows = export_selected_tracks(
        "session",
        [
            {
                "track_id": str(tracklet.tracklet_id),
                "training_observation_ids": sorted(graph_ids),
            }
        ],
        trajectory,
        candidates,
        {str(item.candidate_id): f"window-{index}" for index, item in enumerate(candidates)},
    )
    assert {item["observation_id"] for item in rows[0]["training_alias_points"]} == graph_ids
    assert {item["candidate_id"] for item in rows[0]["training_alias_points"]} == candidate_ids
