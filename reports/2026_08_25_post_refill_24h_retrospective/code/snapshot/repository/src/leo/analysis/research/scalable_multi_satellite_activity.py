"""Exact conflict-branching association for any fixed hypothesis count.

This research-only solver uses the exact single-satellite semi-Markov decoder
as a pricing oracle.  With no shared physical exclusion groups, the joint
objective is the null clutter baseline plus the sum of the independently
decoded reduced objectives.  That sum remains a lower bound when independent
solutions conflict.  A conflict between satellites ``A`` and ``B`` on group
``g`` is covered exactly by the disjunction ``A != g`` or ``B != g``.

The implementation deliberately fixes every satellite's orbital delay and CFO
offset before this search.  It supports the existing linear per-selected-
satellite penalty and does not perform catalogue search or continuous fitting.
Catalog-wide forbiddance uses a finite, strictly dominated match-cost clone. If
the input cost scale leaves no representable positive dominance margin, search
raises ``ValueError`` rather than returning an exact result.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, replace
from numbers import Integral

from leo.analysis.research.multi_satellite_activity import (
    JointSatelliteAssociationResult,
    JointSatelliteSchedule,
    _canonical_hypotheses,
    evaluate_joint_satellite_schedule,
)
from leo.analysis.research.satellite_activity import (
    CfoCandidate,
    SatelliteActivityProblem,
    SingleSatelliteAssociationResult,
    SingleSatelliteHypothesis,
    decode_single_satellite,
    huber_loss,
)

ALGORITHM = "exact-conflict-branch-and-bound-v1"


@dataclass(frozen=True, slots=True)
class ExactJointSearchLimits:
    """Hard limits for an exact conflict search.

    ``max_nodes`` counts distinct branch nodes whose independent lower bounds
    are decoded.  Reaching the limit before the frontier is exhausted raises
    :class:`ExactJointSearchLimitExceeded`; no inexact result is returned.
    """

    max_nodes: int = 100_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_nodes, bool)
            or not isinstance(self.max_nodes, Integral)
            or self.max_nodes < 1
        ):
            raise ValueError("exact joint-search max_nodes must be a positive integer")


@dataclass(frozen=True, slots=True)
class ExactJointSearchAccounting:
    """Auditable work counters for one exact search (or a failed cap)."""

    hypothesis_count: int
    nodes_evaluated: int
    nodes_expanded: int
    nodes_pruned_by_bound: int
    duplicate_nodes_skipped: int
    conflict_branches: int
    single_decodes: int
    single_decode_cache_hits: int
    maximum_frontier_size: int
    root_was_conflict_free: bool
    greedy_incumbent_built: bool


@dataclass(frozen=True, slots=True)
class ExactJointSatelliteAssociation:
    """One certified association together with its limits and search receipt."""

    association: JointSatelliteAssociationResult
    limits: ExactJointSearchLimits
    accounting: ExactJointSearchAccounting

    @property
    def exact(self) -> bool:
        return self.association.exact


class ExactJointSearchLimitExceeded(RuntimeError):
    """Raised instead of returning a result when exact search exceeds its cap."""

    def __init__(
        self,
        limits: ExactJointSearchLimits,
        accounting: ExactJointSearchAccounting,
    ) -> None:
        self.limits = limits
        self.accounting = accounting
        super().__init__(
            "exact joint search exhausted max_nodes="
            f"{limits.max_nodes} before proving optimality "
            f"(evaluated={accounting.nodes_evaluated}, "
            f"expanded={accounting.nodes_expanded})"
        )


@dataclass(slots=True)
class _MutableAccounting:
    hypothesis_count: int
    nodes_evaluated: int = 0
    nodes_expanded: int = 0
    nodes_pruned_by_bound: int = 0
    duplicate_nodes_skipped: int = 0
    conflict_branches: int = 0
    single_decodes: int = 0
    single_decode_cache_hits: int = 0
    maximum_frontier_size: int = 0
    root_was_conflict_free: bool = False
    greedy_incumbent_built: bool = False

    def freeze(self) -> ExactJointSearchAccounting:
        return ExactJointSearchAccounting(
            hypothesis_count=self.hypothesis_count,
            nodes_evaluated=self.nodes_evaluated,
            nodes_expanded=self.nodes_expanded,
            nodes_pruned_by_bound=self.nodes_pruned_by_bound,
            duplicate_nodes_skipped=self.duplicate_nodes_skipped,
            conflict_branches=self.conflict_branches,
            single_decodes=self.single_decodes,
            single_decode_cache_hits=self.single_decode_cache_hits,
            maximum_frontier_size=self.maximum_frontier_size,
            root_was_conflict_free=self.root_was_conflict_free,
            greedy_incumbent_built=self.greedy_incumbent_built,
        )


_ForbiddenByHypothesis = tuple[frozenset[str], ...]


@dataclass(frozen=True, slots=True)
class _NodeEvaluation:
    forbidden_by_hypothesis: _ForbiddenByHypothesis
    independent: tuple[SingleSatelliteAssociationResult, ...]
    lower_bound: float
    conflict: tuple[str, int, int] | None


def _dominated_matched_base_cost(
    observation: CfoCandidate,
    missed_detection_cost: float,
) -> float:
    """Return a finite base cost whose zero-residual match cannot beat a miss."""

    matched_base_cost = observation.clutter_cost + missed_detection_cost
    if not math.isfinite(matched_base_cost):
        raise ValueError("forbidden-group dominance cost is not finitely representable")
    # Addition followed by subtraction can round downward under a very uneven
    # cost scale.  One representable step is sufficient in ordinary cases; the
    # bounded loop makes the dominance claim explicit rather than assumed.
    matched_base_cost = math.nextafter(matched_base_cost, math.inf)
    if not math.isfinite(matched_base_cost):
        raise ValueError("forbidden-group dominance cost is not finitely representable")
    for _attempt in range(8):
        reduced_cost = matched_base_cost - observation.clutter_cost
        if reduced_cost > missed_detection_cost:
            return matched_base_cost
        matched_base_cost = math.nextafter(matched_base_cost, math.inf)
        if not math.isfinite(matched_base_cost):
            break
    raise ValueError("forbidden-group dominance cost is not finitely representable")


def _problem_with_forbidden_groups(
    problem: SatelliteActivityProblem,
    forbidden_groups: frozenset[str],
) -> SatelliteActivityProblem:
    """Clone matching costs while retaining every group's clutter baseline."""

    if not forbidden_groups:
        return problem
    probe_by_id = {item.probe_id: item for item in problem.probes}
    observations = tuple(
        replace(
            observation,
            matched_base_cost=_dominated_matched_base_cost(
                observation,
                probe_by_id[observation.probe_id].missed_detection_cost,
            ),
        )
        if observation.exclusion_group_id in forbidden_groups
        else observation
        for observation in problem.observations
    )
    return replace(problem, observations=observations)


