"""Exact, pure reduction of finite per-dwell results to a shared NORAD.

This research-only component starts *after* each dwell/NORAD nuisance-state
universe has been evaluated exactly.  It has no TLE, RF, filesystem, database,
or acquisition dependencies.  For one catalog number it keeps every optional
dwell at null unless that dwell has a strictly null-improving state, requires
all predeclared confirmation dwells to improve strictly, and requires support
from a configured number of distinct observing sessions.

Per-dwell activation costs must already be included in each state's reduced
objective.  A single nonnegative shared-identity cost is added once to a
same-NORAD association, never once per dwell.  Missing catalog/dwell records,
truncated state universes, pruned states, and unexhausted searches are unknown
evidence and fail closed.  The declared catalog list is likewise usable only
with an exhausted, unpruned, count-reconciled candidate-universe receipt, so a
favorable shortlist cannot silently stand in for a complete catalog search.

The output is a same-NORAD *association*, not a propagated orbit or a track.
Its coherence gap is descriptive: it compares the best admissible shared
catalog before the shared-identity cost with an optimistic lower bound in
which every dwell may independently choose a catalog or remain null.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Literal

ASSOCIATION_CLAIM_KIND: Literal["cross-dwell-same-NORAD-association"] = (
    "cross-dwell-same-NORAD-association"
)
DECODER_ALGORITHM = "exact-finite-state-cross-dwell-shared-norad-v1"
EVALUATOR_ALGORITHM = "independent-optimal-fixed-catalog-schedule-checker-v2"


class IncompleteCrossDwellEvidenceError(ValueError):
    """Raised when an unknown state could be mistaken for null evidence."""


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _canonical_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


@dataclass(frozen=True, slots=True)
class AssociationDwell:
    """One declared dwell and its all-null objective."""

    dwell_id: str
    session_id: str
    null_objective: float

    def __post_init__(self) -> None:
        _nonempty(self.dwell_id, "dwell ID")
        _nonempty(self.session_id, "session ID")
        _finite(self.null_objective, "dwell null objective")


@dataclass(frozen=True, slots=True)
class FiniteDwellState:
    """One already-evaluated active state, expressed relative to dwell null.

    ``reduced_objective`` includes every dwell-local activation, episode, and
    nuisance-state cost.  Negative values improve on the dwell null; zero does
    not improve because activation is deliberately strict.
    """

    state_id: str
    reduced_objective: float

    def __post_init__(self) -> None:
        _nonempty(self.state_id, "finite-state ID")
        _finite(self.reduced_objective, "finite-state reduced objective")


@dataclass(frozen=True, slots=True)
class ExactDwellCatalogStateSpace:
    """Finite-state results for one declared ``(dwell, catalog)`` pair.

    An exhausted record with an expected count of zero explicitly certifies
    that the catalog has no eligible active state in that dwell.  This is
    distinct from an omitted record, which is unknown evidence and fails.
    """

    dwell_id: str
    catalog_number: int
    states: tuple[FiniteDwellState, ...]
    expected_state_count: int
    supplied_state_space_exhausted: bool
    pruned_state_count: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.dwell_id, "state-space dwell ID")
        if (
            not isinstance(self.catalog_number, int)
            or isinstance(self.catalog_number, bool)
            or self.catalog_number <= 0
        ):
            raise ValueError("catalog number must be a positive integer")
        if (
            not isinstance(self.expected_state_count, int)
            or isinstance(self.expected_state_count, bool)
            or self.expected_state_count < 0
        ):
            raise ValueError("expected state count must be a nonnegative integer")
        if (
            not isinstance(self.pruned_state_count, int)
            or isinstance(self.pruned_state_count, bool)
            or self.pruned_state_count < 0
        ):
            raise ValueError("pruned state count must be a nonnegative integer")
        if not isinstance(self.supplied_state_space_exhausted, bool):
            raise ValueError("state-space exhaustion flag must be boolean")

        states = tuple(sorted(tuple(self.states), key=lambda item: item.state_id))
        state_ids = tuple(item.state_id for item in states)
        if len(set(state_ids)) != len(state_ids):
            raise ValueError("finite-state IDs must be unique within a dwell/catalog pair")
        object.__setattr__(self, "states", states)

    @property
    def complete(self) -> bool:
        """Whether every declared state is present and explicitly exhausted."""

        return (
            self.supplied_state_space_exhausted
            and self.pruned_state_count == 0
            and len(self.states) == self.expected_state_count
        )


@dataclass(frozen=True, slots=True)
class CrossDwellAssociationProblem:
    """A predeclared finite association universe with explicit completeness."""

    dwells: tuple[AssociationDwell, ...]
    catalog_numbers: tuple[int, ...]
    candidate_universe_catalog_count: int
    candidate_universe_exhausted: bool
    candidate_universe_pruned: bool
    state_spaces: tuple[ExactDwellCatalogStateSpace, ...]
    required_confirmation_dwell_ids: tuple[str, ...]
    minimum_distinct_session_count: int
    shared_identity_cost: float

    def __post_init__(self) -> None:
        dwells = tuple(sorted(tuple(self.dwells), key=lambda item: item.dwell_id))
        if not dwells:
            raise ValueError("cross-dwell association requires at least one dwell")
        dwell_ids = tuple(item.dwell_id for item in dwells)
        if len(set(dwell_ids)) != len(dwell_ids):
            raise ValueError("cross-dwell association dwell IDs must be unique")

        catalog_numbers = tuple(sorted(tuple(self.catalog_numbers)))
        if not catalog_numbers:
            raise ValueError("cross-dwell association requires at least one catalog number")
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item <= 0
            for item in catalog_numbers
        ):
            raise ValueError("catalog numbers must be positive integers")
        if len(set(catalog_numbers)) != len(catalog_numbers):
            raise ValueError("catalog numbers must be unique")
        if (
            not isinstance(self.candidate_universe_catalog_count, int)
            or isinstance(self.candidate_universe_catalog_count, bool)
            or self.candidate_universe_catalog_count < 1
        ):
            raise ValueError("candidate-universe catalog count must be a positive integer")
        if not isinstance(self.candidate_universe_exhausted, bool):
            raise ValueError("candidate-universe exhaustion flag must be boolean")
        if not isinstance(self.candidate_universe_pruned, bool):
            raise ValueError("candidate-universe pruning flag must be boolean")

        required = tuple(sorted(tuple(self.required_confirmation_dwell_ids)))
        if not required:
            raise ValueError("at least one confirmation dwell must be predeclared")
        if len(set(required)) != len(required):
            raise ValueError("required confirmation dwell IDs must be unique")
        unknown_required = sorted(set(required) - set(dwell_ids))
        if unknown_required:
            raise ValueError(f"required confirmation dwells are not declared: {unknown_required!r}")

        if (
            not isinstance(self.minimum_distinct_session_count, int)
            or isinstance(self.minimum_distinct_session_count, bool)
            or self.minimum_distinct_session_count < 2
        ):
            raise ValueError("minimum distinct session count must be at least two")
        distinct_session_count = len({item.session_id for item in dwells})
        if distinct_session_count < 2:
            raise ValueError("cross-dwell association requires at least two distinct sessions")
        if self.minimum_distinct_session_count > distinct_session_count:
            raise ValueError("minimum distinct session count exceeds the declared session universe")
        _finite(self.shared_identity_cost, "shared identity cost")
        if self.shared_identity_cost < 0.0:
            raise ValueError("shared identity cost must be nonnegative")

        state_spaces = tuple(
            sorted(
                tuple(self.state_spaces),
                key=lambda item: (item.dwell_id, item.catalog_number),
            )
        )
        keys = tuple((item.dwell_id, item.catalog_number) for item in state_spaces)
        if len(set(keys)) != len(keys):
            raise ValueError("dwell/catalog state-space records must be unique")
        unknown_dwell_ids = sorted({item.dwell_id for item in state_spaces} - set(dwell_ids))
        if unknown_dwell_ids:
            raise ValueError(f"state spaces reference unknown dwells: {unknown_dwell_ids!r}")
        unknown_catalogs = sorted(
            {item.catalog_number for item in state_spaces} - set(catalog_numbers)
        )
        if unknown_catalogs:
            raise ValueError(f"state spaces reference undeclared catalogs: {unknown_catalogs!r}")

        object.__setattr__(self, "dwells", dwells)
        object.__setattr__(self, "catalog_numbers", catalog_numbers)
        object.__setattr__(self, "state_spaces", state_spaces)
        object.__setattr__(self, "required_confirmation_dwell_ids", required)


@dataclass(frozen=True, slots=True)
class DwellStateSelection:
    """A selected active state for one dwell."""

    dwell_id: str
    state_id: str

    def __post_init__(self) -> None:
        _nonempty(self.dwell_id, "selection dwell ID")
        _nonempty(self.state_id, "selection state ID")


@dataclass(frozen=True, slots=True)
class SharedNoradSchedule:
    """A null schedule or active dwell states for one shared catalog number."""

    catalog_number: int | None
    selections: tuple[DwellStateSelection, ...] = ()

    def __post_init__(self) -> None:
        selections = tuple(sorted(tuple(self.selections), key=lambda item: item.dwell_id))
        dwell_ids = tuple(item.dwell_id for item in selections)
        if len(set(dwell_ids)) != len(dwell_ids):
            raise ValueError("a shared-NORAD schedule cannot repeat a dwell")
        if self.catalog_number is None:
            if selections:
                raise ValueError("the null shared-NORAD schedule cannot select states")
        elif (
            not isinstance(self.catalog_number, int)
            or isinstance(self.catalog_number, bool)
            or self.catalog_number <= 0
        ):
            raise ValueError("schedule catalog number must be a positive integer")
        object.__setattr__(self, "selections", selections)


@dataclass(frozen=True, slots=True)
class DwellAssociationContribution:
    """One dwell's selected contribution; ``state_id=None`` means dwell null."""

    dwell_id: str
    session_id: str
    state_id: str | None
    reduced_objective: float

    @property
    def active(self) -> bool:
        return self.state_id is not None


