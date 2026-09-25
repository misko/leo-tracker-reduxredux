from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Literal

import pytest

from leo.analysis.research.cross_dwell_shared_norad import (
    AssociationDwell,
    CrossDwellAssociationProblem,
    ExactDwellCatalogStateSpace,
    FiniteDwellState,
)
from leo.analysis.research.prospective_full_catalogue_cohort import (
    NamedCatalogueObject,
    ProspectiveCatalogueArm,
    ProspectiveFullCatalogueCohort,
    adjudicate_prospective_full_catalogue_cohort,
)


def _problem(
    *,
    dwells: tuple[AssociationDwell, ...],
    catalog_numbers: tuple[int, ...],
    values: dict[tuple[str, int], tuple[float, ...]],
    shared_identity_cost: float = 0.0,
    required: tuple[str, ...] | None = None,
    minimum_sessions: int = 2,
) -> CrossDwellAssociationProblem:
    return CrossDwellAssociationProblem(
        dwells=dwells,
        catalog_numbers=catalog_numbers,
        candidate_universe_catalog_count=len(catalog_numbers),
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=tuple(
            ExactDwellCatalogStateSpace(
                dwell_id=dwell.dwell_id,
                catalog_number=catalog_number,
                states=tuple(
                    FiniteDwellState(f"state-{index}", value)
                    for index, value in enumerate(values[(dwell.dwell_id, catalog_number)])
                ),
                expected_state_count=len(values[(dwell.dwell_id, catalog_number)]),
                supplied_state_space_exhausted=True,
            )
            for dwell in dwells
            for catalog_number in catalog_numbers
        ),
        required_confirmation_dwell_ids=(
            tuple(dwell.dwell_id for dwell in dwells) if required is None else required
        ),
        minimum_distinct_session_count=minimum_sessions,
        shared_identity_cost=shared_identity_cost,
    )


def _default_dwells() -> tuple[AssociationDwell, ...]:
    return (
        AssociationDwell("d1", "session-a", 1.0e200),
        AssociationDwell("d2", "session-b", 2.0e200),
    )


def _baseline_identity_values() -> dict[tuple[str, int], tuple[float, ...]]:
    return {
        ("d1", 10): (-10.0,),
        ("d2", 10): (-10.0,),
        ("d1", 20): (-6.0,),
        ("d2", 20): (-6.0,),
    }


def _baseline_control_values() -> dict[tuple[str, int], tuple[float, ...]]:
    return {
        ("d1", 10): (-1.0,),
        ("d2", 10): (-1.0,),
        ("d1", 20): (-0.5,),
        ("d2", 20): (-0.5,),
    }


