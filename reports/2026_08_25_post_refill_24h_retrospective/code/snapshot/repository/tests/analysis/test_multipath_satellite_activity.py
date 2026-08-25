from __future__ import annotations

import ast
import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research.multipath_satellite_activity import (
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    MultipathSatelliteAssociationResult,
    ReceiverPathActivityEvidence,
    ReceiverPathAssignments,
    ReceiverPathFixedHypothesis,
    decode_fixed_multipath_satellite,
    evaluate_fixed_multipath_satellite_schedule,
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
    signal_cells: tuple[int, ...],
    observed_cfo_hz: float,
    clutter_cost: float = 3.0,
    matched_base_cost: float = 0.0,
    missed_detection_cost: float = 0.25,
    component_id: str | None = None,
) -> ReceiverPathActivityEvidence:
    probes = tuple(
        CfoProbe(
            probe_id=f"p-{cell}",
            time_s=1_800_000_000.0 + cell * 0.1 + 0.025,
            cell_index=cell,
            missed_detection_cost=missed_detection_cost,
        )
        for cell in range(cell_count)
    )
    observations = tuple(
        CfoCandidate(
            observation_id=f"o-{cell}",
            probe_id=f"p-{cell}",
            exclusion_group_id=f"group-{cell}",
            cfo_hz=observed_cfo_hz,
            sigma_hz=1.0,
            clutter_cost=clutter_cost,
            matched_base_cost=matched_base_cost,
            component_id=component_id or f"component:{path_id}",
        )
        for cell in signal_cells
    )
    return ReceiverPathActivityEvidence(path_id, probes, observations)


def _problem(
    paths: tuple[ReceiverPathActivityEvidence, ...],
    *,
    cell_count: int,
    minimum_active_cells: int = 5,
    satellite_cost: float = 1.0,
    episode_cost: float = 0.5,
    huber_threshold: float = 1.0,
) -> MultipathSatelliteActivityProblem:
    return MultipathSatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=1_800_000_000.0,
            cell_duration_s=0.1,
            cell_count=cell_count,
            minimum_active_cells=minimum_active_cells,
        ),
        paths=paths,
        costs=AssociationCostModel(satellite_cost, episode_cost, huber_threshold),
    )


