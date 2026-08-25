from __future__ import annotations

import ast
import itertools
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research import scalable_multi_satellite_activity as scalable_module
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
    evaluate_single_satellite_schedule,
)
from leo.analysis.research.scalable_multi_satellite_activity import (
    ALGORITHM,
    ExactJointSearchLimitExceeded,
    ExactJointSearchLimits,
    decode_arbitrary_n_fixed_hypotheses,
)

TEST_COMPONENT = "component:scalable-joint-test"


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
                time_s=0.025 + index * 0.1,
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


def _hypothesis(
    problem: SatelliteActivityProblem,
    *,
    label: str,
    catalog_number: int,
    predicted_cfo_hz: float,
    eligible_probe_ids: tuple[str, ...] | None = None,
) -> SingleSatelliteHypothesis:
    return SingleSatelliteHypothesis(
        hypothesis_id=f"hypothesis-{label}",
        object_name=f"SATELLITE-{label}",
        catalog_number=catalog_number,
        delay_s=0.0,
        cfo_offset_hz=0.0,
        delay_prior_cost=0.0,
        predictions=tuple(
            PredictedProbeCfo(probe.probe_id, predicted_cfo_hz) for probe in problem.probes
        ),
        eligible_probe_ids=eligible_probe_ids,
    )


def _result_key(result: JointSatelliteAssociationResult) -> tuple[object, ...]:
    return (
        result.objective.total_cost,
        len(result.selected_catalog_numbers),
        sum(len(item.episodes) for item in result.satellites),
        sum(sum(item.activity_by_cell) for item in result.satellites),
        tuple(not item.selected for item in result.satellites),
        tuple(item.activity_by_cell for item in result.satellites),
        sum(len(item.assignments) for item in result.satellites),
        tuple(
            (item.hypothesis_id, assignment.probe_id, assignment.observation_id)
            for item in result.satellites
            for assignment in item.assignments
        ),
    )


def _brute_force(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> JointSatelliteAssociationResult:
    """Independent tiny oracle over activity masks and per-probe matchings."""

    activity_masks = tuple(itertools.product((False, True), repeat=problem.grid.cell_count))
    observations_by_probe = {
        probe.probe_id: tuple(
            item for item in problem.observations if item.probe_id == probe.probe_id
        )
        for probe in problem.probes
    }
    candidates: list[JointSatelliteAssociationResult] = []
    for activities in itertools.product(activity_masks, repeat=len(hypotheses)):
        matchings_by_probe: list[tuple[tuple[CfoCandidate | None, ...], ...]] = []
        for probe in problem.probes:
            choices_by_hypothesis = tuple(
                (None, *observations_by_probe[probe.probe_id])
                if activities[index][probe.cell_index]
                else (None,)
                for index in range(len(hypotheses))
            )
            matchings = []
            for matching in itertools.product(*choices_by_hypothesis):
                groups = tuple(item.exclusion_group_id for item in matching if item is not None)
                if len(set(groups)) == len(groups):
                    matchings.append(matching)
            matchings_by_probe.append(tuple(matchings))

        for probe_matchings in itertools.product(*matchings_by_probe):
            assignments: list[list[ProbeAssignment]] = [[] for _item in hypotheses]
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
                for index, hypothesis in enumerate(hypotheses)
            )
            try:
                candidates.append(evaluate_joint_satellite_schedule(problem, hypotheses, schedules))
            except ValueError:
                continue
    return min(candidates, key=_result_key)


def _conflict_case() -> tuple[SatelliteActivityProblem, tuple[SingleSatelliteHypothesis, ...]]:
    problem = _problem(
        cell_count=1,
        observations=(
            _observation(
                probe_index=0,
                label="g-primary",
                group_id="physical-g",
                cfo_hz=0.0,
                clutter_cost=10.0,
            ),
            _observation(
                probe_index=0,
                label="g-alias",
                group_id="physical-g",
                cfo_hz=0.2,
                clutter_cost=10.0,
            ),
            _observation(
                probe_index=0,
                label="h",
                group_id="physical-h",
                cfo_hz=1.0,
                clutter_cost=8.0,
            ),
        ),
    )
    return problem, (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=1.0),
    )


def test_conflict_branch_uses_second_best_and_forbids_every_alias_in_group() -> None:
    problem, hypotheses = _conflict_case()

    receipt = decode_arbitrary_n_fixed_hypotheses(problem, hypotheses)
    result = receipt.association
    assignments = {
        item.catalog_number: tuple(assignment.observation_id for assignment in item.assignments)
        for item in result.satellites
    }

    assert assignments == {10: ("o-0-g-primary",), 20: ("o-0-h",)}
    assert result.objective.total_cost == pytest.approx(0.0)
    assert result.algorithm == ALGORITHM
    assert result.exact
    assert receipt.accounting.conflict_branches > 0
    assert not receipt.accounting.root_was_conflict_free


