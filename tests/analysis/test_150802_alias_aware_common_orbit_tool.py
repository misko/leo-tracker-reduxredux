from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from tools import report_150802_alias_aware_common_orbit as tool


def _member(
    label: str,
    values: np.ndarray,
    *,
    offset_hz: float = 0.0,
) -> tool.MemberSeries:
    times = np.asarray([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], dtype=float)
    return tool.MemberSeries(
        label=label,
        path=f"stream-1/{label}",
        source_kind="synthetic",
        rf_hz=tool.RF_FREQUENCY_HZ,
        source_row_count=times.size,
        time_s=times,
        cfo_hz=np.asarray(values, dtype=float) + offset_hz,
        rows_per_bin=np.ones(times.size, dtype=np.int64),
        train=np.asarray([True, True, True, True, False, False, False]),
    )


def _metadata(number: int) -> dict[str, object]:
    return {
        "catalogue_index": number - 1,
        "catalog_number": number,
        "object_name": f"candidate-{number}",
        "element_epoch_utc_ns": 0,
        "element_age_s": 0.0,
        "peak_elevation_deg": 40.0,
    }


def _replay_row(alias_index: int, *, margin: float, harmful: int = 0) -> dict[str, object]:
    return {
        "alias_index": alias_index,
        "branch_id": "branch",
        "geometry_display_eligible": True,
        "duration_s": 2.0,
        "observation_count": 8,
        "evaluated_probe_count": 20,
        "evaluated_block_count": 2,
        "block_coverage_ratio": 1.0,
        "median_block_corrected_margin": margin,
        "q10_block_margin_delta": 0.0,
        "harmful_block_count": harmful,
        "maximum_consecutive_harmful_blocks": harmful,
        "residual_rms_hz": 10.0,
        "residual_max_hz": 20.0,
    }


def test_common_cutoff_bins_are_built_in_separate_folds() -> None:
    raw_times = np.asarray([0.01, 0.26, 0.51, 0.76, 0.99, 1.0, 1.26, 1.51])
    member = tool._member(
        label="test",
        path="stream-1/RX0",
        source_kind="synthetic",
        raw_times_s=raw_times,
        raw_cfo_hz=10.0 * raw_times,
        train_cutoff_local_s=1.0,
    )

    assert member.train_count == 4
    assert member.holdout_count == 3
    assert np.all(member.time_s[member.train] < 1.0 + tool.STREAM_PATH_OFFSET_S)
    assert np.all(member.time_s[~member.train] >= 1.0 + tool.STREAM_PATH_OFFSET_S)


def test_unique_alias_gate_rejects_weak_same_branch_lift() -> None:
    selected = _replay_row(2, margin=0.2)
    weak = _replay_row(1, margin=0.001)
    final = {
        "lift_replay_digest": "sha256:replay",
        "trajectories": [
            {
                "trajectory_id": "trajectory",
                "branch_id": "branch",
                "alias_index": 2,
                **{
                    key: selected[key]
                    for key in (
                        "evaluated_probe_count",
                        "evaluated_block_count",
                        "block_coverage_ratio",
                        "median_block_corrected_margin",
                        "harmful_block_count",
                        "maximum_consecutive_harmful_blocks",
                    )
                },
            }
        ],
    }
    replay = {"content_digest": "sha256:replay", "rows": [selected, weak]}

    result = tool.validate_unique_alias(
        final,
        replay,
        trajectory_id="trajectory",
        branch_id="branch",
        alias_index=2,
    )

    assert result["unique_strict_replay_winner"]
    assert result["selected_replay"]["median_block_corrected_margin"] == 0.2
    assert result["rejected_same_branch_lifts"] == [
        {"alias_index": 1, "median_block_corrected_margin": 0.001, "harmful_block_count": 0}
    ]


def test_candidate_identity_is_selected_only_by_training_rows() -> None:
    grid = np.linspace(0.0, 5.0, 201)
    right = grid**3
    wrong = -(grid**3)
    member_values = np.asarray([1.0, 3.375, 8.0, 15.625, -27.0, -42.875, -64.0])
    members = (_member("RX0", member_values), _member("RX1", member_values, offset_hz=500.0))
    field = tool.PredictionField(
        shift_s=0.0,
        time_s=grid,
        doppler_hz=np.vstack((right, wrong)),
        elevation_deg=np.full((2, grid.size), 40.0),
        metadata=(_metadata(1), _metadata(2)),
        horizon_deg=10.0,
    )

    selected = tool.select_common_candidate(
        members,
        field,
        epoch_bound_s=0.3,
        drift_bound_hz_s=200.0,
    )

    assert selected["best"]["catalog_number"] == 1
    assert selected["best"]["holdout_residual_rms_hz"] > selected["best_alternative_holdout_rms_hz"]