@dataclass(frozen=True, slots=True)
class EvaluatedSharedNoradSchedule:
    """A schedule independently resolved and scored from primitive states."""

    catalog_number: int | None
    contributions: tuple[DwellAssociationContribution, ...]
    support_session_ids: tuple[str, ...]
    shared_without_identity_reduced_objective: float
    association_reduced_objective: float
    null_objective: float
    objective: float
    claim_kind: Literal["cross-dwell-same-NORAD-association"]
    algorithm: str
    fixed_schedule_score_exact: bool


@dataclass(frozen=True, slots=True)
class CatalogAssociationScore:
    """Optimal optional-dwell schedule for one catalog in the finite universe."""

    catalog_number: int
    admissible: bool
    missing_required_confirmation_dwell_ids: tuple[str, ...]
    support_session_ids: tuple[str, ...]
    contributions: tuple[DwellAssociationContribution, ...]
    shared_without_identity_reduced_objective: float
    association_reduced_objective: float


@dataclass(frozen=True, slots=True)
class CrossDwellAssociationResult:
    """Exact same-NORAD association result and coherence diagnostics."""

    selected_catalog_number: int | None
    contributions: tuple[DwellAssociationContribution, ...]
    support_session_ids: tuple[str, ...]
    null_objective: float
    reduced_objective: float
    objective: float
    runner_up_catalog_number: int | None
    runner_up_reduced_objective: float | None
    runner_up_margin: float | None
    independent_identity_reduced_objective: float
    independent_identity_objective: float
    best_shared_without_identity_catalog_number: int | None
    best_shared_without_identity_reduced_objective: float | None
    coherence_gap: float | None
    catalog_scores: tuple[CatalogAssociationScore, ...]
    claim_kind: Literal["cross-dwell-same-NORAD-association"]
    algorithm: str
    evaluator_algorithm: str
    exact: bool