def test_no_conflict_is_one_node_and_is_permutation_invariant_for_four_hypotheses() -> None:
    observations = tuple(
        _observation(
            probe_index=index,
            label=str(index),
            group_id=f"group-{index}",
            cfo_hz=float(index * 10),
            clutter_cost=6.0,
            sigma_hz=0.1,
        )
        for index in range(4)
    )
    problem = _problem(cell_count=4, observations=observations, satellite_cost=1.0)
    hypotheses = tuple(
        _hypothesis(
            problem,
            label=str(index),
            catalog_number=100 + index,
            predicted_cfo_hz=float(index * 10),
            eligible_probe_ids=(f"p-{index}",),
        )
        for index in range(4)
    )

    receipt = decode_arbitrary_n_fixed_hypotheses(problem, hypotheses)
    reversed_receipt = decode_arbitrary_n_fixed_hypotheses(problem, tuple(reversed(hypotheses)))

    assert receipt.association.selected_catalog_numbers == (100, 101, 102, 103)
    assert receipt.association == reversed_receipt.association
    assert receipt.accounting.nodes_evaluated == 1
    assert receipt.accounting.nodes_expanded == 1
    assert receipt.accounting.single_decodes == 4
    assert receipt.accounting.conflict_branches == 0
    assert receipt.accounting.root_was_conflict_free


@pytest.mark.parametrize(
    ("satellite_cost", "selected"),
    ((2.0, (10, 20)), (8.0, (10,)), (12.0, ())),
)
def test_linear_n_penalty_selects_two_then_one_then_null(
    satellite_cost: float,
    selected: tuple[int, ...],
) -> None:
    observations = (
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
    )
    problem = _problem(
        cell_count=2,
        observations=observations,
        satellite_cost=satellite_cost,
    )
    hypotheses = (
        _hypothesis(
            problem,
            label="strong",
            catalog_number=10,
            predicted_cfo_hz=0.0,
            eligible_probe_ids=("p-0",),
        ),
        _hypothesis(
            problem,
            label="weak",
            catalog_number=20,
            predicted_cfo_hz=100.0,
            eligible_probe_ids=("p-1",),
        ),
    )

    result = decode_arbitrary_n_fixed_hypotheses(problem, hypotheses).association

    assert result.selected_catalog_numbers == selected


def test_randomized_tiny_cases_match_independent_brute_force() -> None:
    source = random.Random(847_112)
    for case_index in range(4):
        observations = tuple(
            _observation(
                probe_index=probe_index,
                label=f"{case_index}",
                group_id=f"g-{probe_index}",
                cfo_hz=source.choice((0.0, 2.0, 4.0)) + source.uniform(-0.2, 0.2),
                clutter_cost=source.uniform(2.0, 7.0),
                matched_base_cost=source.uniform(0.0, 0.8),
                sigma_hz=0.8,
            )
            for probe_index in range(2)
        )
        problem = _problem(
            cell_count=2,
            minimum_active_cells=source.choice((1, 2)),
            observations=observations,
            missed_detection_cost=source.uniform(0.5, 3.0),
            satellite_cost=source.uniform(0.0, 2.0),
            episode_cost=source.uniform(0.0, 1.0),
        )
        hypotheses = tuple(
            _hypothesis(
                problem,
                label=f"{case_index}-{index}",
                catalog_number=100 + index,
                predicted_cfo_hz=float(index * 2),
            )
            for index in range(3)
        )

        expected = _brute_force(problem, hypotheses)
        actual = decode_arbitrary_n_fixed_hypotheses(problem, hypotheses).association

        assert actual.objective.total_cost == pytest.approx(expected.objective.total_cost)
        assert _result_key(actual)[1:] == _result_key(expected)[1:]


def test_one_hypothesis_is_supported_and_candidate_truncation_is_rejected() -> None:
    problem = _problem(cell_count=1, observations=())
    hypothesis = _hypothesis(
        problem,
        label="only",
        catalog_number=42,
        predicted_cfo_hz=0.0,
    )

    receipt = decode_arbitrary_n_fixed_hypotheses(problem, (hypothesis,))

    assert receipt.association.selected_catalog_numbers == ()
    assert receipt.accounting.hypothesis_count == 1
    with pytest.raises(ValueError, match="untruncated"):
        decode_arbitrary_n_fixed_hypotheses(
            replace(problem, truncated_observation_count=1),
            (hypothesis,),
        )


def test_node_cap_fails_closed_with_partial_accounting() -> None:
    problem, hypotheses = _conflict_case()

    with pytest.raises(ExactJointSearchLimitExceeded) as caught:
        decode_arbitrary_n_fixed_hypotheses(
            problem,
            hypotheses,
            limits=ExactJointSearchLimits(max_nodes=1),
        )

    assert caught.value.limits.max_nodes == 1
    assert caught.value.accounting.nodes_evaluated == 1
    assert caught.value.accounting.nodes_expanded == 1
    assert caught.value.accounting.conflict_branches == 1
    assert "before proving optimality" in str(caught.value)


