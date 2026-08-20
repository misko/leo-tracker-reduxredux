from __future__ import annotations

import math
from functools import partial

import pytest

from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    build_lift_replay_document,
    centered_alias_residue_hz,
    default_cfo_dealias_config,
    replay_observed_cfo_lifts,
    select_final_trajectories,
)
from leo.analysis.starlink.cfo_dealias import (
    fit_dealiased_trajectories as _fit_dealiased_trajectories,
)
from leo.analysis.starlink.multi_target import default_multi_target_association_config
from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryObservation,
)
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.contracts.cfo_dealias import CfoLiftReplayRowV1, LiftReplayStatus
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge

fit_dealiased_trajectories = partial(
    _fit_dealiased_trajectories,
    association_config=default_multi_target_association_config(),
)


def _trajectory(
    name: str,
    *,
    intercept_hz: float,
    slope_hz_per_s: float = -2_000.0,
    start_s: float = 0.0,
    end_s: float = 2.0,
) -> PolynomialTrajectory:
    observation_ids = tuple(
        canonical_digest({"trajectory": name, "point": index}) for index in range(6)
    )
    return PolynomialTrajectory(
        trajectory_id=canonical_digest({"trajectory": name}),
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=0.0,
        coefficients_hz=(slope_hz_per_s, intercept_hz),
        start_s=start_s,
        end_s=end_s,
        observation_ids=observation_ids,
        point_count=len(observation_ids),
        residual_rms_hz=1.0,
        bic=1.0,
        high_gate=0.1,
        em_iterations=1,
    )


def _bank(*trajectories: PolynomialTrajectory) -> TrajectoryBankResult:
    return TrajectoryBankResult("sha256:" + "1" * 64, tuple(trajectories), (), 0, 0)


def _observation(name: str, time_s: float, cfo_hz: float) -> TrajectoryObservation:
    return TrajectoryObservation(
        observation_id=canonical_digest({"observation": name}),
        method=PilotMethod.GLRT64,
        sample_start=round(time_s * 1_000),
        time_s=time_s,
        tracking_cfo_hz=cfo_hz,
        score=0.8,
        control_score=0.1,
        margin=0.7,
    )


def _map(
    trajectories: tuple[PolynomialTrajectory, ...],
):
    config = default_cfo_dealias_config()
    representatives = tuple((f"family-{index}", item) for index, item in enumerate(trajectories))
    raw_digest = canonical_digest({"raw": [item.trajectory_id for item in trajectories]})
    return (
        build_cfo_alias_map(
            _bank(*trajectories),
            representatives,
            pilot_scan_digest=canonical_digest({"pilot": 1}),
            raw_bank_digest=raw_digest,
            config=config,
        ),
        representatives,
        raw_digest,
        config,
    )


def test_exact_rational_residue_uses_half_open_interval() -> None:
    config = default_cfo_dealias_config()
    spacing = config.alias_spacing_hz

    assert spacing == pytest.approx(2_500_000 / 11)
    assert centered_alias_residue_hz(spacing / 2, config) == pytest.approx(-spacing / 2)
    assert centered_alias_residue_hz(-spacing / 2, config) == pytest.approx(-spacing / 2)
    assert centered_alias_residue_hz(3 * spacing + 123.0, config) == pytest.approx(123.0)


def test_alias_map_records_merge_rejection_and_no_overlap() -> None:
    spacing = default_cfo_dealias_config().alias_spacing_hz
    main = _trajectory("main", intercept_hz=300_000.0)
    alias = _trajectory("alias", intercept_hz=300_000.0 + spacing + 80.0)
    near = _trajectory("near", intercept_hz=300_000.0 + spacing + 16_000.0)
    later = _trajectory("later", intercept_hz=300_000.0, start_s=3.0, end_s=4.0)

    result, _, _, _ = _map((main, alias, near, later))

    by_status = {item.status for item in result.pair_decisions}
    assert {
        item.component_id
        for item in result.members
        if item.trajectory_id in {main.trajectory_id, alias.trajectory_id}
    } == {
        next(
            item.component_id for item in result.members if item.trajectory_id == main.trajectory_id
        )
    }
    assert "alias_equivalent" in by_status
    assert "rejected_residual" in by_status
    assert "not_compared_no_overlap" in by_status
    assert result.content_digest.startswith("sha256:")


