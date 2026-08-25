from __future__ import annotations

import ast
import itertools
import random
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research import scalable_grouped_satellite_activity as grouped_module
from leo.analysis.research.multi_satellite_activity import (
    JointSatelliteAssociationResult,
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
    decode_single_satellite,
)
from leo.analysis.research.scalable_grouped_satellite_activity import (
    ALGORITHM,
    CatalogNuisanceStateBank,
    ExactGroupedSearchLimitExceeded,
    ExactGroupedSearchLimits,
    decode_arbitrary_n_grouped_nuisance_states,
)

TEST_COMPONENT = "component:scalable-grouped-test"


def _problem(
    *,
    cell_count: int,
    observations: tuple[CfoCandidate, ...],
    minimum_active_cells: int = 1,
    missed_detection_cost: float = 2.0,
    satellite_cost: float = 0.0,
    episode_cost: float = 0.0,
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
                time_s=0.025 + 0.1 * index,
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
    *,
    probe_index: int,
    label: str,
    group_id: str,
    cfo_hz: float,
    clutter_cost: float,
    matched_base_cost: float = 0.0,
    sigma_hz: float = 1.0,
) -> CfoCandidate:
    return CfoCandidate(
        observation_id=f"o-{probe_index}-{label}",
        probe_id=f"p-{probe_index}",
        exclusion_group_id=group_id,
        cfo_hz=cfo_hz,
        sigma_hz=sigma_hz,
        clutter_cost=clutter_cost,
        matched_base_cost=matched_base_cost,
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
    eligible_probe_ids: tuple[str, ...] | None = None,
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
        eligible_probe_ids=eligible_probe_ids,
    )


def _bank(
    catalog_number: int,
    *states: SingleSatelliteHypothesis,
) -> CatalogNuisanceStateBank:
    return CatalogNuisanceStateBank(catalog_number=catalog_number, states=tuple(states))


def _conflicting_state_case() -> tuple[
    SatelliteActivityProblem, tuple[CatalogNuisanceStateBank, ...]
]:
    problem = _problem(
        cell_count=1,
        observations=(
            _observation(
                probe_index=0,
                label="g",
                group_id="physical-g",
                cfo_hz=0.0,
                clutter_cost=10.0,
            ),
            _observation(
                probe_index=0,
                label="h",
                group_id="physical-h",
                cfo_hz=100.0,
                clutter_cost=8.0,
            ),
        ),
    )
    return problem, (
        _bank(
            10,
            _state(
                problem,
                hypothesis_id="cat10-g",
                catalog_number=10,
                predicted_cfo_hz=0.0,
            ),
            _state(
                problem,
                hypothesis_id="cat10-h",
                catalog_number=10,
                predicted_cfo_hz=100.0,
                delay_prior_cost=2.0,
            ),
        ),
        _bank(
            20,
            _state(
                problem,
                hypothesis_id="cat20-g",
                catalog_number=20,
                predicted_cfo_hz=0.0,
                delay_prior_cost=2.0,
            ),
            _state(
                problem,
                hypothesis_id="cat20-h",
                catalog_number=20,
                predicted_cfo_hz=100.0,
                delay_prior_cost=1.0,
            ),
        ),
    )