def test_large_clutter_cancellation_cannot_overestimate_a_child_lower_bound() -> None:
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
                label="h",
                group_id="H",
                cfo_hz=-9.944904871522333,
                clutter_cost=clutter_cost,
            ),
            _observation(
                probe_index=0,
                label="j",
                group_id="J",
                cfo_hz=100.0,
                clutter_cost=3.0,
            ),
        ),
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(
            problem,
            label="B",
            catalog_number=20,
            predicted_cfo_hz=8.092304466474555,
        ),
    )

    receipt = decode_arbitrary_n_fixed_hypotheses(problem, hypotheses)
    assignments = {
        item.catalog_number: tuple(assignment.observation_id for assignment in item.assignments)
        for item in receipt.association.satellites
    }

    assert assignments == {10: ("o-0-h",), 20: ("o-0-g",)}
    assert receipt.association.objective.total_cost == pytest.approx(20.037209337996888)
    assert receipt.exact


def test_lower_bound_flattens_each_baseline_clutter_group_before_cancellation() -> None:
    problem = _problem(
        cell_count=1,
        missed_detection_cost=0.0,
        observations=(
            _observation(
                probe_index=0,
                label="large",
                group_id="large",
                cfo_hz=0.0,
                clutter_cost=1e16,
            ),
            _observation(
                probe_index=0,
                label="tiny",
                group_id="tiny",
                cfo_hz=100.0,
                clutter_cost=1.0,
            ),
        ),
    )
    hypothesis = _hypothesis(
        problem,
        label="baseline",
        catalog_number=10,
        predicted_cfo_hz=0.0,
    )
    schedule = evaluate_single_satellite_schedule(
        problem,
        hypothesis,
        (True,),
        (ProbeAssignment("p-0", "o-0-large"),),
    )
    clutter_by_group = {"large": 1e16, "tiny": 1.0}

    lower_bound = scalable_module._independent_lower_bound(
        problem,
        (hypothesis,),
        (schedule,),
        clutter_by_group,
    )
    prematurely_rounded = math.fsum(
        [math.fsum(clutter_by_group.values()), -clutter_by_group["large"]]
    )

    assert lower_bound == 1.0
    assert prematurely_rounded == 0.0


def test_reduced_terms_flatten_each_matched_base_before_clutter_cancellation() -> None:
    problem = _problem(
        cell_count=2,
        minimum_active_cells=2,
        missed_detection_cost=100.0,
        observations=(
            _observation(
                probe_index=0,
                label="large",
                group_id="large",
                cfo_hz=0.0,
                clutter_cost=1e16,
                matched_base_cost=1e16,
            ),
            _observation(
                probe_index=1,
                label="small",
                group_id="small",
                cfo_hz=0.0,
                clutter_cost=10.0,
                matched_base_cost=1.0,
            ),
        ),
    )
    hypothesis = _hypothesis(
        problem,
        label="matched",
        catalog_number=10,
        predicted_cfo_hz=0.0,
    )
    schedule = evaluate_single_satellite_schedule(
        problem,
        hypothesis,
        (True, True),
        (
            ProbeAssignment("p-0", "o-0-large"),
            ProbeAssignment("p-1", "o-1-small"),
        ),
    )
    clutter_by_group = {"large": 1e16, "small": 10.0}

    terms = scalable_module._single_reduced_terms(
        problem,
        hypothesis,
        schedule,
        clutter_by_group,
    )
    premature_matched_sum = math.fsum((1e16, 1.0))

    assert math.fsum(terms) == -9.0
    assert math.fsum((premature_matched_sum, -1e16, -10.0)) == -10.0


def test_unrepresentable_strict_forbidden_margin_fails_closed() -> None:
    problem = _problem(
        cell_count=1,
        missed_detection_cost=0.0,
        observations=(
            _observation(
                probe_index=0,
                label="maximum",
                group_id="maximum",
                cfo_hz=0.0,
                clutter_cost=sys.float_info.max,
            ),
        ),
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=0.0),
    )

    with pytest.raises(ValueError, match="dominance cost is not finitely representable"):
        decode_arbitrary_n_fixed_hypotheses(problem, hypotheses)


def test_validates_limits_unique_catalogs_and_imports_no_infrastructure() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ExactJointSearchLimits(max_nodes=0)
    with pytest.raises(ValueError, match="positive integer"):
        ExactJointSearchLimits(max_nodes=True)

    problem = _problem(cell_count=1, observations=())
    hypothesis = _hypothesis(
        problem,
        label="one",
        catalog_number=10,
        predicted_cfo_hz=0.0,
    )
    with pytest.raises(ValueError, match="one hypothesis per catalog"):
        decode_arbitrary_n_fixed_hypotheses(
            problem,
            (hypothesis, replace(hypothesis, hypothesis_id="duplicate")),
        )

    path = Path(scalable_module.__file__)
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
