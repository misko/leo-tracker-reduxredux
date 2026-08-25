from __future__ import annotations

import itertools
import math
import random
from dataclasses import replace

import pytest

import leo.analysis.research.cross_dwell_shared_norad as cross_dwell_shared_norad
from leo.analysis.research.cross_dwell_shared_norad import (
    ASSOCIATION_CLAIM_KIND,
    EVALUATOR_ALGORITHM,
    AssociationDwell,
    CrossDwellAssociationProblem,
    DwellStateSelection,
    ExactDwellCatalogStateSpace,
    FiniteDwellState,
    IncompleteCrossDwellEvidenceError,
    SharedNoradSchedule,
    decode_cross_dwell_shared_norad,
    evaluate_shared_norad_schedule,
)


def _space(
    dwell_id: str,
    catalog_number: int,
    *reduced_objectives: float,
    exhausted: bool = True,
    expected_state_count: int | None = None,
    pruned_state_count: int = 0,
    state_id_prefix: str = "state",
) -> ExactDwellCatalogStateSpace:
    states = tuple(
        FiniteDwellState(f"{state_id_prefix}-{index}", value)
        for index, value in enumerate(reduced_objectives)
    )
    return ExactDwellCatalogStateSpace(
        dwell_id=dwell_id,
        catalog_number=catalog_number,
        states=states,
        expected_state_count=(
            len(states) if expected_state_count is None else expected_state_count
        ),
        supplied_state_space_exhausted=exhausted,
        pruned_state_count=pruned_state_count,
    )


def _problem(
    *,
    dwells: tuple[AssociationDwell, ...],
    catalogs: tuple[int, ...],
    values: dict[tuple[str, int], tuple[float, ...]],
    required: tuple[str, ...],
    minimum_sessions: int,
    shared_cost: float,
) -> CrossDwellAssociationProblem:
    return CrossDwellAssociationProblem(
        dwells=dwells,
        catalog_numbers=catalogs,
        candidate_universe_catalog_count=len(catalogs),
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=tuple(
            _space(dwell.dwell_id, catalog, *values[(dwell.dwell_id, catalog)])
            for dwell in dwells
            for catalog in catalogs
        ),
        required_confirmation_dwell_ids=required,
        minimum_distinct_session_count=minimum_sessions,
        shared_identity_cost=shared_cost,
    )


