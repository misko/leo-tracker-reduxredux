from __future__ import annotations

import itertools
from dataclasses import replace

import pytest

from leo.analysis.research.grouped_satellite_activity import (
    decode_grouped_nuisance_states,
)
from leo.analysis.research.multi_satellite_activity import (
    JointSatelliteSchedule,
    evaluate_joint_satellite_schedule,
)
from leo.analysis.research.satellite_activity import (
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    PredictedProbeCfo,
    ProbeAssignment,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
)

TEST_COMPONENT = "component:grouped-state-test"


def _problem(
    *,
    cell_count: int,
    observations: tuple[CfoCandidate, ...],
    missed_detection_cost: float = 4.0,
    satellite_cost: float = 1.0,
    episode_cost: float = 0.5,
    minimum_active_cells: int = 1,
) -> SatelliteActivityProblem:
    return SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=0.1,
            cell_count=cell_count,
            minimum_active_cells=minimum_active_cells,
        ),
        probes=tuple(
            CfoProbe(
                probe_id=f"p-{index}",
                time_s=index * 0.1 + 0.025,
                cell_index=index,
                missed_detection_cost=missed_detection_cost,
            )
            for index in range(cell_count)
        ),
        observations=observations,
        costs=AssociationCostModel(
            satellite_cost=satellite_cost,
            episode_cost=episode_cost,
            huber_threshold=1.0,
        ),
    )


def _observation(
    cell: int,
    label: str,
    cfo_hz: float,
    *,
    clutter_cost: float = 10.0,
    sigma_hz: float = 1.0,
) -> CfoCandidate:
    return CfoCandidate(
        observation_id=f"o-{cell}-{label}",
        probe_id=f"p-{cell}",
        exclusion_group_id=f"group-{cell}-{label}",
        cfo_hz=cfo_hz,
        sigma_hz=sigma_hz,
        clutter_cost=clutter_cost,
        matched_base_cost=0.0,
        component_id=TEST_COMPONENT,
    )


def _state(
    problem: SatelliteActivityProblem,
    *,
    hypothesis_id: str,
    catalog_number: int,
    predicted_cfo_hz: float,
    delay_s: float = 0.0,
    cfo_offset_hz: float = 0.0,
    delay_prior_cost: float = 0.0,
) -> SingleSatelliteHypothesis:
    return SingleSatelliteHypothesis(
        hypothesis_id=hypothesis_id,
        object_name=f"CATALOG-{catalog_number}",
        catalog_number=catalog_number,
        delay_s=delay_s,
        cfo_offset_hz=cfo_offset_hz,
        delay_prior_cost=delay_prior_cost,
        predictions=tuple(
            PredictedProbeCfo(probe.probe_id, predicted_cfo_hz) for probe in problem.probes
        ),
    )


def test_selects_one_fixed_delay_cfo_state_across_every_episode() -> None:
    problem = _problem(
        cell_count=3,
        observations=(
            _observation(0, "signal", 10.0),
            _observation(2, "signal", 10.0),
        ),
        missed_detection_cost=8.0,
        episode_cost=1.0,
    )
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat10-wrong",
            catalog_number=10,
            predicted_cfo_hz=0.0,
            delay_s=-0.1,
        ),
        _state(
            problem,
            hypothesis_id="cat10-right",
            catalog_number=10,
            predicted_cfo_hz=0.0,
            delay_s=0.2,
            cfo_offset_hz=10.0,
            delay_prior_cost=0.1,
        ),
        _state(
            problem,
            hypothesis_id="cat20-only",
            catalog_number=20,
            predicted_cfo_hz=500.0,
        ),
    )

    result = decode_grouped_nuisance_states(problem, hypotheses)
    selected = tuple(item for item in result.association.satellites if item.selected)

    assert result.selected_hypothesis_ids == ("cat10-right",)
    assert len(selected) == 1
    assert selected[0].delay_s == pytest.approx(0.2)
    assert selected[0].cfo_offset_hz == pytest.approx(10.0)
    assert [(item.start_cell, item.end_cell_exclusive) for item in selected[0].episodes] == [
        (0, 1),
        (2, 3),
    ]
    assert {item.hypothesis_id for item in selected} == {"cat10-right"}


