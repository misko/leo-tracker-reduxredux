from __future__ import annotations

import ast
import itertools
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research import satellite_activity as activity_module
from leo.analysis.research.satellite_activity import (
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    DelayProfileCandidate,
    PredictedProbeCfo,
    ProbeAssignment,
    SatelliteActivityProblem,
    SingleSatelliteAssociationResult,
    SingleSatelliteHypothesis,
    SyntheticSingleSatelliteConfig,
    decode_single_satellite,
    evaluate_single_satellite_schedule,
    huber_loss,
    profile_delay_and_cfo_offset,
    simulate_single_satellite_case,
)

TEST_COMPONENT = "component:test"


def _problem(
    *,
    cell_count: int = 6,
    minimum_active_cells: int = 2,
    observations: tuple[CfoCandidate, ...] = (),
    probes: tuple[CfoProbe, ...] | None = None,
    left_censored: bool = False,
    right_censored: bool = False,
    satellite_cost: float = 4.0,
    episode_cost: float = 2.0,
) -> tuple[SatelliteActivityProblem, SingleSatelliteHypothesis]:
    if probes is None:
        probes = tuple(
            CfoProbe(
                probe_id=f"p-{index}",
                time_s=index * 0.1 + 0.025,
                cell_index=index,
                missed_detection_cost=3.0,
            )
            for index in range(cell_count)
        )
    problem = SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=0.1,
            cell_count=cell_count,
            minimum_active_cells=minimum_active_cells,
            allow_left_censored=left_censored,
            allow_right_censored=right_censored,
        ),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(
            satellite_cost=satellite_cost,
            episode_cost=episode_cost,
            huber_threshold=1.0,
        ),
    )
    hypothesis = SingleSatelliteHypothesis(
        hypothesis_id="satellite-delay-offset",
        object_name="STARLINK-TEST",
        catalog_number=12345,
        delay_s=0.1,
        cfo_offset_hz=0.0,
        delay_prior_cost=0.7,
        predictions=tuple(PredictedProbeCfo(item.probe_id, 0.0) for item in probes),
    )
    return problem, hypothesis


def _result_key(result: SingleSatelliteAssociationResult) -> tuple[object, ...]:
    return (
        result.objective.total_cost,
        result.selected,
        len(result.episodes),
        sum(result.activity_by_cell),
        result.activity_by_cell,
        tuple(item.observation_id for item in result.assignments),
    )


def _exhaustive_decode(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
) -> SingleSatelliteAssociationResult:
    observations_by_probe = {
        probe.probe_id: tuple(
            item for item in problem.observations if item.probe_id == probe.probe_id
        )
        for probe in problem.probes
    }
    candidates = []
    for raw_activity in itertools.product((False, True), repeat=problem.grid.cell_count):
        active_probes = tuple(
            probe for probe in problem.probes if probe.usable and raw_activity[probe.cell_index]
        )
        options = tuple(
            (None, *(item.observation_id for item in observations_by_probe[probe.probe_id]))
            for probe in active_probes
        )
        for selected in itertools.product(*options):
            assignments = tuple(
                ProbeAssignment(probe.probe_id, observation_id)
                for probe, observation_id in zip(active_probes, selected, strict=True)
                if observation_id is not None
            )
            try:
                result = evaluate_single_satellite_schedule(
                    problem,
                    hypothesis,
                    tuple(raw_activity),
                    assignments,
                )
            except ValueError:
                continue
            candidates.append(result)
    return min(candidates, key=_result_key)