def _complete_state_space_index(
    problem: CrossDwellAssociationProblem,
) -> dict[tuple[str, int], ExactDwellCatalogStateSpace]:
    if (
        not problem.candidate_universe_exhausted
        or problem.candidate_universe_pruned
        or problem.candidate_universe_catalog_count != len(problem.catalog_numbers)
    ):
        raise IncompleteCrossDwellEvidenceError(
            "candidate catalogue universe is not an exhausted, unpruned, "
            "count-reconciled declaration"
        )
    by_key = {(item.dwell_id, item.catalog_number): item for item in problem.state_spaces}
    expected_keys = {
        (dwell.dwell_id, catalog_number)
        for dwell in problem.dwells
        for catalog_number in problem.catalog_numbers
    }
    missing = sorted(expected_keys - set(by_key))
    if missing:
        raise IncompleteCrossDwellEvidenceError(
            f"missing dwell/catalog state spaces are unknown evidence: {missing!r}"
        )

    incomplete = sorted(
        (
            item.dwell_id,
            item.catalog_number,
            len(item.states),
            item.expected_state_count,
            item.pruned_state_count,
            item.supplied_state_space_exhausted,
        )
        for item in by_key.values()
        if not item.complete
    )
    if incomplete:
        raise IncompleteCrossDwellEvidenceError(
            f"incomplete dwell/catalog state spaces are unknown evidence: {incomplete!r}"
        )
    return by_key