def _hypothesis(
    problem: MultipathSatelliteActivityProblem,
    *,
    predicted_cfo_by_path: dict[str, float],
    cfo_offset_by_path: dict[str, float],
    delay_s: float = 0.2,
    delay_prior_cost: float = 0.4,
    eligible_by_cell_by_path: dict[str, tuple[bool, ...]] | None = None,
) -> FixedMultipathSatelliteHypothesis:
    return FixedMultipathSatelliteHypothesis(
        hypothesis_id="catalog-12345-delay-0.2-path-offsets-fixed",
        object_name="STARLINK-TEST",
        catalog_number=12345,
        delay_s=delay_s,
        delay_prior_cost=delay_prior_cost,
        paths=tuple(
            ReceiverPathFixedHypothesis(
                path_id=path.path_id,
                cfo_offset_hz=cfo_offset_by_path[path.path_id],
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


def _assign_every_observation(
    problem: MultipathSatelliteActivityProblem,
) -> tuple[ReceiverPathAssignments, ...]:
    return tuple(
        ReceiverPathAssignments(
            path.path_id,
            tuple(
                ProbeAssignment(observation.probe_id, observation.observation_id)
                for observation in path.observations
            ),
        )
        for path in problem.paths
    )


def _result_key(result: MultipathSatelliteAssociationResult) -> tuple[object, ...]:
    return (
        result.objective.total_cost,
        result.selected,
        len(result.episodes),
        sum(result.activity_by_cell),
        result.activity_by_cell,
        tuple(
            (path.path_id, tuple(item.observation_id for item in path.assignments))
            for path in result.paths
        ),
    )


def _exhaustive_toy_oracle(
    problem: MultipathSatelliteActivityProblem,
    hypothesis: FixedMultipathSatelliteHypothesis,
) -> MultipathSatelliteAssociationResult:
    hypothesis_by_path = {item.path_id: item for item in hypothesis.paths}
    candidates = []
    for raw_activity in itertools.product((False, True), repeat=problem.grid.cell_count):
        try:
            evaluate_fixed_multipath_satellite_schedule(
                problem,
                hypothesis,
                tuple(raw_activity),
            )
        except ValueError:
            continue

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
                and raw_activity[probe.cell_index]
            )
            choices = tuple(
                (None, *(item.observation_id for item in observations_by_probe[probe.probe_id]))
                for probe in active_probes
            )
            schedules = []
            for selected in itertools.product(*choices):
                schedules.append(
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
                )
            path_options.append(tuple(schedules))

        for assignments in itertools.product(*path_options):
            try:
                candidates.append(
                    evaluate_fixed_multipath_satellite_schedule(
                        problem,
                        hypothesis,
                        tuple(raw_activity),
                        tuple(assignments),
                    )
                )
            except ValueError:
                continue
    return min(candidates, key=_result_key)


def test_evaluator_keeps_path_namespaces_counts_structure_once_and_charges_each_path_miss() -> None:
    first = _path(
        "19f2-rx0",
        cell_count=5,
        signal_cells=(0,),
        observed_cfo_hz=110.0,
        clutter_cost=10.0,
        matched_base_cost=1.0,
        component_id="component:first-independent-gauge",
    )
    second = _path(
        "5d4d-rx1",
        cell_count=5,
        signal_cells=(0,),
        observed_cfo_hz=170.0,
        clutter_cost=7.0,
        matched_base_cost=2.0,
        component_id="component:second-independent-gauge",
    )
    problem = _problem(
        (second, first),
        cell_count=5,
        satellite_cost=3.0,
        episode_cost=2.0,
    )
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"19f2-rx0": 100.0, "5d4d-rx1": 200.0},
        cfo_offset_by_path={"19f2-rx0": 10.0, "5d4d-rx1": -30.0},
        delay_prior_cost=0.5,
    )

    result = evaluate_fixed_multipath_satellite_schedule(
        problem,
        hypothesis,
        (True,) * 5,
        _assign_every_observation(problem),
    )

    assert result.selected
    assert result.delay_s == pytest.approx(0.2)
    assert [item.path_id for item in result.paths] == ["19f2-rx0", "5d4d-rx1"]
    assert [item.cfo_offset_hz for item in result.paths] == pytest.approx([10.0, -30.0])
    assert all(item.assignments[0] == ProbeAssignment("p-0", "o-0") for item in result.paths)
    assert result.objective.null_cost == pytest.approx(17.0)
    assert result.objective.clutter_cost == pytest.approx(0.0)
    assert result.objective.matched_base_cost == pytest.approx(3.0)
    assert result.objective.residual_cost == pytest.approx(0.0)
    assert result.objective.missed_detection_cost == pytest.approx(2.0)
    assert result.objective.satellite_cost == pytest.approx(3.0)
    assert result.objective.episode_cost == pytest.approx(2.0)
    assert result.objective.delay_prior_cost == pytest.approx(0.5)
    assert result.objective.total_cost == pytest.approx(10.5)
    assert [item.objective.null_cost for item in result.paths] == pytest.approx([10.0, 7.0])
    assert [item.objective.missed_detection_cost for item in result.paths] == pytest.approx(
        [1.0, 1.0]
    )
    assert all(item.missed_probe_ids == ("p-1", "p-2", "p-3", "p-4") for item in result.paths)


def test_decoder_uses_one_shared_minimum_duration_mask_and_distinct_path_offsets() -> None:
    first = _path(
        "path-a",
        cell_count=6,
        signal_cells=(0, 1, 2, 3, 4),
        observed_cfo_hz=15.0,
    )
    second = _path(
        "path-b",
        cell_count=6,
        signal_cells=(1, 2, 3, 4, 5),
        observed_cfo_hz=77.0,
    )
    problem = _problem((first, second), cell_count=6)
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"path-a": 10.0, "path-b": 100.0},
        cfo_offset_by_path={"path-a": 5.0, "path-b": -23.0},
    )

    result = decode_fixed_multipath_satellite(problem, hypothesis)

    assert result.exact
    assert result.algorithm == "bounded-exact-fixed-nuisance-multipath-semimarkov-v2"
    assert result.activity_by_cell == (True,) * 6
    assert len(result.episodes) == 1
    assert result.episodes[0].duration_s == pytest.approx(0.6)
    assert {item.path_id: item.cfo_offset_hz for item in result.paths} == {
        "path-a": 5.0,
        "path-b": -23.0,
    }
    assert [len(item.assignments) for item in result.paths] == [5, 5]
    assert [item.missed_probe_ids for item in result.paths] == [("p-5",), ("p-0",)]


