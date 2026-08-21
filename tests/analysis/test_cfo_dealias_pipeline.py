from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import (
    CFO_LIFT_REPLAY_V2_PRODUCT,
    CFO_LIFT_REPLAY_V3_PRODUCT,
    FINAL_TRAJECTORY_BANK_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT,
)
from leo.analysis.starlink.cfo_dealias import (
    _observed_lift_candidates_v2,
    build_cfo_alias_map,
    build_final_trajectory_table_v2,
    build_lift_replay_document,
    calibrate_replay_gate_v2,
    centered_alias_residue_hz,
    classify_observed_lift_replay_v2,
    classify_observed_lift_replay_v3,
    classify_replay_tier_v2,
    classify_replay_tier_v3,
    default_cfo_dealias_config,
    default_replay_gate_v3,
    fit_seed_preserving_dealiased_trajectories,
    replay_observed_cfo_lifts,
    select_final_trajectories,
    select_final_trajectories_v2,
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
from leo.contracts.cfo_dealias import (
    AliasComponentStatus,
    AliasPairStatus,
    CfoAliasMapV2,
    CfoAliasPairDecisionV1,
    CfoLiftReplayRowV1,
    CfoLiftReplayRowV2,
    LiftReplayStatus,
    LiftReplayTierV2,
    LiftReplayTierV3,
    SeededAliasEmConfigV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardScientificStatus
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


def _v2_gate(**overrides: object):
    controls = {
        name: tuple((index - 2) * 0.0001 for index in range(4))
        for name in ("noise", "zero_iq", "wrong_edge", "wrong_alias", "time_shift", "unrelated_iq")
    }
    return calibrate_replay_gate_v2(controls, sample_rate_hz=1_000, **overrides)


def _v2_fixture():
    config = default_cfo_dealias_config()
    reference = _trajectory(
        "v2-reference", intercept_hz=300_000.0, slope_hz_per_s=-200.0, end_s=4.0
    )
    alias_map, representatives, raw_digest, _ = _map((reference,))
    bank = fit_dealiased_trajectories(
        tuple(
            _observation(f"v2-{index}", index * 0.5, 300_000.0 - 100.0 * index)
            for index in range(9)
        ),
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )
    candidates, source_count = _observed_lift_candidates_v2(bank, config, _v2_gate())
    return bank, candidates, source_count


def _v2_rows(trajectory_id: str, per_block: tuple[tuple[float, float], ...], repeats: int):
    return tuple(
        {
            "trajectory_id": trajectory_id,
            "detector_method": "glrt64",
            "sample_start": block * 1_000 + repeat,
            "margin_delta": delta,
            "corrected_margin": corrected,
        }
        for block, (delta, corrected) in enumerate(per_block)
        for repeat in range(repeats)
    )


def _classified_v2(per_block: tuple[tuple[float, float], ...], repeats: int = 5):
    bank, candidates, source_count = _v2_fixture()
    gate = _v2_gate()
    replay = classify_observed_lift_replay_v2(
        candidates,
        _v2_rows(candidates[0].replay_trajectory_id, per_block, repeats),
        source_lift_count=source_count,
        path_input_binding_digest=canonical_digest({"binding": "v2"}),
        pilot_scan_digest=canonical_digest({"pilot": "v2"}),
        canonical_bank=bank,
        gate_config=gate,
    )
    return bank, replay.rows[0], replay


def _classify_v2(per_block: tuple[tuple[float, float], ...], repeats: int = 5):
    _, row, replay = _classified_v2(per_block, repeats)
    return row, replay


def _classified_v3(
    per_block: tuple[tuple[float, float], ...], repeats: int = 5, **gate_overrides: object
):
    bank, _, _ = _v2_fixture()
    gate = default_replay_gate_v3(sample_rate_hz=1_000).model_copy(update=gate_overrides)
    candidates, source_count = _observed_lift_candidates_v2(
        bank, default_cfo_dealias_config(), gate
    )
    replay = classify_observed_lift_replay_v3(
        candidates,
        _v2_rows(candidates[0].replay_trajectory_id, per_block, repeats),
        source_lift_count=source_count,
        path_input_binding_digest=canonical_digest({"binding": "v3"}),
        pilot_scan_digest=canonical_digest({"pilot": "v3"}),
        canonical_bank=bank,
        gate_config=gate,
    )
    return bank, replay.rows[0], replay


def test_exact_rational_residue_uses_half_open_interval() -> None:
    config = default_cfo_dealias_config()
    spacing = config.alias_spacing_hz

    assert spacing == pytest.approx(2_500_000 / 11)
    assert centered_alias_residue_hz(spacing / 2, config) == pytest.approx(-spacing / 2)
    assert centered_alias_residue_hz(-spacing / 2, config) == pytest.approx(-spacing / 2)
    assert centered_alias_residue_hz(3 * spacing + 123.0, config) == pytest.approx(123.0)


def test_seed_preserving_dealias_has_exact_one_seed_to_one_branch_closure() -> None:
    first = _trajectory("seed-a", intercept_hz=280_000.0, slope_hz_per_s=-2_000.0)
    second = _trajectory("seed-b", intercept_hz=330_000.0, slope_hz_per_s=-8_000.0)
    alias_map, representatives, raw_digest, config = _map((first, second))
    observations = tuple(
        TrajectoryObservation(
            observation_id=observation_id,
            method=PilotMethod.GLRT64,
            sample_start=index * 1_000,
            time_s=index * 0.4,
            tracking_cfo_hz=float(trajectory.frequency_hz(index * 0.4)) + (-1) ** index * 50.0,
            score=0.8,
            control_score=0.1,
            margin=0.7,
        )
        for trajectory in (first, second)
        for index, observation_id in enumerate(trajectory.observation_ids)
    )

    result = fit_seed_preserving_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
        seeded_em_config=SeededAliasEmConfigV1(),
    )

    assert result.schema_version == 3
    assert result.source_branch_count == result.returned_branch_count == 2
    assert result.truncated_branch_count == 0
    assert {item.seed_trajectory_id for item in result.seed_dispositions} == {
        first.trajectory_id,
        second.trajectory_id,
    }
    branch_by_id = {item.branch_id: item for item in result.branches}
    for disposition in result.seed_dispositions:
        branch = branch_by_id[disposition.output_branch_id]
        assert len(branch.observation_ids) == disposition.selected_probe_count == 6
        assert {
            trajectory_id
            for observation_id in branch.observation_ids
            for trajectory_id in next(
                item for item in result.observations if item.observation_id == observation_id
            ).source_trajectory_ids
        } == {disposition.seed_trajectory_id}


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


def test_contradictory_alias_cycle_is_component_local_and_path_remains_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contradictory = tuple(
        _trajectory(f"cycle-{index}", intercept_hz=300_000.0) for index in range(3)
    )
    resolved = _trajectory("resolved", intercept_hz=20_000.0)
    cycle_ids = tuple(sorted(item.trajectory_id for item in contradictory))
    forced_deltas = {
        (cycle_ids[0], cycle_ids[1]): 0,
        (cycle_ids[1], cycle_ids[2]): 0,
        (cycle_ids[0], cycle_ids[2]): 1,
    }

    def forced_comparison(left, right, _config):
        pair = tuple(sorted((left.trajectory_id, right.trajectory_id)))
        if pair in forced_deltas:
            return CfoAliasPairDecisionV1(
                left_trajectory_id=pair[0],
                right_trajectory_id=pair[1],
                status=AliasPairStatus.ALIAS_EQUIVALENT,
                overlap_s=1.0,
                alias_index_delta=forced_deltas[pair],
                residual_rms_hz=0.0,
                maximum_absolute_residual_hz=0.0,
                reason="forced contradictory-cycle regression",
            )
        return CfoAliasPairDecisionV1(
            left_trajectory_id=pair[0],
            right_trajectory_id=pair[1],
            status=AliasPairStatus.NOT_COMPARED_NO_OVERLAP,
            overlap_s=0.0,
            alias_index_delta=None,
            residual_rms_hz=None,
            maximum_absolute_residual_hz=None,
            reason="forced separate resolved component",
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.cfo_dealias._compare_representatives", forced_comparison
    )
    alias_map, representatives, raw_digest, config = _map((*contradictory, resolved))

    assert alias_map.status is StandardScientificStatus.PARTIAL
    assert alias_map.insufficient_component_count == 1
    assert {item.status for item in alias_map.components} == {
        AliasComponentStatus.RESOLVED,
        AliasComponentStatus.INSUFFICIENT_CONTRADICTORY_CYCLE,
    }
    result = fit_dealiased_trajectories(
        tuple(
            _observation(f"resolved-{index}", index * 0.1, 20_000.0 - 200.0 * index)
            for index in range(8)
        ),
        representatives,
        alias_map,
        raw_bank_digest=raw_digest,
        config=config,
    )
    assert result.status is StandardScientificStatus.PARTIAL
    assert result.returned_branch_count == 1

    all_inconsistent, inconsistent_representatives, inconsistent_digest, _ = _map(contradictory)
    assert all_inconsistent.status is StandardScientificStatus.INSUFFICIENT_DATA
    assert all_inconsistent.insufficient_component_count == 1
    insufficient = fit_dealiased_trajectories(
        tuple(
            _observation(f"cycle-observation-{index}", index * 0.1, 300_000.0) for index in range(8)
        ),
        inconsistent_representatives,
        all_inconsistent,
        raw_bank_digest=inconsistent_digest,
        config=config,
    )
    assert insufficient.status is StandardScientificStatus.INSUFFICIENT_DATA
    assert insufficient.returned_branch_count == 0


def test_alias_map_v2_rejects_digest_consistent_false_cycle_status() -> None:
    spacing = default_cfo_dealias_config().alias_spacing_hz
    first = _trajectory("contract-first", intercept_hz=300_000.0)
    second = _trajectory("contract-second", intercept_hz=300_000.0 + spacing)
    alias_map, _, _, _ = _map((first, second))
    document = alias_map.model_dump(mode="json")
    document["members"][1]["relative_alias_index"] += 1
    document["content_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "content_digest"}
    )

    with pytest.raises(ValidationError, match="contradiction count disagrees"):
        CfoAliasMapV2.model_validate(document)


def test_four_historical_captures_reproduce_reviewed_alias_pair_decisions() -> None:
    fixture_path = Path("corpus/goldens/recent-cfo-alias-history-fixture-v1.json")
    report_path = Path(
        "reports/figures/2026_08_20_recent_cfo_alias_history/recent-cfo-alias-history.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    report_bytes = report_path.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == (
        "c4c561a4d13ecd8867586ba24b555ea09e1946ec5a5a97c2fe190ea7b8a8f798"
    )
    fixture = json.loads(fixture_bytes)
    assert fixture["source_report_sha256"] == "sha256:" + hashlib.sha256(report_bytes).hexdigest()
    assert fixture["path_count"] == len(fixture["paths"]) == 16

    compared = accepted = rejected = 0
    for path in fixture["paths"]:
        representatives = []
        for item in path["representatives"]:
            observation_ids = tuple(
                canonical_digest({"historical": item["trajectory_id"], "index": index})
                for index in range(6)
            )
            trajectory = PolynomialTrajectory(
                trajectory_id=item["trajectory_id"],
                method=PilotMethod.GLRT64,
                polynomial_degree=item["polynomial_degree"],
                reference_time_s=item["reference_time_s"],
                coefficients_hz=tuple(item["coefficients_hz"]),
                start_s=item["start_s"],
                end_s=item["end_s"],
                observation_ids=observation_ids,
                point_count=len(observation_ids),
                residual_rms_hz=1.0,
                bic=1.0,
                high_gate=0.1,
                em_iterations=0,
            )
            representatives.append(("historical-reviewed", trajectory))
        raw_bank = _bank(*(item[1] for item in representatives))
        result = build_cfo_alias_map(
            raw_bank,
            tuple(representatives),
            pilot_scan_digest=canonical_digest(
                {"historical_pilot": path["trajectory_bank_sha256"]}
            ),
            raw_bank_digest=path["trajectory_bank_sha256"],
            config=default_cfo_dealias_config(),
        )
        actual = {
            (item.left_trajectory_id, item.right_trajectory_id): item
            for item in result.pair_decisions
        }
        for expected in path["expected_pair_comparisons"]:
            key = tuple(
                sorted(
                    (
                        expected["left_trajectory_id"],
                        expected["right_trajectory_id"],
                    )
                )
            )
            expected_delta = expected["alias_index_delta"]
            if key != (
                expected["left_trajectory_id"],
                expected["right_trajectory_id"],
            ):
                expected_delta = -expected_delta
            decision = actual[key]
            is_accepted = decision.status is AliasPairStatus.ALIAS_EQUIVALENT
            assert is_accepted is expected["alias_equivalent"]
            assert decision.alias_index_delta == expected_delta
            assert decision.overlap_s == pytest.approx(expected["overlap_s"], abs=1e-12)
            assert decision.residual_rms_hz == pytest.approx(expected["residual_rms_hz"], abs=1e-9)
            assert decision.maximum_absolute_residual_hz == pytest.approx(
                expected["maximum_absolute_residual_hz"], abs=1e-9
            )
            compared += 1
            accepted += is_accepted
            rejected += not is_accepted
    assert (compared, accepted, rejected) == (12, 9, 3)


def test_trial132_early_ridges_remain_reviewed_as_one_alias_hypothesis() -> None:
    review_path = Path("corpus/goldens/trial-132-0-10s-alias-hypothesis-v1.json")
    review_bytes = review_path.read_bytes()
    assert hashlib.sha256(review_bytes).hexdigest() == (
        "bea5110d1935624c92bfb2ab056e6c63160caf5ff6b2daf940dce6b08b071f63"
    )
    review = json.loads(review_bytes)
    analysis_path = Path(review["source_analysis"]["path"])
    analysis_bytes = analysis_path.read_bytes()
    assert hashlib.sha256(analysis_bytes).hexdigest() == review["source_analysis"]["sha256"]
    analysis = json.loads(analysis_bytes)
    evidence = review["evidence"]
    assert review["classification"] == "alias_duplicate"
    assert analysis["source_observation_count"] == evidence["source_observation_count"]
    assert sum(analysis["selected_fit"]["retained"]) == evidence["retained_observation_count"]
    assert analysis["selected_fit"]["alias_indices"].count(0) == evidence["alias_zero_observations"]
    assert analysis["selected_fit"]["alias_indices"].count(1) == evidence["alias_one_observations"]
    assert analysis["two_branch_comparison"]["bic_delta_vs_one_canonical"] == pytest.approx(
        evidence["two_branch_bic_delta"]
    )
    replay = {item["model"]: item for item in analysis["replay_summary"]}
    assert replay["canonical_lower_quadratic"]["glrt64_positive_count"] == 1
    assert replay["canonical_plus_one_alias"]["glrt64_positive_count"] == 400
    assert replay["published_upper_cubic"]["glrt64_positive_count"] == 401
    assert review["candidate_only"] is True
    assert review["specificity_claimed"] is False
    assert review["payload_decoded"] is False


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


def test_v2_injected_true_trajectory_is_improved_and_inventory_is_explicit() -> None:
    row, replay = _classify_v2(((0.08, 0.30), (0.09, 0.32), (0.07, 0.28), (0.10, 0.35)))

    assert row.tier is LiftReplayTierV2.REPLAY_IMPROVED
    assert row.automatic_correction_eligible
    assert row.geometry_display_eligible
    assert replay.automatic_correction_lifts == replay.geometry_display_lifts
    assert decode_standard_product(
        CFO_LIFT_REPLAY_V2_PRODUCT, replay.model_dump(mode="json")
    ) == replay.model_dump(mode="json")


def test_v3_one_block_short_strong_track_is_automatic() -> None:
    _, row, replay = _classified_v3(((-0.01, 0.30),), repeats=20, minimum_block_coverage_ratio=0.2)

    assert row.evaluated_block_count == 1
    assert row.tier is LiftReplayTierV3.AUTOMATIC
    assert row.automatic_correction_eligible
    assert decode_standard_product(
        CFO_LIFT_REPLAY_V3_PRODUCT, replay.model_dump(mode="json")
    ) == replay.model_dump(mode="json")


def test_persisted_v2_replay_artifact_still_decodes_byte_contract() -> None:
    path = next(
        Path("reports/figures/2026_08_21_e975ebaac089_replay_investigation").glob(
            "upper/*/standard.cfo-lift-replay.v2.json"
        )
    )
    document = json.loads(path.read_text())

    assert decode_standard_product(CFO_LIFT_REPLAY_V2_PRODUCT, document) == document


@pytest.mark.parametrize(
    "branch_prefix",
    ("sha256:822e0b33", "sha256:ce33b982"),
)
def test_e975_archived_strong_tracks_remain_automatic_under_v3(branch_prefix: str) -> None:
    row = next(
        item
        for path in Path("reports/figures/2026_08_21_e975ebaac089_replay_investigation").glob(
            "upper/*/standard.cfo-lift-replay.v2.json"
        )
        for item in json.loads(path.read_text())["rows"]
        if item["branch_id"].startswith(branch_prefix)
        and item["alias_index"] == 0
        and item["median_block_corrected_margin"] >= 0.05
    )
    gate = default_replay_gate_v3()
    tier, _ = classify_replay_tier_v3(
        geometry_ok=row["geometry_display_eligible"],
        enough_replay=(
            row["evaluated_probe_count"] >= gate.minimum_probe_count
            and row["block_coverage_ratio"] >= gate.minimum_block_coverage_ratio
        ),
        strong_absolute=row["median_block_corrected_margin"]
        >= gate.minimum_median_corrected_margin,
        tail_ok=(
            row["harmful_block_count"] / row["evaluated_block_count"]
            <= gate.maximum_harmful_block_fraction
            and row["maximum_consecutive_harmful_blocks"] <= gate.maximum_consecutive_harmful_blocks
        ),
    )

    assert tier is LiftReplayTierV3.AUTOMATIC


def test_e793_archived_exact_evidence_is_geometry_only_under_v3() -> None:
    root = Path("reports/figures/2026_08_21_e7935fe8_recovery/exact-lower")
    replay_path = next(root.glob("*/standard.cfo-lift-replay.v2.json"))
    replay = json.loads(replay_path.read_text())
    row = next(
        item
        for item in replay["rows"]
        if item["branch_id"].startswith("sha256:e7935fe8") and item["alias_index"] == 0
    )
    gate = default_replay_gate_v3()
    tier, _ = classify_replay_tier_v3(
        geometry_ok=row["geometry_display_eligible"],
        enough_replay=(
            row["evaluated_probe_count"] >= gate.minimum_probe_count
            and row["block_coverage_ratio"] >= gate.minimum_block_coverage_ratio
        ),
        strong_absolute=row["median_block_corrected_margin"]
        >= gate.minimum_median_corrected_margin,
        tail_ok=row["harmful_block_count"] == 0,
    )

    assert row["observation_count"] == 82
    assert row["evaluated_probe_count"] == 450
    assert row["median_block_corrected_margin"] == pytest.approx(0.003310, abs=5e-6)
    assert tier is LiftReplayTierV3.GEOMETRY_ONLY
    assert row["median_block_corrected_margin"] >= 0.0025


def test_e975_archived_wrong_edge_never_reaches_display_floor() -> None:
    rows = [
        item
        for path in Path("reports/figures/2026_08_21_e975ebaac089_replay_investigation").glob(
            "lower/*/standard.cfo-lift-replay.v2.json"
        )
        for item in json.loads(path.read_text())["rows"]
    ]
    gate = default_replay_gate_v3()
    safe_geometry = [
        row
        for row in rows
        if row["geometry_display_eligible"]
        and row["evaluated_probe_count"] >= gate.minimum_probe_count
        and row["block_coverage_ratio"] >= gate.minimum_block_coverage_ratio
        and row["harmful_block_count"] == 0
        and row["maximum_consecutive_harmful_blocks"] == 0
        and row["median_block_corrected_margin"] is not None
    ]

    assert safe_geometry
    assert max(row["median_block_corrected_margin"] for row in safe_geometry) < 0.0025


def test_v3_material_nonharmful_negative_delta_does_not_gate_automatic() -> None:
    _, row, _ = _classified_v3(((-0.01, 0.30),) * 4)

    assert row.median_block_margin_delta == pytest.approx(-0.01)
    assert row.tier is LiftReplayTierV3.AUTOMATIC


def test_v3_harmful_tail_still_rejects_strong_absolute_evidence() -> None:
    _, row, _ = _classified_v3(
        ((0.01, 0.30), (0.01, 0.31), (-0.10, 0.32), (-0.11, 0.33), (-0.12, 0.34))
    )

    assert row.tier is LiftReplayTierV3.REPLAY_REJECTED
    assert not row.automatic_correction_eligible


@pytest.mark.parametrize("corrected_margin", (0.0, 0.001, 0.00249))
def test_v3_noise_and_wrong_edge_controls_do_not_reach_final(
    corrected_margin: float,
) -> None:
    bank, row, replay = _classified_v3(((0.0, corrected_margin),) * 4)

    assert row.tier is LiftReplayTierV3.GEOMETRY_ONLY
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    assert final.trajectories == ()


def test_v3_geometry_fallback_is_one_alias_ranked_by_absolute_evidence() -> None:
    bank, candidates, _ = _v2_fixture()
    gate = default_replay_gate_v3(sample_rate_hz=1_000)
    base = candidates[0]
    candidates = tuple(
        replace(
            base,
            alias_index=alias,
            replay_trajectory_id=canonical_digest({"v3-fallback-alias": alias}),
        )
        for alias in (-1, 0, 1)
    )
    rows = tuple(
        raw
        for candidate in candidates
        for raw in _v2_rows(
            candidate.replay_trajectory_id,
            ((-0.01, 0.003 if candidate.alias_index == 0 else 0.001),) * 4,
            5,
        )
    )
    replay = classify_observed_lift_replay_v3(
        candidates,
        rows,
        source_lift_count=3,
        path_input_binding_digest=canonical_digest({"binding": "v3-alias"}),
        pilot_scan_digest=canonical_digest({"pilot": "v3-alias"}),
        canonical_bank=bank,
        gate_config=gate,
    )
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())

    assert [item.alias_index for item in final.trajectories] == [0]
    assert not final.trajectories[0].automatic_correction_eligible
    assert final.selection_config.minimum_corrected_margin == pytest.approx(0.0025)
    tampered = final.model_dump(mode="json")
    tampered["selection_config"]["minimum_corrected_margin"] = 0.0
    with pytest.raises(ValidationError, match="selection configuration digest disagrees"):
        type(final).model_validate(tampered)


