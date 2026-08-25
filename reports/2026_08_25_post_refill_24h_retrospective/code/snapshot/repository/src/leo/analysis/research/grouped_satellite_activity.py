"""Bounded exact activity association over grouped delay/CFO hypotheses.

This research-only layer profiles a small discrete nuisance-state grid without
changing the fixed-hypothesis joint decoder.  Every input hypothesis fixes one
catalog identity, orbital-time delay, CFO offset, delay-prior cost, and complete
set of native-probe predictions.  Hypotheses sharing a catalog number are
alternative nuisance states for the same physical satellite.

The implementation exhausts the Cartesian product containing one state from
each of two or three catalogs.  For every combination it invokes the exact
factorial semi-Markov decoder, which may select any subset of those catalogs,
including the null model.  Consequently a selected catalog uses exactly one
delay/CFO state and that state persists across all of its activity episodes.

Exactness is deliberately bounded and conditional: the retained observation
inventory must be complete, the caller must supply the nuisance states to be
searched, and their Cartesian product must fit the explicit combination limit.
This is a numerical oracle for small, already-gated candidate sets rather than
a catalog-scale optimizer.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from numbers import Integral

from leo.analysis.research.multi_satellite_activity import (
    MAXIMUM_EXACT_HYPOTHESES,
    MINIMUM_EXACT_HYPOTHESES,
    JointSatelliteAssociationResult,
    decode_joint_fixed_hypotheses,
)
from leo.analysis.research.satellite_activity import (
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
)

DEFAULT_MAXIMUM_STATE_COMBINATIONS = 256


def _nonempty(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")


@dataclass(frozen=True, slots=True)
class CatalogNuisanceStateDecision:
    """Auditable state selection for one physical catalog.

    ``evaluated_hypothesis_id`` identifies the member of the winning Cartesian
    combination.  It is retained even when the catalog is inactive so the
    exact winning decoder call is reproducible.  ``selected_hypothesis_id`` is
    ``None`` for an inactive catalog and otherwise must name that same state.
    """

    catalog_number: int
    candidate_hypothesis_ids: tuple[str, ...]
    evaluated_hypothesis_id: str
    selected_hypothesis_id: str | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, Integral)
            or self.catalog_number < 1
        ):
            raise ValueError("catalog number must be a positive integer")
        candidate_ids = tuple(sorted(self.candidate_hypothesis_ids))
        if not candidate_ids:
            raise ValueError("a catalog must expose at least one nuisance state")
        if any(not item for item in candidate_ids):
            raise ValueError("candidate hypothesis IDs must not be empty")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate hypothesis IDs must be unique within a catalog")
        object.__setattr__(self, "candidate_hypothesis_ids", candidate_ids)
        _nonempty(self.evaluated_hypothesis_id, "evaluated hypothesis ID")
        if self.evaluated_hypothesis_id not in candidate_ids:
            raise ValueError("evaluated hypothesis must belong to the catalog state group")
        if (
            self.selected_hypothesis_id is not None
            and self.selected_hypothesis_id != self.evaluated_hypothesis_id
        ):
            raise ValueError("selected hypothesis must equal the evaluated catalog state")

    @property
    def selected(self) -> bool:
        return self.selected_hypothesis_id is not None


@dataclass(frozen=True, slots=True)
class GroupedSatelliteAssociationResult:
    """Exact joint result plus explicit bounded-state-search accounting."""

    association: JointSatelliteAssociationResult
    catalog_states: tuple[CatalogNuisanceStateDecision, ...]
    candidate_state_combination_count: int
    evaluated_state_combination_count: int
    maximum_state_combination_count: int
    candidate_inventory_complete: bool
    supplied_state_space_exhausted: bool
    algorithm: str
    exact: bool

    def __post_init__(self) -> None:
        states = tuple(sorted(self.catalog_states, key=lambda item: item.catalog_number))
        object.__setattr__(self, "catalog_states", states)
        catalog_numbers = tuple(item.catalog_number for item in states)
        if len(set(catalog_numbers)) != len(catalog_numbers):
            raise ValueError("catalog-state decisions must have unique catalog numbers")
        if self.candidate_state_combination_count < 1:
            raise ValueError("candidate state-combination count must be positive")
        if self.evaluated_state_combination_count < 1:
            raise ValueError("evaluated state-combination count must be positive")
        if self.maximum_state_combination_count < 1:
            raise ValueError("maximum state-combination count must be positive")
        if self.candidate_state_combination_count > self.maximum_state_combination_count:
            raise ValueError("candidate state combinations cannot exceed the declared maximum")
        if self.evaluated_state_combination_count > self.candidate_state_combination_count:
            raise ValueError("evaluated state combinations cannot exceed candidate combinations")
        if self.supplied_state_space_exhausted != (
            self.evaluated_state_combination_count == self.candidate_state_combination_count
        ):
            raise ValueError("state-space exhaustion metadata disagrees with combination counts")
        _nonempty(self.algorithm, "grouped association algorithm")

        association_by_catalog = {item.catalog_number: item for item in self.association.satellites}
        if tuple(sorted(association_by_catalog)) != catalog_numbers:
            raise ValueError("catalog-state metadata disagrees with association catalogs")
        for state in states:
            decision = association_by_catalog[state.catalog_number]
            if decision.hypothesis_id != state.evaluated_hypothesis_id:
                raise ValueError("evaluated state metadata disagrees with association result")
            expected_selected = decision.hypothesis_id if decision.selected else None
            if state.selected_hypothesis_id != expected_selected:
                raise ValueError("selected state metadata disagrees with association result")

        proven_exact = (
            self.association.exact
            and self.candidate_inventory_complete
            and self.supplied_state_space_exhausted
            and self.evaluated_state_combination_count == self.candidate_state_combination_count
        )
        if self.exact != proven_exact:
            raise ValueError("grouped exactness metadata disagrees with its evidence")

    @property
    def selected_hypothesis_ids(self) -> tuple[str, ...]:
        return tuple(
            item.selected_hypothesis_id
            for item in self.catalog_states
            if item.selected_hypothesis_id is not None
        )


def _canonical_state_groups(
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
) -> tuple[tuple[SingleSatelliteHypothesis, ...], ...]:
    if not hypotheses:
        raise ValueError("grouped satellite association needs at least one hypothesis")
    hypothesis_ids = tuple(item.hypothesis_id for item in hypotheses)
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise ValueError("grouped satellite hypothesis IDs must be globally unique")

    by_catalog: dict[int, list[SingleSatelliteHypothesis]] = {}
    for hypothesis in hypotheses:
        by_catalog.setdefault(hypothesis.catalog_number, []).append(hypothesis)
    catalog_count = len(by_catalog)
    if not MINIMUM_EXACT_HYPOTHESES <= catalog_count <= MAXIMUM_EXACT_HYPOTHESES:
        raise ValueError("the bounded grouped decoder requires two or three catalogs")
    return tuple(
        tuple(
            sorted(
                by_catalog[catalog_number],
                key=lambda item: (
                    item.hypothesis_id,
                    item.object_name,
                    item.delay_s,
                    item.cfo_offset_hz,
                ),
            )
        )
        for catalog_number in sorted(by_catalog)
    )


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _association_tie_key(
    association: JointSatelliteAssociationResult,
    combination: tuple[SingleSatelliteHypothesis, ...],
) -> tuple[object, ...]:
    """Apply a stable policy after objective minimization across state grids."""

    selected = tuple(item for item in association.satellites if item.selected)
    selected_catalog_key = tuple(not item.selected for item in association.satellites)
    selected_state_ids = tuple(item.hypothesis_id for item in selected)
    activity = tuple(item.activity_by_cell for item in association.satellites)
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
        selected_catalog_key,
        selected_state_ids,
        activity,
        len(assignments),
        assignments,
        tuple(item.hypothesis_id for item in combination),
    )


def decode_grouped_nuisance_states(
    problem: SatelliteActivityProblem,
    hypotheses: tuple[SingleSatelliteHypothesis, ...],
    *,
    maximum_state_combinations: int = DEFAULT_MAXIMUM_STATE_COMBINATIONS,
) -> GroupedSatelliteAssociationResult:
    """Exactly decode a bounded grid of per-catalog delay/CFO states.

    The input is flat for convenient construction; catalog number defines the
    physical grouping.  Every supplied combination is evaluated, including
    combinations whose fixed-state decoder selects no satellite.  The returned
    result is exact only over this supplied discrete nuisance-state grid.
    """

    limit = _positive_integer(maximum_state_combinations, "maximum state combinations")
    groups = _canonical_state_groups(tuple(hypotheses))
    combination_count = math.prod(len(group) for group in groups)
    if combination_count > limit:
        raise ValueError(
            "grouped nuisance-state search requires "
            f"{combination_count} combinations, exceeding the explicit limit {limit}"
        )
    if problem.truncated_observation_count:
        raise ValueError("the bounded grouped decoder requires an untruncated candidate inventory")

    winner: tuple[tuple[object, ...], JointSatelliteAssociationResult] | None = None
    evaluated_count = 0
    for combination in itertools.product(*groups):
        fixed = tuple(combination)
        candidate = decode_joint_fixed_hypotheses(problem, fixed)
        candidate_key = _association_tie_key(candidate, fixed)
        if winner is None or candidate_key < winner[0]:
            winner = (candidate_key, candidate)
        evaluated_count += 1
    if winner is None:
        raise RuntimeError("grouped nuisance-state search produced no combinations")
    _winning_key, association = winner

    state_ids_by_catalog = {
        group[0].catalog_number: tuple(item.hypothesis_id for item in group) for group in groups
    }
    decisions = tuple(
        CatalogNuisanceStateDecision(
            catalog_number=decision.catalog_number,
            candidate_hypothesis_ids=state_ids_by_catalog[decision.catalog_number],
            evaluated_hypothesis_id=decision.hypothesis_id,
            selected_hypothesis_id=(decision.hypothesis_id if decision.selected else None),
        )
        for decision in association.satellites
    )
    return GroupedSatelliteAssociationResult(
        association=association,
        catalog_states=decisions,
        candidate_state_combination_count=combination_count,
        evaluated_state_combination_count=evaluated_count,
        maximum_state_combination_count=limit,
        candidate_inventory_complete=True,
        supplied_state_space_exhausted=True,
        algorithm="bounded-exhaustive-grouped-nuisance-semimarkov-v1",
        exact=True,
    )