def test_fixed_path_cell_eligibility_preserves_global_activity_and_off_band_clutter() -> None:
    first = _path(
        "path-a",
        cell_count=6,
        signal_cells=(0, 1, 2, 3, 4, 5),
        observed_cfo_hz=10.0,
        clutter_cost=5.0,
        missed_detection_cost=7.0,
    )
    second = _path(
        "path-b",
        cell_count=6,
        signal_cells=(0, 1, 2, 3, 4, 5),
        observed_cfo_hz=20.0,
        clutter_cost=5.0,
        missed_detection_cost=7.0,
    )
    problem = _problem(
        (first, second),
        cell_count=6,
        satellite_cost=1.0,
        episode_cost=0.0,
    )
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"path-a": 10.0, "path-b": 20.0},
        cfo_offset_by_path={"path-a": 0.0, "path-b": 0.0},
        delay_prior_cost=0.0,
        eligible_by_cell_by_path={
            "path-a": (True, True, True, False, False, False),
            "path-b": (False, False, False, True, True, True),
        },
    )

    result = decode_fixed_multipath_satellite(problem, hypothesis)

    assert result.activity_by_cell == (True,) * 6
    decisions = {item.path_id: item for item in result.paths}
    assert decisions["path-a"].eligible_by_cell == (
        True,
        True,
        True,
        False,
        False,
        False,
    )
    assert decisions["path-b"].eligible_by_cell == (
        False,
        False,
        False,
        True,
        True,
        True,
    )
    assert tuple(item.probe_id for item in decisions["path-a"].assignments) == (
        "p-0",
        "p-1",
        "p-2",
    )
    assert tuple(item.probe_id for item in decisions["path-b"].assignments) == (
        "p-3",
        "p-4",
        "p-5",
    )
    assert all(item.missed_probe_ids == () for item in result.paths)
    assert [item.objective.clutter_cost for item in result.paths] == pytest.approx([15.0, 15.0])
    assert result.objective.null_cost == pytest.approx(60.0)
    assert result.objective.clutter_cost == pytest.approx(30.0)
    assert result.objective.total_cost == pytest.approx(31.0)

    exhaustive = _exhaustive_toy_oracle(problem, hypothesis)
    assert result.objective.total_cost == pytest.approx(exhaustive.objective.total_cost)
    assert result.activity_by_cell == exhaustive.activity_by_cell


def test_evaluator_rejects_ineligible_assignment_and_non_grid_eligibility() -> None:
    paths = (
        _path("a", cell_count=5, signal_cells=(0,), observed_cfo_hz=0.0),
        _path("b", cell_count=5, signal_cells=(), observed_cfo_hz=0.0),
    )
    problem = _problem(paths, cell_count=5)
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"a": 0.0, "b": 0.0},
        cfo_offset_by_path={"a": 0.0, "b": 0.0},
        eligible_by_cell_by_path={
            "a": (False, True, True, True, True),
            "b": (True,) * 5,
        },
    )
    with pytest.raises(ValueError, match="RF-ineligible"):
        evaluate_fixed_multipath_satellite_schedule(
            problem,
            hypothesis,
            (True,) * 5,
            (ReceiverPathAssignments("a", (ProbeAssignment("p-0", "o-0"),)),),
        )

    malformed_path = replace(hypothesis.paths[0], eligible_by_cell=(True,) * 4)
    malformed = replace(hypothesis, paths=(malformed_path, hypothesis.paths[1]))
    with pytest.raises(ValueError, match="common activity grid exactly"):
        decode_fixed_multipath_satellite(problem, malformed)


def test_decoder_can_select_two_aligned_half_second_chunks_but_rejects_a_short_pop() -> None:
    signal_cells = (0, 1, 2, 3, 4, 6, 7, 8, 9, 10)
    first = _path(
        "path-a",
        cell_count=11,
        signal_cells=signal_cells,
        observed_cfo_hz=20.0,
        missed_detection_cost=2.0,
    )
    second = _path(
        "path-b",
        cell_count=11,
        signal_cells=signal_cells,
        observed_cfo_hz=-30.0,
        missed_detection_cost=2.0,
    )
    problem = _problem((first, second), cell_count=11, episode_cost=0.25)
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"path-a": 0.0, "path-b": 0.0},
        cfo_offset_by_path={"path-a": 20.0, "path-b": -30.0},
    )

    result = decode_fixed_multipath_satellite(problem, hypothesis)

    assert result.activity_by_cell == (True,) * 5 + (False,) + (True,) * 5
    assert [(item.start_cell, item.end_cell_exclusive) for item in result.episodes] == [
        (0, 5),
        (6, 11),
    ]
    assert [item.duration_s for item in result.episodes] == pytest.approx([0.5, 0.5])
    with pytest.raises(ValueError, match="shorter than the minimum"):
        evaluate_fixed_multipath_satellite_schedule(
            problem,
            hypothesis,
            (False, False, True, False, False, False, False, False, False, False, False),
        )