def test_v3_maximum_final_bound_prioritizes_automatic_over_geometry_fallback() -> None:
    bank, fallback, replay = _classified_v3(((-0.01, 0.003),) * 4)
    config = default_cfo_dealias_config().model_copy(update={"maximum_final_trajectories": 1})
    original = bank.branches[0]
    automatic_branch_id = canonical_digest({"v3-branch": "automatic"})
    automatic_models = tuple(
        model.model_copy(
            update={"model_id": canonical_digest({"v3-automatic-model": model.model_id})}
        )
        for model in original.models
    )
    automatic_model = next(
        model for model in automatic_models if model.polynomial_degree == fallback.polynomial_degree
    )
    automatic_branch = original.model_copy(
        update={
            "branch_id": automatic_branch_id,
            "models": automatic_models,
            "selected_model_id": automatic_model.model_id,
        }
    )
    bounded_bank = bank.model_copy(
        update={
            "config_digest": config.digest,
            "branches": (original, automatic_branch),
            "content_digest": canonical_digest({"v3-bank": "bounded"}),
        }
    )
    automatic = fallback.model_copy(
        update={
            "branch_id": automatic_branch_id,
            "canonical_model_id": automatic_model.model_id,
            "tier": LiftReplayTierV3.AUTOMATIC,
            "automatic_correction_eligible": True,
            "median_block_margin_delta": -0.01,
            "median_block_corrected_margin": 0.30,
        }
    )
    bounded_replay = replay.model_copy(
        update={
            "dealiased_bank_digest": bounded_bank.content_digest,
            "source_lift_count": 2,
            "returned_lift_count": 2,
            "rows": tuple(sorted((fallback, automatic), key=lambda row: row.branch_id)),
        }
    )

    final = select_final_trajectories_v2(bounded_bank, bounded_replay, config=config)

    assert final.source_trajectory_count == 2
    assert final.returned_trajectory_count == 1
    assert final.trajectories[0].branch_id == automatic_branch_id
    assert final.trajectories[0].automatic_correction_eligible