def _candidate_key(
    association: JointSatelliteAssociationResult,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> tuple[object, ...]:
    selected = tuple(item for item in association.satellites if item.selected)
    assignments = tuple(
        (item.hypothesis_id, assignment.probe_id, assignment.observation_id)
        for item in association.satellites
        for assignment in item.assignments
    )
    return (
        association.objective.total_cost,
        len(selected),
        sum(len(item.episodes) for item in association.satellites),
        sum(sum(item.activity_by_cell) for item in association.satellites),
        tuple(not item.selected for item in association.satellites),
        tuple(item.hypothesis_id for item in selected),
        tuple(item.activity_by_cell for item in association.satellites),
        len(assignments),
        assignments,
        tuple(item.hypothesis_id for item in hypotheses),
    )


def _brute_force(
    problem: SatelliteActivityProblem,
    banks: tuple[CatalogNuisanceStateBank, ...],
) -> tuple[JointSatelliteAssociationResult, tuple[SingleSatelliteHypothesis, ...]]:
    """Independent tiny oracle over state, activity, and assignment choices."""

    ordered_banks = tuple(sorted(banks, key=lambda item: item.catalog_number))
    masks = tuple(itertools.product((False, True), repeat=problem.grid.cell_count))
    observations_by_probe = {
        probe.probe_id: tuple(
            item for item in problem.observations if item.probe_id == probe.probe_id
        )
        for probe in problem.probes
    }
    candidates: list[
        tuple[
            tuple[object, ...],
            JointSatelliteAssociationResult,
            tuple[SingleSatelliteHypothesis, ...],
        ]
    ] = []
    for hypotheses in itertools.product(*(item.states for item in ordered_banks)):
        fixed = tuple(hypotheses)
        for activities in itertools.product(masks, repeat=len(fixed)):
            matchings_by_probe: list[tuple[tuple[CfoCandidate | None, ...], ...]] = []
            for probe in problem.probes:
                choices_by_catalog = tuple(
                    (None, *observations_by_probe[probe.probe_id])
                    if activities[index][probe.cell_index]
                    else (None,)
                    for index in range(len(fixed))
                )
                matchings = []
                for matching in itertools.product(*choices_by_catalog):
                    groups = tuple(item.exclusion_group_id for item in matching if item is not None)
                    if len(set(groups)) == len(groups):
                        matchings.append(matching)
                matchings_by_probe.append(tuple(matchings))

            for probe_matchings in itertools.product(*matchings_by_probe):
                assignments: list[list[ProbeAssignment]] = [[] for _item in fixed]
                for probe, matching in zip(problem.probes, probe_matchings, strict=True):
                    for index, observation in enumerate(matching):
                        if observation is not None:
                            assignments[index].append(
                                ProbeAssignment(probe.probe_id, observation.observation_id)
                            )
                schedules = tuple(
                    JointSatelliteSchedule(
                        hypothesis_id=hypothesis.hypothesis_id,
                        activity_by_cell=tuple(activities[index]),
                        assignments=tuple(assignments[index]),
                    )
                    for index, hypothesis in enumerate(fixed)
                )
                try:
                    association = evaluate_joint_satellite_schedule(
                        problem,
                        fixed,
                        schedules,
                    )
                except ValueError:
                    continue
                candidates.append((_candidate_key(association, fixed), association, fixed))
    _key, association, hypotheses = min(candidates, key=lambda item: item[0])
    return association, hypotheses


def test_conflict_reprofiles_every_state_and_changes_the_catalog_state() -> None:
    problem, banks = _conflicting_state_case()
    independent_state_ids = tuple(
        min(
            bank.states,
            key=lambda state: (
                decode_single_satellite(problem, state).objective.total_cost,
                state.hypothesis_id,
            ),
        ).hypothesis_id
        for bank in banks
    )

    receipt = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
    result = receipt.association
    assigned = {
        item.catalog_number: tuple(assignment.observation_id for assignment in item.assignments)
        for item in result.satellites
    }

    assert independent_state_ids == ("cat10-g", "cat20-g")
    assert receipt.selected_state_ids == ("cat10-g", "cat20-h")
    assert assigned == {10: ("o-0-g",), 20: ("o-0-h",)}
    assert result.objective.total_cost == pytest.approx(1.0)
    assert result.algorithm == ALGORITHM
    assert result.exact and receipt.exact
    assert receipt.accounting.conflict_branches > 0
    assert receipt.accounting.catalog_oracle_evaluations > len(banks)


def test_one_profiled_state_is_fixed_across_multiple_activity_episodes() -> None:
    problem = _problem(
        cell_count=3,
        observations=(
            _observation(
                probe_index=0,
                label="first",
                group_id="first",
                cfo_hz=10.0,
                clutter_cost=8.0,
            ),
            _observation(
                probe_index=2,
                label="second",
                group_id="second",
                cfo_hz=10.0,
                clutter_cost=8.0,
            ),
        ),
        missed_detection_cost=10.0,
        satellite_cost=1.0,
        episode_cost=0.5,
    )
    banks = (
        _bank(
            10,
            _state(
                problem,
                hypothesis_id="cat10-wrong",
                catalog_number=10,
                predicted_cfo_hz=0.0,
            ),
            _state(
                problem,
                hypothesis_id="cat10-right",
                catalog_number=10,
                predicted_cfo_hz=7.0,
                delay_s=0.2,
                cfo_offset_hz=3.0,
            ),
        ),
    )

    receipt = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
    decision = receipt.association.satellites[0]

    assert receipt.selected_state_ids == ("cat10-right",)
    assert [(item.start_cell, item.end_cell_exclusive) for item in decision.episodes] == [
        (0, 1),
        (2, 3),
    ]
    assert decision.hypothesis_id == "cat10-right"
    assert decision.delay_s == pytest.approx(0.2)
    assert decision.cfo_offset_hz == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("satellite_cost", "selected"),
    ((2.0, (10, 20)), (8.0, (10,)), (12.0, ())),
)
def test_linear_catalog_penalty_selects_two_then_one_then_null(
    satellite_cost: float,
    selected: tuple[int, ...],
) -> None:
    problem = _problem(
        cell_count=2,
        observations=(
            _observation(
                probe_index=0,
                label="strong",
                group_id="strong",
                cfo_hz=0.0,
                clutter_cost=10.0,
                sigma_hz=0.1,
            ),
            _observation(
                probe_index=1,
                label="weak",
                group_id="weak",
                cfo_hz=100.0,
                clutter_cost=6.0,
                sigma_hz=0.1,
            ),
        ),
        satellite_cost=satellite_cost,
    )
    banks = (
        _bank(
            10,
            _state(
                problem,
                hypothesis_id="cat10-only",
                catalog_number=10,
                predicted_cfo_hz=0.0,
                eligible_probe_ids=("p-0",),
            ),
        ),
        _bank(
            20,
            _state(
                problem,
                hypothesis_id="cat20-only",
                catalog_number=20,
                predicted_cfo_hz=100.0,
                eligible_probe_ids=("p-1",),
            ),
        ),
    )

    result = decode_arbitrary_n_grouped_nuisance_states(problem, banks).association

    assert result.selected_catalog_numbers == selected