def _cohort(
    *,
    identity_values: dict[tuple[str, int], tuple[float, ...]] | None = None,
    control_values: dict[int, dict[tuple[str, int], tuple[float, ...]]] | None = None,
    dwells: tuple[AssociationDwell, ...] | None = None,
    catalog_numbers: tuple[int, ...] = (10, 20),
    shared_identity_cost: float = 0.0,
    control_count: int = 20,
    beta: float = 15.0,
    mu: float = 5.0,
    gamma_cohort: float = 10.0,
    gamma_dwell: float = 5.0,
    authority_verified: bool = True,
    calibration_verified: bool = True,
    required: tuple[str, ...] | None = None,
    minimum_sessions: int = 2,
) -> ProspectiveFullCatalogueCohort:
    actual_dwells = _default_dwells() if dwells is None else dwells
    identity_matrix = _baseline_identity_values() if identity_values is None else identity_values
    default_control = _baseline_control_values()
    matrices = {} if control_values is None else control_values
    named = tuple(NamedCatalogueObject(number, f"STARLINK-{number}") for number in catalog_numbers)
    identity = ProspectiveCatalogueArm(
        arm_id="identity",
        kind="identity",
        control_index=None,
        semantic_mapping_digest="mapping-identity",
        evaluation_attempt_count=1,
        named_catalogue=named,
        problem=_problem(
            dwells=actual_dwells,
            catalog_numbers=catalog_numbers,
            values=identity_matrix,
            shared_identity_cost=shared_identity_cost,
            required=required,
            minimum_sessions=minimum_sessions,
        ),
        finite_state_receipt_exact=True,
    )
    controls = tuple(
        ProspectiveCatalogueArm(
            arm_id=f"control-{index:02d}",
            kind="control",
            control_index=index,
            semantic_mapping_digest=f"mapping-control-{index:02d}",
            evaluation_attempt_count=1,
            named_catalogue=named,
            problem=_problem(
                dwells=actual_dwells,
                catalog_numbers=catalog_numbers,
                values=matrices.get(index, default_control),
                shared_identity_cost=shared_identity_cost,
                required=required,
                minimum_sessions=minimum_sessions,
            ),
            finite_state_receipt_exact=True,
        )
        for index in range(control_count)
    )
    return ProspectiveFullCatalogueCohort(
        arms=(identity, *controls),
        beta=beta,
        mu=mu,
        gamma_cohort=gamma_cohort,
        gamma_dwell=gamma_dwell,
        authority_verified=authority_verified,
        calibration_verified=calibration_verified,
    )


def test_strict_full_catalogue_cohort_qualifies_numerically_but_cannot_self_authorize() -> None:
    result = adjudicate_prospective_full_catalogue_cohort(_cohort())

    assert result.disposition == "numerically-qualified-awaiting-authoritative-receipts"
    assert result.structural_gates_passed
    assert result.numerical_gates_passed
    assert result.diagnostic_identity_catalog_number == 10
    assert result.associated_catalog_number is None
    assert result.identity_runner_up_margin == 8.0
    assert result.strongest_control_test_statistic == 2.0
    assert result.cohort_advantage == 18.0
    assert tuple(item.dominance for item in result.dwell_dominance) == (9.0, 9.0)
    assert not result.association_claimed
    assert result.association_claim_kind is None
    assert not result.tracking_claimed
    assert not result.orbit_claimed
    assert not result.payload_claimed
    assert not result.randomization_exchangeability_verified
    assert result.permutation_p_value is None
    assert len(result.arm_diagnostics) == 21


def test_each_control_selects_its_own_confuser_instead_of_reusing_identity_target() -> None:
    confuser = _baseline_control_values()
    confuser.update({("d1", 20): (-8.0,), ("d2", 20): (-8.0,)})
    cohort = _cohort(
        control_values={0: confuser},
        gamma_cohort=5.0,
        gamma_dwell=1.0,
    )

    result = adjudicate_prospective_full_catalogue_cohort(cohort)

    control_zero = result.arm_diagnostics[1]
    assert control_zero.selected_catalog_number == 20
    assert control_zero.test_statistic == 16.0
    assert cohort.gamma_cohort < 20.0 - 2.0  # A fixed-target-only check would pass.
    assert result.cohort_advantage == 4.0
    assert result.numerical_failure_reasons == ("gamma-cohort-not-strictly-exceeded",)
    assert result.disposition == "numerical-qualification-failed"
    assert not result.association_claimed


@pytest.mark.parametrize("control_count", [19, 21])
def test_exactly_twenty_controls_are_required(control_count: int) -> None:
    result = adjudicate_prospective_full_catalogue_cohort(_cohort(control_count=control_count))

    assert result.disposition == "invalid-evidence"
    assert "arm-count-must-be-exactly-21" in result.structural_failure_reasons
    assert not result.arm_diagnostics


