from __future__ import annotations

from dataclasses import replace

import pytest

from leo.analysis.research.activity_block_derangement import (
    ActivityBlockDerangement,
    build_activity_block_derangement,
)
from leo.analysis.research.satellite_activity import (
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    DelayProfileCandidate,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
    profile_delay_and_cfo_offset,
)


def _plan(
    *,
    grid: ActivityGrid | None = None,
    session_key: str = "capture-alpha:control-0",
    maximum_delay_support_s: float = 0.75,
    minimum_circular_displacement_blocks: int = 2,
) -> ActivityBlockDerangement:
    return build_activity_block_derangement(
        grid or ActivityGrid(1_800_000_000.0, 0.1, 60, minimum_active_cells=5),
        session_key=session_key,
        maximum_delay_support_s=maximum_delay_support_s,
        minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
    )


def _circular_distance(left: int, right: int, count: int) -> int:
    direct = abs(left - right)
    return min(direct, count - direct)


def test_plan_is_deterministic_and_digest_bound_to_key_and_grid() -> None:
    first = _plan(session_key="session-a")
    repeated = _plan(session_key="session-a")
    different_key = _plan(session_key="session-b")
    different_grid = _plan(
        grid=ActivityGrid(1_800_000_000.1, 0.1, 60, minimum_active_cells=5),
        session_key="session-a",
    )

    assert first == repeated
    assert first.plan_digest == repeated.plan_digest
    assert first.ranking_version == "research-activity-block-affine-ranking-v2"
    assert first.session_key_digest != different_key.session_key_digest
    assert first.prediction_block_by_observation_block != (
        different_key.prediction_block_by_observation_block
    )
    assert first.plan_digest != different_key.plan_digest
    assert first.prediction_block_by_observation_block != (
        different_grid.prediction_block_by_observation_block
    )
    assert first.plan_digest != different_grid.plan_digest

    with pytest.raises(ValueError, match="plan digest does not bind"):
        replace(first, plan_digest="sha256:" + "0" * 64)


def test_mapping_is_an_exact_affine_derangement_beyond_delay_support() -> None:
    plan = _plan()
    mapping = plan.prediction_block_by_observation_block

    assert sorted(mapping) == list(range(plan.block_count))
    assert all(predicted != observed for observed, predicted in enumerate(mapping))
    assert all(
        _circular_distance(observed, predicted, plan.block_count)
        >= plan.minimum_circular_displacement_blocks
        for observed, predicted in enumerate(mapping)
    )
    assert mapping == tuple(
        (plan.affine_multiplier * observed + plan.affine_offset) % plan.block_count
        for observed in range(plan.block_count)
    )
    assert plan.affine_multiplier != 1
    assert plan.forward_block_adjacency_broken
    assert all(
        mapping[(observed + 1) % plan.block_count] != (predicted + 1) % plan.block_count
        for observed, predicted in enumerate(mapping)
    )
    assert plan.minimum_circular_displacement_s > plan.maximum_delay_support_s
    assert (
        plan.realized_minimum_circular_displacement_blocks
        >= plan.minimum_circular_displacement_blocks
    )

    rotated = tuple((observed + 2) % plan.block_count for observed in range(plan.block_count))
    with pytest.raises(ValueError, match="break forward block order"):
        replace(
            plan,
            affine_multiplier=1,
            affine_offset=2,
            prediction_block_by_observation_block=rotated,
        )


@pytest.mark.parametrize("block_count", (4, 6, 8, 10, 12, 16))
@pytest.mark.parametrize("session_key", ("control-a", "control-b", "control-c"))
def test_digest_ranking_never_selects_a_forward_order_rotation(
    block_count: int,
    session_key: str,
) -> None:
    plan = _plan(
        grid=ActivityGrid(0.0, 0.1, 5 * block_count, minimum_active_cells=5),
        session_key=session_key,
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )
    mapping = plan.prediction_block_by_observation_block

    assert plan.affine_multiplier != 1
    assert plan.forward_block_adjacency_broken
    assert all(
        mapping[(observed + 1) % block_count] != (predicted + 1) % block_count
        for observed, predicted in enumerate(mapping)
    )


