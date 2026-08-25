from __future__ import annotations

import math
from dataclasses import asdict, replace

import pytest

import leo.analysis.research.activity_block_permutation as permutation_module
from leo.analysis.research.activity_block_permutation import (
    ActivityBlockPermutation,
    build_activity_block_permutation,
)
from leo.analysis.research.satellite_activity import ActivityGrid, CfoProbe


def _plan(
    *,
    grid: ActivityGrid | None = None,
    session_key: str = "115401",
    control_index: int = 0,
    maximum_delay_support_s: float = 2.0,
) -> ActivityBlockPermutation:
    return build_activity_block_permutation(
        grid or ActivityGrid(0.0, 0.1, 100, minimum_active_cells=5),
        session_key=session_key,
        control_index=control_index,
        maximum_delay_support_s=maximum_delay_support_s,
    )


def _circular_distance(left: int, right: int, count: int) -> int:
    direct = abs(left - right)
    return min(direct, count - direct)


def test_v1_selection_is_deterministic_digest_bound_and_snapshot_pinned() -> None:
    first = _plan()
    repeated = _plan()

    assert first == repeated
    assert first.algorithm_version == "research-activity-block-permutation-v1"
    assert first.ranking_version == "research-activity-block-matching-ranking-v1"
    assert first.prediction_block_by_observation_block == (
        15,
        7,
        9,
        14,
        18,
        0,
        12,
        16,
        13,
        1,
        4,
        17,
        2,
        6,
        19,
        10,
        3,
        5,
        8,
        11,
    )
    assert first.plan_digest == (
        "sha256:1311b77141c13257082a7d199f05fd3aefd1207937c2f058c3e585012a1d14ee"
    )

    with pytest.raises(ValueError, match="plan digest does not bind"):
        replace(first, plan_digest="sha256:" + "0" * 64)


def test_session_key_control_index_and_grid_select_distinct_maps() -> None:
    baseline = _plan()
    next_control = _plan(control_index=1)
    next_session = _plan(session_key="115402")
    shifted_grid = _plan(
        grid=ActivityGrid(0.1, 0.1, 100, minimum_active_cells=5),
    )

    plans = (baseline, next_control, next_session, shifted_grid)
    assert len({plan.prediction_block_by_observation_block for plan in plans}) == len(plans)
    assert len({plan.plan_digest for plan in plans}) == len(plans)
    assert baseline.session_key_digest == next_control.session_key_digest
    assert baseline.control_index != next_control.control_index
    assert baseline.session_key_digest != next_session.session_key_digest


def test_b120_selection_is_bounded_and_snapshot_pinned() -> None:
    plan = _plan(
        grid=ActivityGrid(0.0, 0.1, 600, minimum_active_cells=5),
        session_key="b120",
    )

    assert plan.block_count == 120
    assert len(plan.prediction_block_by_observation_block) == 120
    assert sorted(plan.prediction_block_by_observation_block) == list(range(120))
    assert plan.diagnostics.required_distinct_directed_displacement_count == 60
    assert plan.diagnostics.selection_attempt_count == 1
    assert plan.diagnostics.selected_attempt_search_step_count == 610
    assert plan.diagnostics.total_search_step_count == 610
    assert plan.plan_digest == (
        "sha256:fd1f23fcdbf284994f152af2cfdda890e47429d596a0f5209e0d8421e0bef823"
    )