def _best_state(state_space: ExactDwellCatalogStateSpace) -> FiniteDwellState | None:
    if not state_space.states:
        return None
    return min(state_space.states, key=lambda item: (item.reduced_objective, item.state_id))


def _null_contribution(dwell: AssociationDwell) -> DwellAssociationContribution:
    return DwellAssociationContribution(
        dwell_id=dwell.dwell_id,
        session_id=dwell.session_id,
        state_id=None,
        reduced_objective=0.0,
    )


def _score_catalog(
    problem: CrossDwellAssociationProblem,
    catalog_number: int,
    state_space_by_key: dict[tuple[str, int], ExactDwellCatalogStateSpace],
) -> CatalogAssociationScore:
    contributions = []
    for dwell in problem.dwells:
        state = _best_state(state_space_by_key[(dwell.dwell_id, catalog_number)])
        if state is not None and state.reduced_objective < 0.0:
            contributions.append(
                DwellAssociationContribution(
                    dwell_id=dwell.dwell_id,
                    session_id=dwell.session_id,
                    state_id=state.state_id,
                    reduced_objective=state.reduced_objective,
                )
            )
        else:
            contributions.append(_null_contribution(dwell))

    active = tuple(item for item in contributions if item.active)
    active_dwell_ids = {item.dwell_id for item in active}
    missing_required = tuple(
        item for item in problem.required_confirmation_dwell_ids if item not in active_dwell_ids
    )
    support_sessions = tuple(sorted({item.session_id for item in active}))
    admissible = (
        not missing_required and len(support_sessions) >= problem.minimum_distinct_session_count
    )
    reduced_without_identity = _canonical_zero(
        math.fsum(item.reduced_objective for item in contributions)
    )
    association_reduced = _canonical_zero(
        math.fsum(
            (
                problem.shared_identity_cost,
                *(item.reduced_objective for item in contributions),
            )
        )
    )
    return CatalogAssociationScore(
        catalog_number=catalog_number,
        admissible=admissible,
        missing_required_confirmation_dwell_ids=missing_required,
        support_session_ids=support_sessions,
        contributions=tuple(contributions),
        shared_without_identity_reduced_objective=reduced_without_identity,
        association_reduced_objective=association_reduced,
    )


def _independently_score_catalog(
    problem: CrossDwellAssociationProblem,
    catalog_number: int,
    state_space_by_key: dict[tuple[str, int], ExactDwellCatalogStateSpace],
) -> CatalogAssociationScore:
    """Rescan primitive states without using the optimizer's selection helper."""

    contributions: list[DwellAssociationContribution] = []
    for dwell in problem.dwells:
        states = state_space_by_key[(dwell.dwell_id, catalog_number)].states
        best = min(
            states,
            key=lambda item: (item.reduced_objective, item.state_id),
            default=None,
        )
        if best is None or not best.reduced_objective < 0.0:
            contributions.append(
                DwellAssociationContribution(
                    dwell_id=dwell.dwell_id,
                    session_id=dwell.session_id,
                    state_id=None,
                    reduced_objective=0.0,
                )
            )
        else:
            contributions.append(
                DwellAssociationContribution(
                    dwell_id=dwell.dwell_id,
                    session_id=dwell.session_id,
                    state_id=best.state_id,
                    reduced_objective=best.reduced_objective,
                )
            )

    active_dwell_ids = {item.dwell_id for item in contributions if item.active}
    missing_required = tuple(
        dwell_id
        for dwell_id in problem.required_confirmation_dwell_ids
        if dwell_id not in active_dwell_ids
    )
    support_sessions = tuple(sorted({item.session_id for item in contributions if item.active}))
    reduced_without_identity = _canonical_zero(
        math.fsum(item.reduced_objective for item in contributions)
    )
    association_reduced = _canonical_zero(
        math.fsum(
            (
                problem.shared_identity_cost,
                *(item.reduced_objective for item in contributions),
            )
        )
    )
    return CatalogAssociationScore(
        catalog_number=catalog_number,
        admissible=(
            not missing_required and len(support_sessions) >= problem.minimum_distinct_session_count
        ),
        missing_required_confirmation_dwell_ids=missing_required,
        support_session_ids=support_sessions,
        contributions=tuple(contributions),
        shared_without_identity_reduced_objective=reduced_without_identity,
        association_reduced_objective=association_reduced,
    )