def test_visibility_is_evaluated_at_each_candidate_epoch_shift() -> None:
    grid = np.linspace(0.0, 5.0, 501)
    members = (_member("RX0", np.asarray([1, 3.375, 8, 15.625, 27, 42.875, 64])),)
    # This curve is exact only at +0.30 s, but the satellite is below the
    # horizon at any positive shift for the final training row.
    shifted_cubic = (grid - 0.30) ** 3
    safe_but_imperfect = grid**3 + 0.02 * grid**2
    elevation = np.vstack(
        (
            np.where(grid <= 2.5, 40.0, 0.0),
            np.full(grid.size, 40.0),
        )
    )
    field = tool.PredictionField(
        0.0,
        grid,
        np.vstack((shifted_cubic, safe_but_imperfect)),
        elevation,
        (_metadata(1), _metadata(2)),
        10.0,
    )

    selected = tool.select_common_candidate(
        members,
        field,
        epoch_bound_s=0.3,
        drift_bound_hz_s=0.0,
    )

    if selected["best"]["catalog_number"] == 1:
        assert selected["best"]["epoch_adjustment_s"] <= 0.0
    assert min(selected["best"]["train_visibility_fraction_by_member"]) >= 0.95


def test_holdout_visibility_is_a_falsifier_not_a_selection_input() -> None:
    grid = np.linspace(0.0, 5.0, 501)
    values = np.asarray([1.0, 3.375, 8.0, 15.625, 27.0, 42.875, 64.0])
    members = (_member("RX0", values),)
    field = tool.PredictionField(
        0.0,
        grid,
        np.vstack((grid**3, grid**3 + 2.0 * grid**2)),
        np.vstack(
            (
                np.where(grid < 2.75, 40.0, 0.0),
                np.full(grid.size, 40.0),
            )
        ),
        (_metadata(1), _metadata(2)),
        10.0,
    )

    selected = tool.select_common_candidate(
        members,
        field,
        epoch_bound_s=0.3,
        drift_bound_hz_s=0.0,
    )
    finished = tool.finish_field(
        selected,
        members,
        tuple(tool.polynomial_null(member) for member in members),
        tool.shared_curvature_null(members),
        0.3,
    )
    aliases = {
        "rx1_alias": {"unique_strict_replay_winner": True},
        "rx0_alias": {"unique_strict_replay_winner": True},
        "rx1_counter_continuity": {"passed": True},
    }
    sensitivity = [
        {
            "catalog_number": finished["catalog_number"],
            "epoch_adjustment_s": finished["epoch_adjustment_s"],
        }
        for _ in tool.DRIFT_SENSITIVITY_BOUNDS_HZ_S
    ]
    raw_null = tool.empirical_p(finished["named_association_statistic"], [-2.0] * 40)
    null = tool.calibrate_wrong_time_null(raw_null, finished, sensitivity, aliases)
    gate = tool.numerical_gate(finished, null, sensitivity, aliases)

    assert selected["best"]["catalog_number"] == 1
    assert selected["best"]["train_visibility_eligible"]
    assert not selected["best"]["holdout_visibility_eligible"]
    assert not finished["selected_candidate_visibility_confirmed"]
    assert finished["named_association_statistic"] <= -1.0
    assert not gate["checks"]["selected_candidate_holdout_visibility_eligible"]
    assert not gate["passed"]