def test_v2_already_aligned_trajectory_is_stable_not_dropped() -> None:
    row, _ = _classify_v2(((-0.00010, 0.36), (0.00005, 0.35), (-0.00008, 0.37), (0.00002, 0.36)))

    assert row.tier is LiftReplayTierV2.REPLAY_STABLE
    assert row.automatic_correction_eligible
    assert row.equivalence_tolerance == pytest.approx(0.0004)


def test_v2_geometry_only_track_is_retained_but_never_correction_eligible() -> None:
    bank, row, replay = _classified_v2(
        ((-0.00010, 0.00331), (-0.00008, 0.00320), (-0.00009, 0.00342), (-0.00007, 0.00335))
    )

    assert row.tier is LiftReplayTierV2.GEOMETRY_ONLY
    assert not row.automatic_correction_eligible
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    table = build_final_trajectory_table_v2(final)

    assert final.returned_trajectory_count == 1
    assert final.automatic_correction_trajectory_ids == ()
    assert final.trajectories[0].replay_tier is LiftReplayTierV2.GEOMETRY_ONLY
    assert not final.trajectories[0].automatic_correction_eligible
    assert table.trajectories == final.trajectories
    assert decode_standard_product(
        FINAL_TRAJECTORY_BANK_PRODUCT, final.model_dump(mode="json")
    ) == final.model_dump(mode="json")
    assert decode_standard_product(
        GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT, table.model_dump(mode="json")
    ) == table.model_dump(mode="json")


