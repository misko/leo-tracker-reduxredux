"""Exact arbitrary-catalog association over retained delay/CFO state banks.

Each catalog supplies a finite bank of fixed :class:`SingleSatelliteHypothesis`
states.  At a conflict-search node, the catalog oracle decodes every retained
state under the same catalog-wide set of forbidden physical exclusion groups
and profiles the deterministic minimum.  Thus a selected catalog uses exactly
one delay/CFO state across every activity episode.

The profiled catalog objectives are additive lower bounds until two catalogs
claim the same physical group.  The conflict is covered by forbidding that
group for either owner, exactly as in the fixed-state conflict search.  This is
a Research-only optimizer over caller-supplied discrete states; it does not
query catalogs, propagate TLEs, or fit continuous nuisance parameters.
It inherits the fixed-state solver's fail-closed requirement that strict
forbidden-match dominance be finitely representable at the supplied cost scale.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from fractions import Fraction
from numbers import Integral

from leo.analysis.research.multi_satellite_activity import (
    JointSatelliteAssociationResult,
    JointSatelliteSchedule,
    evaluate_joint_satellite_schedule,
)
from leo.analysis.research.satellite_activity import (
    SatelliteActivityProblem,
    SingleSatelliteAssociationResult,
    SingleSatelliteHypothesis,
    decode_single_satellite,
)
from leo.analysis.research.scalable_multi_satellite_activity import (
    _assigned_groups,
    _definitely_above,
    _independent_lower_bound,
    _node_signature,
    _problem_with_forbidden_groups,
    _single_reduced_terms,
)

ALGORITHM = "exact-grouped-conflict-branch-and-bound-v1"


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class CatalogNuisanceStateBank:
    """Finite retained delay/CFO states for one physical catalog."""

    catalog_number: int
    states: tuple[SingleSatelliteHypothesis, ...]

    def __post_init__(self) -> None:
        catalog_number = _positive_integer(self.catalog_number, "state-bank catalog number")
        states = tuple(
            sorted(
                self.states,
                key=lambda item: (
                    item.hypothesis_id,
                    item.object_name,
                    item.delay_s,
                    item.cfo_offset_hz,
                ),
            )
        )
        if not states:
            raise ValueError("a catalog nuisance-state bank must not be empty")
        state_ids = tuple(item.hypothesis_id for item in states)
        if len(set(state_ids)) != len(state_ids):
            raise ValueError("nuisance-state hypothesis IDs must be unique within a catalog")
        mismatches = sorted(
            {item.catalog_number for item in states if item.catalog_number != catalog_number}
        )
        if mismatches:
            raise ValueError(
                "every nuisance state must match its state-bank catalog number "
                f"(mismatches={mismatches!r})"
            )
        object_names = {item.object_name for item in states}
        if len(object_names) != 1:
            raise ValueError("nuisance states in one catalog bank must share one object name")
        object.__setattr__(self, "catalog_number", catalog_number)
        object.__setattr__(self, "states", states)

    @property
    def state_ids(self) -> tuple[str, ...]:
        return tuple(item.hypothesis_id for item in self.states)


@dataclass(frozen=True, slots=True)
class ExactGroupedSearchLimits:
    """Fail-closed node and exact state-decoder limits."""

    max_nodes: int = 100_000
    max_state_decodes: int = 1_000_000

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_nodes",
            _positive_integer(self.max_nodes, "grouped exact-search max_nodes"),
        )
        object.__setattr__(
            self,
            "max_state_decodes",
            _positive_integer(
                self.max_state_decodes,
                "grouped exact-search max_state_decodes",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExactGroupedSearchAccounting:
    """Auditable work counters for a completed or capped grouped search."""

    catalog_count: int
    supplied_state_count: int
    nodes_evaluated: int
    nodes_expanded: int
    nodes_pruned_by_bound: int
    duplicate_nodes_skipped: int
    conflict_branches: int
    catalog_oracle_evaluations: int
    catalog_oracle_cache_hits: int
    state_decodes: int
    state_decode_cache_hits: int
    maximum_frontier_size: int
    root_was_conflict_free: bool
    greedy_incumbent_built: bool


@dataclass(frozen=True, slots=True)
class CatalogNuisanceStateDecision:
    """The profiled state and selection status for one catalog."""

    catalog_number: int
    candidate_state_ids: tuple[str, ...]
    evaluated_state_id: str
    selected_state_id: str | None

    def __post_init__(self) -> None:
        catalog_number = _positive_integer(self.catalog_number, "state-decision catalog number")
        candidate_state_ids = tuple(sorted(self.candidate_state_ids))
        if not candidate_state_ids:
            raise ValueError("a catalog state decision needs candidate states")
        if any(not item for item in candidate_state_ids):
            raise ValueError("candidate nuisance-state IDs must not be empty")
        if len(set(candidate_state_ids)) != len(candidate_state_ids):
            raise ValueError("candidate nuisance-state IDs must be unique")
        if self.evaluated_state_id not in candidate_state_ids:
            raise ValueError("evaluated nuisance state is not in its candidate bank")
        if self.selected_state_id not in (None, self.evaluated_state_id):
            raise ValueError("selected nuisance state must equal the evaluated state")
        object.__setattr__(self, "catalog_number", catalog_number)
        object.__setattr__(self, "candidate_state_ids", candidate_state_ids)

    @property
    def selected(self) -> bool:
        return self.selected_state_id is not None


@dataclass(frozen=True, slots=True)
class ExactGroupedSatelliteAssociation:
    """A certified association and its discrete-state search receipt."""

    association: JointSatelliteAssociationResult
    catalog_states: tuple[CatalogNuisanceStateDecision, ...]
    limits: ExactGroupedSearchLimits
    accounting: ExactGroupedSearchAccounting

    def __post_init__(self) -> None:
        states = tuple(sorted(self.catalog_states, key=lambda item: item.catalog_number))
        object.__setattr__(self, "catalog_states", states)
        if not self.association.exact:
            raise ValueError("a grouped exact-search result must contain an exact association")
        association_by_catalog = {item.catalog_number: item for item in self.association.satellites}
        if tuple(sorted(association_by_catalog)) != tuple(item.catalog_number for item in states):
            raise ValueError("catalog-state metadata disagrees with association catalogs")
        for state in states:
            decision = association_by_catalog[state.catalog_number]
            if decision.hypothesis_id != state.evaluated_state_id:
                raise ValueError("evaluated state metadata disagrees with association")
            expected = decision.hypothesis_id if decision.selected else None
            if state.selected_state_id != expected:
                raise ValueError("selected state metadata disagrees with association")

    @property
    def exact(self) -> bool:
        return self.association.exact

    @property
    def selected_state_ids(self) -> tuple[str, ...]:
        return tuple(
            item.selected_state_id
            for item in self.catalog_states
            if item.selected_state_id is not None
        )


class ExactGroupedSearchLimitExceeded(RuntimeError):
    """Raised rather than returning an unproven grouped association."""

    def __init__(
        self,
        *,
        limit_kind: str,
        limits: ExactGroupedSearchLimits,
        accounting: ExactGroupedSearchAccounting,
    ) -> None:
        if limit_kind not in {"nodes", "state_decodes"}:
            raise ValueError("unknown grouped exact-search limit kind")
        self.limit_kind = limit_kind
        self.limits = limits
        self.accounting = accounting
        maximum = limits.max_nodes if limit_kind == "nodes" else limits.max_state_decodes
        observed = accounting.nodes_evaluated if limit_kind == "nodes" else accounting.state_decodes
        super().__init__(
            f"grouped exact search exhausted max_{limit_kind}={maximum} "
            f"at {observed} before proving optimality"
        )


@dataclass(slots=True)
class _MutableAccounting:
    catalog_count: int
    supplied_state_count: int
    nodes_evaluated: int = 0
    nodes_expanded: int = 0
    nodes_pruned_by_bound: int = 0
    duplicate_nodes_skipped: int = 0
    conflict_branches: int = 0
    catalog_oracle_evaluations: int = 0
    catalog_oracle_cache_hits: int = 0
    state_decodes: int = 0
    state_decode_cache_hits: int = 0
    maximum_frontier_size: int = 0
    root_was_conflict_free: bool = False
    greedy_incumbent_built: bool = False

    def freeze(self) -> ExactGroupedSearchAccounting:
        return ExactGroupedSearchAccounting(
            catalog_count=self.catalog_count,
            supplied_state_count=self.supplied_state_count,
            nodes_evaluated=self.nodes_evaluated,
            nodes_expanded=self.nodes_expanded,
            nodes_pruned_by_bound=self.nodes_pruned_by_bound,
            duplicate_nodes_skipped=self.duplicate_nodes_skipped,
            conflict_branches=self.conflict_branches,
            catalog_oracle_evaluations=self.catalog_oracle_evaluations,
            catalog_oracle_cache_hits=self.catalog_oracle_cache_hits,
            state_decodes=self.state_decodes,
            state_decode_cache_hits=self.state_decode_cache_hits,
            maximum_frontier_size=self.maximum_frontier_size,
            root_was_conflict_free=self.root_was_conflict_free,
            greedy_incumbent_built=self.greedy_incumbent_built,
        )


@dataclass(frozen=True, slots=True)
class _CatalogDecode:
    hypothesis: SingleSatelliteHypothesis
    result: SingleSatelliteAssociationResult


_ForbiddenByCatalog = tuple[frozenset[str], ...]


@dataclass(frozen=True, slots=True)
class _NodeEvaluation:
    forbidden_by_catalog: _ForbiddenByCatalog
    catalogs: tuple[_CatalogDecode, ...]
    lower_bound: float
    conflict: tuple[str, int, int] | None


@dataclass(frozen=True, slots=True)
class _FeasibleCandidate:
    association: JointSatelliteAssociationResult
    hypotheses: tuple[SingleSatelliteHypothesis, ...]


def _canonical_banks(
    banks: tuple[CatalogNuisanceStateBank, ...],
) -> tuple[CatalogNuisanceStateBank, ...]:
    ordered = tuple(sorted(tuple(banks), key=lambda item: item.catalog_number))
    if not ordered:
        raise ValueError("grouped exact search needs at least one catalog state bank")
    catalog_numbers = tuple(item.catalog_number for item in ordered)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("catalog nuisance-state banks must have unique catalog numbers")
    state_ids = tuple(state.hypothesis_id for bank in ordered for state in bank.states)
    if len(set(state_ids)) != len(state_ids):
        raise ValueError("nuisance-state hypothesis IDs must be globally unique")
    return ordered


def _catalog_state_key(
    hypothesis: SingleSatelliteHypothesis,
    result: SingleSatelliteAssociationResult,
    reduced_cost: Fraction,
) -> tuple[object, ...]:
    """Profile reduced cost, then apply the repository's deterministic ties."""

    selected_state_id = hypothesis.hypothesis_id if result.selected else ""
    return (
        reduced_cost,
        result.objective.total_cost,
        result.selected,
        len(result.episodes),
        sum(result.activity_by_cell),
        selected_state_id,
        result.activity_by_cell,
        len(result.assignments),
        tuple(
            (assignment.probe_id, assignment.observation_id) for assignment in result.assignments
        ),
        hypothesis.hypothesis_id,
    )