def test_control_indices_must_be_in_exact_order_and_mappings_must_be_unique() -> None:
    cohort = _cohort()
    swapped = replace(
        cohort,
        arms=(cohort.arms[0], cohort.arms[2], cohort.arms[1], *cohort.arms[3:]),
    )
    duplicated_mapping = replace(
        cohort,
        arms=(
            cohort.arms[0],
            replace(
                cohort.arms[1],
                semantic_mapping_digest=cohort.arms[0].semantic_mapping_digest,
            ),
            *cohort.arms[2:],
        ),
    )

    swapped_result = adjudicate_prospective_full_catalogue_cohort(swapped)
    duplicate_result = adjudicate_prospective_full_catalogue_cohort(duplicated_mapping)

    assert "control-arms-must-be-ordered-exactly-0-through-19" in (
        swapped_result.structural_failure_reasons
    )
    assert "semantic-mapping-digests-must-be-unique" in (
        duplicate_result.structural_failure_reasons
    )


def test_retries_are_invalid_evidence() -> None:
    cohort = _cohort()
    retried = replace(
        cohort,
        arms=(
            cohort.arms[0],
            replace(cohort.arms[1], evaluation_attempt_count=2),
            *cohort.arms[2:],
        ),
    )

    result = adjudicate_prospective_full_catalogue_cohort(retried)

    assert result.disposition == "invalid-evidence"
    assert "each-arm-must-have-exactly-one-evaluation-attempt" in (
        result.structural_failure_reasons
    )


@pytest.mark.parametrize("mismatch", ["name", "count", "eligibility"])
def test_every_arm_must_have_the_same_named_and_state_count_partition(
    mismatch: str,
) -> None:
    cohort = _cohort()
    control = cohort.arms[1]
    if mismatch == "name":
        changed = replace(
            control,
            named_catalogue=(
                control.named_catalogue[0],
                replace(control.named_catalogue[1], object_name="ALTERED-NAME"),
            ),
        )
    else:
        problem = control.problem
        first = problem.state_spaces[0]
        if mismatch == "count":
            changed_space = replace(
                first,
                states=(*first.states, FiniteDwellState("extra-state", -0.25)),
                expected_state_count=2,
            )
        else:
            changed_space = replace(first, states=(), expected_state_count=0)
        changed = replace(
            control,
            problem=replace(
                problem,
                state_spaces=(changed_space, *problem.state_spaces[1:]),
            ),
        )
    malformed = replace(
        cohort,
        arms=(cohort.arms[0], changed, *cohort.arms[2:]),
    )

    result = adjudicate_prospective_full_catalogue_cohort(malformed)

    assert result.disposition == "invalid-evidence"
    assert any("mismatch" in item for item in result.structural_failure_reasons)


@pytest.mark.parametrize("failure", ["pruned", "unexhausted", "truncated", "receipt"])
def test_pruned_unknown_or_unreceipted_rows_fail_closed(failure: str) -> None:
    cohort = _cohort()
    arm = cohort.arms[1]
    if failure == "pruned":
        changed = replace(
            arm,
            problem=replace(arm.problem, candidate_universe_pruned=True),
        )
    elif failure == "unexhausted":
        changed = replace(
            arm,
            problem=replace(arm.problem, candidate_universe_exhausted=False),
        )
    elif failure == "truncated":
        first = arm.problem.state_spaces[0]
        changed = replace(
            arm,
            problem=replace(
                arm.problem,
                state_spaces=(
                    replace(first, expected_state_count=first.expected_state_count + 1),
                    *arm.problem.state_spaces[1:],
                ),
            ),
        )
    else:
        changed = replace(arm, finite_state_receipt_exact=False)
    malformed = replace(
        cohort,
        arms=(cohort.arms[0], changed, *cohort.arms[2:]),
    )

    result = adjudicate_prospective_full_catalogue_cohort(malformed)

    assert result.disposition == "invalid-evidence"
    assert result.structural_failure_reasons
    assert not result.association_claimed