def test_reverse_block_order_remains_a_deterministic_small_geometry_fallback() -> None:
    plan = _plan(
        grid=ActivityGrid(0.0, 0.1, 30, minimum_active_cells=5),
        session_key="six-block-reversal",
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )

    # Modulo six, only 1 and 5 are invertible affine multipliers.  Rejecting
    # forward order therefore leaves reversal as the unique multiplier family.
    assert plan.block_count == 6
    assert plan.affine_multiplier == plan.block_count - 1
    assert plan.forward_block_adjacency_broken


def test_probe_time_mapping_preserves_cell_offset_and_within_block_cadence() -> None:
    grid = ActivityGrid(100.0, 0.1, 40, minimum_active_cells=5)
    plan = _plan(
        grid=grid,
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )
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
        predicted_cell = plan.prediction_cell_for_observation_cell(probe.cell_index)
        observed_block, within_block = divmod(probe.cell_index, plan.block_cells)
        expected_cell = (
            plan.prediction_block_by_observation_block[observed_block] * plan.block_cells
            + within_block
        )
        assert predicted_cell == expected_cell
        assert prediction_time_s == pytest.approx(
            grid.start_s + predicted_cell * grid.cell_duration_s + 0.025
        )

    first_block_times = prediction_times[: plan.block_cells]
    assert [
        later - earlier
        for earlier, later in zip(first_block_times, first_block_times[1:], strict=False)
    ] == pytest.approx([grid.cell_duration_s] * (plan.block_cells - 1))


def test_one_plan_maps_corresponding_probes_identically_across_paths() -> None:
    grid = ActivityGrid(10.0, 0.1, 30, minimum_active_cells=5)
    first = _plan(
        grid=grid,
        session_key="shared-capture-control",
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )
    rebuilt = _plan(
        grid=grid,
        session_key="shared-capture-control",
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )
    path_a = tuple(
        CfoProbe(f"path-a-{index}", 10.0 + 0.1 * index + 0.075, index, 1.0) for index in range(30)
    )
    path_b = tuple(
        CfoProbe(f"path-b-{index}", 10.0 + 0.1 * index + 0.075, index, 2.0) for index in range(30)
    )

    assert first == rebuilt
    assert first.prediction_times_for_probes(path_a) == first.prediction_times_for_probes(path_b)