def test_v2_geometry_fallback_selects_one_non_degrading_alias_per_branch() -> None:
    bank, base_candidates, _ = _v2_fixture()
    base = base_candidates[0]
    candidates = tuple(
        replace(
            base,
            alias_index=alias_index,
            replay_trajectory_id=canonical_digest(
                {"candidate": "fallback-alias", "alias_index": alias_index}
            ),
        )
        for alias_index in (-1, 0, 1, 2)
    )
    rows = tuple(
        row
        for candidate in candidates
        for row in _v2_rows(
            candidate.replay_trajectory_id,
            (((-0.00010, 0.00331),) * 4 if candidate.alias_index == 0 else ((-0.005, 0.004),) * 4),
            repeats=5,
        )
    )
    replay = classify_observed_lift_replay_v2(
        candidates,
        rows,
        source_lift_count=len(candidates),
        path_input_binding_digest=canonical_digest({"binding": "fallback-alias"}),
        pilot_scan_digest=canonical_digest({"pilot": "fallback-alias"}),
        canonical_bank=bank,
        gate_config=_v2_gate(),
    )

    assert all(item.tier is LiftReplayTierV2.GEOMETRY_ONLY for item in replay.rows)
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    assert len(final.trajectories) == 1
    assert final.trajectories[0].alias_index == 0
    assert not final.trajectories[0].automatic_correction_eligible