def test_one_catalog_cannot_activate_two_nuisance_states_for_two_simultaneous_peaks() -> None:
    problem = _problem(
        cell_count=1,
        observations=(
            _observation(0, "low", 0.0, clutter_cost=10.0),
            _observation(0, "high", 100.0, clutter_cost=12.0),
        ),
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat10-low-state",
            catalog_number=10,
            predicted_cfo_hz=0.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-high-state",
            catalog_number=10,
            predicted_cfo_hz=100.0,
        ),
        _state(
            problem,
            hypothesis_id="cat20-dummy",
            catalog_number=20,
            predicted_cfo_hz=1000.0,
        ),
    )

    result = decode_grouped_nuisance_states(problem, hypotheses)
    selected = tuple(item for item in result.association.satellites if item.selected)
    assignments = tuple(item for decision in selected for item in decision.assignments)

    assert result.selected_hypothesis_ids == ("cat10-high-state",)
    assert len(assignments) == 1
    assert assignments[0].observation_id == "o-0-high"
    assert result.association.unexplained_observation_ids == ("o-0-low",)


def test_delay_prior_can_outweigh_a_better_residual_state() -> None:
    problem = _problem(
        cell_count=1,
        observations=(_observation(0, "signal", 0.0),),
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat10-best-residual-high-prior",
            catalog_number=10,
            predicted_cfo_hz=0.0,
            delay_s=1.5,
            delay_prior_cost=4.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-near-prior",
            catalog_number=10,
            predicted_cfo_hz=0.5,
            delay_s=0.0,
            delay_prior_cost=0.0,
        ),
        _state(
            problem,
            hypothesis_id="cat20-only",
            catalog_number=20,
            predicted_cfo_hz=500.0,
        ),
    )

    result = decode_grouped_nuisance_states(problem, hypotheses)

    assert result.selected_hypothesis_ids == ("cat10-near-prior",)
    assert result.association.objective.residual_cost == pytest.approx(0.125)
    assert result.association.objective.delay_prior_cost == pytest.approx(0.0)


def test_null_result_has_no_selected_state_but_retains_reproducible_combination() -> None:
    problem = _problem(cell_count=1, observations=())
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat20-z",
            catalog_number=20,
            predicted_cfo_hz=20.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-z",
            catalog_number=10,
            predicted_cfo_hz=10.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-a",
            catalog_number=10,
            predicted_cfo_hz=11.0,
        ),
    )

    result = decode_grouped_nuisance_states(problem, hypotheses)

    assert result.association.selected_catalog_numbers == ()
    assert result.selected_hypothesis_ids == ()
    assert [item.evaluated_hypothesis_id for item in result.catalog_states] == [
        "cat10-a",
        "cat20-z",
    ]
    assert all(not item.selected for item in result.catalog_states)
    assert result.association.objective.total_cost == result.association.objective.null_cost
    assert result.candidate_state_combination_count == 2
    assert result.evaluated_state_combination_count == 2
    assert result.candidate_inventory_complete
    assert result.supplied_state_space_exhausted
    assert result.exact


def test_state_and_input_ties_are_permutation_deterministic() -> None:
    problem = _problem(
        cell_count=1,
        observations=(_observation(0, "signal", 0.0),),
        episode_cost=0.0,
    )
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat10-z",
            catalog_number=10,
            predicted_cfo_hz=0.0,
        ),
        _state(
            problem,
            hypothesis_id="cat20-only",
            catalog_number=20,
            predicted_cfo_hz=100.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-a",
            catalog_number=10,
            predicted_cfo_hz=0.0,
        ),
    )

    forward = decode_grouped_nuisance_states(problem, hypotheses)
    reverse = decode_grouped_nuisance_states(problem, tuple(reversed(hypotheses)))

    assert forward == reverse
    assert forward.selected_hypothesis_ids == ("cat10-a",)


def test_three_catalog_upper_bound_searches_every_grouped_state_combination() -> None:
    problem = _problem(
        cell_count=1,
        observations=(
            _observation(0, "first", 10.0),
            _observation(0, "second", 20.0),
            _observation(0, "third", 30.0),
        ),
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _state(
            problem,
            hypothesis_id="cat10-wrong",
            catalog_number=10,
            predicted_cfo_hz=11.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-right",
            catalog_number=10,
            predicted_cfo_hz=10.0,
        ),
        _state(
            problem,
            hypothesis_id="cat20-only",
            catalog_number=20,
            predicted_cfo_hz=20.0,
        ),
        _state(
            problem,
            hypothesis_id="cat30-only",
            catalog_number=30,
            predicted_cfo_hz=30.0,
        ),
    )

    result = decode_grouped_nuisance_states(problem, tuple(reversed(hypotheses)))

    assert result.association.selected_catalog_numbers == (10, 20, 30)
    assert result.selected_hypothesis_ids == (
        "cat10-right",
        "cat20-only",
        "cat30-only",
    )
    assert result.candidate_state_combination_count == 2
    assert result.evaluated_state_combination_count == 2


