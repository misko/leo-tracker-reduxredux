from __future__ import annotations

import ast
import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research.joint_multipath_satellite_activity import (
    JointMultipathSatelliteAssociationResult,
    JointMultipathSatelliteSchedule,
    decode_joint_fixed_multipath_satellites,
    evaluate_joint_fixed_multipath_schedule,
)
from leo.analysis.research.multipath_satellite_activity import (
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    ReceiverPathActivityEvidence,
    ReceiverPathAssignments,
    ReceiverPathFixedHypothesis,
)
from leo.analysis.research.satellite_activity import (
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    PredictedProbeCfo,
    ProbeAssignment,
)


def _path(
    path_id: str,
    *,
    cell_count: int,
    observations: tuple[tuple[int, str, float, str, float], ...],
    probe_cells: tuple[int, ...] | None = None,
    missed_detection_cost: float = 0.5,
) -> ReceiverPathActivityEvidence:
    cells = tuple(range(cell_count)) if probe_cells is None else probe_cells
    probes = tuple(
        CfoProbe(
            probe_id=f"p-{cell}",
            time_s=1_800_000_000.0 + cell * 0.1 + 0.025,
            cell_index=cell,
            missed_detection_cost=missed_detection_cost,
        )
        for cell in cells
    )
    candidates = tuple(
        CfoCandidate(
            observation_id=f"o-{cell}-{label}",
            probe_id=f"p-{cell}",
            exclusion_group_id=group_id,
            cfo_hz=cfo_hz,
            sigma_hz=1.0,
            clutter_cost=clutter_cost,
            matched_base_cost=0.0,
            component_id=f"component:{path_id}",
        )
        for cell, label, cfo_hz, group_id, clutter_cost in observations
    )
    return ReceiverPathActivityEvidence(path_id, probes, candidates)


def _problem(
    paths: tuple[ReceiverPathActivityEvidence, ...],
    *,
    cell_count: int = 5,
    satellite_cost: float = 1.0,
    episode_cost: float = 0.0,
) -> MultipathSatelliteActivityProblem:
    return MultipathSatelliteActivityProblem(
        grid=ActivityGrid(1_800_000_000.0, 0.1, cell_count, minimum_active_cells=5),
        paths=paths,
        costs=AssociationCostModel(satellite_cost, episode_cost, huber_threshold=1.0),
    )


def _hypothesis(
    problem: MultipathSatelliteActivityProblem,
    *,
    label: str,
    catalog_number: int,
    predicted_cfo_by_path: dict[str, float],
    cfo_offset_by_path: dict[str, float] | None = None,
    delay_s: float = 0.0,
    delay_prior_cost: float = 0.0,
    eligible_by_cell_by_path: dict[str, tuple[bool, ...]] | None = None,
) -> FixedMultipathSatelliteHypothesis:
    offsets = cfo_offset_by_path or {item.path_id: 0.0 for item in problem.paths}
    return FixedMultipathSatelliteHypothesis(
        hypothesis_id=f"hypothesis-{label}",
        object_name=f"STARLINK-{label}",
        catalog_number=catalog_number,
        delay_s=delay_s,
        delay_prior_cost=delay_prior_cost,
        paths=tuple(
            ReceiverPathFixedHypothesis(
                path_id=path.path_id,
                cfo_offset_hz=offsets[path.path_id],
                predictions=tuple(
                    PredictedProbeCfo(probe.probe_id, predicted_cfo_by_path[path.path_id])
                    for probe in path.probes
                ),
                eligible_by_cell=(
                    None
                    if eligible_by_cell_by_path is None
                    else eligible_by_cell_by_path[path.path_id]
                ),
            )
            for path in problem.paths
        ),
    )


def _schedule(
    hypothesis: FixedMultipathSatelliteHypothesis,
    activity: tuple[bool, ...],
    assignments_by_path: dict[str, tuple[ProbeAssignment, ...]] | None = None,
) -> JointMultipathSatelliteSchedule:
    supplied = assignments_by_path or {}
    return JointMultipathSatelliteSchedule(
        hypothesis_id=hypothesis.hypothesis_id,
        activity_by_cell=activity,
        path_assignments=tuple(
            ReceiverPathAssignments(path.path_id, supplied.get(path.path_id, ()))
            for path in hypothesis.paths
        ),
    )


