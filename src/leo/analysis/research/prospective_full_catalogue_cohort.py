"""Pure adjudication of a frozen prospective full-catalogue control cohort.

The component consumes already-evaluated finite state spaces.  It deliberately
has no TLE, RF, filesystem, database, or acquisition dependency.  One identity
arm and exactly twenty block-control arms are reduced independently with the
exact cross-dwell shared-NORAD reducer; a control is never evaluated only at
the identity arm's winning catalogue number.

The numerical result is a bounded association to a named catalogue ephemeris.
It is not an orbit estimate, payload identification, continuous RF track, or
randomization-test result.  In particular, the block mappings used by the
current experiment are not asserted to be exchangeable, so no permutation
``p`` value is produced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from leo.analysis.research.cross_dwell_shared_norad import (
    CrossDwellAssociationProblem,
    CrossDwellAssociationResult,
    IncompleteCrossDwellEvidenceError,
    decode_cross_dwell_shared_norad,
)

CONTROL_COUNT = 20
COHORT_ALGORITHM = "exact-prospective-full-catalogue-cohort-adjudicator-v1"
ASSOCIATION_CLAIM_KIND: Literal["prospective-full-catalogue-same-NORAD-association"] = (
    "prospective-full-catalogue-same-NORAD-association"
)

ArmKind = Literal["identity", "control"]
Disposition = Literal[
    "invalid-evidence",
    "numerical-qualification-failed",
    "numerically-qualified-awaiting-authoritative-receipts",
]


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


def _finite_nonnegative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _canonical_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


@dataclass(frozen=True, slots=True)
class NamedCatalogueObject:
    """The stable catalogue number/name pair frozen before cohort evidence."""

    catalog_number: int
    object_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.catalog_number, int)
            or isinstance(self.catalog_number, bool)
            or self.catalog_number <= 0
        ):
            raise ValueError("catalog number must be a positive integer")
        _nonempty(self.object_name, "catalogue object name")


@dataclass(frozen=True, slots=True)
class ProspectiveCatalogueArm:
    """One frozen semantic mapping and its complete finite association problem."""

    arm_id: str
    kind: ArmKind
    control_index: int | None
    semantic_mapping_digest: str
    evaluation_attempt_count: int
    named_catalogue: tuple[NamedCatalogueObject, ...]
    problem: CrossDwellAssociationProblem
    finite_state_receipt_exact: bool

    def __post_init__(self) -> None:
        _nonempty(self.arm_id, "arm ID")
        _nonempty(self.semantic_mapping_digest, "semantic mapping digest")
        if self.control_index is not None and (
            not isinstance(self.control_index, int)
            or isinstance(self.control_index, bool)
            or self.control_index < 0
        ):
            raise ValueError("control index must be a nonnegative integer or None")
        if (
            not isinstance(self.evaluation_attempt_count, int)
            or isinstance(self.evaluation_attempt_count, bool)
            or self.evaluation_attempt_count < 1
        ):
            raise ValueError("evaluation attempt count must be a positive integer")
        if not isinstance(self.finite_state_receipt_exact, bool):
            raise ValueError("finite-state receipt flag must be boolean")
        object.__setattr__(self, "named_catalogue", tuple(self.named_catalogue))


@dataclass(frozen=True, slots=True)
class ProspectiveFullCatalogueCohort:
    """Frozen identity/control family and its four strict promotion thresholds.

    The two verification booleans preserve adapter diagnostics only.  A naked
    caller-supplied Boolean is not an authenticated or digest-recomputed
    receipt and therefore cannot authorize an association claim in this core.
    """

    arms: tuple[ProspectiveCatalogueArm, ...]
    beta: float
    mu: float
    gamma_cohort: float
    gamma_dwell: float
    authority_verified: bool
    calibration_verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "arms", tuple(self.arms))
        _finite_nonnegative(self.beta, "beta")
        _finite_nonnegative(self.mu, "mu")
        _finite_nonnegative(self.gamma_cohort, "gamma cohort")
        _finite_nonnegative(self.gamma_dwell, "gamma dwell")
        if not isinstance(self.authority_verified, bool):
            raise ValueError("authority verification flag must be boolean")
        if not isinstance(self.calibration_verified, bool):
            raise ValueError("calibration verification flag must be boolean")


@dataclass(frozen=True, slots=True)
class ArmAssociationDiagnostic:
    """One arm's independently selected full-catalogue association."""

    arm_id: str
    kind: ArmKind
    control_index: int | None
    selected_catalog_number: int | None
    test_statistic: float
    reducer_result: CrossDwellAssociationResult