def test_four_catalog_no_conflict_fast_path_and_permutation_invariance() -> None:
    problem = _problem(
        cell_count=4,
        observations=tuple(
            _observation(
                probe_index=index,
                label=str(index),
                group_id=f"group-{index}",
                cfo_hz=float(index * 10),
                clutter_cost=6.0,
                sigma_hz=0.1,
            )
            for index in range(4)
        ),
        satellite_cost=1.0,
    )
    banks = tuple(
        _bank(
            100 + index,
            _state(
                problem,
                hypothesis_id=f"cat{100 + index}-z",
                catalog_number=100 + index,
                predicted_cfo_hz=float(index * 10),
                eligible_probe_ids=(f"p-{index}",),
            ),
            _state(
                problem,
                hypothesis_id=f"cat{100 + index}-a",
                catalog_number=100 + index,
                predicted_cfo_hz=float(index * 10),
                eligible_probe_ids=(f"p-{index}",),
            ),
        )
        for index in range(4)
    )
    permuted = tuple(
        CatalogNuisanceStateBank(
            catalog_number=bank.catalog_number,
            states=tuple(reversed(bank.states)),
        )
        for bank in reversed(banks)
    )

    receipt = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
    reversed_receipt = decode_arbitrary_n_grouped_nuisance_states(problem, permuted)

    assert receipt == reversed_receipt
    assert receipt.association.selected_catalog_numbers == (100, 101, 102, 103)
    assert receipt.selected_state_ids == (
        "cat100-a",
        "cat101-a",
        "cat102-a",
        "cat103-a",
    )
    assert receipt.accounting.nodes_evaluated == 1
    assert receipt.accounting.state_decodes == 8
    assert receipt.accounting.root_was_conflict_free