def test_exact_decoder_matches_independent_exhaustive_activity_assignment_oracle() -> None:
    first = _path(
        "path-a",
        cell_count=6,
        signal_cells=(0, 1, 2, 3, 4),
        observed_cfo_hz=15.25,
        clutter_cost=2.75,
        missed_detection_cost=0.4,
    )
    second = _path(
        "path-b",
        cell_count=6,
        signal_cells=(1, 2, 3, 4, 5),
        observed_cfo_hz=-8.75,
        clutter_cost=3.25,
        missed_detection_cost=0.6,
    )
    problem = _problem(
        (first, second),
        cell_count=6,
        satellite_cost=1.3,
        episode_cost=0.7,
    )
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"path-a": 10.0, "path-b": -10.0},
        cfo_offset_by_path={"path-a": 5.0, "path-b": 1.0},
        delay_prior_cost=0.35,
    )

    decoded = decode_fixed_multipath_satellite(problem, hypothesis)
    exhaustive = _exhaustive_toy_oracle(problem, hypothesis)

    assert decoded.objective.total_cost == pytest.approx(exhaustive.objective.total_cost)
    assert decoded.activity_by_cell == exhaustive.activity_by_cell
    assert tuple((item.path_id, item.assignments) for item in decoded.paths) == tuple(
        (item.path_id, item.assignments) for item in exhaustive.paths
    )


@pytest.mark.parametrize(
    ("grid", "message"),
    (
        (ActivityGrid(0.0, 0.2, 5, minimum_active_cells=5), "100-ms"),
        (ActivityGrid(0.05, 0.1, 5, minimum_active_cells=5), "100-ms boundary"),
        (ActivityGrid(0.0, 0.1, 5, minimum_active_cells=4), "at least 0.5"),
        (
            ActivityGrid(0.0, 0.1, 5, minimum_active_cells=5, allow_left_censored=True),
            "boundary censoring",
        ),
    ),
)
def test_problem_enforces_common_100ms_grid_and_uncensored_half_second_runs(
    grid: ActivityGrid,
    message: str,
) -> None:
    first = _path("a", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    second = _path("b", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    with pytest.raises(ValueError, match=message):
        MultipathSatelliteActivityProblem(
            grid=grid,
            paths=(first, second),
            costs=AssociationCostModel(1.0, 1.0),
        )


def test_problem_rejects_one_path_and_decoder_rejects_truncated_inventory() -> None:
    first = _path("a", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    with pytest.raises(ValueError, match="at least two"):
        _problem((first,), cell_count=5)

    second = _path("b", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    truncated = replace(first, truncated_observation_count=1)
    problem = _problem((truncated, second), cell_count=5)
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"a": 0.0, "b": 0.0},
        cfo_offset_by_path={"a": 0.0, "b": 0.0},
    )

    with pytest.raises(ValueError, match="complete path candidate inventories"):
        decode_fixed_multipath_satellite(problem, hypothesis)


def test_hypothesis_must_cover_every_path_and_native_probe_exactly() -> None:
    first = _path("a", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    second = _path("b", cell_count=5, signal_cells=(), observed_cfo_hz=0.0)
    problem = _problem((first, second), cell_count=5)
    hypothesis = _hypothesis(
        problem,
        predicted_cfo_by_path={"a": 0.0, "b": 0.0},
        cfo_offset_by_path={"a": 0.0, "b": 0.0},
    )

    missing_path = replace(hypothesis, paths=hypothesis.paths[:-1])
    with pytest.raises(ValueError, match="path coverage differs"):
        evaluate_fixed_multipath_satellite_schedule(
            problem,
            missing_path,
            (False,) * 5,
        )

    broken_path = replace(hypothesis.paths[0], predictions=hypothesis.paths[0].predictions[:-1])
    incomplete = replace(hypothesis, paths=(broken_path, hypothesis.paths[1]))
    with pytest.raises(ValueError, match="must cover path"):
        evaluate_fixed_multipath_satellite_schedule(
            problem,
            incomplete,
            (False,) * 5,
        )


def test_module_remains_a_pure_research_core() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src"
        / "leo"
        / "analysis"
        / "research"
        / "multipath_satellite_activity.py"
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