def test_shared_curvature_null_has_per_member_affine_terms() -> None:
    times = np.asarray([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
    common = 7.0 * times**2 - 0.4 * times**3
    members = (
        _member("RX0", common + 100.0 + 4.0 * times),
        _member("RX1", common - 300.0 - 8.0 * times),
    )

    result = tool.shared_curvature_null(members)

    cubic = next(row for row in result["models"] if row["degree"] == 3)
    assert cubic["train_residual_rms_hz"] < 1e-9
    assert cubic["holdout_residual_rms_hz"] < 1e-8
    assert result["holdout_oracle_best_degree"] == 3


def test_matched_empirical_p_requires_all_forty_controls() -> None:
    result = tool.empirical_p(10.0, [float(value) for value in range(40)])
    assert result["control_exceedance_count"] == 30
    assert result["empirical_p"] == pytest.approx(31 / 41)
    with pytest.raises(ValueError, match="exactly forty"):
        tool.empirical_p(10.0, [1.0] * 39)


def test_numerical_gate_requires_holdout_identity_separation() -> None:
    true = {
        "epoch_adjustment_s": 0.0,
        "train_visibility_eligible": True,
        "holdout_visibility_eligible": True,
        "full_visibility_eligible": True,
        "epoch_interior": True,
        "all_members_beat_best_polynomial": True,
        "holdout_rms_hz": 50.0,
        "holdout_advantage_over_strongest_radio_null_hz": 150.0,
        "shared_curvature_null": {"holdout_oracle_best_rms_hz": 200.0},
        "runner_margin_hz": 150.0,
        "heldout_alternative_margin_hz": -1.0,
        "catalog_number": 1,
    }
    aliases = {
        "rx1_alias": {"unique_strict_replay_winner": True},
        "rx0_alias": {"unique_strict_replay_winner": True},
        "rx1_counter_continuity": {"passed": True},
    }
    sensitivity = [
        {"catalog_number": 1, "epoch_adjustment_s": 0.0} for _ in tool.DRIFT_SENSITIVITY_BOUNDS_HZ_S
    ]
    null = tool.calibrate_wrong_time_null(
        tool.empirical_p(1.0, [0.0] * 40), true, sensitivity, aliases
    )

    gate = tool.numerical_gate(true, null, sensitivity, aliases)

    assert not gate["checks"]["train_selected_identity_beats_every_alternative_on_holdout"]
    assert not gate["checks"]["heldout_alternative_margin_at_least_100_hz"]
    assert not gate["passed"]


def test_numerical_gate_requires_epoch_stability_across_drift_bounds() -> None:
    true = {
        "epoch_adjustment_s": 2.5,
        "train_visibility_eligible": True,
        "holdout_visibility_eligible": True,
        "full_visibility_eligible": True,
        "epoch_interior": True,
        "all_members_beat_best_polynomial": True,
        "holdout_rms_hz": 50.0,
        "holdout_advantage_over_strongest_radio_null_hz": 150.0,
        "shared_curvature_null": {"holdout_oracle_best_rms_hz": 200.0},
        "runner_margin_hz": 150.0,
        "heldout_alternative_margin_hz": 150.0,
        "catalog_number": 1,
    }
    aliases = {
        "rx1_alias": {"unique_strict_replay_winner": True},
        "rx0_alias": {"unique_strict_replay_winner": True},
        "rx1_counter_continuity": {"passed": True},
    }
    sensitivity = [{"catalog_number": 1, "epoch_adjustment_s": epoch} for epoch in (-2.5, 2.5, 2.5)]
    null = tool.calibrate_wrong_time_null(
        tool.empirical_p(1.0, [0.0] * 40), true, sensitivity, aliases
    )

    gate = tool.numerical_gate(true, null, sensitivity, aliases)

    assert gate["checks"]["catalog_identity_stable_at_0_25_200_hz_s_drifts"]
    assert not gate["checks"]["epoch_adjustment_stable_at_0_25_200_hz_s_drifts"]
    assert not null["identity_calibration_eligible"]
    assert null["identity_empirical_p"] is None
    assert not gate["passed"]


def test_invalid_true_field_cannot_pass_identity_empirical_p_gate() -> None:
    true = {
        "epoch_adjustment_s": 2.5,
        "train_visibility_eligible": True,
        "holdout_visibility_eligible": True,
        "full_visibility_eligible": True,
        "epoch_interior": False,
        "all_members_beat_best_polynomial": True,
        "holdout_rms_hz": 50.0,
        "holdout_advantage_over_strongest_radio_null_hz": 150.0,
        "shared_curvature_null": {"holdout_oracle_best_rms_hz": 200.0},
        "runner_margin_hz": 150.0,
        "heldout_alternative_margin_hz": 150.0,
        "catalog_number": 1,
    }
    aliases = {
        "rx1_alias": {"unique_strict_replay_winner": True},
        "rx0_alias": {"unique_strict_replay_winner": True},
        "rx1_counter_continuity": {"passed": True},
    }
    sensitivity = [
        {"catalog_number": 1, "epoch_adjustment_s": 2.5} for _ in tool.DRIFT_SENSITIVITY_BOUNDS_HZ_S
    ]
    raw = tool.empirical_p(-1.0, [-2.0] * 39 + [-1.0])
    null = tool.calibrate_wrong_time_null(raw, true, sensitivity, aliases)

    gate = tool.numerical_gate(true, null, sensitivity, aliases)

    assert null["raw_diagnostic_empirical_p"] == pytest.approx(2 / 41)
    assert null["identity_empirical_p_status"] == "not_applicable"
    assert null["identity_empirical_p"] is None
    assert not gate["checks"]["matched_wrong_time_identity_empirical_p_at_most_0p05"]
    assert not gate["passed"]
    summary = tool._summary_markdown(
        {
            "status": "complete",
            "result": {
                "true_field": {
                    **true,
                    "candidate_name": "candidate-1",
                    "train_rms_hz": 40.0,
                },
                "numerical_identity_gate": gate,
                "wrong_time_null": null,
            },
        }
    )
    assert "raw diagnostic matched wrong-time p-value was 0.04878" in summary
    assert "cannot indicate identity specificity" in summary


def test_startup_file_freeze_detects_mutation(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    snapshot = tool.freeze_file("input", path)
    assert snapshot.digest == tool.sha256_bytes(b"{}")
    path.write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed during execution"):
        tool.verify_frozen_files((snapshot,))


def test_frozen_wrong_time_field_family_is_exact() -> None:
    assert len(tool.WRONG_TIME_SHIFTS_S) == 40
    assert tool.WRONG_TIME_SHIFTS_S[:2] == (-600.0, -570.0)
    assert tool.WRONG_TIME_SHIFTS_S[-2:] == (570.0, 600.0)
    assert 0.0 not in tool.WRONG_TIME_SHIFTS_S
    assert math.isclose(tool.STREAM_PATH_OFFSET_S, -0.064546309, abs_tol=1e-12)