def test_randomized_tiny_cases_match_state_activity_assignment_brute_force() -> None:
    source = random.Random(419_337)
    for case_index in range(3):
        problem = _problem(
            cell_count=2,
            observations=tuple(
                _observation(
                    probe_index=probe_index,
                    label=f"{case_index}",
                    group_id=f"group-{probe_index}",
                    cfo_hz=source.choice((0.0, 3.0)) + source.uniform(-0.2, 0.2),
                    clutter_cost=source.uniform(2.0, 7.0),
                    matched_base_cost=source.uniform(0.0, 0.7),
                    sigma_hz=0.8,
                )
                for probe_index in range(2)
            ),
            minimum_active_cells=source.choice((1, 2)),
            missed_detection_cost=source.uniform(0.5, 3.0),
            satellite_cost=source.uniform(0.0, 2.0),
            episode_cost=source.uniform(0.0, 1.0),
        )
        banks = tuple(
            _bank(
                10 + catalog_index,
                *(
                    _state(
                        problem,
                        hypothesis_id=(f"cat{10 + catalog_index}-state{state_index}-{case_index}"),
                        catalog_number=10 + catalog_index,
                        predicted_cfo_hz=float(catalog_index * 3 + state_index),
                        delay_prior_cost=source.uniform(0.0, 0.4),
                    )
                    for state_index in range(2)
                ),
            )
            for catalog_index in range(2)
        )

        expected, expected_hypotheses = _brute_force(problem, banks)
        receipt = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
        state_by_id = {state.hypothesis_id: state for bank in banks for state in bank.states}
        actual_hypotheses = tuple(
            state_by_id[item.hypothesis_id] for item in receipt.association.satellites
        )

        assert receipt.association.objective.total_cost == pytest.approx(
            expected.objective.total_cost
        )
        assert (
            _candidate_key(receipt.association, actual_hypotheses)[1:]
            == _candidate_key(expected, expected_hypotheses)[1:]
        )


def test_state_profile_keeps_reduced_difference_hidden_by_common_background() -> None:
    problem = _problem(
        cell_count=2,
        observations=(
            _observation(
                probe_index=0,
                label="signal",
                group_id="signal",
                cfo_hz=0.0,
                clutter_cost=10.0,
            ),
            _observation(
                probe_index=1,
                label="background",
                group_id="background",
                cfo_hz=100.0,
                clutter_cost=1e16,
            ),
        ),
    )
    worse_but_lexical = _state(
        problem,
        hypothesis_id="cat10-a-worse",
        catalog_number=10,
        predicted_cfo_hz=1.0,
        eligible_probe_ids=("p-0",),
    )
    better_but_later = _state(
        problem,
        hypothesis_id="cat10-z-better",
        catalog_number=10,
        predicted_cfo_hz=0.0,
        eligible_probe_ids=("p-0",),
    )
    background_consumer = _state(
        problem,
        hypothesis_id="cat20-background",
        catalog_number=20,
        predicted_cfo_hz=100.0,
        eligible_probe_ids=("p-1",),
    )
    banks = (
        _bank(10, worse_but_lexical, better_but_later),
        _bank(20, background_consumer),
    )
    worse_result = decode_single_satellite(problem, worse_but_lexical)
    better_result = decode_single_satellite(problem, better_but_later)

    scalable = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
    worse_joint = evaluate_joint_satellite_schedule(
        problem,
        (worse_but_lexical, background_consumer),
        (
            JointSatelliteSchedule(
                hypothesis_id=worse_but_lexical.hypothesis_id,
                activity_by_cell=(True, False),
                assignments=(ProbeAssignment("p-0", "o-0-signal"),),
            ),
            JointSatelliteSchedule(
                hypothesis_id=background_consumer.hypothesis_id,
                activity_by_cell=(False, True),
                assignments=(ProbeAssignment("p-1", "o-1-background"),),
            ),
        ),
    )

    assert worse_result.objective.total_cost == better_result.objective.total_cost == 1e16
    assert worse_result.objective.residual_cost > better_result.objective.residual_cost
    assert scalable.selected_state_ids == ("cat10-z-better", "cat20-background")
    assert scalable.association.objective.total_cost == 0.0
    assert worse_joint.objective.total_cost == 0.5


def test_node_and_state_decode_caps_fail_closed_with_partial_accounting() -> None:
    problem, banks = _conflicting_state_case()

    with pytest.raises(ExactGroupedSearchLimitExceeded) as node_caught:
        decode_arbitrary_n_grouped_nuisance_states(
            problem,
            banks,
            limits=ExactGroupedSearchLimits(max_nodes=1, max_state_decodes=100),
        )
    assert node_caught.value.limit_kind == "nodes"
    assert node_caught.value.accounting.nodes_evaluated == 1
    assert node_caught.value.accounting.conflict_branches == 1
    assert "before proving optimality" in str(node_caught.value)

    with pytest.raises(ExactGroupedSearchLimitExceeded) as state_caught:
        decode_arbitrary_n_grouped_nuisance_states(
            problem,
            banks,
            limits=ExactGroupedSearchLimits(max_nodes=100, max_state_decodes=3),
        )
    assert state_caught.value.limit_kind == "state_decodes"
    assert state_caught.value.accounting.state_decodes == 3
    assert state_caught.value.accounting.nodes_evaluated == 0