def test_search_caps_are_explicit_serialized_validated_and_digest_bound() -> None:
    plan = _plan()
    serialized = asdict(plan)

    assert plan.maximum_search_attempts == 64
    assert plan.maximum_search_steps_per_attempt == 100_000
    assert serialized["maximum_search_attempts"] == 64
    assert serialized["maximum_search_steps_per_attempt"] == 100_000
    assert serialized["diagnostics"]["selected_attempt_search_step_count"] == (
        plan.diagnostics.selected_attempt_search_step_count
    )
    assert serialized["diagnostics"]["total_search_step_count"] == (
        plan.diagnostics.total_search_step_count
    )

    payload = permutation_module._plan_payload(
        grid=plan.grid,
        block_cells=plan.block_cells,
        block_count=plan.block_count,
        maximum_delay_support_s=plan.maximum_delay_support_s,
        minimum_circular_displacement_blocks=plan.minimum_circular_displacement_blocks,
        session_key_digest=plan.session_key_digest,
        control_index=plan.control_index,
        maximum_search_attempts=plan.maximum_search_attempts,
        maximum_search_steps_per_attempt=plan.maximum_search_steps_per_attempt,
        prediction_block_by_observation_block=plan.prediction_block_by_observation_block,
        diagnostics=plan.diagnostics,
    )
    assert permutation_module.canonical_digest(payload) == plan.plan_digest
    for cap_name, cap_value in (
        ("maximum_search_attempts", plan.maximum_search_attempts),
        ("maximum_search_steps_per_attempt", plan.maximum_search_steps_per_attempt),
    ):
        changed_payload = {**payload, cap_name: cap_value + 1}
        assert permutation_module.canonical_digest(changed_payload) != plan.plan_digest

    with pytest.raises(ValueError, match="search caps disagree"):
        replace(plan, maximum_search_attempts=65)
    with pytest.raises(ValueError, match="search caps disagree"):
        replace(plan, maximum_search_steps_per_attempt=100_001)

    with pytest.raises(ValueError, match="search caps must be integer"):
        replace(plan, maximum_search_attempts=64.0)  # type: ignore[arg-type]


def test_later_attempt_reports_selected_and_total_search_steps() -> None:
    plan = _plan(session_key="key-20")
    diagnostics = plan.diagnostics

    assert diagnostics.selection_attempt_count == 2
    assert diagnostics.selected_attempt_search_step_count == 3_400
    assert diagnostics.total_search_step_count == 103_400
    assert diagnostics.total_search_step_count == (
        plan.maximum_search_steps_per_attempt + diagnostics.selected_attempt_search_step_count
    )

    with pytest.raises(ValueError, match="total search step count"):
        replace(
            diagnostics,
            total_search_step_count=diagnostics.selected_attempt_search_step_count,
        )


def test_mapping_is_non_affine_perfect_matching_with_all_constraints_diagnosed() -> None:
    plan = _plan()
    mapping = plan.prediction_block_by_observation_block
    diagnostics = plan.diagnostics

    assert plan.block_duration_s == 0.5
    assert plan.block_cells == 5
    assert plan.block_count == 20
    assert sorted(mapping) == list(range(plan.block_count))
    assert plan.minimum_circular_displacement_blocks == 5
    assert plan.minimum_circular_displacement_s == 2.5
    assert plan.minimum_circular_displacement_s > plan.maximum_delay_support_s
    assert all(
        _circular_distance(observed, predicted, plan.block_count)
        >= plan.minimum_circular_displacement_blocks
        for observed, predicted in enumerate(mapping)
    )

    assert plan.forbidden_forward_lag_blocks == (1, 2, 3, 4)
    assert all(
        mapping[(observed + lag) % plan.block_count] != (predicted + lag) % plan.block_count
        for lag in plan.forbidden_forward_lag_blocks
        for observed, predicted in enumerate(mapping)
    )
    assert diagnostics.preserved_forward_lag_counts == (
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
    )

    displacement_counts = dict(diagnostics.directed_displacement_multiplicities)
    assert sum(displacement_counts.values()) == plan.block_count
    assert diagnostics.distinct_directed_displacement_count == len(displacement_counts)
    assert diagnostics.distinct_directed_displacement_count >= 10
    assert diagnostics.required_distinct_directed_displacement_count == 10
    assert diagnostics.maximum_directed_displacement_multiplicity == max(
        displacement_counts.values()
    )
    assert diagnostics.maximum_directed_displacement_multiplicity <= 3
    assert diagnostics.allowed_maximum_directed_displacement_multiplicity == 3
    assert diagnostics.realized_minimum_circular_displacement_blocks == min(
        _circular_distance(observed, predicted, plan.block_count)
        for observed, predicted in enumerate(mapping)
    )
    assert not diagnostics.mapping_is_affine
    assert 1 <= diagnostics.selection_attempt_count <= 64
    assert 1 <= diagnostics.selected_attempt_search_step_count <= 100_000
    assert (
        diagnostics.selected_attempt_search_step_count
        <= diagnostics.total_search_step_count
        <= diagnostics.selection_attempt_count * 100_000
    )