def test_v2_bounded_final_selection_prioritizes_automatic_before_digest_order() -> None:
    bank, fallback, replay = _classified_v2(((-0.00010, 0.00331),) * 4)
    config = default_cfo_dealias_config().model_copy(update={"maximum_final_trajectories": 1})
    original_branch = bank.branches[0]
    automatic_branch_id = canonical_digest({"branch": "automatic-priority"})
    automatic_models = tuple(
        item.model_copy(update={"model_id": canonical_digest({"automatic_model": item.model_id})})
        for item in original_branch.models
    )
    automatic_model = next(
        item for item in automatic_models if item.polynomial_degree == fallback.polynomial_degree
    )
    automatic_branch = original_branch.model_copy(
        update={
            "branch_id": automatic_branch_id,
            "models": automatic_models,
            "selected_model_id": automatic_model.model_id,
        }
    )
    bounded_bank = bank.model_copy(
        update={
            "config_digest": config.digest,
            "branches": (original_branch, automatic_branch),
            "content_digest": canonical_digest({"bank": "automatic-priority"}),
        }
    )
    automatic = CfoLiftReplayRowV2.model_validate(
        {
            **fallback.model_dump(mode="json"),
            "branch_id": automatic_branch_id,
            "canonical_model_id": automatic_model.model_id,
            "tier": LiftReplayTierV2.REPLAY_IMPROVED,
            "automatic_correction_eligible": True,
            "median_block_margin_delta": 0.10,
            "median_block_corrected_margin": 0.30,
            "improved_block_count": fallback.evaluated_block_count,
            "blocks": tuple(
                item.model_copy(
                    update={
                        "median_margin_delta": 0.10,
                        "median_corrected_margin": 0.30,
                    }
                )
                for item in fallback.blocks
            ),
        }
    )
    ordered_rows = tuple(sorted((fallback, automatic), key=lambda item: item.branch_id))
    bounded_replay = replay.model_copy(
        update={
            "dealiased_bank_digest": bounded_bank.content_digest,
            "source_lift_count": 2,
            "returned_lift_count": 2,
            "rows": ordered_rows,
        }
    )

    final = select_final_trajectories_v2(bounded_bank, bounded_replay, config=config)

    assert final.source_trajectory_count == 2
    assert final.returned_trajectory_count == 1
    assert final.truncated_trajectory_count == 1
    assert final.trajectories[0].branch_id == automatic_branch_id
    assert final.trajectories[0].automatic_correction_eligible