def test_same_probe_alias_hypotheses_collapse_but_distinct_peak_survives() -> None:
    config = default_cfo_dealias_config()
    spacing = config.alias_spacing_hz
    main = _trajectory("main", intercept_hz=300_000.0, end_s=1.0)
    alias = _trajectory("alias", intercept_hz=300_000.0 + spacing, end_s=1.0)
    distinct = _trajectory("distinct", intercept_hz=306_000.0, end_s=1.0)
    alias_map, representatives, raw_digest, _ = _map((main, alias, distinct))
    observations = []
    for index in range(8):
        time_s = index * 0.1
        base = 300_000.0 - 2_000.0 * time_s
        observations.extend(
            (
                _observation(f"base-{index}", time_s, base),
                _observation(f"alias-{index}", time_s, base + spacing),
                _observation(f"distinct-{index}", time_s, base + 6_000.0),
            )
        )

    result = fit_dealiased_trajectories(
        tuple(observations),
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )

    assert result.source_observation_count == 16
    assert len(result.branches) == 2
    assert sorted(len(item.observation_ids) for item in result.branches) == [8, 8]
    assert all(
        tuple(model.polynomial_degree for model in item.models) == (1, 2, 3)
        for item in result.branches
    )


def test_permutation_invariance_and_crossing_assignment() -> None:
    config = default_cfo_dealias_config().model_copy(
        update={
            "association_frequency_gate_hz": 4_000.0,
            "association_slope_gate_hz_per_s": 40_000.0,
            "association_acceleration_gate_hz_per_s2": 200_000.0,
        }
    )
    reference = _trajectory("reference", intercept_hz=300_000.0, slope_hz_per_s=0.0)
    alias_map, representatives, raw_digest, _ = _map((reference,))
    # Rebind the map to the intentionally changed association configuration.
    alias_map = build_cfo_alias_map(
        _bank(reference),
        representatives,
        pilot_scan_digest=alias_map.pilot_scan_digest,
        raw_bank_digest=raw_digest,
        config=config,
    )
    observations = tuple(
        _observation(f"{branch}-{index}", time_s, value)
        for index, time_s in enumerate((0.0, 0.1, 0.2, 0.3, 0.4, 0.5))
        for branch, value in (
            ("up", 297_500.0 + 10_000.0 * time_s),
            ("down", 302_500.0 - 10_000.0 * time_s),
        )
    )

    forward = fit_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )
    reverse = fit_dealiased_trajectories(
        tuple(reversed(observations)),
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )

    assert reverse == forward
    assert len(forward.branches) == 2
    slopes = sorted(branch.models[0].coefficients_hz[0] for branch in forward.branches)
    assert slopes == pytest.approx([-10_000.0, 10_000.0], abs=1e-6)


def test_final_selection_preserves_multiple_supported_lifts() -> None:
    config = default_cfo_dealias_config()
    reference = _trajectory("reference", intercept_hz=300_000.0, end_s=1.0)
    alias_map, representatives, raw_digest, _ = _map((reference,))
    observations = tuple(
        _observation(f"point-{index}", index * 0.1, 300_000.0 - 200.0 * index) for index in range(8)
    )
    bank = fit_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )
    branch = bank.branches[0]
    rows = tuple(
        CfoLiftReplayRowV1(
            branch_id=branch.branch_id,
            canonical_model_id=branch.selected_model_id,
            alias_index=alias_index,
            status=LiftReplayStatus.SUPPORTED,
            evaluated_probe_count=8,
            improved_probe_count=8,
            median_margin_delta=0.5 - 0.1 * abs(alias_index),
            median_control_separation=0.4,
            reason="same-IQ GLRT64 replay passed the reviewed gate",
        )
        for alias_index in (0, 1)
    )
    replay = build_lift_replay_document(
        rows,
        config=config,
        path_input_binding_digest=canonical_digest({"binding": 1}),
        pilot_scan_digest=alias_map.pilot_scan_digest,
        canonical_bank=bank,
    )

    final = select_final_trajectories(bank, replay, config=config)

    assert final.returned_trajectory_count == 2
    assert {item.alias_index for item in final.trajectories} == {0, 1}
    by_lift = {item.alias_index: item for item in final.trajectories}
    assert by_lift[1].absolute_coefficients_hz[-1] - by_lift[0].absolute_coefficients_hz[
        -1
    ] == pytest.approx(config.alias_spacing_hz)
    assert all(
        math.isfinite(value)
        for item in final.trajectories
        for value in item.absolute_coefficients_hz
    )