def evaluate_shared_norad_schedule(
    problem: CrossDwellAssociationProblem,
    schedule: SharedNoradSchedule,
) -> EvaluatedSharedNoradSchedule:
    """Independently validate the optimal fixed-catalog schedule and score it.

    For an active catalog, every canonical best strict-null-improving state
    must be present and no other state may be substituted.  Thus this checker
    detects an optimizer that omits a favorable optional dwell or returns a
    suboptimal/tie-noncanonical state.  ``fixed_schedule_score_exact`` describes
    this finite fixed-catalog check, not orbit propagation or tracking.
    """

    state_space_by_key = _complete_state_space_index(problem)
    null_objective = math.fsum(item.null_objective for item in problem.dwells)
    if schedule.catalog_number is None:
        null_contributions = tuple(_null_contribution(item) for item in problem.dwells)
        return EvaluatedSharedNoradSchedule(
            catalog_number=None,
            contributions=null_contributions,
            support_session_ids=(),
            shared_without_identity_reduced_objective=0.0,
            association_reduced_objective=0.0,
            null_objective=null_objective,
            objective=null_objective,
            claim_kind=ASSOCIATION_CLAIM_KIND,
            algorithm=EVALUATOR_ALGORITHM,
            fixed_schedule_score_exact=True,
        )

    if schedule.catalog_number not in problem.catalog_numbers:
        raise ValueError("schedule references an undeclared catalog number")
    independent_optimum = _independently_score_catalog(
        problem,
        schedule.catalog_number,
        state_space_by_key,
    )
    dwell_by_id = {item.dwell_id: item for item in problem.dwells}
    selection_by_dwell = {item.dwell_id: item for item in schedule.selections}
    unknown_dwells = sorted(set(selection_by_dwell) - set(dwell_by_id))
    if unknown_dwells:
        raise ValueError(f"schedule selections reference unknown dwells: {unknown_dwells!r}")

    contributions: list[DwellAssociationContribution] = []
    for dwell in problem.dwells:
        state_space = state_space_by_key[(dwell.dwell_id, schedule.catalog_number)]
        canonical_best = min(
            state_space.states,
            key=lambda item: (item.reduced_objective, item.state_id),
            default=None,
        )
        selection = selection_by_dwell.get(dwell.dwell_id)
        if selection is None:
            if canonical_best is not None and canonical_best.reduced_objective < 0.0:
                raise ValueError(
                    "optimal fixed-catalog schedule omits a strict-null-improving state"
                )
            contributions.append(_null_contribution(dwell))
            continue
        state_by_id = {item.state_id: item for item in state_space.states}
        try:
            state = state_by_id[selection.state_id]
        except KeyError as error:
            raise ValueError(
                f"schedule references unknown state {selection.state_id!r} "
                f"for dwell {dwell.dwell_id!r}"
            ) from error
        if not state.reduced_objective < 0.0:
            raise ValueError("active schedule states must strictly improve on dwell null")
        if canonical_best is None or state.state_id != canonical_best.state_id:
            raise ValueError("fixed-catalog schedule does not select the canonical best state")
        contributions.append(
            DwellAssociationContribution(
                dwell_id=dwell.dwell_id,
                session_id=dwell.session_id,
                state_id=state.state_id,
                reduced_objective=state.reduced_objective,
            )
        )

    if tuple(contributions) != independent_optimum.contributions:
        raise ArithmeticError("independent fixed-catalog optimum recheck disagrees")
    active = tuple(item for item in contributions if item.active)
    active_dwell_ids = {item.dwell_id for item in active}
    missing_required = sorted(set(problem.required_confirmation_dwell_ids) - active_dwell_ids)
    if missing_required:
        raise ValueError(f"schedule omits required confirmation dwells: {missing_required!r}")
    support_sessions = tuple(sorted({item.session_id for item in active}))
    if len(support_sessions) < problem.minimum_distinct_session_count:
        raise ValueError("schedule has insufficient distinct-session support")

    reduced_without_identity = _canonical_zero(
        math.fsum(item.reduced_objective for item in contributions)
    )
    association_reduced = _canonical_zero(
        math.fsum(
            (
                problem.shared_identity_cost,
                *(item.reduced_objective for item in contributions),
            )
        )
    )
    objective = math.fsum(
        (
            *(item.null_objective for item in problem.dwells),
            problem.shared_identity_cost,
            *(item.reduced_objective for item in contributions),
        )
    )
    return EvaluatedSharedNoradSchedule(
        catalog_number=schedule.catalog_number,
        contributions=tuple(contributions),
        support_session_ids=support_sessions,
        shared_without_identity_reduced_objective=reduced_without_identity,
        association_reduced_objective=association_reduced,
        null_objective=null_objective,
        objective=objective,
        claim_kind=ASSOCIATION_CLAIM_KIND,
        algorithm=EVALUATOR_ALGORITHM,
        fixed_schedule_score_exact=True,
    )