@pytest.mark.parametrize(
    ("corrected_margin", "expected_count"),
    ((0.001, 0), (0.00249, 0), (0.0025, 1)),
)
def test_v2_geometry_display_absolute_floor_is_explicit_and_closed(
    corrected_margin: float, expected_count: int
) -> None:
    bank, row, replay = _classified_v2(((-0.00010, corrected_margin),) * 4)

    assert row.tier is LiftReplayTierV2.GEOMETRY_ONLY
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    assert final.returned_trajectory_count == expected_count
    assert final.automatic_correction_trajectory_ids == ()


def test_v2_harmful_replay_is_not_retained_as_final_candidate_geometry() -> None:
    bank, row, replay = _classified_v2(
        ((0.01, 0.30), (0.01, 0.31), (-0.10, 0.32), (-0.11, 0.33), (-0.12, 0.34))
    )

    assert row.tier is LiftReplayTierV2.REPLAY_REJECTED
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    assert final.trajectories == ()
    assert final.automatic_correction_trajectory_ids == ()


def test_v2_automatic_track_is_retained_in_both_inventories() -> None:
    bank, row, replay = _classified_v2(((0.08, 0.30), (0.09, 0.32), (0.07, 0.28), (0.10, 0.35)))

    assert row.tier is LiftReplayTierV2.REPLAY_IMPROVED
    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    assert len(final.trajectories) == 1
    assert final.automatic_correction_trajectory_ids == (final.trajectories[0].trajectory_id,)