@dataclass(frozen=True, slots=True)
class DwellDominanceDiagnostic:
    """Identity evidence minus the strongest control/catalog evidence in a dwell."""

    dwell_id: str
    identity_reduced_objective: float
    strongest_control_reduced_objective: float
    strongest_control_index: int
    strongest_control_catalog_number: int
    dominance: float


@dataclass(frozen=True, slots=True)
class ProspectiveFullCatalogueCohortResult:
    """Fail-closed cohort decision with primitive-derived diagnostics."""

    disposition: Disposition
    structural_gates_passed: bool
    numerical_gates_passed: bool
    structural_failure_reasons: tuple[str, ...]
    numerical_failure_reasons: tuple[str, ...]
    authority_verified: bool
    calibration_verified: bool
    diagnostic_identity_catalog_number: int | None
    associated_catalog_number: int | None
    arm_diagnostics: tuple[ArmAssociationDiagnostic, ...]
    identity_runner_up_margin: float | None
    strongest_control_index: int | None
    strongest_control_test_statistic: float | None
    cohort_advantage: float | None
    dwell_dominance: tuple[DwellDominanceDiagnostic, ...]
    association_claimed: bool
    association_claim_kind: Literal["prospective-full-catalogue-same-NORAD-association"] | None
    tracking_claimed: bool
    orbit_claimed: bool
    payload_claimed: bool
    randomization_exchangeability_verified: bool
    permutation_p_value: None
    algorithm: str


def _state_partition_signature(
    problem: CrossDwellAssociationProblem,
) -> tuple[tuple[str, int, bool, int], ...]:
    return tuple(
        (
            item.dwell_id,
            item.catalog_number,
            item.expected_state_count > 0,
            item.expected_state_count,
        )
        for item in problem.state_spaces
    )