def test_plan_rejects_tampered_diagnostics_and_nonselected_valid_shape() -> None:
    plan = _plan()
    tampered_diagnostics = replace(
        plan.diagnostics,
        preserved_forward_lag_counts=((1, 1), (2, 0), (3, 0), (4, 0)),
    )
    with pytest.raises(ValueError, match="diagnostics disagree with the mapping"):
        replace(plan, diagnostics=tampered_diagnostics)

    swapped_mapping = list(plan.prediction_block_by_observation_block)
    swapped_mapping[0], swapped_mapping[1] = swapped_mapping[1], swapped_mapping[0]
    with pytest.raises(ValueError):
        replace(plan, prediction_block_by_observation_block=tuple(swapped_mapping))

    alternative = _plan(control_index=1)
    assert alternative.prediction_block_by_observation_block != (
        plan.prediction_block_by_observation_block
    )
    with pytest.raises(ValueError, match="not the digest-ranked bounded selection"):
        replace(
            plan,
            prediction_block_by_observation_block=(
                alternative.prediction_block_by_observation_block
            ),
            diagnostics=alternative.diagnostics,
        )


def test_probe_mapping_preserves_cell_offset_and_within_block_cadence() -> None:
    grid = ActivityGrid(100.0, 0.1, 100, minimum_active_cells=5)
    plan = _plan(grid=grid)
    probes = tuple(
        CfoProbe(
            probe_id=f"probe-{cell_index}",
            time_s=grid.start_s + cell_index * grid.cell_duration_s + 0.025,
            cell_index=cell_index,
            missed_detection_cost=1.0,
        )
        for cell_index in range(grid.cell_count)
    )
    prediction_times = plan.prediction_times_for_probes(probes)

    for probe, prediction_time_s in zip(probes, prediction_times, strict=True):
        observed_block, within_block = divmod(probe.cell_index, plan.block_cells)
        expected_cell = (
            plan.prediction_block_by_observation_block[observed_block] * plan.block_cells
            + within_block
        )
        assert plan.prediction_cell_for_observation_cell(probe.cell_index) == expected_cell
        assert prediction_time_s == pytest.approx(
            grid.start_s + expected_cell * grid.cell_duration_s + 0.025
        )

    first_block_times = prediction_times[: plan.block_cells]
    assert [
        later - earlier
        for earlier, later in zip(first_block_times, first_block_times[1:], strict=False)
    ] == pytest.approx([grid.cell_duration_s] * (plan.block_cells - 1))

    with pytest.raises(ValueError, match="outside the block-permutation grid"):
        plan.prediction_cell_for_observation_cell(-1)
    with pytest.raises(ValueError, match="outside its declared"):
        plan.prediction_time_for_probe(CfoProbe("misdeclared", 100.15, 0, 1.0))