@pytest.mark.parametrize(
    "control_name",
    ("noise", "zero_iq", "wrong_edge", "wrong_alias", "time_shift", "unrelated_iq"),
)
def test_v2_negative_controls_never_enter_automatic_inventory(control_name: str) -> None:
    row, replay = _classify_v2(((0.0, 0.001),) * 4)

    assert control_name  # names are part of the reviewed red-test inventory
    assert row.tier is LiftReplayTierV2.GEOMETRY_ONLY
    assert not row.automatic_correction_eligible
    assert replay.automatic_correction_lifts == ()
    assert len(replay.geometry_display_lifts) == 1


def test_v2_harmful_tail_rejects_despite_strong_median_absolute_evidence() -> None:
    row, _ = _classify_v2(((0.01, 0.30), (0.01, 0.31), (-0.10, 0.32), (-0.11, 0.33), (-0.12, 0.34)))

    assert row.median_block_corrected_margin == pytest.approx(0.32)
    assert row.tier is LiftReplayTierV2.REPLAY_REJECTED
    assert not row.automatic_correction_eligible


@pytest.mark.parametrize("repeats", (5, 10, 25), ids=("1x20ms", "2x20ms", "dense"))
def test_v2_probe_density_is_invariant_after_block_aggregation(repeats: int) -> None:
    row, _ = _classify_v2(
        ((0.02, 0.20), (0.03, 0.21), (0.01, 0.22), (0.02, 0.23)),
        repeats=repeats,
    )

    assert row.tier is LiftReplayTierV2.REPLAY_IMPROVED
    assert row.evaluated_block_count == 4
    assert row.median_block_margin_delta == pytest.approx(0.02)