def test_same_iq_replay_gate_classifies_supported_lift(monkeypatch: pytest.MonkeyPatch) -> None:
    config = default_cfo_dealias_config()
    reference = _trajectory("replay-reference", intercept_hz=300_000.0, end_s=1.0)
    alias_map, representatives, raw_digest, _ = _map((reference,))
    observations = tuple(
        _observation(f"replay-{index}", index * 0.1, 300_000.0 - 200.0 * index)
        for index in range(8)
    )
    bank = fit_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )

    def fake_replay(_iq, _detections, replayed, _feedback, *, edge):
        assert edge is StarlinkEdge.LOWER
        trajectory_id = replayed[0][1].trajectory_id
        return tuple(
            {
                "family_id": replayed[0][0],
                "trajectory_id": trajectory_id,
                "detector_method": "glrt64",
                "sample_start": index,
                "corrected_margin": 0.30 + index * 0.01,
                "margin_delta": 0.20 + index * 0.01,
            }
            for index in range(4)
        )

    monkeypatch.setattr("leo.analysis.starlink.cfo_dealias.replay_pilot_trajectories", fake_replay)
    replay = replay_observed_cfo_lifts(
        object(),  # type: ignore[arg-type]
        (),
        bank,
        TrajectoryFeedbackConfig(),
        edge=StarlinkEdge.LOWER,
        path_input_binding_digest=canonical_digest({"binding": "replay"}),
        pilot_scan_digest=alias_map.pilot_scan_digest,
        config=config,
    )

    assert replay.status == "complete"
    assert len(replay.rows) == 1
    assert replay.rows[0].status is LiftReplayStatus.SUPPORTED
    assert replay.rows[0].improved_probe_count == 4


@pytest.mark.parametrize(
    ("row_statuses", "source_count", "expected"),
    (
        ((LiftReplayStatus.REJECTED,), 1, "no_result"),
        ((LiftReplayStatus.INSUFFICIENT_DATA,), 1, "insufficient_data"),
        (
            (LiftReplayStatus.SUPPORTED, LiftReplayStatus.INSUFFICIENT_DATA),
            2,
            "partial",
        ),
        ((LiftReplayStatus.SUPPORTED,), 2, "partial"),
    ),
)
def test_lift_replay_status_algebra_is_contagious(
    row_statuses: tuple[LiftReplayStatus, ...],
    source_count: int,
    expected: str,
) -> None:
    config = default_cfo_dealias_config()
    reference = _trajectory("status-reference", intercept_hz=300_000.0, end_s=1.0)
    alias_map, representatives, raw_digest, _ = _map((reference,))
    bank = fit_dealiased_trajectories(
        tuple(
            _observation(f"status-{index}", index * 0.1, 300_000.0 - 200.0 * index)
            for index in range(8)
        ),
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )
    branch = bank.branches[0]
    rows = tuple(
        CfoLiftReplayRowV1(
            branch_id=branch.branch_id,
            canonical_model_id=branch.selected_model_id,
            alias_index=index,
            status=status,
            evaluated_probe_count=4 if status is not LiftReplayStatus.INSUFFICIENT_DATA else 0,
            improved_probe_count=4 if status is LiftReplayStatus.SUPPORTED else 0,
            median_margin_delta=0.2 if status is not LiftReplayStatus.INSUFFICIENT_DATA else None,
            median_control_separation=(
                0.3 if status is not LiftReplayStatus.INSUFFICIENT_DATA else None
            ),
            reason="bounded replay status fixture",
        )
        for index, status in enumerate(row_statuses)
    )

    replay = build_lift_replay_document(
        rows,
        config=config,
        path_input_binding_digest=canonical_digest({"binding": "status"}),
        pilot_scan_digest=alias_map.pilot_scan_digest,
        canonical_bank=bank,
        source_lift_count=source_count,
    )

    assert replay.status == expected
    final = select_final_trajectories(bank, replay, config=config)
    assert final.status == expected