@pytest.mark.parametrize(
    ("threshold", "value", "reason"),
    [
        ("beta", 20.0, "beta-not-strictly-exceeded"),
        ("mu", 8.0, "mu-not-strictly-exceeded"),
        ("gamma_cohort", 18.0, "gamma-cohort-not-strictly-exceeded"),
        ("gamma_dwell", 9.0, "gamma-dwell-not-strictly-exceeded:d1"),
    ],
)
def test_exact_threshold_equality_fails(
    threshold: Literal["beta", "mu", "gamma_cohort", "gamma_dwell"],
    value: float,
    reason: str,
) -> None:
    cohort = _cohort()
    if threshold == "beta":
        cohort = replace(cohort, beta=value)
    elif threshold == "mu":
        cohort = replace(cohort, mu=value)
    elif threshold == "gamma_cohort":
        cohort = replace(cohort, gamma_cohort=value)
    else:
        cohort = replace(cohort, gamma_dwell=value)
    result = adjudicate_prospective_full_catalogue_cohort(cohort)

    assert result.disposition == "numerical-qualification-failed"
    assert reason in result.numerical_failure_reasons
    assert not result.association_claimed


def test_a_single_dwell_control_dominance_failure_blocks_the_cohort() -> None:
    one_dwell_confuser = _baseline_control_values()
    one_dwell_confuser.update({("d1", 20): (-11.0,), ("d2", 20): (-0.5,)})
    result = adjudicate_prospective_full_catalogue_cohort(
        _cohort(
            control_values={0: one_dwell_confuser},
            gamma_cohort=5.0,
            gamma_dwell=0.0,
        )
    )

    assert result.cohort_advantage == 8.5
    assert tuple(item.dominance for item in result.dwell_dominance) == (-1.0, 9.0)
    assert result.numerical_failure_reasons == ("gamma-dwell-not-strictly-exceeded:d1",)
    assert not result.association_claimed


def test_duplicate_sessions_are_structurally_invalid_even_with_another_session() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 0.0),
        AssociationDwell("d2", "session-a", 0.0),
        AssociationDwell("d3", "session-b", 0.0),
    )
    identity: dict[tuple[str, int], tuple[float, ...]] = {
        (dwell.dwell_id, catalog): (-10.0 if catalog == 10 else -6.0,)
        for dwell in dwells
        for catalog in (10, 20)
    }
    control: dict[tuple[str, int], tuple[float, ...]] = {
        (dwell.dwell_id, catalog): (-1.0 if catalog == 10 else -0.5,)
        for dwell in dwells
        for catalog in (10, 20)
    }
    result = adjudicate_prospective_full_catalogue_cohort(
        _cohort(
            dwells=dwells,
            identity_values=identity,
            control_values={index: control for index in range(20)},
            beta=20.0,
        )
    )

    assert result.disposition == "invalid-evidence"
    assert any(
        item.endswith("dwell-sessions-must-be-distinct")
        for item in result.structural_failure_reasons
    )


def test_cross_arm_minimum_session_count_mismatch_is_invalid_evidence() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 0.0),
        AssociationDwell("d2", "session-b", 0.0),
        AssociationDwell("d3", "session-c", 0.0),
    )
    identity: dict[tuple[str, int], tuple[float, ...]] = {
        (dwell.dwell_id, catalog): (-10.0 if catalog == 10 else -6.0,)
        for dwell in dwells
        for catalog in (10, 20)
    }
    control: dict[tuple[str, int], tuple[float, ...]] = {
        (dwell.dwell_id, catalog): (-1.0 if catalog == 10 else -0.5,)
        for dwell in dwells
        for catalog in (10, 20)
    }
    cohort = _cohort(
        dwells=dwells,
        identity_values=identity,
        control_values={index: control for index in range(20)},
        minimum_sessions=2,
    )
    changed_control = replace(
        cohort.arms[1],
        problem=replace(
            cohort.arms[1].problem,
            minimum_distinct_session_count=3,
        ),
    )
    malformed = replace(
        cohort,
        arms=(cohort.arms[0], changed_control, *cohort.arms[2:]),
    )

    result = adjudicate_prospective_full_catalogue_cohort(malformed)

    assert result.disposition == "invalid-evidence"
    assert "control-00:minimum-session-count-mismatch" in (result.structural_failure_reasons)