def _independent_identity_contributions(
    problem: CrossDwellAssociationProblem,
    state_space_by_key: dict[tuple[str, int], ExactDwellCatalogStateSpace],
) -> tuple[float, ...]:
    contributions = []
    for dwell in problem.dwells:
        available_states = tuple(
            state
            for catalog_number in problem.catalog_numbers
            if (state := _best_state(state_space_by_key[(dwell.dwell_id, catalog_number)]))
            is not None
        )
        best = min(
            available_states,
            key=lambda item: (item.reduced_objective, item.state_id),
            default=None,
        )
        contributions.append(0.0 if best is None else min(0.0, best.reduced_objective))
    return tuple(contributions)


def _catalog_margin(
    runner_up: CatalogAssociationScore | None,
    selected: CatalogAssociationScore,
    shared_identity_cost: float,
) -> float:
    """Return runner-minus-selected from primitive contributions in one sum."""

    runner_terms = (
        ()
        if runner_up is None
        else (
            shared_identity_cost,
            *(item.reduced_objective for item in runner_up.contributions),
        )
    )
    return _canonical_zero(
        math.fsum(
            (
                *runner_terms,
                -shared_identity_cost,
                *(-item.reduced_objective for item in selected.contributions),
            )
        )
    )


def _compare_catalog_scores(
    left: CatalogAssociationScore,
    right: CatalogAssociationScore,
) -> int:
    """Compare exact primitive dwell sums; use catalog number only on equality.

    The shared identity cost is common to both catalogs and cancels.  Comparing
    their already-rounded serialized totals would lose subnormal differences.
    """

    difference = math.fsum(
        (
            *(item.reduced_objective for item in left.contributions),
            *(-item.reduced_objective for item in right.contributions),
        )
    )
    if difference < 0.0:
        return -1
    if difference > 0.0:
        return 1
    return (left.catalog_number > right.catalog_number) - (
        left.catalog_number < right.catalog_number
    )


def _compare_catalog_with_null(
    score: CatalogAssociationScore,
    shared_identity_cost: float,
) -> int:
    """Compare one catalog with null directly from primitive objective terms."""

    difference = math.fsum(
        (
            shared_identity_cost,
            *(item.reduced_objective for item in score.contributions),
        )
    )
    if difference < 0.0:
        return -1
    if difference > 0.0:
        return 1
    return 0


