from __future__ import annotations

import ast
import itertools
import random
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research import multi_satellite_activity as joint_module
from leo.analysis.research.multi_satellite_activity import (
    JointSatelliteAssociationResult,
    JointSatelliteDecision,
    JointSatelliteSchedule,
    decode_joint_fixed_hypotheses,
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

TEST_COMPONENT = "component:joint-test"


def _probes(
    cell_count: int,
    *,
    missed_detection_cost: float = 4.0,
) -> tuple[CfoProbe, ...]:
    return tuple(
        CfoProbe(
            probe_id=f"p-{index}",
            time_s=index * 0.1 + 0.025,
            cell_index=index,
            missed_detection_cost=missed_detection_cost,
        )
        for index in range(cell_count)
    )


def _problem(
    *,
    cell_count: int,
    minimum_active_cells: int,
    observations: tuple[CfoCandidate, ...],
    probes: tuple[CfoProbe, ...] | None = None,
    satellite_cost: float = 2.0,
    episode_cost: float = 1.0,
    left_censored: bool = False,
    right_censored: bool = False,
) -> SatelliteActivityProblem:
    return SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=0.1,
            cell_count=cell_count,
            minimum_active_cells=minimum_active_cells,
            allow_left_censored=left_censored,
            allow_right_censored=right_censored,
        ),
        probes=_probes(cell_count) if probes is None else probes,
        observations=observations,
        costs=AssociationCostModel(
            satellite_cost=satellite_cost,
            episode_cost=episode_cost,
            huber_threshold=1.0,
        ),
    )


def _hypothesis(
    problem: SatelliteActivityProblem,
    *,
    label: str,
    catalog_number: int,
    predicted_cfo_hz: float,
    cfo_offset_hz: float = 0.0,
    delay_s: float = 0.0,
    delay_prior_cost: float = 0.0,
    eligible_probe_ids: tuple[str, ...] | None = None,
) -> SingleSatelliteHypothesis:
    return SingleSatelliteHypothesis(
        hypothesis_id=f"hypothesis-{label}",
        object_name=f"SATELLITE-{label}",
        catalog_number=catalog_number,
        delay_s=delay_s,
        cfo_offset_hz=cfo_offset_hz,
        delay_prior_cost=delay_prior_cost,
        predictions=tuple(
            PredictedProbeCfo(probe.probe_id, predicted_cfo_hz) for probe in problem.probes
        ),
        eligible_probe_ids=eligible_probe_ids,
    )


def _observation(
    probe_index: int,
    label: str,
    cfo_hz: float,
    *,
    clutter_cost: float,
    matched_base_cost: float = 0.0,
    sigma_hz: float = 1.0,
    exclusion_group_id: str | None = None,
) -> CfoCandidate:
    return CfoCandidate(
        observation_id=f"o-{probe_index}-{label}",
        probe_id=f"p-{probe_index}",
        exclusion_group_id=(
            f"group-{probe_index}-{label}" if exclusion_group_id is None else exclusion_group_id
        ),
        cfo_hz=cfo_hz,
        sigma_hz=sigma_hz,
        clutter_cost=clutter_cost,
        matched_base_cost=matched_base_cost,
        component_id=TEST_COMPONENT,
    )


def _by_catalog(result: JointSatelliteAssociationResult) -> dict[int, JointSatelliteDecision]:
    return {item.catalog_number: item for item in result.satellites}