def test_large_cancelling_cost_preserves_a_minimum_subnormal_strict_margin() -> None:
    minimum_subnormal = 5e-324
    dwells = (
        AssociationDwell("d1", "session-a", 0.0),
        AssociationDwell("d2", "session-b", 0.0),
    )
    identity: dict[tuple[str, int], tuple[float, ...]] = {
        ("d1", 10): (-1.0e308,),
        ("d2", 10): (-minimum_subnormal,),
    }
    control: dict[tuple[str, int], tuple[float, ...]] = {
        ("d1", 10): (1.0,),
        ("d2", 10): (1.0,),
    }
    result = adjudicate_prospective_full_catalogue_cohort(
        _cohort(
            dwells=dwells,
            catalog_numbers=(10,),
            identity_values=identity,
            control_values={index: control for index in range(20)},
            shared_identity_cost=1.0e308,
            beta=0.0,
            mu=0.0,
            gamma_cohort=0.0,
            gamma_dwell=0.0,
        )
    )

    assert result.disposition == "numerically-qualified-awaiting-authoritative-receipts"
    assert result.arm_diagnostics[0].test_statistic == minimum_subnormal
    assert result.identity_runner_up_margin == minimum_subnormal
    assert result.cohort_advantage == minimum_subnormal
    assert tuple(item.dominance for item in result.dwell_dominance) == (
        1.0e308,
        minimum_subnormal,
    )


@pytest.mark.parametrize(
    ("authority", "calibration"),
    [(True, True), (False, True), (True, False), (False, False)],
)
def test_untrusted_authority_and_calibration_booleans_never_create_a_claim(
    authority: bool,
    calibration: bool,
) -> None:
    result = adjudicate_prospective_full_catalogue_cohort(
        _cohort(
            authority_verified=authority,
            calibration_verified=calibration,
        )
    )

    assert result.structural_gates_passed
    assert result.numerical_gates_passed
    assert result.diagnostic_identity_catalog_number == 10
    assert result.associated_catalog_number is None
    assert result.authority_verified is authority
    assert result.calibration_verified is calibration
    assert result.disposition == "numerically-qualified-awaiting-authoritative-receipts"
    assert not result.association_claimed


def test_extreme_null_objectives_fail_closed_instead_of_raising() -> None:
    dwells = (
        AssociationDwell("d1", "session-a", 1.0e308),
        AssociationDwell("d2", "session-b", 1.0e308),
    )

    result = adjudicate_prospective_full_catalogue_cohort(_cohort(dwells=dwells))

    assert result.disposition == "invalid-evidence"
    assert any(
        reason.startswith("underlying-reducer-incomplete:")
        for reason in result.structural_failure_reasons
    )
    assert not result.association_claimed


def _oracle_arm(
    values: dict[tuple[str, int], tuple[float, ...]],
    catalog_numbers: tuple[int, ...],
    dwell_ids: tuple[str, ...],
    shared_cost: float,
) -> tuple[int | None, float, dict[tuple[str, int], float], float | None]:
    deltas = {key: min(0.0, min(states)) for key, states in values.items()}
    scores = []
    for catalog in catalog_numbers:
        contributions = tuple(deltas[(dwell_id, catalog)] for dwell_id in dwell_ids)
        if all(item < 0.0 for item in contributions):
            scores.append((math.fsum((shared_cost, *contributions)), catalog))
    scores.sort(key=lambda item: (item[0], item[1]))
    if not scores or not scores[0][0] < 0.0:
        return None, 0.0, deltas, None
    selected_score, selected_catalog = scores[0]
    alternatives = [0.0, *(score for score, _catalog in scores[1:])]
    runner = min(alternatives)
    return selected_catalog, -selected_score, deltas, runner - selected_score