def _result_key(result: JointMultipathSatelliteAssociationResult) -> tuple[object, ...]:
    selected_catalog_key = tuple(not item.selected for item in result.satellites)
    assignments = tuple(
        (
            satellite.hypothesis_id,
            path.path_id,
            assignment.probe_id,
            assignment.observation_id,
        )
        for satellite in result.satellites
        for path in satellite.paths
        for assignment in path.assignments
    )
    return (
        result.objective.total_cost,
        len(result.selected_catalog_numbers),
        sum(len(item.episodes) for item in result.satellites),
        sum(sum(item.activity_by_cell) for item in result.satellites),
        selected_catalog_key,
        tuple(item.activity_by_cell for item in result.satellites),
        len(assignments),
        assignments,
    )


def _exhaustive_toy_oracle(
    problem: MultipathSatelliteActivityProblem,
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...],
) -> JointMultipathSatelliteAssociationResult:
    raw_masks = tuple(itertools.product((False, True), repeat=problem.grid.cell_count))
    candidates = []
    for masks in itertools.product(raw_masks, repeat=len(hypotheses)):
        try:
            evaluate_joint_fixed_multipath_schedule(
                problem,
                hypotheses,
                tuple(
                    _schedule(hypothesis, tuple(mask))
                    for hypothesis, mask in zip(hypotheses, masks, strict=True)
                ),
            )
        except ValueError:
            continue

        schedule_options = []
        for hypothesis, mask in zip(hypotheses, masks, strict=True):
            hypothesis_by_path = {item.path_id: item for item in hypothesis.paths}
            path_options = []
            for path in problem.paths:
                eligibility = hypothesis_by_path[path.path_id].eligible_by_cell
                effective_eligibility = (
                    (True,) * problem.grid.cell_count if eligibility is None else eligibility
                )
                observations_by_probe = {
                    probe.probe_id: tuple(
                        item for item in path.observations if item.probe_id == probe.probe_id
                    )
                    for probe in path.probes
                }
                active_probes = tuple(
                    probe
                    for probe in path.probes
                    if probe.usable
                    and effective_eligibility[probe.cell_index]
                    and mask[probe.cell_index]
                )
                choices = tuple(
                    (
                        None,
                        *(item.observation_id for item in observations_by_probe[probe.probe_id]),
                    )
                    for probe in active_probes
                )
                path_options.append(
                    tuple(
                        ReceiverPathAssignments(
                            path.path_id,
                            tuple(
                                ProbeAssignment(probe.probe_id, observation_id)
                                for probe, observation_id in zip(
                                    active_probes,
                                    selected,
                                    strict=True,
                                )
                                if observation_id is not None
                            ),
                        )
                        for selected in itertools.product(*choices)
                    )
                )
            schedule_options.append(
                tuple(
                    JointMultipathSatelliteSchedule(
                        hypothesis.hypothesis_id,
                        tuple(mask),
                        tuple(path_assignments),
                    )
                    for path_assignments in itertools.product(*path_options)
                )
            )

        for schedules in itertools.product(*schedule_options):
            try:
                candidates.append(
                    evaluate_joint_fixed_multipath_schedule(
                        problem,
                        hypotheses,
                        tuple(schedules),
                    )
                )
            except ValueError:
                continue
    return min(candidates, key=_result_key)