def test_problem_is_canonical_and_keeps_empty_native_probes() -> None:
    probes = (
        CfoProbe("later", 0.125, 1, 2.0),
        CfoProbe("boundary", 0.100, 1, 2.0),
        CfoProbe("early", 0.025, 0, 2.0),
    )
    observations = (
        CfoCandidate("b", "later", "g-b", 20.0, 2.0, 4.0, 0.0, TEST_COMPONENT),
        CfoCandidate("a", "later", "g-a", 10.0, 2.0, 4.0, 0.0, TEST_COMPONENT),
    )
    problem = SatelliteActivityProblem(
        grid=ActivityGrid(0.0, 0.1, 2),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(1.0, 1.0),
        truncated_observation_count=3,
    )

    assert [item.probe_id for item in problem.probes] == ["early", "boundary", "later"]
    assert [item.observation_id for item in problem.observations] == ["a", "b"]
    assert problem.probes[1].cell_index == 1
    assert problem.source_observation_count == 5
    assert {item.probe_id for item in problem.probes} - {
        item.probe_id for item in problem.observations
    } == {"early", "boundary"}

    reversed_problem = SatelliteActivityProblem(
        grid=problem.grid,
        probes=tuple(reversed(problem.probes)),
        observations=tuple(reversed(problem.observations)),
        costs=problem.costs,
        truncated_observation_count=3,
    )
    assert reversed_problem == problem


def test_problem_rejects_misdeclared_cell_and_cross_probe_exclusion_group() -> None:
    with pytest.raises(ValueError, match="half-open activity cell"):
        SatelliteActivityProblem(
            grid=ActivityGrid(0.0, 0.1, 2),
            probes=(CfoProbe("p", 0.1, 0, 1.0),),
            observations=(),
            costs=AssociationCostModel(1.0, 1.0),
        )
    with pytest.raises(ValueError, match="half-open activity cell"):
        SatelliteActivityProblem(
            grid=ActivityGrid(0.0, 0.1, 4),
            probes=(CfoProbe("decimal-boundary", 0.3, 2, 1.0),),
            observations=(),
            costs=AssociationCostModel(1.0, 1.0),
        )
    accepted_boundary = SatelliteActivityProblem(
        grid=ActivityGrid(0.0, 0.1, 4),
        probes=(CfoProbe("decimal-boundary", 0.3, 3, 1.0),),
        observations=(),
        costs=AssociationCostModel(1.0, 1.0),
    )
    assert accepted_boundary.probes[0].cell_index == 3

    probes = (CfoProbe("a", 0.025, 0, 1.0), CfoProbe("b", 0.125, 1, 1.0))
    observations = (
        CfoCandidate("a-1", "a", "shared", 0.0, 1.0, 1.0, 0.0, TEST_COMPONENT),
        CfoCandidate("b-1", "b", "shared", 0.0, 1.0, 1.0, 0.0, TEST_COMPONENT),
    )
    with pytest.raises(ValueError, match="cannot span multiple probes"):
        _problem(probes=probes, observations=observations)

    mismatched_alias_costs = (
        CfoCandidate("alias-a", "a", "aliases", 0.0, 1.0, 1.0, 0.0, TEST_COMPONENT),
        CfoCandidate("alias-b", "a", "aliases", 1.0, 1.0, 2.0, 0.0, TEST_COMPONENT),
    )
    with pytest.raises(ValueError, match="share one clutter cost"):
        _problem(probes=probes, observations=mismatched_alias_costs)

    independent_components = (
        CfoCandidate("component-a", "a", "group-a", 0.0, 1.0, 1.0, 0.0, "component:a"),
        CfoCandidate("component-b", "a", "group-b", 0.0, 1.0, 1.0, 0.0, "component:b"),
    )
    with pytest.raises(ValueError, match="independently gauged components"):
        _problem(probes=probes, observations=independent_components)


def test_objective_checker_recomputes_every_cost_term() -> None:
    observations = (
        CfoCandidate("assigned", "p-0", "g-0", 10.0, 10.0, 5.0, 1.0, TEST_COMPONENT),
        CfoCandidate("clutter", "p-1", "g-1", 100.0, 10.0, 2.0, 1.0, TEST_COMPONENT),
    )
    problem, hypothesis = _problem(observations=observations)
    result = evaluate_single_satellite_schedule(
        problem,
        hypothesis,
        (True, True, False, True, True, False),
        (ProbeAssignment("p-0", "assigned"),),
    )

    assert result.objective.clutter_cost == pytest.approx(2.0)
    assert result.objective.matched_base_cost == pytest.approx(1.0)
    assert result.objective.residual_cost == pytest.approx(0.5)
    assert result.objective.missed_detection_cost == pytest.approx(9.0)
    assert result.objective.satellite_cost == pytest.approx(4.0)
    assert result.objective.episode_cost == pytest.approx(4.0)
    assert result.objective.delay_prior_cost == pytest.approx(0.7)
    assert result.objective.null_cost == pytest.approx(7.0)
    assert result.objective.total_cost == pytest.approx(21.2)
    assert result.objective.delta_from_null == pytest.approx(14.2)
    assert result.missed_probe_ids == ("p-1", "p-3", "p-4")
    assert result.unexplained_observation_ids == ("clutter",)


