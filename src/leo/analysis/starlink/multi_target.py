"""Deterministic sparse minimum-cost path cover for canonical CFO observations."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_target import (
    AssociationEdgeDecisionV1,
    AssociationEdgeStatus,
    DuplicateBranchDecisionV1,
    DuplicateBranchStatus,
    MultiTargetAssociationConfigV1,
    MultiTargetAssociationV1,
    MultiTargetBranchV1,
    MultiTargetObservationV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus


@dataclass(slots=True)
class _FlowEdge:
    destination: int
    reverse_index: int
    capacity: int
    cost: float
    association_key: tuple[Sha256Digest, Sha256Digest] | None = None


_ProvisionalBranch = tuple[
    Sha256Digest,
    tuple[Sha256Digest, ...],
    tuple[MultiTargetObservationV1, ...],
    float,
]


def default_multi_target_association_config() -> MultiTargetAssociationConfigV1:
    """Return the reviewed deterministic association gates and explicit penalties."""

    return MultiTargetAssociationConfigV1(
        gate_id="cfo-multi-target-association-v1",
        expected_probe_interval_s=0.05,
        maximum_gap_s=1.1,
        maximum_frequency_error_hz=8_000.0,
        maximum_slope_error_hz_per_s=20_000.0,
        maximum_acceleration_error_hz_per_s2=40_000.0,
        frequency_weight=1.0,
        slope_weight=0.75,
        acceleration_weight=0.5,
        birth_penalty=2.0,
        death_penalty=2.0,
        missed_probe_penalty=0.15,
        duplicate_frequency_gate_hz=2_500.0,
        duplicate_slope_gate_hz_per_s=5_000.0,
        maximum_observations=9_600,
        maximum_edge_decisions=65_536,
        maximum_branches=64,
        maximum_assignment_iterations=12,
    )


def associate_multi_target_observations(
    observations: tuple[MultiTargetObservationV1, ...],
    *,
    config: MultiTargetAssociationConfigV1,
) -> MultiTargetAssociationV1:
    """Associate observations globally, preserving births, deaths and crossings."""

    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("multi-target observation IDs must be unique")
    ordered_source = tuple(sorted(observations, key=_observation_key))
    retained = ordered_source[: config.maximum_observations]
    observation_truncation = len(ordered_source) - len(retained)
    working = retained
    previous_signature: tuple[tuple[Sha256Digest, ...], ...] | None = None
    converged = not working
    iterations = 1
    retained_decisions: tuple[AssociationEdgeDecisionV1, ...] = ()
    selected_keys: frozenset[tuple[Sha256Digest, Sha256Digest]] = frozenset()
    raw_paths: tuple[tuple[Sha256Digest, ...], ...] = ()
    source_edge_count = 0
    edge_truncation = 0
    for iteration in range(1, config.maximum_assignment_iterations + 1):
        iterations = iteration
        decisions = _edge_decisions(working, config)
        source_edge_count = len(decisions)
        retained_decisions = decisions[: config.maximum_edge_decisions]
        edge_truncation = source_edge_count - len(retained_decisions)
        selected_keys = _minimum_cost_path_cover(working, retained_decisions, config)
        raw_paths = _paths(working, selected_keys)
        signature = tuple(sorted(raw_paths))
        if previous_signature == signature or not working:
            converged = True
            break
        previous_signature = signature
        working = _refit_observation_hints(working, raw_paths)
    selected_decisions = tuple(
        decision.model_copy(
            update={
                "selected": (
                    decision.source_observation_id,
                    decision.destination_observation_id,
                )
                in selected_keys
            }
        )
        for decision in retained_decisions
    )
    source_branch_count = len(raw_paths)
    retained_paths = raw_paths[: config.maximum_branches]
    branch_truncation = source_branch_count - len(retained_paths)
    branches, duplicate_decisions = _classify_duplicates(retained_paths, working, config)
    incomplete = bool(observation_truncation or edge_truncation or branch_truncation)
    status = (
        StandardScientificStatus.INSUFFICIENT_DATA
        if not converged
        else StandardScientificStatus.PARTIAL
        if incomplete
        else StandardScientificStatus.COMPLETE
        if branches
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "global association did not converge within its declared iteration bound"
        if status is StandardScientificStatus.INSUFFICIENT_DATA
        else "bounded global association truncated declared observations, edges, or branches"
        if status is StandardScientificStatus.PARTIAL
        else "global minimum-cost path cover converged with explicit branch decisions"
        if status is StandardScientificStatus.COMPLETE
        else "complete global association received no canonical observations"
    )
    document = {
        "config_digest": config.digest,
        "source_observation_count": len(ordered_source),
        "returned_observation_count": len(retained),
        "truncated_observation_count": observation_truncation,
        "source_edge_count": source_edge_count,
        "returned_edge_count": len(selected_decisions),
        "truncated_edge_count": edge_truncation,
        "source_branch_count": source_branch_count,
        "returned_branch_count": len(branches),
        "truncated_branch_count": branch_truncation,
        "assignment_iterations": iterations,
        "converged": converged,
        "observations": [item.model_dump(mode="json") for item in working],
        "edge_decisions": [item.model_dump(mode="json") for item in selected_decisions],
        "branches": [item.model_dump(mode="json") for item in branches],
        "duplicate_decisions": [item.model_dump(mode="json") for item in duplicate_decisions],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 1,
            "algorithm_version": "global-min-cost-path-cover-v1",
            **document,
        }
    )
    return MultiTargetAssociationV1.model_validate(document)


def _observation_key(item: MultiTargetObservationV1) -> tuple[float, str]:
    return item.time_s, item.observation_id


def _refit_observation_hints(
    observations: tuple[MultiTargetObservationV1, ...],
    paths: tuple[tuple[Sha256Digest, ...], ...],
) -> tuple[MultiTargetObservationV1, ...]:
    """Refit branch-local quadratic kinematics for the next global assignment."""

    by_id = {item.observation_id: item for item in observations}
    updates: dict[Sha256Digest, tuple[float, float]] = {}
    for path in paths:
        items = tuple(by_id[item] for item in path)
        if len(items) < 2:
            continue
        times = np.asarray([item.time_s for item in items], dtype=float)
        values = np.asarray([item.canonical_cfo_hz for item in items], dtype=float)
        reference_time = float(times[0])
        relative = times - reference_time
        degree = 2 if len(items) >= 3 else 1
        coefficients = np.polyfit(relative, values, degree)
        first_derivative = np.polyder(coefficients, 1)
        second_derivative = np.polyder(coefficients, 2)
        for item, relative_time in zip(items, relative, strict=True):
            updates[item.observation_id] = (
                float(np.polyval(first_derivative, relative_time)),
                float(np.polyval(second_derivative, relative_time)) if degree == 2 else 0.0,
            )
    return tuple(
        item.model_copy(
            update={
                "slope_hint_hz_per_s": updates.get(
                    item.observation_id,
                    (item.slope_hint_hz_per_s, item.acceleration_hint_hz_per_s2),
                )[0],
                "acceleration_hint_hz_per_s2": updates.get(
                    item.observation_id,
                    (item.slope_hint_hz_per_s, item.acceleration_hint_hz_per_s2),
                )[1],
            }
        )
        for item in observations
    )


def _edge_decisions(
    observations: tuple[MultiTargetObservationV1, ...],
    config: MultiTargetAssociationConfigV1,
) -> tuple[AssociationEdgeDecisionV1, ...]:
    result: list[AssociationEdgeDecisionV1] = []
    for source_index, source in enumerate(observations):
        for destination in observations[source_index + 1 :]:
            dt = destination.time_s - source.time_s
            if dt <= 0:
                continue
            if destination.component_id != source.component_id:
                continue
            if dt > config.maximum_gap_s:
                break
            predicted = (
                source.canonical_cfo_hz
                + source.slope_hint_hz_per_s * dt
                + 0.5 * source.acceleration_hint_hz_per_s2 * dt * dt
            )
            frequency_error = abs(destination.canonical_cfo_hz - predicted)
            slope_error = abs(destination.slope_hint_hz_per_s - source.slope_hint_hz_per_s)
            acceleration_error = abs(
                destination.acceleration_hint_hz_per_s2 - source.acceleration_hint_hz_per_s2
            )
            intervals = max(1, int(round(dt / config.expected_probe_interval_s)))
            missed = max(0, intervals - 1)
            cost = (
                config.frequency_weight * frequency_error / config.maximum_frequency_error_hz
                + config.slope_weight * slope_error / config.maximum_slope_error_hz_per_s
                + config.acceleration_weight
                * acceleration_error
                / config.maximum_acceleration_error_hz_per_s2
                + missed * config.missed_probe_penalty
            )
            if frequency_error > config.maximum_frequency_error_hz:
                status = AssociationEdgeStatus.REJECTED_FREQUENCY
                reason = "frequency residual exceeds the frozen association gate"
            elif slope_error > config.maximum_slope_error_hz_per_s:
                status = AssociationEdgeStatus.REJECTED_SLOPE
                reason = "slope residual exceeds the frozen association gate"
            elif acceleration_error > config.maximum_acceleration_error_hz_per_s2:
                status = AssociationEdgeStatus.REJECTED_ACCELERATION
                reason = "acceleration residual exceeds the frozen association gate"
            else:
                status = AssociationEdgeStatus.ACCEPTED
                reason = "edge satisfies gap, frequency, slope, and acceleration gates"
            result.append(
                AssociationEdgeDecisionV1(
                    source_observation_id=source.observation_id,
                    destination_observation_id=destination.observation_id,
                    status=status,
                    delta_time_s=dt,
                    missed_probe_count=missed,
                    frequency_error_hz=frequency_error,
                    slope_error_hz_per_s=slope_error,
                    acceleration_error_hz_per_s2=acceleration_error,
                    link_cost=cost,
                    selected=False,
                    reason=reason,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda item: (item.source_observation_id, item.destination_observation_id),
        )
    )


def _add_edge(
    graph: list[list[_FlowEdge]],
    source: int,
    destination: int,
    capacity: int,
    cost: float,
    key: tuple[Sha256Digest, Sha256Digest] | None = None,
) -> _FlowEdge:
    forward = _FlowEdge(destination, len(graph[destination]), capacity, cost, key)
    reverse = _FlowEdge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[destination].append(reverse)
    return forward


def _minimum_cost_path_cover(
    observations: tuple[MultiTargetObservationV1, ...],
    decisions: tuple[AssociationEdgeDecisionV1, ...],
    config: MultiTargetAssociationConfigV1,
) -> frozenset[tuple[Sha256Digest, Sha256Digest]]:
    """Solve optional sparse bipartite matching by successive shortest paths."""

    count = len(observations)
    if not count:
        return frozenset()
    index_by_id = {item.observation_id: index for index, item in enumerate(observations)}
    source_node = 0
    left_start = 1
    right_start = left_start + count
    sink_node = right_start + count
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink_node + 1)]
    for index in range(count):
        _add_edge(graph, source_node, left_start + index, 1, 0.0)
        _add_edge(graph, right_start + index, sink_node, 1, 0.0)
    tracked: list[_FlowEdge] = []
    for decision in decisions:
        if decision.status is not AssociationEdgeStatus.ACCEPTED:
            continue
        adjusted = decision.link_cost - config.birth_penalty - config.death_penalty
        tracked.append(
            _add_edge(
                graph,
                left_start + index_by_id[decision.source_observation_id],
                right_start + index_by_id[decision.destination_observation_id],
                1,
                adjusted,
                (decision.source_observation_id, decision.destination_observation_id),
            )
        )

    node_count = len(graph)
    potential = [0.0] * node_count
    for right_index in range(count):
        incoming = [
            edge.cost
            for left_index in range(count)
            for edge in graph[left_start + left_index]
            if edge.destination == right_start + right_index and edge.capacity
        ]
        potential[right_start + right_index] = min(incoming, default=0.0)
    potential[sink_node] = min(potential[right_start : right_start + count], default=0.0)

    while True:
        distance = [math.inf] * node_count
        predecessor: list[tuple[int, int] | None] = [None] * node_count
        distance[source_node] = 0.0
        pending: list[tuple[float, int]] = [(0.0, source_node)]
        while pending:
            current_distance, node = heapq.heappop(pending)
            if current_distance != distance[node]:
                continue
            for edge_index, edge in enumerate(graph[node]):
                if not edge.capacity:
                    continue
                reduced = edge.cost + potential[node] - potential[edge.destination]
                if reduced < 0 and reduced > -1e-12:
                    reduced = 0.0
                candidate = current_distance + reduced
                prior = predecessor[edge.destination]
                tie = prior is None or (node, edge_index) < prior
                if candidate < distance[edge.destination] - 1e-12 or (
                    abs(candidate - distance[edge.destination]) <= 1e-12 and tie
                ):
                    distance[edge.destination] = candidate
                    predecessor[edge.destination] = (node, edge_index)
                    heapq.heappush(pending, (candidate, edge.destination))
        if not math.isfinite(distance[sink_node]):
            break
        actual_cost = distance[sink_node] - potential[source_node] + potential[sink_node]
        if actual_cost >= -1e-12:
            break
        for node, value in enumerate(distance):
            if math.isfinite(value):
                potential[node] += value
        if not _augment_zero_reduced_blocking_flow(
            graph,
            potential,
            source_node=source_node,
            sink_node=sink_node,
        ):
            raise RuntimeError("minimum-cost association admissible graph has no augmenting path")
    return frozenset(
        edge.association_key
        for edge in tracked
        if edge.capacity == 0 and edge.association_key is not None
    )


def _augment_zero_reduced_blocking_flow(
    graph: list[list[_FlowEdge]],
    potential: list[float],
    *,
    source_node: int,
    sink_node: int,
) -> int:
    """Augment every current shortest path instead of rerunning Dijkstra per edge.

    Successive-shortest-path optimality gives every residual edge a nonnegative
    reduced cost after the potential update.  All zero-reduced-cost source/sink
    paths therefore have the same negative marginal cost and may be sent as one
    deterministic blocking flow.  This preserves the exact min-cost objective
    while avoiding one global heap traversal for every selected trajectory link.
    """

    augmented = 0
    while True:
        levels = [-1] * len(graph)
        levels[source_node] = 0
        pending = [source_node]
        for node in pending:
            for edge in graph[node]:
                if (
                    edge.capacity
                    and levels[edge.destination] < 0
                    and _is_zero_reduced(edge, node, potential)
                ):
                    levels[edge.destination] = levels[node] + 1
                    pending.append(edge.destination)
        if levels[sink_node] < 0:
            return augmented

        cursor = [0] * len(graph)
        while True:
            node = source_node
            path: list[tuple[int, int]] = []
            while node != sink_node:
                edges = graph[node]
                while cursor[node] < len(edges):
                    edge = edges[cursor[node]]
                    if (
                        edge.capacity
                        and levels[edge.destination] == levels[node] + 1
                        and _is_zero_reduced(edge, node, potential)
                    ):
                        break
                    cursor[node] += 1
                if cursor[node] < len(edges):
                    edge_index = cursor[node]
                    path.append((node, edge_index))
                    node = edges[edge_index].destination
                    continue
                levels[node] = -1
                if not path:
                    break
                parent, edge_index = path.pop()
                cursor[parent] = edge_index + 1
                node = parent
            if node != sink_node:
                break
            for parent, edge_index in path:
                edge = graph[parent][edge_index]
                edge.capacity -= 1
                graph[edge.destination][edge.reverse_index].capacity += 1
            augmented += 1


def _is_zero_reduced(edge: _FlowEdge, source: int, potential: list[float]) -> bool:
    reduced = edge.cost + potential[source] - potential[edge.destination]
    return abs(reduced) <= 1e-10


def _paths(
    observations: tuple[MultiTargetObservationV1, ...],
    selected: frozenset[tuple[Sha256Digest, Sha256Digest]],
) -> tuple[tuple[Sha256Digest, ...], ...]:
    outgoing = {source: destination for source, destination in selected}
    incoming = {destination: source for source, destination in selected}
    roots = sorted(
        item.observation_id for item in observations if item.observation_id not in incoming
    )
    paths = []
    visited: set[Sha256Digest] = set()
    for root in roots:
        path = [root]
        visited.add(root)
        while path[-1] in outgoing:
            destination = outgoing[path[-1]]
            if destination in visited:
                raise ValueError("association path cover contains a cycle")
            path.append(destination)
            visited.add(destination)
        paths.append(tuple(path))
    if len(visited) != len(observations):
        raise ValueError("association path cover omitted observations")
    return tuple(sorted(paths, key=lambda item: (item[0], item)))


def _classify_duplicates(
    paths: tuple[tuple[Sha256Digest, ...], ...],
    observations: tuple[MultiTargetObservationV1, ...],
    config: MultiTargetAssociationConfigV1,
) -> tuple[tuple[MultiTargetBranchV1, ...], tuple[DuplicateBranchDecisionV1, ...]]:
    by_id = {item.observation_id: item for item in observations}
    provisional = []
    for path in paths:
        items = tuple(by_id[item] for item in path)
        component_ids = {item.component_id for item in items}
        if len(component_ids) != 1:
            raise ValueError("association branch crosses alias components")
        component_id = next(iter(component_ids))
        branch_id = canonical_digest({"component_id": component_id, "observation_ids": path})
        selected_cost = sum(
            _link_cost(left, right, config) for left, right in zip(items, items[1:], strict=False)
        )
        provisional.append((branch_id, path, items, selected_cost))
    duplicate_of: dict[Sha256Digest, Sha256Digest] = {}
    decisions: list[DuplicateBranchDecisionV1] = []
    for left_index, left in enumerate(provisional):
        for right in provisional[left_index + 1 :]:
            left_id, right_id = sorted((left[0], right[0]))
            left_item = left if left[0] == left_id else right
            right_item = right if right[0] == right_id else left
            decision = _duplicate_decision(left_item, right_item, config)
            decisions.append(decision)
            if decision.retained_branch_id is not None:
                removed = right_id if decision.retained_branch_id == left_id else left_id
                duplicate_of.setdefault(removed, decision.retained_branch_id)
    branches = []
    for branch_id, path, items, selected_cost in provisional:
        canonical_duplicate = duplicate_of.get(branch_id)
        branches.append(
            MultiTargetBranchV1(
                branch_id=branch_id,
                component_id=component_id,
                observation_ids=path,
                hypothesis_set_ids=tuple(item.hypothesis_set_id for item in items),
                start_s=items[0].time_s,
                end_s=items[-1].time_s,
                birth_penalty=config.birth_penalty,
                death_penalty=config.death_penalty,
                selected_link_cost=selected_cost,
                retained=canonical_duplicate is None,
                duplicate_of_branch_id=canonical_duplicate,
            )
        )
    return (
        tuple(sorted(branches, key=lambda item: item.branch_id)),
        tuple(sorted(decisions, key=lambda item: (item.left_branch_id, item.right_branch_id))),
    )


def _link_cost(
    source: MultiTargetObservationV1,
    destination: MultiTargetObservationV1,
    config: MultiTargetAssociationConfigV1,
) -> float:
    dt = destination.time_s - source.time_s
    predicted = (
        source.canonical_cfo_hz
        + source.slope_hint_hz_per_s * dt
        + 0.5 * source.acceleration_hint_hz_per_s2 * dt * dt
    )
    intervals = max(1, int(round(dt / config.expected_probe_interval_s)))
    return (
        config.frequency_weight
        * abs(destination.canonical_cfo_hz - predicted)
        / config.maximum_frequency_error_hz
        + config.slope_weight
        * abs(destination.slope_hint_hz_per_s - source.slope_hint_hz_per_s)
        / config.maximum_slope_error_hz_per_s
        + config.acceleration_weight
        * abs(destination.acceleration_hint_hz_per_s2 - source.acceleration_hint_hz_per_s2)
        / config.maximum_acceleration_error_hz_per_s2
        + max(0, intervals - 1) * config.missed_probe_penalty
    )


def _duplicate_decision(
    left: _ProvisionalBranch,
    right: _ProvisionalBranch,
    config: MultiTargetAssociationConfigV1,
) -> DuplicateBranchDecisionV1:
    left_id, _, left_items, _ = left
    right_id, _, right_items, _ = right
    overlap_start = max(left_items[0].time_s, right_items[0].time_s)
    overlap_end = min(left_items[-1].time_s, right_items[-1].time_s)
    overlap = max(0.0, overlap_end - overlap_start)
    left_hypotheses = tuple(item.hypothesis_set_id for item in left_items)
    right_hypotheses = tuple(item.hypothesis_set_id for item in right_items)
    same_support = left_hypotheses == right_hypotheses
    if not overlap or not same_support:
        return DuplicateBranchDecisionV1(
            left_branch_id=left_id,
            right_branch_id=right_id,
            status=DuplicateBranchStatus.RETAINED_DISTINCT_SUPPORT,
            overlap_s=overlap,
            maximum_frequency_residual_hz=None,
            maximum_slope_residual_hz_per_s=None,
            retained_branch_id=None,
            reason="branches lack identical alias-hypothesis support",
        )
    times = np.linspace(overlap_start, overlap_end, 128)
    left_coefficients = np.polyfit(
        [item.time_s for item in left_items], [item.canonical_cfo_hz for item in left_items], 1
    )
    right_coefficients = np.polyfit(
        [item.time_s for item in right_items], [item.canonical_cfo_hz for item in right_items], 1
    )
    frequency_residual = float(
        np.max(np.abs(np.polyval(left_coefficients, times) - np.polyval(right_coefficients, times)))
    )
    slope_residual = abs(float(left_coefficients[0] - right_coefficients[0]))
    equivalent = (
        frequency_residual <= config.duplicate_frequency_gate_hz
        and slope_residual <= config.duplicate_slope_gate_hz_per_s
    )
    retained = min(left_id, right_id) if equivalent else None
    return DuplicateBranchDecisionV1(
        left_branch_id=left_id,
        right_branch_id=right_id,
        status=(
            DuplicateBranchStatus.COLLAPSED_ALIAS_HYPOTHESIS
            if equivalent
            else DuplicateBranchStatus.RETAINED_MODEL_RESIDUAL
        ),
        overlap_s=overlap,
        maximum_frequency_residual_hz=frequency_residual,
        maximum_slope_residual_hz_per_s=slope_residual,
        retained_branch_id=retained,
        reason=(
            "equivalent fitted values share the same alias-hypothesis support"
            if equivalent
            else "fitted values exceed the duplicate-collapse gate"
        ),
    )