def decode_cross_dwell_shared_norad(
    problem: CrossDwellAssociationProblem,
) -> CrossDwellAssociationResult:
    """Find and independently recheck the exact best same-NORAD association."""

    state_space_by_key = _complete_state_space_index(problem)
    catalog_scores = tuple(
        _score_catalog(problem, catalog_number, state_space_by_key)
        for catalog_number in problem.catalog_numbers
    )
    independent_catalog_scores = tuple(
        _independently_score_catalog(problem, catalog_number, state_space_by_key)
        for catalog_number in problem.catalog_numbers
    )
    if catalog_scores != independent_catalog_scores:
        raise ArithmeticError("independent catalog-score checker disagrees with optimizer")
    admissible_scores = tuple(item for item in catalog_scores if item.admissible)
    independently_checked_by_catalog = {}
    for score in admissible_scores:
        candidate_schedule = SharedNoradSchedule(
            catalog_number=score.catalog_number,
            selections=tuple(
                DwellStateSelection(item.dwell_id, item.state_id)
                for item in score.contributions
                if item.state_id is not None
            ),
        )
        candidate_check = evaluate_shared_norad_schedule(problem, candidate_schedule)
        if (
            candidate_check.catalog_number != score.catalog_number
            or candidate_check.contributions != score.contributions
            or candidate_check.support_session_ids != score.support_session_ids
            or candidate_check.shared_without_identity_reduced_objective
            != score.shared_without_identity_reduced_objective
            or candidate_check.association_reduced_objective != score.association_reduced_objective
        ):
            raise ArithmeticError("independent shared-NORAD schedule recheck disagrees")
        independently_checked_by_catalog[score.catalog_number] = candidate_check
    ranked_scores = tuple(
        sorted(
            admissible_scores,
            key=cmp_to_key(_compare_catalog_scores),
        )
    )

    best_score = ranked_scores[0] if ranked_scores else None
    selected_score = (
        best_score
        if best_score is not None
        and _compare_catalog_with_null(best_score, problem.shared_identity_cost) < 0
        else None
    )
    checked = (
        evaluate_shared_norad_schedule(problem, SharedNoradSchedule(None))
        if selected_score is None
        else independently_checked_by_catalog[selected_score.catalog_number]
    )

    if selected_score is None:
        runner_up_score = best_score
        runner_up_reduced = (
            None if runner_up_score is None else runner_up_score.association_reduced_objective
        )
        runner_up_margin = runner_up_reduced
    else:
        alternatives = tuple(item for item in ranked_scores if item is not selected_score)
        next_score = alternatives[0] if alternatives else None
        if (
            next_score is None
            or _compare_catalog_with_null(next_score, problem.shared_identity_cost) >= 0
        ):
            runner_up_score = None
            runner_up_reduced = 0.0
        else:
            runner_up_score = next_score
            runner_up_reduced = next_score.association_reduced_objective
        runner_up_margin = _catalog_margin(
            runner_up_score,
            selected_score,
            problem.shared_identity_cost,
        )
        if runner_up_margin < 0.0:
            raise ArithmeticError("runner-up margin became negative")

    independent_contributions = _independent_identity_contributions(problem, state_space_by_key)
    independent_reduced = _canonical_zero(math.fsum(independent_contributions))
    independent_objective = math.fsum(
        (
            *(item.null_objective for item in problem.dwells),
            *independent_contributions,
        )
    )
    if admissible_scores:
        best_shared_without_identity = ranked_scores[0]
        coherence_gap = _canonical_zero(
            math.fsum(
                (
                    *(
                        item.reduced_objective
                        for item in best_shared_without_identity.contributions
                    ),
                    *(-item for item in independent_contributions),
                )
            )
        )
        if coherence_gap < 0.0:
            raise ArithmeticError("shared-identity coherence gap became negative")
    else:
        best_shared_without_identity = None
        coherence_gap = None

    return CrossDwellAssociationResult(
        selected_catalog_number=checked.catalog_number,
        contributions=checked.contributions,
        support_session_ids=checked.support_session_ids,
        null_objective=checked.null_objective,
        reduced_objective=checked.association_reduced_objective,
        objective=checked.objective,
        runner_up_catalog_number=(
            None if runner_up_score is None else runner_up_score.catalog_number
        ),
        runner_up_reduced_objective=runner_up_reduced,
        runner_up_margin=runner_up_margin,
        independent_identity_reduced_objective=independent_reduced,
        independent_identity_objective=independent_objective,
        best_shared_without_identity_catalog_number=(
            None
            if best_shared_without_identity is None
            else best_shared_without_identity.catalog_number
        ),
        best_shared_without_identity_reduced_objective=(
            None
            if best_shared_without_identity is None
            else best_shared_without_identity.shared_without_identity_reduced_objective
        ),
        coherence_gap=coherence_gap,
        catalog_scores=catalog_scores,
        claim_kind=ASSOCIATION_CLAIM_KIND,
        algorithm=DECODER_ALGORITHM,
        evaluator_algorithm=EVALUATOR_ALGORITHM,
        exact=True,
    )