def test_reducer_selects_one_shared_catalog_charges_identity_once_and_reports_gap() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 1_000.0),
        AssociationDwell("d2", "session-b", 2_000.0),
        AssociationDwell("d3", "session-c", 3_000.0),
    )
    problem = _problem(
        dwells=dwells,
        catalogs=(10, 20),
        values={
            ("d1", 10): (-3.0, -4.0),
            ("d2", 10): (-3.0,),
            ("d3", 10): (1.0,),
            ("d1", 20): (-3.0,),
            ("d2", 20): (-2.0,),
            ("d3", 20): (-4.0,),
        },
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=2.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number == 20
    assert result.reduced_objective == -7.0  # -9 dwell-local + one shared cost of 2.
    assert result.objective == 5_993.0
    assert result.support_session_ids == ("session-a", "session-b", "session-c")
    assert tuple(item.reduced_objective for item in result.contributions) == (
        -3.0,
        -2.0,
        -4.0,
    )
    assert result.runner_up_catalog_number == 10
    assert result.runner_up_reduced_objective == -5.0
    assert result.runner_up_margin == 2.0
    assert result.independent_identity_reduced_objective == -11.0
    assert result.independent_identity_objective == 5_989.0
    assert result.best_shared_without_identity_catalog_number == 20
    assert result.best_shared_without_identity_reduced_objective == -9.0
    assert result.coherence_gap == 2.0
    assert result.claim_kind == ASSOCIATION_CLAIM_KIND
    assert "track" not in result.claim_kind
    assert result.exact


def test_optional_silent_gap_stays_null_without_a_transition_or_bridge_cost() -> None:
    dwells = (
        AssociationDwell("early", "session-a", 10.0),
        AssociationDwell("gap", "session-gap", 20.0),
        AssociationDwell("late", "session-b", 30.0),
    )
    problem = _problem(
        dwells=dwells,
        catalogs=(42,),
        values={
            ("early", 42): (-2.0,),
            ("gap", 42): (0.25,),
            ("late", 42): (-3.0,),
        },
        required=("early", "late"),
        minimum_sessions=2,
        shared_cost=1.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number == 42
    assert result.reduced_objective == -4.0
    assert [
        (item.dwell_id, item.state_id, item.reduced_objective) for item in result.contributions
    ] == [
        ("early", "state-0", -2.0),
        ("gap", None, 0.0),
        ("late", "state-0", -3.0),
    ]
    assert result.support_session_ids == ("session-a", "session-b")


def test_duplicate_dwell_support_does_not_substitute_for_distinct_sessions() -> None:
    dwells = (
        AssociationDwell("d1", "same-session", 1.0),
        AssociationDwell("d2", "same-session", 1.0),
        AssociationDwell("d3", "other-session", 1.0),
    )
    problem = _problem(
        dwells=dwells,
        catalogs=(42,),
        values={("d1", 42): (-5.0,), ("d2", 42): (-4.0,), ("d3", 42): (1.0,)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=0.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number is None
    assert not result.catalog_scores[0].admissible
    assert result.catalog_scores[0].support_session_ids == ("same-session",)
    assert result.best_shared_without_identity_catalog_number is None
    assert result.coherence_gap is None


def test_every_predeclared_confirmation_dwell_must_improve_strictly() -> None:
    dwells = (
        AssociationDwell("required-a", "session-a", 1.0),
        AssociationDwell("required-b", "session-b", 1.0),
        AssociationDwell("optional", "session-c", 1.0),
    )
    problem = _problem(
        dwells=dwells,
        catalogs=(7,),
        values={
            ("required-a", 7): (-2.0,),
            ("required-b", 7): (0.0,),
            ("optional", 7): (-100.0,),
        },
        required=("required-a", "required-b"),
        minimum_sessions=2,
        shared_cost=0.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number is None
    score = result.catalog_scores[0]
    assert not score.admissible
    assert score.missing_required_confirmation_dwell_ids == ("required-b",)
    assert (
        next(item for item in score.contributions if item.dwell_id == "required-b").state_id is None
    )


def test_null_wins_an_exact_nonimproving_universe_and_is_the_tie_preference() -> None:
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 12.0),
            AssociationDwell("d2", "session-b", 8.0),
        ),
        catalogs=(8,),
        values={("d1", 8): (-0.5,), ("d2", 8): (-0.5,)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=1.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number is None
    assert result.objective == 20.0
    assert result.runner_up_catalog_number == 8
    assert result.runner_up_reduced_objective == 0.0
    assert result.runner_up_margin == 0.0


def test_ties_and_input_permutations_have_a_canonical_result() -> None:
    dwells = (
        AssociationDwell("b", "session-b", 2.0),
        AssociationDwell("a", "session-a", 1.0),
    )
    spaces = tuple(
        ExactDwellCatalogStateSpace(
            dwell_id=dwell_id,
            catalog_number=catalog,
            states=(FiniteDwellState("z", -2.0), FiniteDwellState("a", -2.0)),
            expected_state_count=2,
            supplied_state_space_exhausted=True,
        )
        for catalog in (20, 10)
        for dwell_id in ("b", "a")
    )
    problem = CrossDwellAssociationProblem(
        dwells=dwells,
        catalog_numbers=(20, 10),
        candidate_universe_catalog_count=2,
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=spaces,
        required_confirmation_dwell_ids=("b", "a"),
        minimum_distinct_session_count=2,
        shared_identity_cost=1.0,
    )
    permuted = CrossDwellAssociationProblem(
        dwells=tuple(reversed(dwells)),
        catalog_numbers=(10, 20),
        candidate_universe_catalog_count=2,
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=tuple(reversed(spaces)),
        required_confirmation_dwell_ids=("a", "b"),
        minimum_distinct_session_count=2,
        shared_identity_cost=1.0,
    )

    first = decode_cross_dwell_shared_norad(problem)
    second = decode_cross_dwell_shared_norad(permuted)

    assert first == second
    assert first.selected_catalog_number == 10
    assert all(item.state_id == "a" for item in first.contributions)
    assert first.runner_up_catalog_number == 20
    assert first.runner_up_margin == 0.0


@pytest.mark.parametrize("failure_kind", ["missing", "truncated", "unexhausted", "pruned"])
def test_incomplete_candidate_evidence_fails_closed(failure_kind: str) -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 1.0),
        AssociationDwell("d2", "session-b", 1.0),
    )
    spaces = [
        _space("d1", 10, -2.0),
        _space("d2", 10, -2.0),
        _space("d1", 20, -3.0),
        _space("d2", 20, -3.0),
    ]
    if failure_kind == "missing":
        spaces.pop()
    elif failure_kind == "truncated":
        spaces[-1] = replace(spaces[-1], expected_state_count=2)
    elif failure_kind == "unexhausted":
        spaces[-1] = replace(spaces[-1], supplied_state_space_exhausted=False)
    else:
        spaces[-1] = replace(spaces[-1], expected_state_count=2, pruned_state_count=1)
    problem = CrossDwellAssociationProblem(
        dwells=dwells,
        catalog_numbers=(10, 20),
        candidate_universe_catalog_count=2,
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=tuple(spaces),
        required_confirmation_dwell_ids=("d1", "d2"),
        minimum_distinct_session_count=2,
        shared_identity_cost=0.0,
    )

    with pytest.raises(IncompleteCrossDwellEvidenceError, match="unknown evidence"):
        decode_cross_dwell_shared_norad(problem)
    with pytest.raises(IncompleteCrossDwellEvidenceError, match="unknown evidence"):
        evaluate_shared_norad_schedule(problem, SharedNoradSchedule(None))


def test_large_null_objectives_cannot_erase_a_small_reduced_improvement() -> None:
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 1.0e16),
            AssociationDwell("d2", "session-b", 1.0e16),
        ),
        catalogs=(55,),
        values={("d1", 55): (-0.75,), ("d2", 55): (-0.75,)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=1.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number == 55
    assert result.reduced_objective == -0.5
    assert result.null_objective == 2.0e16
    assert (
        result.objective == 2.0e16
    )  # Rounded full total is diagnostic, not the decision primitive.
    assert result.independent_identity_reduced_objective == -1.5
    assert result.coherence_gap == 0.0


def test_shared_cost_is_summed_with_primitive_contributions_before_strict_gate() -> None:
    minimum_subnormal = 5e-324
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 0.0),
            AssociationDwell("d2", "session-b", 0.0),
            AssociationDwell("d3", "session-c", 0.0),
        ),
        catalogs=(55,),
        values={
            ("d1", 55): (-9.0,),
            ("d2", 55): (-1.0,),
            ("d3", 55): (-minimum_subnormal,),
        },
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=10.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert math.fsum((-9.0, -1.0, -minimum_subnormal)) == -10.0
    assert result.selected_catalog_number == 55
    assert result.reduced_objective == -minimum_subnormal
    assert result.objective == -minimum_subnormal