def test_joint_objective_counts_clutter_once_and_every_selected_satellite_term() -> None:
    observations = (
        _observation(0, "a", 10.0, clutter_cost=5.0, matched_base_cost=1.0),
        _observation(0, "b", 100.0, clutter_cost=7.0, matched_base_cost=0.5),
        _observation(0, "junk", 500.0, clutter_cost=2.0),
        _observation(1, "a", 10.0, clutter_cost=4.0, matched_base_cost=0.25),
    )
    probes = (
        CfoProbe("p-0", 0.025, 0, 2.0),
        CfoProbe("p-1", 0.125, 1, 3.0),
    )
    problem = _problem(
        cell_count=2,
        minimum_active_cells=1,
        probes=probes,
        observations=observations,
        satellite_cost=3.0,
        episode_cost=2.0,
    )
    first = _hypothesis(
        problem,
        label="A",
        catalog_number=10,
        predicted_cfo_hz=10.0,
        delay_prior_cost=0.4,
    )
    second = _hypothesis(
        problem,
        label="B",
        catalog_number=20,
        predicted_cfo_hz=100.0,
        delay_prior_cost=0.6,
    )

    result = evaluate_joint_satellite_schedule(
        problem,
        (first, second),
        (
            JointSatelliteSchedule(
                first.hypothesis_id,
                (True, True),
                (ProbeAssignment("p-0", "o-0-a"), ProbeAssignment("p-1", "o-1-a")),
            ),
            JointSatelliteSchedule(
                second.hypothesis_id,
                (True, True),
                (ProbeAssignment("p-0", "o-0-b"),),
            ),
        ),
    )

    assert result.selected_catalog_numbers == (10, 20)
    assert result.objective.clutter_cost == pytest.approx(2.0)
    assert result.objective.matched_base_cost == pytest.approx(1.75)
    assert result.objective.residual_cost == pytest.approx(0.0)
    assert result.objective.missed_detection_cost == pytest.approx(3.0)
    assert result.objective.satellite_cost == pytest.approx(6.0)
    assert result.objective.episode_cost == pytest.approx(4.0)
    assert result.objective.delay_prior_cost == pytest.approx(1.0)
    assert result.objective.null_cost == pytest.approx(18.0)
    assert result.objective.total_cost == pytest.approx(17.75)
    assert result.unexplained_observation_ids == ("o-0-junk",)


def test_satellite_and_delay_prior_are_paid_once_across_two_episodes() -> None:
    probes = _probes(3, missed_detection_cost=0.0)
    problem = _problem(
        cell_count=3,
        minimum_active_cells=1,
        probes=probes,
        observations=(),
        satellite_cost=3.0,
        episode_cost=2.0,
    )
    first = _hypothesis(
        problem,
        label="A",
        catalog_number=10,
        predicted_cfo_hz=0.0,
        delay_prior_cost=0.4,
    )
    second = _hypothesis(
        problem,
        label="B",
        catalog_number=20,
        predicted_cfo_hz=100.0,
        delay_prior_cost=0.6,
    )

    result = evaluate_joint_satellite_schedule(
        problem,
        (first, second),
        (JointSatelliteSchedule(first.hypothesis_id, (True, False, True)),),
    )

    assert result.selected_catalog_numbers == (10,)
    assert len(result.satellites[0].episodes) == 2
    assert result.objective.satellite_cost == pytest.approx(3.0)
    assert result.objective.episode_cost == pytest.approx(4.0)
    assert result.objective.delay_prior_cost == pytest.approx(0.4)


def test_distinct_groups_at_one_probe_feed_simultaneous_satellites() -> None:
    observations = (
        _observation(0, "low", 0.0, clutter_cost=10.0),
        _observation(0, "middle", 100.0, clutter_cost=10.0),
        _observation(0, "high", 200.0, clutter_cost=10.0),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=observations,
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(problem, label="LOW", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="MIDDLE", catalog_number=20, predicted_cfo_hz=100.0),
        _hypothesis(problem, label="HIGH", catalog_number=30, predicted_cfo_hz=200.0),
    )

    result = decode_joint_fixed_hypotheses(problem, hypotheses)

    assert result.selected_catalog_numbers == (10, 20, 30)
    assert {
        assignment.observation_id
        for satellite in result.satellites
        for assignment in satellite.assignments
    } == {"o-0-low", "o-0-middle", "o-0-high"}
    assert all(item.activity_by_cell == (True,) for item in result.satellites)
    assert result.objective.total_cost == pytest.approx(3.0)


def test_physical_alias_group_cannot_be_split_between_satellites() -> None:
    aliases = (
        _observation(
            0,
            "alias-low",
            0.0,
            clutter_cost=5.0,
            exclusion_group_id="one-physical-peak",
        ),
        _observation(
            0,
            "alias-high",
            100.0,
            clutter_cost=5.0,
            exclusion_group_id="one-physical-peak",
        ),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=aliases,
    )
    first = _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0)
    second = _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0)

    with pytest.raises(ValueError, match="physical exclusion group"):
        evaluate_joint_satellite_schedule(
            problem,
            (first, second),
            (
                JointSatelliteSchedule(
                    first.hypothesis_id,
                    (True,),
                    (ProbeAssignment("p-0", "o-0-alias-low"),),
                ),
                JointSatelliteSchedule(
                    second.hypothesis_id,
                    (True,),
                    (ProbeAssignment("p-0", "o-0-alias-high"),),
                ),
            ),
        )

    decoded = decode_joint_fixed_hypotheses(problem, (first, second))
    assignments = [item for satellite in decoded.satellites for item in satellite.assignments]
    assert len(assignments) == 1
    assert decoded.objective.clutter_cost == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("satellite_cost", "expected"),
    ((0.0, (10, 20)), (9.0, (10,)), (13.0, ())),
)
def test_selection_penalty_changes_two_to_one_to_null(
    satellite_cost: float,
    expected: tuple[int, ...],
) -> None:
    observations = (
        _observation(0, "strong", 0.0, clutter_cost=12.0),
        _observation(0, "weak", 100.0, clutter_cost=7.0),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=observations,
        satellite_cost=satellite_cost,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )

    result = decode_joint_fixed_hypotheses(problem, hypotheses)

    assert result.selected_catalog_numbers == expected
    assert result.objective.satellite_cost == pytest.approx(satellite_cost * len(expected))
    if not expected:
        assert result.objective.total_cost == pytest.approx(result.objective.null_cost)