def test_v2_prefers_simpler_model_within_bic_delta() -> None:
    bank, candidates, _ = _v2_fixture()
    branch = bank.branches[0]
    best_bic = min(item.bic for item in branch.models)
    eligible = [item for item in branch.models if item.bic <= best_bic + 2.0]

    assert candidates[0].trajectory.polynomial_degree == min(
        item.polynomial_degree for item in eligible
    )


@pytest.mark.parametrize(
    ("branch_id", "strong_absolute", "median_delta", "expected"),
    (
        ("68fe3fe1", False, -0.0000028940959461189186, LiftReplayTierV2.GEOMETRY_ONLY),
        ("d9e9d74c", True, -0.00009005971126146983, LiftReplayTierV2.REPLAY_STABLE),
    ),
)
def test_v2_reviewed_live_branches_keep_expected_tiers(
    branch_id: str,
    strong_absolute: bool,
    median_delta: float,
    expected: LiftReplayTierV2,
) -> None:
    tier, _ = classify_replay_tier_v2(
        geometry_ok=True,
        enough_replay=True,
        strong_absolute=strong_absolute,
        tail_ok=True,
        median_delta=median_delta,
        equivalence_tolerance=0.0004,
    )

    assert branch_id in {"68fe3fe1", "d9e9d74c"}
    assert tier is expected