def _brute_force_one_cell(
    problem: SatelliteActivityProblem,
    groups: tuple[
        tuple[SingleSatelliteHypothesis, ...],
        tuple[SingleSatelliteHypothesis, ...],
    ],
) -> tuple[float, tuple[str, ...]]:
    candidates: list[tuple[float, tuple[str, ...]]] = []
    observations = tuple(problem.observations)
    for fixed in itertools.product(*groups):
        for active in itertools.product((False, True), repeat=2):
            active_indices = tuple(index for index, value in enumerate(active) if value)
            options = (None, *observations)
            for assignments_by_active in itertools.product(options, repeat=len(active_indices)):
                assigned = tuple(item for item in assignments_by_active if item is not None)
                if len({item.exclusion_group_id for item in assigned}) != len(assigned):
                    continue
                per_satellite: list[list[ProbeAssignment]] = [[], []]
                for index, observation in zip(
                    active_indices,
                    assignments_by_active,
                    strict=True,
                ):
                    if observation is not None:
                        per_satellite[index].append(
                            ProbeAssignment(observation.probe_id, observation.observation_id)
                        )
                schedules = tuple(
                    JointSatelliteSchedule(
                        hypothesis_id=hypothesis.hypothesis_id,
                        activity_by_cell=(active[index],),
                        assignments=tuple(per_satellite[index]),
                    )
                    for index, hypothesis in enumerate(fixed)
                )
                try:
                    association = evaluate_joint_satellite_schedule(problem, fixed, schedules)
                except ValueError:
                    continue
                candidates.append(
                    (
                        association.objective.total_cost,
                        tuple(
                            item.hypothesis_id for item in association.satellites if item.selected
                        ),
                    )
                )
    return min(candidates)


def test_grouped_decoder_matches_independent_state_activity_assignment_brute_force() -> None:
    problem = _problem(
        cell_count=1,
        observations=(
            _observation(0, "first", 4.0),
            _observation(0, "second", 14.0),
        ),
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    first_group = (
        _state(
            problem,
            hypothesis_id="cat10-low",
            catalog_number=10,
            predicted_cfo_hz=0.0,
        ),
        _state(
            problem,
            hypothesis_id="cat10-high",
            catalog_number=10,
            predicted_cfo_hz=4.0,
        ),
    )
    second_group = (
        _state(
            problem,
            hypothesis_id="cat20-low",
            catalog_number=20,
            predicted_cfo_hz=10.0,
        ),
        _state(
            problem,
            hypothesis_id="cat20-high",
            catalog_number=20,
            predicted_cfo_hz=14.0,
        ),
    )

    expected_cost, expected_states = _brute_force_one_cell(
        problem,
        (first_group, second_group),
    )
    result = decode_grouped_nuisance_states(problem, (*first_group, *second_group))

    assert result.association.objective.total_cost == pytest.approx(expected_cost)
    assert result.selected_hypothesis_ids == expected_states == ("cat10-high", "cat20-high")
    assert result.evaluated_state_combination_count == 4


def test_rejects_truncation_catalog_bounds_and_excessive_state_product() -> None:
    problem = _problem(cell_count=1, observations=())
    two_catalogs = tuple(
        _state(
            problem,
            hypothesis_id=f"cat{catalog}-{state}",
            catalog_number=catalog,
            predicted_cfo_hz=float(catalog + state),
        )
        for catalog in (10, 20)
        for state in range(3)
    )

    with pytest.raises(ValueError, match="untruncated candidate inventory"):
        decode_grouped_nuisance_states(
            replace(problem, truncated_observation_count=1),
            two_catalogs,
        )
    with pytest.raises(ValueError, match="9 combinations.*limit 5"):
        decode_grouped_nuisance_states(
            problem,
            two_catalogs,
            maximum_state_combinations=5,
        )
    with pytest.raises(ValueError, match="two or three catalogs"):
        decode_grouped_nuisance_states(problem, two_catalogs[:3])

    four_catalogs = tuple(
        _state(
            problem,
            hypothesis_id=f"cat{catalog}-only",
            catalog_number=catalog,
            predicted_cfo_hz=float(catalog),
        )
        for catalog in (10, 20, 30, 40)
    )
    with pytest.raises(ValueError, match="two or three catalogs"):
        decode_grouped_nuisance_states(problem, four_catalogs)