def test_runner_margin_uses_primitive_catalog_contributions() -> None:
    minimum_subnormal = 5e-324
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 0.0),
            AssociationDwell("d2", "session-b", 0.0),
            AssociationDwell("d3", "session-c", 0.0),
        ),
        catalogs=(10, 20),
        values={
            ("d1", 10): (-9.0,),
            ("d2", 10): (-1.0,),
            ("d3", 10): (-2.0 * minimum_subnormal,),
            ("d1", 20): (-9.0,),
            ("d2", 20): (-1.0,),
            ("d3", 20): (-minimum_subnormal,),
        },
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=10.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number == 10
    assert result.reduced_objective == -2.0 * minimum_subnormal
    assert result.runner_up_catalog_number == 20
    assert result.runner_up_reduced_objective == -minimum_subnormal
    assert result.runner_up_margin == minimum_subnormal


@pytest.mark.parametrize("shared_cost", [0.0, 10.0])
def test_primitive_catalog_ordering_breaks_a_rounded_total_tie_correctly(
    shared_cost: float,
) -> None:
    minimum_subnormal = 5e-324
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 0.0),
            AssociationDwell("d2", "session-b", 0.0),
            AssociationDwell("d3", "session-c", 0.0),
        ),
        catalogs=(10, 20),
        values={
            ("d1", 10): (-9.0,),
            ("d2", 10): (-1.0,),
            ("d3", 10): (-minimum_subnormal,),
            ("d1", 20): (-9.0,),
            ("d2", 20): (-1.0,),
            ("d3", 20): (-2.0 * minimum_subnormal,),
        },
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=shared_cost,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.catalog_scores[0].shared_without_identity_reduced_objective == -10.0
    assert result.catalog_scores[1].shared_without_identity_reduced_objective == -10.0
    assert result.selected_catalog_number == 20
    assert result.runner_up_catalog_number == 10
    assert result.runner_up_margin == minimum_subnormal
    assert result.runner_up_margin >= 0.0
    assert result.best_shared_without_identity_catalog_number == 20
    assert result.coherence_gap == 0.0