def _duration_case(*, include_second_satellite_fifth_peak: bool) -> JointSatelliteAssociationResult:
    observations = []
    for cell in range(5):
        observations.append(_observation(cell, "a", 0.0, clutter_cost=2.0))
    for cell in range(1, 5):
        observations.append(_observation(cell, "b", 100.0, clutter_cost=2.0))
    if include_second_satellite_fifth_peak:
        observations.append(_observation(5, "b", 100.0, clutter_cost=2.0))
    probes = _probes(6, missed_detection_cost=20.0)
    problem = _problem(
        cell_count=6,
        minimum_active_cells=5,
        probes=probes,
        observations=tuple(observations),
        satellite_cost=1.0,
        episode_cost=1.0,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )
    return decode_joint_fixed_hypotheses(problem, hypotheses)


def test_minimum_duration_is_enforced_per_satellite_during_overlap() -> None:
    full = _duration_case(include_second_satellite_fifth_peak=True)
    full_by_catalog = _by_catalog(full)
    assert full.selected_catalog_numbers == (10, 20)
    assert full_by_catalog[10].activity_by_cell == (True, True, True, True, True, False)
    assert full_by_catalog[20].activity_by_cell == (False, True, True, True, True, True)

    four_cells_only = _duration_case(include_second_satellite_fifth_peak=False)
    short_by_catalog = _by_catalog(four_cells_only)
    assert four_cells_only.selected_catalog_numbers == (10,)
    assert short_by_catalog[20].activity_by_cell == (False,) * 6


@pytest.mark.parametrize(
    ("left_censored", "right_censored", "signal_cell", "expected_activity"),
    (
        (True, False, 0, (True, False, False)),
        (False, True, 2, (False, False, True)),
    ),
)
def test_boundary_censoring_is_applied_per_satellite(
    left_censored: bool,
    right_censored: bool,
    signal_cell: int,
    expected_activity: tuple[bool, ...],
) -> None:
    problem = _problem(
        cell_count=3,
        minimum_active_cells=5,
        observations=(_observation(signal_cell, "a", 0.0, clutter_cost=8.0),),
        satellite_cost=1.0,
        episode_cost=1.0,
        left_censored=left_censored,
        right_censored=right_censored,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )

    result = decode_joint_fixed_hypotheses(problem, hypotheses)
    by_catalog = _by_catalog(result)

    assert result.selected_catalog_numbers == (10,)
    assert by_catalog[10].activity_by_cell == expected_activity
    assert by_catalog[10].episodes[0].left_censored is left_censored
    assert by_catalog[10].episodes[0].right_censored is right_censored
    assert by_catalog[20].activity_by_cell == (False, False, False)


def test_joint_decoder_resolves_collision_between_independent_winners() -> None:
    observations = (
        _observation(0, "shared", 0.0, clutter_cost=10.0),
        _observation(0, "alternative", 1.0, clutter_cost=8.0),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=observations,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=0.0),
    )

    independent = tuple(decode_single_satellite(problem, item) for item in hypotheses)
    assert [item.assignments[0].observation_id for item in independent] == [
        "o-0-shared",
        "o-0-shared",
    ]

    joint = decode_joint_fixed_hypotheses(problem, hypotheses)
    jointly_assigned = [
        assignment.observation_id
        for satellite in joint.satellites
        for assignment in satellite.assignments
    ]
    assert sorted(jointly_assigned) == ["o-0-alternative", "o-0-shared"]
    assert len(set(jointly_assigned)) == 2
    assert joint.objective.total_cost == pytest.approx(0.5)