def test_metrics_match_an_exhaustive_tiny_full_catalogue_oracle() -> None:
    dwells = _default_dwells()
    dwell_ids = tuple(item.dwell_id for item in dwells)
    catalogs = (10, 20, 30)
    choices = (-5.0, -2.0, -0.5, 0.5, 2.0)
    for seed in range(12):
        generator = random.Random(seed)

        def values(
            random_generator: random.Random = generator,
        ) -> dict[tuple[str, int], tuple[float, ...]]:
            return {
                (dwell_id, catalog): (
                    random_generator.choice(choices),
                    random_generator.choice(choices),
                )
                for dwell_id in dwell_ids
                for catalog in catalogs
            }

        identity_values = values()
        control_values = {index: values() for index in range(20)}
        cohort = _cohort(
            dwells=dwells,
            catalog_numbers=catalogs,
            identity_values=identity_values,
            control_values=control_values,
            shared_identity_cost=1.0,
            beta=0.0,
            mu=0.0,
            gamma_cohort=0.0,
            gamma_dwell=0.0,
            authority_verified=False,
            calibration_verified=False,
        )
        result = adjudicate_prospective_full_catalogue_cohort(cohort)
        identity_oracle = _oracle_arm(identity_values, catalogs, dwell_ids, shared_cost=1.0)
        control_oracles = tuple(
            _oracle_arm(control_values[index], catalogs, dwell_ids, shared_cost=1.0)
            for index in range(20)
        )

        assert result.diagnostic_identity_catalog_number == identity_oracle[0]
        assert tuple(item.test_statistic for item in result.arm_diagnostics) == (
            identity_oracle[1],
            *(item[1] for item in control_oracles),
        )
        if identity_oracle[0] is None:
            assert result.identity_runner_up_margin is None
            assert result.cohort_advantage is None
            continue
        assert result.identity_runner_up_margin == identity_oracle[3]
        assert result.cohort_advantage == identity_oracle[1] - max(
            item[1] for item in control_oracles
        )
        expected_dominance = tuple(
            -identity_oracle[2][(dwell_id, identity_oracle[0])]
            - max(
                -control_oracle[2][(dwell_id, catalog)]
                for control_oracle in control_oracles
                for catalog in catalogs
            )
            for dwell_id in dwell_ids
        )
        assert tuple(item.dominance for item in result.dwell_dominance) == (expected_dominance)


def test_catalogue_dwell_state_and_required_input_permutations_are_invariant() -> None:
    cohort = _cohort()
    permuted_arms = []
    for arm in cohort.arms:
        problem = arm.problem
        permuted_spaces = tuple(
            replace(item, states=tuple(reversed(item.states)))
            for item in reversed(problem.state_spaces)
        )
        permuted_problem = CrossDwellAssociationProblem(
            dwells=tuple(reversed(problem.dwells)),
            catalog_numbers=tuple(reversed(problem.catalog_numbers)),
            candidate_universe_catalog_count=problem.candidate_universe_catalog_count,
            candidate_universe_exhausted=problem.candidate_universe_exhausted,
            candidate_universe_pruned=problem.candidate_universe_pruned,
            state_spaces=permuted_spaces,
            required_confirmation_dwell_ids=tuple(
                reversed(problem.required_confirmation_dwell_ids)
            ),
            minimum_distinct_session_count=problem.minimum_distinct_session_count,
            shared_identity_cost=problem.shared_identity_cost,
        )
        permuted_arms.append(replace(arm, problem=permuted_problem))
    permuted = replace(cohort, arms=tuple(permuted_arms))

    assert adjudicate_prospective_full_catalogue_cohort(permuted) == (
        adjudicate_prospective_full_catalogue_cohort(cohort)
    )