def _exact_reduced_cost(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
    result: SingleSatelliteAssociationResult,
    clutter_by_group: dict[str, float],
) -> Fraction:
    return sum(
        (
            Fraction.from_float(item)
            for item in _single_reduced_terms(
                problem,
                hypothesis,
                result,
                clutter_by_group,
            )
        ),
        start=Fraction(),
    )


def _candidate_key(candidate: _FeasibleCandidate) -> tuple[object, ...]:
    association = candidate.association
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
        tuple(item.hypothesis_id for item in candidate.hypotheses),
    )


def _first_conflict(
    catalogs: tuple[_CatalogDecode, ...],
    group_by_observation_id: dict[str, str],
) -> tuple[str, int, int] | None:
    owners_by_group: dict[str, list[int]] = {}
    for catalog_index, decoded in enumerate(catalogs):
        groups = _assigned_groups(decoded.result, group_by_observation_id)
        for group_id in sorted(groups):
            owners_by_group.setdefault(group_id, []).append(catalog_index)
    for group_id in sorted(owners_by_group):
        owners = owners_by_group[group_id]
        if len(owners) > 1:
            return (group_id, owners[0], owners[1])
    return None


def _schedule(decoded: _CatalogDecode) -> JointSatelliteSchedule:
    return JointSatelliteSchedule(
        hypothesis_id=decoded.hypothesis.hypothesis_id,
        activity_by_cell=decoded.result.activity_by_cell,
        assignments=decoded.result.assignments,
    )