def _structural_failure_reasons(
    cohort: ProspectiveFullCatalogueCohort,
) -> tuple[str, ...]:
    reasons: list[str] = []
    arms = cohort.arms
    if len(arms) != CONTROL_COUNT + 1:
        reasons.append("arm-count-must-be-exactly-21")

    if arms:
        identity = arms[0]
        if identity.kind != "identity" or identity.control_index is not None:
            reasons.append("first-arm-must-be-identity")
        for expected_index, arm in enumerate(arms[1:]):
            if arm.kind != "control" or arm.control_index != expected_index:
                reasons.append("control-arms-must-be-ordered-exactly-0-through-19")
                break
    else:
        reasons.append("first-arm-must-be-identity")

    arm_ids = tuple(item.arm_id for item in arms)
    if len(set(arm_ids)) != len(arm_ids):
        reasons.append("arm-ids-must-be-unique")
    mapping_digests = tuple(item.semantic_mapping_digest for item in arms)
    if len(set(mapping_digests)) != len(mapping_digests):
        reasons.append("semantic-mapping-digests-must-be-unique")
    if any(item.evaluation_attempt_count != 1 for item in arms):
        reasons.append("each-arm-must-have-exactly-one-evaluation-attempt")

    for arm in arms:
        problem = arm.problem
        named_numbers = tuple(item.catalog_number for item in arm.named_catalogue)
        if not arm.named_catalogue:
            reasons.append(f"{arm.arm_id}:named-catalogue-must-not-be-empty")
        if len(set(named_numbers)) != len(named_numbers):
            reasons.append(f"{arm.arm_id}:named-catalogue-numbers-must-be-unique")
        if named_numbers != problem.catalog_numbers:
            reasons.append(f"{arm.arm_id}:named-catalogue-partition-mismatch")
        if not arm.finite_state_receipt_exact:
            reasons.append(f"{arm.arm_id}:finite-state-receipt-not-exact")
        if (
            not problem.candidate_universe_exhausted
            or problem.candidate_universe_pruned
            or problem.candidate_universe_catalog_count != len(problem.catalog_numbers)
        ):
            reasons.append(f"{arm.arm_id}:catalogue-universe-not-complete")

        expected_keys = {
            (dwell.dwell_id, catalog_number)
            for dwell in problem.dwells
            for catalog_number in problem.catalog_numbers
        }
        supplied_keys = {(item.dwell_id, item.catalog_number) for item in problem.state_spaces}
        if supplied_keys != expected_keys:
            reasons.append(f"{arm.arm_id}:dwell-catalogue-partition-not-complete")
        if any(not item.complete for item in problem.state_spaces):
            reasons.append(f"{arm.arm_id}:finite-state-space-not-complete")
        if len(problem.dwells) < 2:
            reasons.append(f"{arm.arm_id}:at-least-two-dwells-required")
        sessions = tuple(item.session_id for item in problem.dwells)
        if len(set(sessions)) != len(sessions):
            reasons.append(f"{arm.arm_id}:dwell-sessions-must-be-distinct")

    if arms:
        reference = arms[0]
        reference_problem = reference.problem
        reference_partition = _state_partition_signature(reference_problem)
        for arm in arms[1:]:
            problem = arm.problem
            if arm.named_catalogue != reference.named_catalogue:
                reasons.append(f"{arm.arm_id}:named-catalogue-order-or-name-mismatch")
            if problem.dwells != reference_problem.dwells:
                reasons.append(f"{arm.arm_id}:dwell-partition-mismatch")
            if (
                problem.required_confirmation_dwell_ids
                != reference_problem.required_confirmation_dwell_ids
            ):
                reasons.append(f"{arm.arm_id}:required-dwell-partition-mismatch")
            if (
                problem.minimum_distinct_session_count
                != reference_problem.minimum_distinct_session_count
            ):
                reasons.append(f"{arm.arm_id}:minimum-session-count-mismatch")
            if problem.shared_identity_cost != reference_problem.shared_identity_cost:
                reasons.append(f"{arm.arm_id}:shared-identity-cost-mismatch")
            if _state_partition_signature(problem) != reference_partition:
                reasons.append(f"{arm.arm_id}:eligible-state-count-partition-mismatch")

    # Stable deduplication keeps a malformed receipt's diagnostics concise.
    return tuple(dict.fromkeys(reasons))


def _invalid_result(
    cohort: ProspectiveFullCatalogueCohort,
    reasons: tuple[str, ...],
) -> ProspectiveFullCatalogueCohortResult:
    return ProspectiveFullCatalogueCohortResult(
        disposition="invalid-evidence",
        structural_gates_passed=False,
        numerical_gates_passed=False,
        structural_failure_reasons=reasons,
        numerical_failure_reasons=(),
        authority_verified=cohort.authority_verified,
        calibration_verified=cohort.calibration_verified,
        diagnostic_identity_catalog_number=None,
        associated_catalog_number=None,
        arm_diagnostics=(),
        identity_runner_up_margin=None,
        strongest_control_index=None,
        strongest_control_test_statistic=None,
        cohort_advantage=None,
        dwell_dominance=(),
        association_claimed=False,
        association_claim_kind=None,
        tracking_claimed=False,
        orbit_claimed=False,
        payload_claimed=False,
        randomization_exchangeability_verified=False,
        permutation_p_value=None,
        algorithm=COHORT_ALGORITHM,
    )