@pytest.mark.parametrize(
    ("grid", "message"),
    [
        (ActivityGrid(0.0, 0.12, 10), "exactly tile a 0.5-second block"),
        (ActivityGrid(0.0, 0.1, 12), "cell_count divisible"),
        (ActivityGrid(0.0, 0.1, 5), "at least two complete"),
    ],
)
def test_v1_rejects_invalid_block_geometry(grid: ActivityGrid, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_activity_block_derangement(
            grid,
            session_key="invalid-geometry",
            maximum_delay_support_s=0.2,
            minimum_circular_displacement_blocks=1,
        )


def test_control_rejects_invalid_displacement_and_probe_geometry() -> None:
    grid = ActivityGrid(0.0, 0.1, 60, minimum_active_cells=5)
    with pytest.raises(ValueError, match="beyond maximum delay support"):
        _plan(
            grid=grid,
            maximum_delay_support_s=1.0,
            minimum_circular_displacement_blocks=2,
        )
    with pytest.raises(ValueError, match="positive integer block count"):
        _plan(
            grid=grid,
            maximum_delay_support_s=0.0,
            minimum_circular_displacement_blocks=0,
        )
    with pytest.raises(ValueError, match="impossible on this block circle"):
        _plan(
            grid=grid,
            maximum_delay_support_s=0.0,
            minimum_circular_displacement_blocks=7,
        )
    with pytest.raises(ValueError, match="nonempty string"):
        _plan(grid=grid, session_key="")
    with pytest.raises(ValueError, match="no order-breaking affine"):
        _plan(
            grid=ActivityGrid(0.0, 0.1, 10, minimum_active_cells=5),
            maximum_delay_support_s=0.2,
            minimum_circular_displacement_blocks=1,
        )
    with pytest.raises(ValueError, match="no order-breaking affine"):
        _plan(
            grid=ActivityGrid(0.0, 0.1, 15, minimum_active_cells=5),
            maximum_delay_support_s=0.2,
            minimum_circular_displacement_blocks=1,
        )

    plan = _plan(grid=grid)
    with pytest.raises(ValueError, match="outside the derangement grid"):
        plan.prediction_cell_for_observation_cell(-1)
    with pytest.raises(ValueError, match="outside its declared"):
        plan.prediction_time_for_probe(CfoProbe("misdeclared", 0.15, 0, 1.0))
    with pytest.raises(ValueError, match="outside the derangement grid"):
        plan.prediction_time_for_probe(CfoProbe("outside", 6.025, 60, 1.0))


def test_correct_curve_activates_but_deranged_curve_does_not_after_offset_profile() -> None:
    grid = ActivityGrid(0.0, 0.1, 40, minimum_active_cells=5)
    plan = _plan(
        grid=grid,
        session_key="scientific-toy",
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )

    def curve(time_s: float) -> float:
        return 1_500.0 * time_s**2 + 250.0 * time_s**3

    probes = tuple(
        CfoProbe(f"probe-{index}", index * 0.1 + 0.05, index, 3.0)
        for index in range(grid.cell_count)
    )
    observed_cfo_hz = tuple(curve(probe.time_s) for probe in probes)
    observations = tuple(
        CfoCandidate(
            observation_id=f"observation-{index}",
            probe_id=probe.probe_id,
            exclusion_group_id=f"group-{index}",
            cfo_hz=observed_cfo_hz[index],
            sigma_hz=1.0,
            clutter_cost=8.0,
            matched_base_cost=0.0,
            component_id="component:derangement-toy",
        )
        for index, probe in enumerate(probes)
    )
    problem = SatelliteActivityProblem(
        grid=grid,
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(satellite_cost=8.0, episode_cost=2.0, huber_threshold=1.0),
    )
    correct = SingleSatelliteHypothesis(
        hypothesis_id="correct-time",
        object_name="TOY-SATELLITE",
        catalog_number=1,
        delay_s=0.0,
        cfo_offset_hz=0.0,
        delay_prior_cost=0.0,
        predictions=tuple(
            PredictedProbeCfo(probe.probe_id, curve(probe.time_s)) for probe in probes
        ),
    )

    correct_result = decode_single_satellite(problem, correct)
    deranged_results = []
    for delay_s in (-plan.maximum_delay_support_s, 0.0, plan.maximum_delay_support_s):
        deranged_cfo_hz = tuple(
            curve(plan.prediction_time_for_probe(probe) + delay_s) for probe in probes
        )
        offset_profile = profile_delay_and_cfo_offset(
            observed_cfo_hz,
            (1.0,) * len(probes),
            (DelayProfileCandidate(delay_s=delay_s, predicted_cfo_hz=deranged_cfo_hz),),
            delay_prior_mean_s=0.0,
            delay_prior_sigma_s=1.0,
            huber_threshold=1.0,
        )
        deranged = SingleSatelliteHypothesis(
            hypothesis_id=f"deranged-time-{delay_s:+.1f}",
            object_name="TOY-SATELLITE",
            catalog_number=1,
            delay_s=delay_s,
            cfo_offset_hz=offset_profile.posterior_best.fitted_cfo_offset_hz,
            delay_prior_cost=0.0,
            predictions=tuple(
                PredictedProbeCfo(probe.probe_id, predicted)
                for probe, predicted in zip(probes, deranged_cfo_hz, strict=True)
            ),
        )
        deranged_results.append(decode_single_satellite(problem, deranged))

    assert correct_result.selected
    assert correct_result.objective.delta_from_null < 0.0
    assert all(not result.selected for result in deranged_results)
    assert all(
        result.objective.delta_from_null > correct_result.objective.delta_from_null
        for result in deranged_results
    )