def test_grouped_large_clutter_lower_bound_uses_primitive_reduced_terms() -> None:
    clutter_cost = 1.7e16
    problem = _problem(
        cell_count=1,
        missed_detection_cost=0.0,
        observations=(
            _observation(
                probe_index=0,
                label="g",
                group_id="G",
                cfo_hz=0.0,
                clutter_cost=clutter_cost,
            ),
            _observation(
                probe_index=0,
                label="j",
                group_id="J",
                cfo_hz=100.0,
                clutter_cost=3.0,
            ),
            _observation(
                probe_index=0,
                label="h",
                group_id="H",
                cfo_hz=-9.944904871522333,
                clutter_cost=clutter_cost,
            ),
        ),
    )
    banks = (
        _bank(
            10,
            _state(
                problem,
                hypothesis_id="cat10-only",
                catalog_number=10,
                predicted_cfo_hz=0.0,
            ),
        ),
        _bank(
            20,
            _state(
                problem,
                hypothesis_id="cat20-only",
                catalog_number=20,
                predicted_cfo_hz=8.092304466474555,
            ),
        ),
    )

    receipt = decode_arbitrary_n_grouped_nuisance_states(problem, banks)
    assignments = {
        item.catalog_number: tuple(assignment.observation_id for assignment in item.assignments)
        for item in receipt.association.satellites
    }

    assert assignments == {10: ("o-0-h",), 20: ("o-0-g",)}
    assert receipt.association.objective.total_cost == pytest.approx(20.037209337996888)
    assert receipt.exact


def test_rejects_bad_banks_duplicate_ids_truncation_and_invalid_limits() -> None:
    problem = _problem(cell_count=1, observations=())
    cat10 = _state(
        problem,
        hypothesis_id="shared-state",
        catalog_number=10,
        predicted_cfo_hz=0.0,
    )
    cat20 = _state(
        problem,
        hypothesis_id="cat20-state",
        catalog_number=20,
        predicted_cfo_hz=0.0,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        CatalogNuisanceStateBank(catalog_number=10, states=())
    with pytest.raises(ValueError, match="match its state-bank catalog"):
        CatalogNuisanceStateBank(catalog_number=10, states=(cat20,))
    with pytest.raises(ValueError, match="unique within a catalog"):
        CatalogNuisanceStateBank(catalog_number=10, states=(cat10, cat10))
    with pytest.raises(ValueError, match="share one object name"):
        CatalogNuisanceStateBank(
            catalog_number=10,
            states=(cat10, replace(cat10, hypothesis_id="renamed", object_name="ALIAS")),
        )
    with pytest.raises(ValueError, match="unique catalog numbers"):
        decode_arbitrary_n_grouped_nuisance_states(
            problem,
            (_bank(10, cat10), _bank(10, cat10)),
        )
    duplicate_global = replace(cat20, hypothesis_id=cat10.hypothesis_id)
    with pytest.raises(ValueError, match="globally unique"):
        decode_arbitrary_n_grouped_nuisance_states(
            problem,
            (_bank(10, cat10), _bank(20, duplicate_global)),
        )
    with pytest.raises(ValueError, match="untruncated"):
        decode_arbitrary_n_grouped_nuisance_states(
            replace(problem, truncated_observation_count=1),
            (_bank(10, cat10),),
        )
    with pytest.raises(ValueError, match="positive integer"):
        ExactGroupedSearchLimits(max_nodes=0)
    with pytest.raises(ValueError, match="positive integer"):
        ExactGroupedSearchLimits(max_state_decodes=True)


def test_grouped_solver_imports_no_infrastructure() -> None:
    path = Path(grouped_module.__file__)
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    forbidden = (
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "httpx",
        "typer",
        "leo.storage",
        "leo.operations",
        "leo.api",
        "leo.cli",
    )
    assert not {
        module
        for module in imported
        for root in forbidden
        if module == root or module.startswith(f"{root}.")
    }