def test_native_probes_in_one_cell_include_candidate_free_and_unusable_support() -> None:
    probes = (
        CfoProbe("p-a", 0.010, 0, 1.0),
        CfoProbe("p-b", 0.035, 0, 1.0),
        CfoProbe("p-empty", 0.060, 0, 1.0),
        CfoProbe("p-unusable", 0.085, 0, 0.0, usable=False),
    )
    observations = (
        CfoCandidate("o-a", "p-a", "group-a", 0.0, 1.0, 10.0, 0.0, TEST_COMPONENT),
        CfoCandidate("o-b", "p-b", "group-b", 100.0, 1.0, 10.0, 0.0, TEST_COMPONENT),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        probes=probes,
        observations=observations,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )

    result = decode_joint_fixed_hypotheses(problem, hypotheses)
    by_catalog = _by_catalog(result)

    assert result.selected_catalog_numbers == (10, 20)
    assert [item.observation_id for item in by_catalog[10].assignments] == ["o-a"]
    assert [item.observation_id for item in by_catalog[20].assignments] == ["o-b"]
    assert by_catalog[10].missed_probe_ids == ("p-b", "p-empty")
    assert by_catalog[20].missed_probe_ids == ("p-a", "p-empty")
    assert result.objective.missed_detection_cost == pytest.approx(4.0)


def test_joint_solver_applies_satellite_specific_eligibility_at_one_cell() -> None:
    probes = (
        CfoProbe("p-0", 0.025, 0, 9.0),
        CfoProbe("p-1", 0.075, 0, 9.0),
    )
    observations = (
        _observation(0, "a", 0.0, clutter_cost=10.0),
        _observation(1, "b", 100.0, clutter_cost=10.0),
    )
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        probes=probes,
        observations=observations,
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(
            problem,
            label="A",
            catalog_number=10,
            predicted_cfo_hz=0.0,
            eligible_probe_ids=("p-0",),
        ),
        _hypothesis(
            problem,
            label="B",
            catalog_number=20,
            predicted_cfo_hz=100.0,
            eligible_probe_ids=("p-1",),
        ),
    )

    result = decode_joint_fixed_hypotheses(problem, tuple(reversed(hypotheses)))
    by_catalog = _by_catalog(result)

    assert result.selected_catalog_numbers == (10, 20)
    assert by_catalog[10].assignments == (ProbeAssignment("p-0", "o-0-a"),)
    assert by_catalog[20].assignments == (ProbeAssignment("p-1", "o-1-b"),)
    assert all(item.missed_probe_ids == () for item in result.satellites)
    assert result.objective.null_cost == pytest.approx(20.0)
    assert result.objective.total_cost == pytest.approx(2.0)


def test_exact_symmetric_identity_tie_prefers_lower_catalog_number() -> None:
    problem = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=(_observation(0, "shared", 0.0, clutter_cost=10.0),),
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypotheses = (
        _hypothesis(problem, label="LOW", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="HIGH", catalog_number=20, predicted_cfo_hz=0.0),
    )

    result = decode_joint_fixed_hypotheses(problem, tuple(reversed(hypotheses)))

    assert result.selected_catalog_numbers == (10,)
    assert _by_catalog(result)[10].assignments[0].observation_id == "o-0-shared"


def test_short_right_censored_second_episode_is_legal_after_mature_episode() -> None:
    observations = tuple(_observation(cell, "a", 0.0, clutter_cost=5.0) for cell in (0, 1, 2, 5, 6))
    problem = _problem(
        cell_count=7,
        minimum_active_cells=3,
        probes=_probes(7, missed_detection_cost=10.0),
        observations=observations,
        satellite_cost=1.0,
        episode_cost=1.0,
        right_censored=True,
    )
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )

    result = decode_joint_fixed_hypotheses(problem, hypotheses)
    episodes = _by_catalog(result)[10].episodes

    assert [(item.start_cell, item.end_cell_exclusive) for item in episodes] == [
        (0, 3),
        (5, 7),
    ]
    assert not episodes[0].right_censored
    assert episodes[1].right_censored


def test_exact_decoder_rejects_declared_candidate_truncation() -> None:
    problem = _problem(cell_count=1, minimum_active_cells=1, observations=())
    truncated = replace(problem, truncated_observation_count=1)
    hypotheses = (
        _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0),
        _hypothesis(problem, label="B", catalog_number=20, predicted_cfo_hz=100.0),
    )

    with pytest.raises(ValueError, match="untruncated candidate inventory"):
        decode_joint_fixed_hypotheses(truncated, hypotheses)