def test_overlapping_satellites_use_distinct_groups_on_each_path_and_count_costs_once() -> None:
    observations = (
        (0, "low", 10.0, "group-low", 8.0),
        (0, "high", 90.0, "group-high", 9.0),
    )
    first_path = _path("19f2-rx0", cell_count=5, observations=observations)
    second_path = _path("5d4d-rx1", cell_count=5, observations=observations)
    problem = _problem(
        (second_path, first_path),
        satellite_cost=3.0,
        episode_cost=2.0,
    )
    first = _hypothesis(
        problem,
        label="LOW",
        catalog_number=10,
        predicted_cfo_by_path={"19f2-rx0": 0.0, "5d4d-rx1": 20.0},
        cfo_offset_by_path={"19f2-rx0": 10.0, "5d4d-rx1": -10.0},
        delay_s=-0.1,
        delay_prior_cost=0.4,
    )
    second = _hypothesis(
        problem,
        label="HIGH",
        catalog_number=20,
        predicted_cfo_by_path={"19f2-rx0": 100.0, "5d4d-rx1": 80.0},
        cfo_offset_by_path={"19f2-rx0": -10.0, "5d4d-rx1": 10.0},
        delay_s=0.2,
        delay_prior_cost=0.6,
    )
    active = (True,) * 5
    result = evaluate_joint_fixed_multipath_schedule(
        problem,
        (second, first),
        (
            _schedule(
                first,
                active,
                {path.path_id: (ProbeAssignment("p-0", "o-0-low"),) for path in problem.paths},
            ),
            _schedule(
                second,
                active,
                {path.path_id: (ProbeAssignment("p-0", "o-0-high"),) for path in problem.paths},
            ),
        ),
    )

    assert result.selected_catalog_numbers == (10, 20)
    assert all(item.activity_by_cell == active for item in result.satellites)
    assert result.objective.null_cost == pytest.approx(34.0)
    assert result.objective.clutter_cost == pytest.approx(0.0)
    assert result.objective.residual_cost == pytest.approx(0.0)
    assert result.objective.missed_detection_cost == pytest.approx(8.0)
    assert result.objective.satellite_cost == pytest.approx(6.0)
    assert result.objective.episode_cost == pytest.approx(4.0)
    assert result.objective.delay_prior_cost == pytest.approx(1.0)
    assert result.objective.total_cost == pytest.approx(19.0)
    assert [item.objective.missed_detection_cost for item in result.paths] == pytest.approx(
        [4.0, 4.0]
    )
    assert all(item.unexplained_observation_ids == () for item in result.paths)


@pytest.mark.parametrize(
    ("satellite_cost", "expected_catalogs"),
    ((0.0, (10, 20)), (15.0, (10,)), (21.0, ())),
)
def test_satellite_penalty_changes_two_to_one_to_null(
    satellite_cost: float,
    expected_catalogs: tuple[int, ...],
) -> None:
    observations = (
        (0, "strong", 0.0, "group-strong", 10.0),
        (0, "weak", 100.0, "group-weak", 6.0),
    )
    paths = (
        _path("a", cell_count=5, observations=observations, probe_cells=(0,)),
        _path("b", cell_count=5, observations=observations, probe_cells=(0,)),
    )
    problem = _problem(paths, satellite_cost=satellite_cost)
    hypotheses = (
        _hypothesis(
            problem,
            label="A",
            catalog_number=10,
            predicted_cfo_by_path={"a": 0.0, "b": 0.0},
        ),
        _hypothesis(
            problem,
            label="B",
            catalog_number=20,
            predicted_cfo_by_path={"a": 100.0, "b": 100.0},
        ),
    )

    result = decode_joint_fixed_multipath_satellites(problem, hypotheses)

    assert result.selected_catalog_numbers == expected_catalogs
    assert result.objective.satellite_cost == pytest.approx(satellite_cost * len(expected_catalogs))


def test_active_satellite_pays_misses_on_sparse_path_while_inactive_satellite_does_not() -> None:
    first_path = _path(
        "strong",
        cell_count=5,
        observations=tuple((cell, "signal", 0.0, f"group-{cell}", 8.0) for cell in range(5)),
        missed_detection_cost=2.0,
    )
    sparse_path = _path(
        "sparse",
        cell_count=5,
        observations=(),
        missed_detection_cost=2.0,
    )
    problem = _problem((first_path, sparse_path))
    active_satellite = _hypothesis(
        problem,
        label="ACTIVE",
        catalog_number=10,
        predicted_cfo_by_path={"sparse": 0.0, "strong": 0.0},
    )
    inactive_satellite = _hypothesis(
        problem,
        label="INACTIVE",
        catalog_number=20,
        predicted_cfo_by_path={"sparse": 100.0, "strong": 100.0},
    )
    result = evaluate_joint_fixed_multipath_schedule(
        problem,
        (active_satellite, inactive_satellite),
        (
            _schedule(
                active_satellite,
                (True,) * 5,
                {
                    "strong": tuple(
                        ProbeAssignment(f"p-{cell}", f"o-{cell}-signal") for cell in range(5)
                    )
                },
            ),
            _schedule(inactive_satellite, (False,) * 5),
        ),
    )

    by_catalog = {item.catalog_number: item for item in result.satellites}
    active_paths = {item.path_id: item for item in by_catalog[10].paths}
    inactive_paths = {item.path_id: item for item in by_catalog[20].paths}
    assert active_paths["sparse"].missed_probe_ids == tuple(f"p-{cell}" for cell in range(5))
    assert active_paths["sparse"].evidence.missed_detection_cost == pytest.approx(10.0)
    assert inactive_paths["sparse"].missed_probe_ids == ()
    assert inactive_paths["sparse"].evidence.missed_detection_cost == pytest.approx(0.0)
    assert result.objective.missed_detection_cost == pytest.approx(10.0)