def test_fixed_probe_eligibility_suppresses_only_matching_and_misses_not_clutter() -> None:
    observations = (
        CfoCandidate("on-band", "p-0", "g-0", 0.0, 1.0, 10.0, 0.0, TEST_COMPONENT),
        CfoCandidate("off-band", "p-1", "g-1", 0.0, 1.0, 8.0, 0.0, TEST_COMPONENT),
    )
    problem, base = _problem(
        cell_count=2,
        minimum_active_cells=2,
        observations=observations,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypothesis = replace(base, eligible_probe_ids=("p-0",))

    result = decode_single_satellite(problem, hypothesis)

    assert result.activity_by_cell == (True, True)
    assert result.assignments == (ProbeAssignment("p-0", "on-band"),)
    assert result.missed_probe_ids == ()
    assert result.unexplained_observation_ids == ("off-band",)
    assert result.objective.null_cost == pytest.approx(18.0)
    assert result.objective.clutter_cost == pytest.approx(8.0)
    assert result.objective.total_cost == pytest.approx(8.7)
    assert problem.probes[1].usable

    with pytest.raises(ValueError, match="RF-ineligible"):
        evaluate_single_satellite_schedule(
            problem,
            hypothesis,
            (True, True),
            (ProbeAssignment("p-1", "off-band"),),
        )

    explicitly_nowhere = decode_single_satellite(
        problem,
        replace(base, eligible_probe_ids=()),
    )
    assert not explicitly_nowhere.selected
    assert explicitly_nowhere.objective.total_cost == pytest.approx(18.0)

    with pytest.raises(ValueError, match="unknown probes"):
        decode_single_satellite(
            problem,
            replace(base, eligible_probe_ids=("not-scheduled",)),
        )


def test_huber_convention_and_assignment_constraints_are_explicit() -> None:
    assert huber_loss(0.0, 1.0) == 0.0
    assert huber_loss(1.0, 1.0) == pytest.approx(0.5)
    assert huber_loss(2.0, 1.0) == pytest.approx(1.5)

    observation = CfoCandidate("o", "p-0", "g", 0.0, 1.0, 1.0, 0.0, TEST_COMPONENT)
    problem, hypothesis = _problem(observations=(observation,))
    with pytest.raises(ValueError, match="inactive"):
        evaluate_single_satellite_schedule(
            problem,
            hypothesis,
            (False,) * problem.grid.cell_count,
            (ProbeAssignment("p-0", "o"),),
        )


def test_alias_group_has_one_joint_clutter_cost_and_is_consumed_once() -> None:
    aliases = (
        CfoCandidate("alias-minus", "p-0", "physical-peak", -1.0, 1.0, 4.0, 0.0, TEST_COMPONENT),
        CfoCandidate("alias-plus", "p-0", "physical-peak", 0.0, 1.0, 4.0, 0.0, TEST_COMPONENT),
    )
    problem, hypothesis = _problem(
        cell_count=1,
        minimum_active_cells=1,
        observations=aliases,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypothesis = replace(hypothesis, delay_prior_cost=0.0)

    result = decode_single_satellite(problem, hypothesis)

    assert result.assignments == (ProbeAssignment("p-0", "alias-plus"),)
    assert result.objective.null_cost == pytest.approx(4.0)
    assert result.objective.clutter_cost == pytest.approx(0.0)
    assert result.unexplained_observation_ids == ()


@pytest.mark.parametrize(
    ("mask", "left", "right", "legal"),
    (
        ((False, True, True, True, True, False), False, False, False),
        ((True, True, True, True, False, False), False, False, False),
        ((True, True, True, True, False, False), True, False, True),
        ((False, False, True, True, True, True), False, False, False),
        ((False, False, True, True, True, True), False, True, True),
        ((False, True, True, True, True, True, False), False, False, True),
    ),
)
def test_duration_and_boundary_censoring_truth_table(
    mask: tuple[bool, ...],
    left: bool,
    right: bool,
    legal: bool,
) -> None:
    problem, hypothesis = _problem(
        cell_count=len(mask),
        minimum_active_cells=5,
        left_censored=left,
        right_censored=right,
    )
    if legal:
        result = evaluate_single_satellite_schedule(problem, hypothesis, mask)
        assert len(result.episodes) == 1
        assert result.episodes[0].duration_s == pytest.approx(sum(mask) * 0.1)
    else:
        with pytest.raises(ValueError, match="shorter than the minimum"):
            evaluate_single_satellite_schedule(problem, hypothesis, mask)


def test_simulator_is_reproducible_and_noiseless_truth_is_exact() -> None:
    config = SyntheticSingleSatelliteConfig(
        seed=17,
        cell_count=8,
        active_intervals=((1, 6),),
        noise_sigma_hz=1.0,
        detection_probability=0.8,
        mean_clutter_per_probe=0.5,
    )
    first = simulate_single_satellite_case(config)
    second = simulate_single_satellite_case(config)
    changed = simulate_single_satellite_case(replace(config, seed=18))

    assert first == second
    assert changed.problem != first.problem
    assert changed.truth.activity_by_cell == first.truth.activity_by_cell

    noiseless = simulate_single_satellite_case(
        replace(
            config,
            seed=2,
            noise_sigma_hz=1e-9,
            detection_probability=1.0,
            mean_clutter_per_probe=0.0,
        )
    )
    prediction = {item.probe_id: item.cfo_hz for item in noiseless.hypothesis.predictions}
    for assignment in noiseless.truth.assignments:
        observation = next(
            item
            for item in noiseless.problem.observations
            if item.observation_id == assignment.observation_id
        )
        assert observation.cfo_hz == pytest.approx(
            prediction[assignment.probe_id] + noiseless.truth.cfo_offset_hz,
            abs=5e-9,
        )


def test_linear_doppler_exposes_the_delay_offset_ridge() -> None:
    times = np.linspace(-1.0, 1.0, 9)
    delays = (-0.5, 0.0, 0.25, 0.5)
    slope = -3_000.0
    observed = slope * (times + 0.25) + 120_000.0
    candidates = tuple(
        DelayProfileCandidate(
            delay_s=delay,
            predicted_cfo_hz=tuple(slope * (times + delay)),
        )
        for delay in delays
    )
    profile = profile_delay_and_cfo_offset(
        observed,
        np.full_like(observed, 10.0),
        candidates,
        delay_prior_mean_s=0.0,
        delay_prior_sigma_s=0.2,
    )

    assert profile.data_flat is True
    assert profile.data_ambiguous is True
    assert profile.delay_prior_dominated is True
    assert profile.posterior_differs_from_data_only is False
    assert profile.data_minimum_count == len(delays)
    assert profile.posterior_best.delay_s == pytest.approx(0.0)
    assert len({round(item.fitted_cfo_offset_hz, 6) for item in profile.points}) == len(delays)


def test_curvature_breaks_the_delay_offset_ridge() -> None:
    times = np.linspace(-1.0, 1.0, 21)
    delays = (-0.2, 0.0, 0.2, 0.4)
    observed = 500.0 * (times + 0.2) ** 2 + 80_000.0
    candidates = tuple(
        DelayProfileCandidate(
            delay_s=delay,
            predicted_cfo_hz=tuple(500.0 * (times + delay) ** 2),
        )
        for delay in delays
    )
    profile = profile_delay_and_cfo_offset(
        observed,
        np.full_like(observed, 5.0),
        candidates,
        delay_prior_mean_s=0.0,
        delay_prior_sigma_s=1.0,
    )

    assert profile.data_only_best.delay_s == pytest.approx(0.2)
    assert profile.posterior_best.delay_s == pytest.approx(0.2)
    assert profile.data_minimum_count == 1
    assert profile.data_ambiguous is False
    assert profile.delay_prior_dominated is False
    assert profile.posterior_differs_from_data_only is False
    assert profile.data_only_best.fitted_cfo_offset_hz == pytest.approx(80_000.0)

    strong_wrong_prior = profile_delay_and_cfo_offset(
        observed,
        np.full_like(observed, 5.0),
        candidates,
        delay_prior_mean_s=0.0,
        delay_prior_sigma_s=0.005,
    )
    assert strong_wrong_prior.data_only_best.delay_s == pytest.approx(0.2)
    assert strong_wrong_prior.posterior_best.delay_s == pytest.approx(0.0)
    assert strong_wrong_prior.data_ambiguous is False
    assert strong_wrong_prior.posterior_differs_from_data_only is True
    assert strong_wrong_prior.delay_prior_dominated is True


def test_huber_offset_profile_handles_extreme_heteroscedastic_outliers() -> None:
    observed = np.array([-10_000.0, -9_000.0, 9_000.0])
    profile = profile_delay_and_cfo_offset(
        observed,
        np.array([10.0, 1.0, 0.9]),
        (DelayProfileCandidate(0.0, (0.0, 0.0, 0.0)),),
        delay_prior_mean_s=0.0,
        delay_prior_sigma_s=1.0,
    )

    assert profile.posterior_best.fitted_cfo_offset_hz == pytest.approx(
        8_998.801605,
        abs=1e-5,
    )


def test_decoder_recovers_exact_five_cell_episode_and_prefers_null_without_evidence() -> None:
    case = simulate_single_satellite_case(
        SyntheticSingleSatelliteConfig(
            seed=4,
            cell_count=10,
            active_intervals=((2, 7),),
            noise_sigma_hz=1.0,
        )
    )
    decoded = decode_single_satellite(case.problem, case.hypothesis)
    assert decoded.activity_by_cell == case.truth.activity_by_cell
    assert decoded.selected is True
    assert decoded.episodes[0].duration_s == pytest.approx(0.5)

    null_case = simulate_single_satellite_case(
        SyntheticSingleSatelliteConfig(
            seed=4,
            cell_count=10,
            active_intervals=(),
            mean_clutter_per_probe=0.0,
        )
    )
    null = decode_single_satellite(null_case.problem, null_case.hypothesis)
    assert null.selected is False
    assert null.activity_by_cell == (False,) * 10

    clutter_observations = tuple(
        CfoCandidate(
            f"noise-{index}",
            f"p-{index}",
            f"noise-g-{index}",
            50.0,
            1.0,
            2.0,
            9.0,
            TEST_COMPONENT,
        )
        for index in range(3)
    )
    clutter_problem, clutter_hypothesis = _problem(
        cell_count=3,
        minimum_active_cells=1,
        observations=clutter_observations,
    )
    clutter_null = decode_single_satellite(clutter_problem, clutter_hypothesis)
    assert clutter_null.selected is False
    assert clutter_null.objective.total_cost == pytest.approx(6.0)
    assert clutter_null.objective.null_cost == pytest.approx(6.0)
    assert clutter_null.objective.delta_from_null == pytest.approx(0.0)
    assert clutter_null.unexplained_observation_ids == tuple(
        item.observation_id for item in clutter_problem.observations
    )


def test_four_supported_cells_cannot_buy_a_free_fifth_cell() -> None:
    probes = tuple(CfoProbe(f"p-{index}", index * 0.1 + 0.025, index, 20.0) for index in range(6))
    observations = tuple(
        CfoCandidate(
            f"o-{index}",
            f"p-{index}",
            f"g-{index}",
            0.0,
            1.0,
            2.0,
            0.0,
            TEST_COMPONENT,
        )
        for index in range(1, 5)
    )
    problem, hypothesis = _problem(
        cell_count=6,
        minimum_active_cells=5,
        probes=probes,
        observations=observations,
        satellite_cost=1.0,
        episode_cost=1.0,
    )
    hypothesis = replace(hypothesis, delay_prior_cost=0.0)

    decoded = decode_single_satellite(problem, hypothesis)
    assert decoded.selected is False


def test_two_episodes_pay_one_satellite_cost_and_two_episode_costs() -> None:
    case = simulate_single_satellite_case(
        SyntheticSingleSatelliteConfig(
            seed=8,
            cell_count=15,
            active_intervals=((0, 5), (10, 15)),
            noise_sigma_hz=1.0,
        )
    )
    decoded = decode_single_satellite(case.problem, case.hypothesis)

    assert decoded.activity_by_cell == case.truth.activity_by_cell
    assert decoded.assignments == case.truth.assignments
    assert decoded.missed_probe_ids == ()
    assert len(decoded.episodes) == 2
    assert decoded.objective.satellite_cost == pytest.approx(case.problem.costs.satellite_cost)
    assert decoded.objective.episode_cost == pytest.approx(2.0 * case.problem.costs.episode_cost)


def test_exact_ties_prefer_null_then_fewer_episodes_and_active_cells() -> None:
    null_problem, null_hypothesis = _problem(
        cell_count=3,
        minimum_active_cells=1,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    null_hypothesis = replace(null_hypothesis, delay_prior_cost=0.0)
    assert decode_single_satellite(null_problem, null_hypothesis).selected is False

    observations = tuple(
        CfoCandidate(
            f"o-{index}",
            f"p-{index}",
            f"g-{index}",
            0.0,
            1.0,
            0.0 if index == 2 else 1.0,
            0.0,
            TEST_COMPONENT,
        )
        for index in range(5)
    )
    episode_problem, episode_hypothesis = _problem(
        cell_count=5,
        minimum_active_cells=2,
        observations=observations,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    episode_hypothesis = replace(episode_hypothesis, delay_prior_cost=0.0)
    episode_result = decode_single_satellite(episode_problem, episode_hypothesis)
    assert episode_result.activity_by_cell == (True, True, True, True, True)
    assert len(episode_result.episodes) == 1

    zero_miss_probes = tuple(
        CfoProbe(f"p-{index}", index * 0.1 + 0.025, index, 0.0) for index in range(4)
    )
    final_evidence = (CfoCandidate("last", "p-3", "last-g", 0.0, 1.0, 1.0, 0.0, TEST_COMPONENT),)
    activity_problem, activity_hypothesis = _problem(
        cell_count=4,
        minimum_active_cells=2,
        probes=zero_miss_probes,
        observations=final_evidence,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    activity_hypothesis = replace(activity_hypothesis, delay_prior_cost=0.0)
    activity_result = decode_single_satellite(activity_problem, activity_hypothesis)
    assert activity_result.activity_by_cell == (False, False, True, True)


def test_probe_choice_ties_prefer_miss_then_lexical_observation() -> None:
    probes = (
        CfoProbe("force", 0.01, 0, 10.0),
        CfoProbe("miss-tie", 0.04, 0, 0.0),
        CfoProbe("lexical-tie", 0.07, 0, 10.0),
    )
    observations = (
        CfoCandidate("force-signal", "force", "force-g", 0.0, 1.0, 5.0, 0.0, TEST_COMPONENT),
        CfoCandidate("miss-a", "miss-tie", "miss-a-g", 0.0, 1.0, 1.0, 1.0, TEST_COMPONENT),
        CfoCandidate("miss-b", "miss-tie", "miss-b-g", 0.0, 1.0, 1.0, 1.0, TEST_COMPONENT),
        CfoCandidate("z-choice", "lexical-tie", "z-g", 0.0, 1.0, 2.0, 1.0, TEST_COMPONENT),
        CfoCandidate("a-choice", "lexical-tie", "a-g", 0.0, 1.0, 2.0, 1.0, TEST_COMPONENT),
    )
    problem, hypothesis = _problem(
        cell_count=1,
        minimum_active_cells=1,
        probes=probes,
        observations=observations,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    hypothesis = replace(hypothesis, delay_prior_cost=0.0)

    result = decode_single_satellite(problem, hypothesis)

    assert result.selected is True
    assert result.missed_probe_ids == ("miss-tie",)
    assert tuple(item.observation_id for item in result.assignments) == (
        "force-signal",
        "a-choice",
    )


def test_oracle_covers_multiple_native_probes_and_candidate_choices_per_cell() -> None:
    probes = (
        CfoProbe("p-0-a", 0.01, 0, 1.2),
        CfoProbe("p-0-empty", 0.06, 0, 0.7),
        CfoProbe("p-1", 0.14, 1, 2.1),
        CfoProbe("p-2", 0.24, 2, 1.8),
    )
    observations = (
        CfoCandidate("p0-near", "p-0-a", "p0-near-g", 0.1, 1.0, 3.1, 0.2, TEST_COMPONENT),
        CfoCandidate("p0-far", "p-0-a", "p0-far-g", 4.0, 1.0, 1.4, 0.8, TEST_COMPONENT),
        CfoCandidate("p1", "p-1", "p1-g", -0.2, 1.0, 2.8, 0.1, TEST_COMPONENT),
    )
    problem, hypothesis = _problem(
        cell_count=3,
        minimum_active_cells=2,
        probes=probes,
        observations=observations,
        satellite_cost=0.3,
        episode_cost=0.4,
    )
    hypothesis = replace(hypothesis, delay_prior_cost=0.2)

    expected = _exhaustive_decode(problem, hypothesis)
    actual = decode_single_satellite(problem, hypothesis)

    assert actual.objective.total_cost == pytest.approx(expected.objective.total_cost)
    assert _result_key(actual)[1:] == _result_key(expected)[1:]


@pytest.mark.parametrize("left", (False, True))
@pytest.mark.parametrize("right", (False, True))
def test_semimarkov_decoder_matches_exhaustive_oracle(left: bool, right: bool) -> None:
    source = random.Random(9103 + 10 * left + right)
    for case_index in range(4):
        probes = tuple(
            CfoProbe(
                f"p-{index}",
                index * 0.1 + 0.025,
                index,
                source.uniform(0.5, 4.0),
            )
            for index in range(6)
        )
        observations = tuple(
            CfoCandidate(
                f"o-{index}",
                f"p-{index}",
                f"g-{index}",
                source.uniform(-3.0, 3.0),
                1.0,
                source.uniform(0.0, 5.0),
                source.uniform(0.0, 2.0),
                TEST_COMPONENT,
            )
            for index in range(6)
        )
        problem, hypothesis = _problem(
            cell_count=6,
            minimum_active_cells=3,
            probes=probes,
            observations=observations,
            left_censored=left,
            right_censored=right,
            satellite_cost=source.uniform(0.0, 3.0),
            episode_cost=source.uniform(0.0, 2.0),
        )
        hypothesis = replace(
            hypothesis,
            hypothesis_id=f"oracle-{case_index}",
            delay_prior_cost=source.uniform(0.0, 1.0),
        )
        expected = _exhaustive_decode(problem, hypothesis)
        actual = decode_single_satellite(problem, hypothesis)

        assert actual.objective.total_cost == pytest.approx(
            expected.objective.total_cost, abs=1e-10
        )
        assert _result_key(actual)[1:] == _result_key(expected)[1:]


def test_decoder_is_invariant_to_probe_and_observation_order() -> None:
    case = simulate_single_satellite_case(
        SyntheticSingleSatelliteConfig(
            seed=12,
            cell_count=8,
            active_intervals=((1, 6),),
            noise_sigma_hz=2.0,
            mean_clutter_per_probe=0.25,
        )
    )
    reversed_problem = SatelliteActivityProblem(
        grid=case.problem.grid,
        probes=tuple(reversed(case.problem.probes)),
        observations=tuple(reversed(case.problem.observations)),
        costs=case.problem.costs,
        truncated_observation_count=case.problem.truncated_observation_count,
    )

    assert decode_single_satellite(reversed_problem, case.hypothesis) == decode_single_satellite(
        case.problem, case.hypothesis
    )


def test_research_prototype_imports_no_infrastructure() -> None:
    path = Path(activity_module.__file__)
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
    offending = {
        module
        for module in imported
        for root in forbidden
        if module == root or module.startswith(f"{root}.")
    }
    assert not offending