def _result_key(result: JointSatelliteAssociationResult) -> tuple[object, ...]:
    return (
        result.objective.total_cost,
        len(result.selected_catalog_numbers),
        sum(len(item.episodes) for item in result.satellites),
        sum(sum(item.activity_by_cell) for item in result.satellites),
        tuple(item.activity_by_cell for item in result.satellites),
        sum(len(item.assignments) for item in result.satellites),
        tuple(
            (item.hypothesis_id, assignment.probe_id, assignment.observation_id)
            for item in result.satellites
            for assignment in item.assignments
        ),
    )


def _brute_force_two_satellites(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, SingleSatelliteHypothesis],
) -> JointSatelliteAssociationResult:
    candidates = []
    for activities in itertools.product(
        itertools.product((False, True), repeat=problem.grid.cell_count),
        repeat=2,
    ):
        per_probe_owners = []
        for probe in problem.probes:
            active = tuple(
                index for index, activity in enumerate(activities) if activity[probe.cell_index]
            )
            # Randomized oracle fixtures contain one physical candidate per probe.
            per_probe_owners.append((None, *active))
        for owners in itertools.product(*per_probe_owners):
            assignments: list[list[ProbeAssignment]] = [[], []]
            for probe, owner in zip(problem.probes, owners, strict=True):
                if owner is None:
                    continue
                observation = next(
                    item for item in problem.observations if item.probe_id == probe.probe_id
                )
                assignments[owner].append(
                    ProbeAssignment(probe.probe_id, observation.observation_id)
                )
            schedules = tuple(
                JointSatelliteSchedule(
                    hypothesis.hypothesis_id,
                    tuple(activities[index]),
                    tuple(assignments[index]),
                )
                for index, hypothesis in enumerate(hypotheses)
            )
            try:
                result = evaluate_joint_satellite_schedule(problem, hypotheses, schedules)
            except ValueError:
                continue
            candidates.append(result)
    return min(candidates, key=_result_key)


def test_joint_decoder_matches_tiny_randomized_brute_force_and_is_permutation_invariant() -> None:
    source = random.Random(7721)
    for case_index in range(3):
        observations = tuple(
            _observation(
                probe_index,
                "candidate",
                source.choice((0.0, 3.0)) + source.uniform(-0.2, 0.2),
                clutter_cost=source.uniform(1.0, 6.0),
                matched_base_cost=source.uniform(0.0, 1.0),
                sigma_hz=0.7,
            )
            for probe_index in range(3)
        )
        probes = tuple(
            CfoProbe(
                f"p-{index}",
                index * 0.1 + 0.025,
                index,
                source.uniform(0.5, 3.0),
            )
            for index in range(3)
        )
        problem = _problem(
            cell_count=3,
            minimum_active_cells=2,
            probes=probes,
            observations=observations,
            satellite_cost=source.uniform(0.0, 2.0),
            episode_cost=source.uniform(0.0, 1.0),
        )
        hypotheses = (
            _hypothesis(
                problem,
                label=f"A-{case_index}",
                catalog_number=10,
                predicted_cfo_hz=0.0,
                delay_prior_cost=source.uniform(0.0, 0.5),
            ),
            _hypothesis(
                problem,
                label=f"B-{case_index}",
                catalog_number=20,
                predicted_cfo_hz=3.0,
                delay_prior_cost=source.uniform(0.0, 0.5),
            ),
        )

        expected = _brute_force_two_satellites(problem, hypotheses)
        actual = decode_joint_fixed_hypotheses(problem, hypotheses)
        reversed_actual = decode_joint_fixed_hypotheses(problem, tuple(reversed(hypotheses)))

        assert actual.objective.total_cost == pytest.approx(expected.objective.total_cost)
        assert _result_key(actual)[1:] == _result_key(expected)[1:]
        assert reversed_actual == actual


def test_joint_decoder_bounds_catalog_hypotheses_and_imports_no_infrastructure() -> None:
    problem = _problem(cell_count=1, minimum_active_cells=1, observations=())
    one = _hypothesis(problem, label="A", catalog_number=10, predicted_cfo_hz=0.0)
    duplicate_catalog = replace(one, hypothesis_id="duplicate-parameter-state")
    with pytest.raises(ValueError, match="two or three"):
        decode_joint_fixed_hypotheses(problem, (one,))
    with pytest.raises(ValueError, match="one hypothesis per catalog"):
        decode_joint_fixed_hypotheses(problem, (one, duplicate_catalog))

    four = tuple(
        _hypothesis(
            problem,
            label=str(index),
            catalog_number=100 + index,
            predicted_cfo_hz=float(index),
        )
        for index in range(4)
    )
    with pytest.raises(ValueError, match="two or three"):
        decode_joint_fixed_hypotheses(problem, four)

    path = Path(joint_module.__file__)
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