def test_coherence_gap_uses_primitive_per_dwell_contributions() -> None:
    minimum_subnormal = 5e-324
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 0.0),
            AssociationDwell("d2", "session-b", 0.0),
            AssociationDwell("d3", "session-c", 0.0),
        ),
        catalogs=(10, 20),
        values={
            ("d1", 10): (-9.0,),
            ("d2", 10): (-1.0,),
            ("d3", 10): (-minimum_subnormal,),
            ("d1", 20): (-8.0,),
            ("d2", 20): (-0.5,),
            ("d3", 20): (-2.0 * minimum_subnormal,),
        },
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=0.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.best_shared_without_identity_catalog_number == 10
    assert result.best_shared_without_identity_reduced_objective == -10.0
    assert result.independent_identity_reduced_objective == -10.0
    assert result.coherence_gap == minimum_subnormal


def test_public_evaluator_rejects_nonimproving_unknown_and_inadmissible_schedules() -> None:
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 1.0),
            AssociationDwell("d2", "session-b", 1.0),
        ),
        catalogs=(10,),
        values={("d1", 10): (-2.0, -1.0, 0.0), ("d2", 10): (-3.0,)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=1.0,
    )
    valid = evaluate_shared_norad_schedule(
        problem,
        SharedNoradSchedule(
            10,
            (DwellStateSelection("d1", "state-0"), DwellStateSelection("d2", "state-0")),
        ),
    )

    assert valid.association_reduced_objective == -4.0
    assert valid.algorithm == EVALUATOR_ALGORITHM
    assert valid.claim_kind == ASSOCIATION_CLAIM_KIND
    assert valid.fixed_schedule_score_exact
    with pytest.raises(ValueError, match="strictly improve"):
        evaluate_shared_norad_schedule(
            problem,
            SharedNoradSchedule(
                10,
                (
                    DwellStateSelection("d1", "state-2"),
                    DwellStateSelection("d2", "state-0"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="unknown state"):
        evaluate_shared_norad_schedule(
            problem,
            SharedNoradSchedule(
                10,
                (
                    DwellStateSelection("d1", "absent"),
                    DwellStateSelection("d2", "state-0"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="canonical best state"):
        evaluate_shared_norad_schedule(
            problem,
            SharedNoradSchedule(
                10,
                (
                    DwellStateSelection("d1", "state-1"),
                    DwellStateSelection("d2", "state-0"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="omits a strict-null-improving state"):
        evaluate_shared_norad_schedule(
            problem,
            SharedNoradSchedule(10, (DwellStateSelection("d1", "state-0"),)),
        )


def test_independent_checker_catches_optimizer_bug_even_if_catalog_is_labelled_inadmissible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 1.0),
            AssociationDwell("d2", "session-b", 1.0),
        ),
        catalogs=(10,),
        values={("d1", 10): (-2.0, 1.0), ("d2", 10): (-3.0, 1.0)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=0.0,
    )
    monkeypatch.setattr(
        cross_dwell_shared_norad,
        "_best_state",
        lambda state_space: state_space.states[-1],
    )

    independently_checked = evaluate_shared_norad_schedule(
        problem,
        SharedNoradSchedule(
            10,
            (DwellStateSelection("d1", "state-0"), DwellStateSelection("d2", "state-0")),
        ),
    )

    assert independently_checked.association_reduced_objective == -5.0
    with pytest.raises(ArithmeticError, match="independent catalog-score checker"):
        decode_cross_dwell_shared_norad(problem)


@pytest.mark.parametrize(
    ("catalog_count", "exhausted", "pruned"),
    [
        (2, True, False),
        (1, False, False),
        (1, True, True),
    ],
)
def test_favorable_shortlist_without_complete_catalogue_receipt_fails_closed(
    catalog_count: int,
    exhausted: bool,
    pruned: bool,
) -> None:
    problem = _problem(
        dwells=(
            AssociationDwell("d1", "session-a", 1.0),
            AssociationDwell("d2", "session-b", 1.0),
        ),
        catalogs=(10,),
        values={("d1", 10): (-100.0,), ("d2", 10): (-100.0,)},
        required=("d1", "d2"),
        minimum_sessions=2,
        shared_cost=0.0,
    )
    incomplete = replace(
        problem,
        candidate_universe_catalog_count=catalog_count,
        candidate_universe_exhausted=exhausted,
        candidate_universe_pruned=pruned,
    )

    with pytest.raises(IncompleteCrossDwellEvidenceError, match="catalogue universe"):
        decode_cross_dwell_shared_norad(incomplete)
    with pytest.raises(IncompleteCrossDwellEvidenceError, match="catalogue universe"):
        evaluate_shared_norad_schedule(incomplete, SharedNoradSchedule(None))


def test_explicit_exhausted_empty_state_space_is_certified_ineligibility() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 1.0),
        AssociationDwell("d2", "session-b", 1.0),
    )
    problem = CrossDwellAssociationProblem(
        dwells=dwells,
        catalog_numbers=(10,),
        candidate_universe_catalog_count=1,
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=(_space("d1", 10), _space("d2", 10, -100.0)),
        required_confirmation_dwell_ids=("d1",),
        minimum_distinct_session_count=2,
        shared_identity_cost=0.0,
    )

    result = decode_cross_dwell_shared_norad(problem)

    assert result.selected_catalog_number is None
    assert result.catalog_scores[0].missing_required_confirmation_dwell_ids == ("d1",)
    assert result.catalog_scores[0].contributions[0].state_id is None


def _exhaustive_best(problem: CrossDwellAssociationProblem) -> tuple[int | None, float]:
    """Independent tiny oracle over null plus every active state combination."""

    state_space_by_key = {
        (item.dwell_id, item.catalog_number): item for item in problem.state_spaces
    }
    candidates: list[tuple[float, int]] = []
    for catalog in problem.catalog_numbers:
        options = tuple(
            (
                None,
                *(
                    state
                    for state in state_space_by_key[(dwell.dwell_id, catalog)].states
                    if state.reduced_objective < 0.0
                ),
            )
            for dwell in problem.dwells
        )
        for choices in itertools.product(*options):
            active_dwell_ids = {
                dwell.dwell_id
                for dwell, state in zip(problem.dwells, choices, strict=True)
                if state is not None
            }
            if not set(problem.required_confirmation_dwell_ids) <= active_dwell_ids:
                continue
            support_sessions = {
                dwell.session_id
                for dwell, state in zip(problem.dwells, choices, strict=True)
                if state is not None
            }
            if len(support_sessions) < problem.minimum_distinct_session_count:
                continue
            reduced = math.fsum(
                (
                    problem.shared_identity_cost,
                    *(state.reduced_objective for state in choices if state is not None),
                )
            )
            candidates.append((reduced, catalog))
    if not candidates:
        return None, 0.0
    best_reduced, best_catalog = min(candidates, key=lambda item: (item[0], item[1]))
    if not best_reduced < 0.0:
        return None, 0.0
    return best_catalog, best_reduced


def test_reducer_matches_an_exhaustive_finite_schedule_oracle() -> None:
    for seed in range(32):
        random_generator = random.Random(seed)
        dwells = (
            AssociationDwell("d0", "session-a", 100.0),
            AssociationDwell("d1", "session-b", 200.0),
            AssociationDwell("d2", "session-c", 300.0),
        )
        catalogs = (101, 202, 303)
        spaces = tuple(
            _space(
                dwell.dwell_id,
                catalog,
                random_generator.choice((-4.0, -1.0, 0.0, 2.0)),
                random_generator.choice((-3.0, -0.5, 0.0, 1.0)),
            )
            for dwell in dwells
            for catalog in catalogs
        )
        problem = CrossDwellAssociationProblem(
            dwells=dwells,
            catalog_numbers=catalogs,
            candidate_universe_catalog_count=len(catalogs),
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=spaces,
            required_confirmation_dwell_ids=("d0",),
            minimum_distinct_session_count=2,
            shared_identity_cost=2.25,
        )

        result = decode_cross_dwell_shared_norad(problem)
        oracle_catalog, oracle_reduced = _exhaustive_best(problem)

        assert result.selected_catalog_number == oracle_catalog
        assert result.reduced_objective == oracle_reduced


def test_invalid_problem_and_schedule_contracts_are_rejected() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 1.0),
        AssociationDwell("d2", "session-b", 1.0),
    )
    spaces = (_space("d1", 1, -1.0), _space("d2", 1, -1.0))
    with pytest.raises(ValueError, match="confirmation dwell"):
        CrossDwellAssociationProblem(
            dwells=dwells,
            catalog_numbers=(1,),
            candidate_universe_catalog_count=1,
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=spaces,
            required_confirmation_dwell_ids=(),
            minimum_distinct_session_count=2,
            shared_identity_cost=0.0,
        )
    with pytest.raises(ValueError, match="nonnegative"):
        CrossDwellAssociationProblem(
            dwells=dwells,
            catalog_numbers=(1,),
            candidate_universe_catalog_count=1,
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=spaces,
            required_confirmation_dwell_ids=("d1",),
            minimum_distinct_session_count=2,
            shared_identity_cost=-1.0,
        )
    with pytest.raises(ValueError, match="cannot repeat a dwell"):
        SharedNoradSchedule(
            1,
            (DwellStateSelection("d", "a"), DwellStateSelection("d", "b")),
        )
    with pytest.raises(ValueError, match="null.*cannot select"):
        SharedNoradSchedule(None, (DwellStateSelection("d", "a"),))


def test_cross_dwell_contract_rejects_one_session_or_a_one_session_minimum() -> None:
    one_dwell = AssociationDwell("d1", "one-session", 1.0)
    with pytest.raises(ValueError, match="at least two distinct sessions"):
        CrossDwellAssociationProblem(
            dwells=(one_dwell,),
            catalog_numbers=(1,),
            candidate_universe_catalog_count=1,
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=(_space("d1", 1, -1.0),),
            required_confirmation_dwell_ids=("d1",),
            minimum_distinct_session_count=2,
            shared_identity_cost=0.0,
        )

    same_session_dwells = (
        AssociationDwell("d1", "one-session", 1.0),
        AssociationDwell("d2", "one-session", 1.0),
    )
    same_session_spaces = (_space("d1", 1, -1.0), _space("d2", 1, -1.0))
    with pytest.raises(ValueError, match="at least two"):
        CrossDwellAssociationProblem(
            dwells=same_session_dwells,
            catalog_numbers=(1,),
            candidate_universe_catalog_count=1,
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=same_session_spaces,
            required_confirmation_dwell_ids=("d1",),
            minimum_distinct_session_count=2,
            shared_identity_cost=0.0,
        )

    two_session_dwells = (
        AssociationDwell("d1", "session-a", 1.0),
        AssociationDwell("d2", "session-b", 1.0),
    )
    with pytest.raises(ValueError, match="at least two"):
        CrossDwellAssociationProblem(
            dwells=two_session_dwells,
            catalog_numbers=(1,),
            candidate_universe_catalog_count=1,
            candidate_universe_exhausted=True,
            candidate_universe_pruned=False,
            state_spaces=same_session_spaces,
            required_confirmation_dwell_ids=("d1",),
            minimum_distinct_session_count=1,
            shared_identity_cost=0.0,
        )