def test_satellite_specific_path_eligibility_avoids_cross_band_misses() -> None:
    first_path = _path(
        "band-a",
        cell_count=5,
        observations=tuple((cell, "a", 0.0, f"group-a-{cell}", 5.0) for cell in range(5)),
        missed_detection_cost=9.0,
    )
    second_path = _path(
        "band-b",
        cell_count=5,
        observations=tuple((cell, "b", 100.0, f"group-b-{cell}", 5.0) for cell in range(5)),
        missed_detection_cost=9.0,
    )
    problem = _problem(
        (first_path, second_path),
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    first = _hypothesis(
        problem,
        label="A",
        catalog_number=10,
        predicted_cfo_by_path={"band-a": 0.0, "band-b": 100.0},
        eligible_by_cell_by_path={
            "band-a": (True,) * 5,
            "band-b": (False,) * 5,
        },
    )
    second = _hypothesis(
        problem,
        label="B",
        catalog_number=20,
        predicted_cfo_by_path={"band-a": 0.0, "band-b": 100.0},
        eligible_by_cell_by_path={
            "band-a": (False,) * 5,
            "band-b": (True,) * 5,
        },
    )

    result = decode_joint_fixed_multipath_satellites(problem, (second, first))

    assert result.selected_catalog_numbers == (10, 20)
    assert result.objective.null_cost == pytest.approx(50.0)
    assert result.objective.clutter_cost == pytest.approx(0.0)
    assert result.objective.missed_detection_cost == pytest.approx(0.0)
    assert result.objective.total_cost == pytest.approx(2.0)
    by_catalog = {item.catalog_number: item for item in result.satellites}
    first_paths = {item.path_id: item for item in by_catalog[10].paths}
    second_paths = {item.path_id: item for item in by_catalog[20].paths}
    assert len(first_paths["band-a"].assignments) == 5
    assert first_paths["band-b"].assignments == ()
    assert first_paths["band-b"].missed_probe_ids == ()
    assert len(second_paths["band-b"].assignments) == 5
    assert second_paths["band-a"].assignments == ()
    assert second_paths["band-a"].missed_probe_ids == ()
    assert first_paths["band-b"].eligible_by_cell == (False,) * 5
    assert second_paths["band-a"].eligible_by_cell == (False,) * 5


def test_aliases_of_one_path_group_cannot_be_split_between_satellites() -> None:
    aliases = (
        (0, "alias-low", 0.0, "one-physical-group", 10.0),
        (0, "alias-high", 100.0, "one-physical-group", 10.0),
    )
    problem = _problem(
        (
            _path("a", cell_count=5, observations=aliases, probe_cells=(0,)),
            _path("b", cell_count=5, observations=(), probe_cells=(0,)),
        ),
        satellite_cost=0.0,
    )
    first = _hypothesis(
        problem,
        label="A",
        catalog_number=10,
        predicted_cfo_by_path={"a": 0.0, "b": 0.0},
    )
    second = _hypothesis(
        problem,
        label="B",
        catalog_number=20,
        predicted_cfo_by_path={"a": 100.0, "b": 100.0},
    )
    active = (True,) * 5
    with pytest.raises(ValueError, match="physical exclusion group"):
        evaluate_joint_fixed_multipath_schedule(
            problem,
            (first, second),
            (
                _schedule(
                    first,
                    active,
                    {"a": (ProbeAssignment("p-0", "o-0-alias-low"),)},
                ),
                _schedule(
                    second,
                    active,
                    {"a": (ProbeAssignment("p-0", "o-0-alias-high"),)},
                ),
            ),
        )

    decoded = decode_joint_fixed_multipath_satellites(problem, (first, second))
    path_a_assignments = tuple(
        assignment
        for satellite in decoded.satellites
        for path in satellite.paths
        if path.path_id == "a"
        for assignment in path.assignments
    )
    assert len(path_a_assignments) == 1
    assert decoded.paths[0].objective.clutter_cost == pytest.approx(0.0)


def test_three_fixed_catalogues_can_overlap_on_three_distinct_groups() -> None:
    observations = tuple(
        (0, str(index), float(index * 100), f"group-{index}", 10.0) for index in range(3)
    )
    problem = _problem(
        (
            _path("a", cell_count=5, observations=observations, probe_cells=(0,)),
            _path("b", cell_count=5, observations=observations, probe_cells=(0,)),
        ),
        satellite_cost=1.0,
    )
    hypotheses = tuple(
        _hypothesis(
            problem,
            label=str(index),
            catalog_number=(index + 1) * 10,
            predicted_cfo_by_path={"a": float(index * 100), "b": float(index * 100)},
        )
        for index in range(3)
    )

    result = decode_joint_fixed_multipath_satellites(problem, tuple(reversed(hypotheses)))

    assert result.selected_catalog_numbers == (10, 20, 30)
    assert all(item.activity_by_cell == (True,) * 5 for item in result.satellites)
    assert all(len(path.assignments) == 1 for item in result.satellites for path in item.paths)
    assert result.objective.total_cost == pytest.approx(3.0)


def test_decoder_matches_independent_exhaustive_activity_assignment_oracle() -> None:
    observations = (
        (0, "near-a", 1.25, "group-a", 5.25),
        (0, "near-b", 9.5, "group-b", 4.75),
    )
    problem = _problem(
        (
            _path("a", cell_count=5, observations=observations, probe_cells=(0,)),
            _path("b", cell_count=5, observations=observations, probe_cells=(0,)),
        ),
        satellite_cost=1.1,
        episode_cost=0.3,
    )
    hypotheses = (
        _hypothesis(
            problem,
            label="A",
            catalog_number=10,
            predicted_cfo_by_path={"a": 1.0, "b": 1.0},
            delay_prior_cost=0.2,
        ),
        _hypothesis(
            problem,
            label="B",
            catalog_number=20,
            predicted_cfo_by_path={"a": 10.0, "b": 10.0},
            delay_prior_cost=0.4,
        ),
    )

    decoded = decode_joint_fixed_multipath_satellites(problem, hypotheses)
    exhaustive = _exhaustive_toy_oracle(problem, hypotheses)

    assert decoded.objective.total_cost == pytest.approx(exhaustive.objective.total_cost)
    assert decoded.selected_catalog_numbers == exhaustive.selected_catalog_numbers
    assert tuple(item.activity_by_cell for item in decoded.satellites) == tuple(
        item.activity_by_cell for item in exhaustive.satellites
    )
    assert tuple(
        (satellite.hypothesis_id, path.path_id, path.assignments)
        for satellite in decoded.satellites
        for path in satellite.paths
    ) == tuple(
        (satellite.hypothesis_id, path.path_id, path.assignments)
        for satellite in exhaustive.satellites
        for path in satellite.paths
    )


def test_bounds_unique_catalogues_and_complete_inventory_are_required() -> None:
    problem = _problem(
        (
            _path("a", cell_count=5, observations=(), probe_cells=(0,)),
            _path("b", cell_count=5, observations=(), probe_cells=(0,)),
        )
    )
    base = _hypothesis(
        problem,
        label="A",
        catalog_number=10,
        predicted_cfo_by_path={"a": 0.0, "b": 0.0},
    )
    with pytest.raises(ValueError, match="two or three"):
        decode_joint_fixed_multipath_satellites(problem, (base,))
    four = tuple(
        replace(base, hypothesis_id=f"hypothesis-{index}", catalog_number=index + 1)
        for index in range(4)
    )
    with pytest.raises(ValueError, match="two or three"):
        decode_joint_fixed_multipath_satellites(problem, four)
    duplicate_catalog = replace(base, hypothesis_id="hypothesis-other")
    with pytest.raises(ValueError, match="unique catalog"):
        decode_joint_fixed_multipath_satellites(problem, (base, duplicate_catalog))

    truncated_path = replace(problem.paths[0], truncated_observation_count=1)
    truncated_problem = replace(problem, paths=(truncated_path, problem.paths[1]))
    second = replace(base, hypothesis_id="hypothesis-B", catalog_number=20)
    with pytest.raises(ValueError, match="complete path candidate inventories"):
        decode_joint_fixed_multipath_satellites(truncated_problem, (base, second))


def test_module_remains_a_pure_research_core() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src"
        / "leo"
        / "analysis"
        / "research"
        / "joint_multipath_satellite_activity.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert not any(
        name.startswith(
            (
                "leo.storage",
                "leo.catalog",
                "leo.api",
                "leo.cli",
                "sqlalchemy",
                "psycopg",
                "httpx",
            )
        )
        for name in imported
    )