def test_probe_time_mapping_uses_strict_half_open_edges_and_contains_target() -> None:
    grid = ActivityGrid(0.0, 0.1, 100, minimum_active_cells=5)
    plan = _plan(grid=grid)
    prediction_cell = plan.prediction_cell_for_observation_cell(0)
    target_start_s = grid.start_s + prediction_cell * grid.cell_duration_s
    target_end_s = target_start_s + grid.cell_duration_s

    assert plan.prediction_time_for_probe(CfoProbe("at-start", 0.0, 0, 1.0)) == (target_start_s)

    source_inside_upper_edge_s = math.nextafter(grid.cell_duration_s, -math.inf)
    translated_upper_edge_s = plan.prediction_time_for_probe(
        CfoProbe("inside-upper-edge", source_inside_upper_edge_s, 0, 1.0)
    )
    assert target_start_s <= translated_upper_edge_s < target_end_s
    assert translated_upper_edge_s == math.nextafter(target_end_s, target_start_s)

    with pytest.raises(ValueError, match="half-open"):
        plan.prediction_time_for_probe(
            CfoProbe("below-start", math.nextafter(grid.start_s, -math.inf), 0, 1.0)
        )
    with pytest.raises(ValueError, match="half-open"):
        plan.prediction_time_for_probe(CfoProbe("at-end", grid.cell_duration_s, 0, 1.0))

    large_grid = ActivityGrid(1_800_000_000.0, 0.1, 100, minimum_active_cells=5)
    large_plan = _plan(grid=large_grid, session_key="large-absolute-time-edges")
    source_start_s = large_grid.start_s
    source_end_s = source_start_s + large_grid.cell_duration_s
    large_prediction_cell = large_plan.prediction_cell_for_observation_cell(0)
    large_target_start_s = large_grid.start_s + large_prediction_cell * large_grid.cell_duration_s
    large_target_end_s = large_target_start_s + large_grid.cell_duration_s
    for probe_id, source_time_s in (
        ("large-interior", source_start_s + 0.037),
        ("large-inside-upper-edge", math.nextafter(source_end_s, source_start_s)),
    ):
        translated_s = large_plan.prediction_time_for_probe(
            CfoProbe(probe_id, source_time_s, 0, 1.0)
        )
        assert large_target_start_s <= translated_s < large_target_end_s
        assert translated_s - large_target_start_s == source_time_s - source_start_s


@pytest.mark.parametrize(
    ("grid", "message"),
    [
        (ActivityGrid(0.0, 0.12, 10), "exactly tile a 0.5-second block"),
        (ActivityGrid(0.0, 0.1, 12), "cell_count divisible"),
        (ActivityGrid(0.0, 0.1, 5), "at least two complete"),
    ],
)
def test_rejects_invalid_block_geometry(grid: ActivityGrid, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_activity_block_permutation(
            grid,
            session_key="invalid-geometry",
            control_index=0,
            maximum_delay_support_s=0.0,
        )


@pytest.mark.parametrize("delay_support", (-0.1, float("nan"), float("inf"), True))
def test_rejects_invalid_delay_support(delay_support: object) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        build_activity_block_permutation(
            ActivityGrid(0.0, 0.1, 100),
            session_key="invalid-support",
            control_index=0,
            maximum_delay_support_s=delay_support,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("control_index", (-1, True, 1.5))
def test_rejects_invalid_control_index(control_index: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        build_activity_block_permutation(
            ActivityGrid(0.0, 0.1, 100),
            session_key="invalid-index",
            control_index=control_index,  # type: ignore[arg-type]
            maximum_delay_support_s=2.0,
        )


def test_infeasible_constraints_and_exhausted_bounded_search_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="diversity is impossible"):
        _plan(maximum_delay_support_s=2.5)
    with pytest.raises(ValueError, match="within bounded search"):
        _plan(
            grid=ActivityGrid(0.0, 0.1, 20),
            maximum_delay_support_s=0.2,
        )

    monkeypatch.setattr(permutation_module, "_MAXIMUM_SEARCH_STEPS_PER_ATTEMPT", 1)
    with pytest.raises(ValueError, match="within bounded search"):
        _plan()


def test_rejects_empty_session_key() -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        _plan(session_key="")