def _assigned_groups(
    result: SingleSatelliteAssociationResult,
    group_by_observation_id: dict[str, str],
) -> frozenset[str]:
    return frozenset(
        group_by_observation_id[assignment.observation_id] for assignment in result.assignments
    )


def _single_reduced_terms(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
    result: SingleSatelliteAssociationResult,
    clutter_by_group: dict[str, float],
) -> tuple[float, ...]:
    """Return primitive reduced terms without ``total - null`` cancellation."""

    observation_by_id = {item.observation_id: item for item in problem.observations}
    probe_by_id = {item.probe_id: item for item in problem.probes}
    prediction_by_probe = {item.probe_id: item.cfo_hz for item in hypothesis.predictions}
    matched_base_terms = []
    residual_terms = []
    consumed_group_ids = []
    for assignment in result.assignments:
        observation = observation_by_id[assignment.observation_id]
        predicted = prediction_by_probe[assignment.probe_id] + hypothesis.cfo_offset_hz
        residual = (observation.cfo_hz - predicted) / observation.sigma_hz
        matched_base_terms.append(observation.matched_base_cost)
        residual_terms.append(huber_loss(residual, problem.costs.huber_threshold))
        consumed_group_ids.append(observation.exclusion_group_id)
    if len(set(consumed_group_ids)) != len(consumed_group_ids):
        raise RuntimeError("single schedule consumed one exclusion group more than once")
    missed_terms = [
        probe_by_id[probe_id].missed_detection_cost for probe_id in result.missed_probe_ids
    ]
    structural_terms = [problem.costs.episode_cost] * len(result.episodes)
    if result.selected:
        structural_terms.extend((problem.costs.satellite_cost, hypothesis.delay_prior_cost))
    return (
        *matched_base_terms,
        *residual_terms,
        *missed_terms,
        *structural_terms,
        *(-clutter_by_group[group_id] for group_id in sorted(consumed_group_ids)),
    )


def _single_reduced_cost(
    problem: SatelliteActivityProblem,
    hypothesis: SingleSatelliteHypothesis,
    result: SingleSatelliteAssociationResult,
    clutter_by_group: dict[str, float],
) -> float:
    """Return a scalar reduced cost for deterministic greedy ordering only."""

    return math.fsum(_single_reduced_terms(problem, hypothesis, result, clutter_by_group))


def _independent_lower_bound(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
    independent: tuple[SingleSatelliteAssociationResult, ...],
    clutter_by_group: dict[str, float],
) -> float:
    """Cancel clutter once, inside one compensated sum over primitive terms."""

    terms = [clutter_by_group[group_id] for group_id in sorted(clutter_by_group)]
    for hypothesis, result in zip(hypotheses, independent, strict=True):
        terms.extend(_single_reduced_terms(problem, hypothesis, result, clutter_by_group))
    return math.fsum(terms)