def decode_arbitrary_n_grouped_nuisance_states(
    problem: SatelliteActivityProblem,
    banks: tuple[CatalogNuisanceStateBank, ...],
    *,
    limits: ExactGroupedSearchLimits | None = None,
) -> ExactGroupedSatelliteAssociation:
    """Exactly profile finite state banks while selecting any catalog subset."""

    ordered_banks = _canonical_banks(banks)
    if problem.truncated_observation_count:
        raise ValueError("grouped exact search requires an untruncated candidate inventory")
    selected_limits = ExactGroupedSearchLimits() if limits is None else limits
    if not isinstance(selected_limits, ExactGroupedSearchLimits):
        raise TypeError("limits must be an ExactGroupedSearchLimits instance")

    accounting = _MutableAccounting(
        catalog_count=len(ordered_banks),
        supplied_state_count=sum(len(item.states) for item in ordered_banks),
    )
    group_by_observation_id = {
        item.observation_id: item.exclusion_group_id for item in problem.observations
    }
    clutter_by_group: dict[str, float] = {}
    for observation in problem.observations:
        clutter_by_group.setdefault(observation.exclusion_group_id, observation.clutter_cost)
    problem_cache: dict[frozenset[str], SatelliteActivityProblem] = {frozenset(): problem}
    state_cache: dict[tuple[int, str, frozenset[str]], SingleSatelliteAssociationResult] = {}
    catalog_cache: dict[tuple[int, frozenset[str]], _CatalogDecode] = {}

    def state_decode(
        catalog_index: int,
        state: SingleSatelliteHypothesis,
        forbidden_groups: frozenset[str],
    ) -> SingleSatelliteAssociationResult:
        bank = ordered_banks[catalog_index]
        cache_key = (bank.catalog_number, state.hypothesis_id, forbidden_groups)
        cached = state_cache.get(cache_key)
        if cached is not None:
            accounting.state_decode_cache_hits += 1
            return cached
        if accounting.state_decodes >= selected_limits.max_state_decodes:
            raise ExactGroupedSearchLimitExceeded(
                limit_kind="state_decodes",
                limits=selected_limits,
                accounting=accounting.freeze(),
            )
        restricted_problem = problem_cache.get(forbidden_groups)
        if restricted_problem is None:
            restricted_problem = _problem_with_forbidden_groups(problem, forbidden_groups)
            problem_cache[forbidden_groups] = restricted_problem
        result = decode_single_satellite(restricted_problem, state)
        state_cache[cache_key] = result
        accounting.state_decodes += 1
        return result

    def catalog_decode(
        catalog_index: int,
        forbidden_groups: frozenset[str],
    ) -> _CatalogDecode:
        bank = ordered_banks[catalog_index]
        cache_key = (bank.catalog_number, forbidden_groups)
        cached = catalog_cache.get(cache_key)
        if cached is not None:
            accounting.catalog_oracle_cache_hits += 1
            return cached
        candidates = tuple(
            _CatalogDecode(
                hypothesis=state,
                result=state_decode(catalog_index, state, forbidden_groups),
            )
            for state in bank.states
        )
        winner = min(
            candidates,
            key=lambda item: _catalog_state_key(
                item.hypothesis,
                item.result,
                _exact_reduced_cost(
                    problem,
                    item.hypothesis,
                    item.result,
                    clutter_by_group,
                ),
            ),
        )
        catalog_cache[cache_key] = winner
        accounting.catalog_oracle_evaluations += 1
        return winner

    def evaluate_node(forbidden: _ForbiddenByCatalog) -> _NodeEvaluation:
        if accounting.nodes_evaluated >= selected_limits.max_nodes:
            raise ExactGroupedSearchLimitExceeded(
                limit_kind="nodes",
                limits=selected_limits,
                accounting=accounting.freeze(),
            )
        catalogs = tuple(
            catalog_decode(index, forbidden_groups)
            for index, forbidden_groups in enumerate(forbidden)
        )
        accounting.nodes_evaluated += 1
        return _NodeEvaluation(
            forbidden_by_catalog=forbidden,
            catalogs=catalogs,
            lower_bound=_independent_lower_bound(
                problem,
                tuple(item.hypothesis for item in catalogs),
                tuple(item.result for item in catalogs),
                clutter_by_group,
            ),
            conflict=_first_conflict(catalogs, group_by_observation_id),
        )

    def feasible_candidate(catalogs: tuple[_CatalogDecode, ...]) -> _FeasibleCandidate:
        hypotheses = tuple(item.hypothesis for item in catalogs)
        association = evaluate_joint_satellite_schedule(
            problem,
            hypotheses,
            tuple(_schedule(item) for item in catalogs),
            algorithm=ALGORITHM,
            exact=True,
        )
        return _FeasibleCandidate(association=association, hypotheses=hypotheses)

    root_forbidden: _ForbiddenByCatalog = tuple(frozenset() for _item in ordered_banks)
    root = evaluate_node(root_forbidden)
    accounting.root_was_conflict_free = root.conflict is None
    frontier: list[tuple[float, tuple[tuple[str, ...], ...], _NodeEvaluation]] = [
        (root.lower_bound, _node_signature(root.forbidden_by_catalog), root)
    ]
    accounting.maximum_frontier_size = 1
    seen = {root.forbidden_by_catalog}
    incumbent: _FeasibleCandidate | None = None

    if root.conflict is not None:
        claimed_groups: set[str] = set()
        greedy_catalogs: list[_CatalogDecode | None] = [None for _item in ordered_banks]
        greedy_order = sorted(
            range(len(ordered_banks)),
            key=lambda index: (
                _exact_reduced_cost(
                    problem,
                    root.catalogs[index].hypothesis,
                    root.catalogs[index].result,
                    clutter_by_group,
                ),
                ordered_banks[index].catalog_number,
            ),
        )
        for index in greedy_order:
            independent = root.catalogs[index]
            if _assigned_groups(independent.result, group_by_observation_id).isdisjoint(
                claimed_groups
            ):
                selected = independent
            else:
                selected = catalog_decode(index, frozenset(claimed_groups))
            greedy_catalogs[index] = selected
            claimed_groups.update(_assigned_groups(selected.result, group_by_observation_id))
        if any(item is None for item in greedy_catalogs):
            raise RuntimeError("grouped greedy incumbent omitted a catalog")
        incumbent = feasible_candidate(tuple(item for item in greedy_catalogs if item is not None))
        accounting.greedy_incumbent_built = True

    while frontier:
        _bound, _signature, node = heapq.heappop(frontier)
        accounting.nodes_expanded += 1
        if incumbent is not None and _definitely_above(
            node.lower_bound,
            incumbent.association.objective.total_cost,
        ):
            accounting.nodes_pruned_by_bound += 1
            continue

        if node.conflict is None:
            candidate = feasible_candidate(node.catalogs)
            if not math.isclose(
                candidate.association.objective.total_cost,
                node.lower_bound,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise RuntimeError("conflict-free grouped lower bound disagrees with joint checker")
            if incumbent is None or _candidate_key(candidate) < _candidate_key(incumbent):
                incumbent = candidate
            continue

        group_id, first_owner, second_owner = node.conflict
        accounting.conflict_branches += 1
        for owner in (first_owner, second_owner):
            child_forbidden = list(node.forbidden_by_catalog)
            child_forbidden[owner] = child_forbidden[owner] | {group_id}
            child_signature = tuple(child_forbidden)
            if child_signature in seen:
                accounting.duplicate_nodes_skipped += 1
                continue
            seen.add(child_signature)
            child = evaluate_node(child_signature)
            if incumbent is not None and _definitely_above(
                child.lower_bound,
                incumbent.association.objective.total_cost,
            ):
                accounting.nodes_pruned_by_bound += 1
                continue
            heapq.heappush(
                frontier,
                (child.lower_bound, _node_signature(child.forbidden_by_catalog), child),
            )
        accounting.maximum_frontier_size = max(
            accounting.maximum_frontier_size,
            len(frontier),
        )

    if incumbent is None:
        raise RuntimeError("grouped exact conflict search found no feasible schedule")

    decision_by_catalog = {item.catalog_number: item for item in incumbent.association.satellites}
    hypothesis_by_catalog = {item.catalog_number: item for item in incumbent.hypotheses}
    state_decisions = tuple(
        CatalogNuisanceStateDecision(
            catalog_number=bank.catalog_number,
            candidate_state_ids=bank.state_ids,
            evaluated_state_id=hypothesis_by_catalog[bank.catalog_number].hypothesis_id,
            selected_state_id=(
                hypothesis_by_catalog[bank.catalog_number].hypothesis_id
                if decision_by_catalog[bank.catalog_number].selected
                else None
            ),
        )
        for bank in ordered_banks
    )
    return ExactGroupedSatelliteAssociation(
        association=incumbent.association,
        catalog_states=state_decisions,
        limits=selected_limits,
        accounting=accounting.freeze(),
    )