def _selected_terms(
    arm: ProspectiveCatalogueArm,
    result: CrossDwellAssociationResult,
) -> tuple[float, ...]:
    if result.selected_catalog_number is None:
        return (0.0,)
    return (
        arm.problem.shared_identity_cost,
        *(item.reduced_objective for item in result.contributions),
    )


def _catalog_terms(
    arm: ProspectiveCatalogueArm,
    result: CrossDwellAssociationResult,
    catalog_number: int | None,
) -> tuple[float, ...]:
    if catalog_number is None:
        return (0.0,)
    score = next(item for item in result.catalog_scores if item.catalog_number == catalog_number)
    return (
        arm.problem.shared_identity_cost,
        *(item.reduced_objective for item in score.contributions),
    )


def _sum_difference(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return ``sum(left) - sum(right)`` without subtracting rounded totals."""

    return _canonical_zero(math.fsum((*left, *(-item for item in right))))


def _test_statistic(terms: tuple[float, ...]) -> float:
    reduced = math.fsum(terms)
    return _canonical_zero(-reduced) if reduced < 0.0 else 0.0


def _disposition(*, numerical_passed: bool) -> Disposition:
    if not numerical_passed:
        return "numerical-qualification-failed"
    return "numerically-qualified-awaiting-authoritative-receipts"


def adjudicate_prospective_full_catalogue_cohort(
    cohort: ProspectiveFullCatalogueCohort,
) -> ProspectiveFullCatalogueCohortResult:
    """Adjudicate all arms and promote only on four strict calibrated margins."""

    structural_reasons = _structural_failure_reasons(cohort)
    if structural_reasons:
        return _invalid_result(cohort, structural_reasons)

    reducer_results: list[CrossDwellAssociationResult] = []
    try:
        for arm in cohort.arms:
            reducer_results.append(decode_cross_dwell_shared_norad(arm.problem))
    except (IncompleteCrossDwellEvidenceError, OverflowError) as error:
        return _invalid_result(cohort, (f"underlying-reducer-incomplete:{error}",))

    primitive_terms = tuple(
        _selected_terms(arm, result)
        for arm, result in zip(cohort.arms, reducer_results, strict=True)
    )
    arm_diagnostics = tuple(
        ArmAssociationDiagnostic(
            arm_id=arm.arm_id,
            kind=arm.kind,
            control_index=arm.control_index,
            selected_catalog_number=result.selected_catalog_number,
            test_statistic=_test_statistic(terms),
            reducer_result=result,
        )
        for arm, result, terms in zip(
            cohort.arms,
            reducer_results,
            primitive_terms,
            strict=True,
        )
    )

    identity_arm = cohort.arms[0]
    identity_result = reducer_results[0]
    identity_terms = primitive_terms[0]
    control_best_position = 1
    for position in range(2, len(cohort.arms)):
        difference = _sum_difference(
            primitive_terms[position], primitive_terms[control_best_position]
        )
        if difference < 0.0:
            control_best_position = position
    strongest_control_arm = cohort.arms[control_best_position]
    strongest_control_terms = primitive_terms[control_best_position]
    assert strongest_control_arm.control_index is not None

    numerical_reasons: list[str] = []
    selected_catalog = identity_result.selected_catalog_number
    identity_margin: float | None = None
    cohort_advantage: float | None = None
    dwell_dominance: tuple[DwellDominanceDiagnostic, ...] = ()

    if selected_catalog is None:
        numerical_reasons.append("identity-has-no-admissible-strict-association")
    else:
        required = set(identity_arm.problem.required_confirmation_dwell_ids)
        for contribution in identity_result.contributions:
            if contribution.dwell_id in required and not contribution.reduced_objective < 0.0:
                numerical_reasons.append(
                    f"identity-required-dwell-not-strictly-negative:{contribution.dwell_id}"
                )

        runner_terms = _catalog_terms(
            identity_arm,
            identity_result,
            identity_result.runner_up_catalog_number,
        )
        identity_margin = _sum_difference(runner_terms, identity_terms)
        cohort_advantage = _sum_difference(strongest_control_terms, identity_terms)

        if not math.fsum((*identity_terms, cohort.beta)) < 0.0:
            numerical_reasons.append("beta-not-strictly-exceeded")
        if not math.fsum((*runner_terms, *(-item for item in identity_terms), -cohort.mu)) > 0.0:
            numerical_reasons.append("mu-not-strictly-exceeded")
        if (
            not math.fsum(
                (
                    *strongest_control_terms,
                    *(-item for item in identity_terms),
                    -cohort.gamma_cohort,
                )
            )
            > 0.0
        ):
            numerical_reasons.append("gamma-cohort-not-strictly-exceeded")

        identity_by_dwell = {
            item.dwell_id: item.reduced_objective for item in identity_result.contributions
        }
        dominance_rows: list[DwellDominanceDiagnostic] = []
        for dwell in identity_arm.problem.dwells:
            strongest_delta = 0.0
            strongest_index = 0
            strongest_catalog = identity_arm.problem.catalog_numbers[0]
            for arm, result in zip(cohort.arms[1:], reducer_results[1:], strict=True):
                assert arm.control_index is not None
                for catalog_score in result.catalog_scores:
                    contribution = next(
                        item
                        for item in catalog_score.contributions
                        if item.dwell_id == dwell.dwell_id
                    )
                    candidate_delta = contribution.reduced_objective
                    candidate_key = (arm.control_index, catalog_score.catalog_number)
                    strongest_key = (strongest_index, strongest_catalog)
                    if candidate_delta < strongest_delta or (
                        candidate_delta == strongest_delta and candidate_key < strongest_key
                    ):
                        strongest_delta = candidate_delta
                        strongest_index = arm.control_index
                        strongest_catalog = catalog_score.catalog_number

            identity_delta = identity_by_dwell[dwell.dwell_id]
            dominance = _canonical_zero(math.fsum((-identity_delta, strongest_delta)))
            dominance_rows.append(
                DwellDominanceDiagnostic(
                    dwell_id=dwell.dwell_id,
                    identity_reduced_objective=identity_delta,
                    strongest_control_reduced_objective=strongest_delta,
                    strongest_control_index=strongest_index,
                    strongest_control_catalog_number=strongest_catalog,
                    dominance=dominance,
                )
            )
            if not math.fsum((-identity_delta, strongest_delta, -cohort.gamma_dwell)) > 0.0:
                numerical_reasons.append(f"gamma-dwell-not-strictly-exceeded:{dwell.dwell_id}")
        dwell_dominance = tuple(dominance_rows)

    numerical_failure_reasons = tuple(dict.fromkeys(numerical_reasons))
    numerical_passed = not numerical_failure_reasons
    disposition = _disposition(numerical_passed=numerical_passed)
    # Only a later adapter that validates typed, content-bound authority and
    # calibration receipts may promote this numerical result to a claim.
    association_claimed = False
    return ProspectiveFullCatalogueCohortResult(
        disposition=disposition,
        structural_gates_passed=True,
        numerical_gates_passed=numerical_passed,
        structural_failure_reasons=(),
        numerical_failure_reasons=numerical_failure_reasons,
        authority_verified=cohort.authority_verified,
        calibration_verified=cohort.calibration_verified,
        diagnostic_identity_catalog_number=selected_catalog,
        associated_catalog_number=None,
        arm_diagnostics=arm_diagnostics,
        identity_runner_up_margin=identity_margin,
        strongest_control_index=strongest_control_arm.control_index,
        strongest_control_test_statistic=_test_statistic(strongest_control_terms),
        cohort_advantage=cohort_advantage,
        dwell_dominance=dwell_dominance,
        association_claimed=association_claimed,
        association_claim_kind=None,
        tracking_claimed=False,
        orbit_claimed=False,
        payload_claimed=False,
        randomization_exchangeability_verified=False,
        permutation_p_value=None,
        algorithm=COHORT_ALGORITHM,
    )