def _first_conflict(
    independent: tuple[SingleSatelliteAssociationResult, ...],
    group_by_observation_id: dict[str, str],
) -> tuple[str, int, int] | None:
    owners_by_group: dict[str, list[int]] = {}
    for hypothesis_index, result in enumerate(independent):
        for group_id in sorted(_assigned_groups(result, group_by_observation_id)):
            owners_by_group.setdefault(group_id, []).append(hypothesis_index)
    for group_id in sorted(owners_by_group):
        owners = owners_by_group[group_id]
        if len(owners) > 1:
            return (group_id, owners[0], owners[1])
    return None


def _schedule_from_single(
    result: SingleSatelliteAssociationResult,
) -> JointSatelliteSchedule:
    return JointSatelliteSchedule(
        hypothesis_id=result.hypothesis_id,
        activity_by_cell=result.activity_by_cell,
        assignments=result.assignments,
    )


def _association_key(result: JointSatelliteAssociationResult) -> tuple[object, ...]:
    selected_catalog_key = tuple(not item.selected for item in result.satellites)
    return (
        result.objective.total_cost,
        len(result.selected_catalog_numbers),
        sum(len(item.episodes) for item in result.satellites),
        sum(sum(item.activity_by_cell) for item in result.satellites),
        selected_catalog_key,
        tuple(item.activity_by_cell for item in result.satellites),
        sum(len(item.assignments) for item in result.satellites),
        tuple(
            (item.hypothesis_id, assignment.probe_id, assignment.observation_id)
            for item in result.satellites
            for assignment in item.assignments
        ),
    )


def _definitely_above(value: float, incumbent: float) -> bool:
    """Prune only beyond the objective checker's floating-point tolerance."""

    return value > incumbent and not math.isclose(
        value,
        incumbent,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )


def _node_signature(forbidden: _ForbiddenByHypothesis) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(sorted(groups)) for groups in forbidden)


def decode_arbitrary_n_fixed_hypotheses(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
    *,
    limits: ExactJointSearchLimits | None = None,
) -> ExactJointSatelliteAssociation:
    """Exactly decode any positive number of unique-catalog fixed hypotheses.

    Each node forbids selected ``(hypothesis, exclusion-group)`` assignments.
    The independent exact decodes give a node lower bound.  A conflict-free
    union attains that bound, while a conflicting group yields an exhaustive
    two-way branch.  The returned schedule is rescored by the independent joint
    objective checker.  Candidate truncation is rejected because it cannot
    support an exact claim about the supplied observation inventory.  The
    forbidden-group dominance clone must also be finitely representable; an
    extreme cost scale that cannot express a strict margin fails closed.
    """

    ordered_hypotheses = _canonical_hypotheses(hypotheses)
    if problem.truncated_observation_count:
        raise ValueError("exact joint search requires an untruncated candidate inventory")
    selected_limits = ExactJointSearchLimits() if limits is None else limits
    if not isinstance(selected_limits, ExactJointSearchLimits):
        raise TypeError("limits must be an ExactJointSearchLimits instance")

    accounting = _MutableAccounting(hypothesis_count=len(ordered_hypotheses))
    group_by_observation_id = {
        item.observation_id: item.exclusion_group_id for item in problem.observations
    }
    null_cost_by_group: dict[str, float] = {}
    for observation in problem.observations:
        null_cost_by_group.setdefault(observation.exclusion_group_id, observation.clutter_cost)

    # Catalog identity is sufficient only because this API rejects multiple
    # states for one catalog.  The grouped-state layer uses a separate
    # ``(catalog, state ID, forbidden groups)`` decode cache before profiling a
    # catalog winner; this key must not be reused for grouped hypotheses.
    decode_cache: dict[tuple[int, frozenset[str]], SingleSatelliteAssociationResult] = {}
    problem_cache: dict[frozenset[str], SatelliteActivityProblem] = {frozenset(): problem}

    def single_decode(
        hypothesis_index: int,
        forbidden_groups: frozenset[str],
    ) -> SingleSatelliteAssociationResult:
        hypothesis = ordered_hypotheses[hypothesis_index]
        cache_key = (hypothesis.catalog_number, forbidden_groups)
        cached = decode_cache.get(cache_key)
        if cached is not None:
            accounting.single_decode_cache_hits += 1
            return cached
        restricted_problem = problem_cache.get(forbidden_groups)
        if restricted_problem is None:
            restricted_problem = _problem_with_forbidden_groups(problem, forbidden_groups)
            problem_cache[forbidden_groups] = restricted_problem
        result = decode_single_satellite(
            restricted_problem,
            hypothesis,
        )
        decode_cache[cache_key] = result
        accounting.single_decodes += 1
        return result

    def evaluate_node(forbidden: _ForbiddenByHypothesis) -> _NodeEvaluation:
        if accounting.nodes_evaluated >= selected_limits.max_nodes:
            raise ExactJointSearchLimitExceeded(selected_limits, accounting.freeze())
        independent = tuple(
            single_decode(index, forbidden_groups)
            for index, forbidden_groups in enumerate(forbidden)
        )
        accounting.nodes_evaluated += 1
        return _NodeEvaluation(
            forbidden_by_hypothesis=forbidden,
            independent=independent,
            lower_bound=_independent_lower_bound(
                problem,
                ordered_hypotheses,
                independent,
                null_cost_by_group,
            ),
            conflict=_first_conflict(independent, group_by_observation_id),
        )

    root_forbidden: _ForbiddenByHypothesis = tuple(frozenset() for _item in ordered_hypotheses)
    root = evaluate_node(root_forbidden)
    accounting.root_was_conflict_free = root.conflict is None
    frontier: list[tuple[float, tuple[tuple[str, ...], ...], _NodeEvaluation]] = [
        (root.lower_bound, _node_signature(root.forbidden_by_hypothesis), root)
    ]
    accounting.maximum_frontier_size = 1
    seen = {root.forbidden_by_hypothesis}
    incumbent: JointSatelliteAssociationResult | None = None

    # A deterministic strongest-first feasible union supplies an early upper
    # bound.  Exactness still comes only from exhausting/pruning the frontier.
    if root.conflict is not None:
        claimed_groups: set[str] = set()
        greedy_results: list[SingleSatelliteAssociationResult | None] = [
            None for _item in ordered_hypotheses
        ]
        greedy_order = sorted(
            range(len(ordered_hypotheses)),
            key=lambda index: (
                _single_reduced_cost(
                    problem,
                    ordered_hypotheses[index],
                    root.independent[index],
                    null_cost_by_group,
                ),
                ordered_hypotheses[index].catalog_number,
                ordered_hypotheses[index].hypothesis_id,
            ),
        )
        for index in greedy_order:
            independent = root.independent[index]
            if _assigned_groups(independent, group_by_observation_id).isdisjoint(claimed_groups):
                selected = independent
            else:
                selected = single_decode(index, frozenset(claimed_groups))
            greedy_results[index] = selected
            claimed_groups.update(_assigned_groups(selected, group_by_observation_id))
        if any(item is None for item in greedy_results):
            raise RuntimeError("greedy joint incumbent omitted a hypothesis")
        incumbent = evaluate_joint_satellite_schedule(
            problem,
            ordered_hypotheses,
            tuple(_schedule_from_single(item) for item in greedy_results if item is not None),
            algorithm=ALGORITHM,
            exact=True,
        )
        accounting.greedy_incumbent_built = True

    while frontier:
        _bound, _signature, node = heapq.heappop(frontier)
        accounting.nodes_expanded += 1
        if incumbent is not None and _definitely_above(
            node.lower_bound,
            incumbent.objective.total_cost,
        ):
            accounting.nodes_pruned_by_bound += 1
            continue

        if node.conflict is None:
            schedules = tuple(_schedule_from_single(item) for item in node.independent)
            association = evaluate_joint_satellite_schedule(
                problem,
                ordered_hypotheses,
                schedules,
                algorithm=ALGORITHM,
                exact=True,
            )
            if not math.isclose(
                association.objective.total_cost,
                node.lower_bound,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise RuntimeError(
                    "conflict-free independent lower bound disagrees with joint checker"
                )
            if incumbent is None or _association_key(association) < _association_key(incumbent):
                incumbent = association
            continue

        group_id, first_owner, second_owner = node.conflict
        accounting.conflict_branches += 1
        for owner in (first_owner, second_owner):
            child_forbidden = list(node.forbidden_by_hypothesis)
            child_forbidden[owner] = child_forbidden[owner] | {group_id}
            child_signature = tuple(child_forbidden)
            if child_signature in seen:
                accounting.duplicate_nodes_skipped += 1
                continue
            seen.add(child_signature)
            child = evaluate_node(child_signature)
            if incumbent is not None and _definitely_above(
                child.lower_bound,
                incumbent.objective.total_cost,
            ):
                accounting.nodes_pruned_by_bound += 1
                continue
            heapq.heappush(
                frontier,
                (child.lower_bound, _node_signature(child.forbidden_by_hypothesis), child),
            )
        accounting.maximum_frontier_size = max(
            accounting.maximum_frontier_size,
            len(frontier),
        )

    if incumbent is None:
        raise RuntimeError("exact joint conflict search found no feasible schedule")
    return ExactJointSatelliteAssociation(
        association=incumbent,
        limits=selected_limits,
        accounting=accounting.freeze(),
    )
