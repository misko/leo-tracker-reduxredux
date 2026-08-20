"""Pure bounded CFO de-aliasing, multi-branch association, and final selection."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

import numpy as np

from leo.analysis.starlink.multi_target import associate_multi_target_observations
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotProbeDetection
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryObservation,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    replay_pilot_trajectories,
)
from leo.contracts.cfo_dealias import (
    AliasPairStatus,
    CanonicalBranchV1,
    CanonicalObservationV1,
    CanonicalPolynomialV1,
    CfoAliasMapV1,
    CfoAliasMemberV1,
    CfoAliasPairDecisionV1,
    CfoDealiasConfigV1,
    CfoLiftReplayRowV1,
    CfoLiftReplayV1,
    DealiasedTrajectoryBankV1,
    DealiasedTrajectoryBankV2,
    FinalTrajectoryBankV1,
    FinalTrajectoryV1,
    Glrt64FinalTrajectoryTableV1,
    LiftReplayStatus,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_target import (
    MultiTargetAssociationConfigV1,
    MultiTargetObservationV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.contracts.states import StarlinkEdge
from leo.pipeline import IqReader


@dataclass(slots=True)
class _MutableBranch:
    component_id: Sha256Digest
    observations: list[CanonicalObservationV1]


@dataclass(frozen=True, slots=True)
class _ObservedLiftCandidate:
    branch_id: Sha256Digest
    model_id: Sha256Digest
    alias_index: int
    replay_trajectory_id: Sha256Digest
    trajectory: PolynomialTrajectory


def default_cfo_dealias_config() -> CfoDealiasConfigV1:
    """Return the explicit reviewed Standard/Research shared configuration."""

    return CfoDealiasConfigV1(
        minimum_overlap_s=0.25,
        comparison_point_count=128,
        maximum_alias_residual_hz=2_500.0,
        maximum_raw_representatives=64,
        maximum_pair_comparisons=2_016,
        maximum_alias_components=64,
        maximum_observations_per_component=9_600,
        maximum_observed_lifts_per_component=5,
        maximum_final_lifts_per_component=3,
        maximum_final_trajectories=64,
        polynomial_degrees=(1, 2, 3),
        continuity_gap_s=1.1,
        association_frequency_gate_hz=8_000.0,
        association_slope_gate_hz_per_s=20_000.0,
        association_acceleration_gate_hz_per_s2=40_000.0,
        maximum_branches_per_component=16,
        maximum_assignment_iterations=12,
        replay_gate_version="glrt64-margin-control-v1",
    )


def centered_alias_residue_hz(value_hz: float, config: CfoDealiasConfigV1) -> float:
    """Map CFO into the exact declared half-open ambiguity interval."""

    if not math.isfinite(value_hz):
        raise ValueError("CFO residue input must be finite")
    spacing = config.alias_spacing_hz
    residue = (value_hz + spacing / 2.0) % spacing - spacing / 2.0
    if residue >= spacing / 2.0:
        residue -= spacing
    return float(residue)


def build_cfo_alias_map(
    raw_bank: TrajectoryBankResult,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    *,
    pilot_scan_digest: Sha256Digest,
    raw_bank_digest: Sha256Digest,
    config: CfoDealiasConfigV1,
) -> CfoAliasMapV1:
    """Build an auditable potential-aware alias graph from raw GLRT64 representatives."""

    del raw_bank
    source = tuple(
        sorted(
            (
                trajectory
                for _, trajectory in representatives
                if trajectory.method is PilotMethod.GLRT64
            ),
            key=lambda item: (item.start_s, item.end_s, item.trajectory_id),
        )
    )
    if len({item.trajectory_id for item in source}) != len(source):
        raise ValueError("raw representative trajectory IDs must be unique")
    retained = source[: config.maximum_raw_representatives]
    truncated = len(source) - len(retained)
    comparisons: list[CfoAliasPairDecisionV1] = []
    accepted: list[tuple[int, int, int, CfoAliasPairDecisionV1]] = []
    for left_index, left in enumerate(retained):
        for right_index, right in enumerate(retained[left_index + 1 :], left_index + 1):
            pair = _compare_representatives(left, right, config)
            comparisons.append(pair)
            if pair.status is AliasPairStatus.ALIAS_EQUIVALENT:
                assert pair.alias_index_delta is not None
                raw_delta = (
                    pair.alias_index_delta
                    if pair.left_trajectory_id == left.trajectory_id
                    else -pair.alias_index_delta
                )
                accepted.append((left_index, right_index, raw_delta, pair))
    if len(comparisons) > config.maximum_pair_comparisons:
        raise ValueError("alias comparison inventory exceeds its configured bound")

    adjacency: list[list[tuple[int, int]]] = [[] for _ in retained]
    for left_index, right_index, delta, _ in accepted:
        adjacency[left_index].append((right_index, delta))
        adjacency[right_index].append((left_index, -delta))
    potentials: list[int | None] = [None] * len(retained)
    raw_components: list[tuple[int, ...]] = []
    for root in range(len(retained)):
        if potentials[root] is not None:
            continue
        potentials[root] = 0
        pending = [root]
        component_members: list[int] = []
        while pending:
            index = pending.pop()
            component_members.append(index)
            current_potential = potentials[index]
            assert current_potential is not None
            for other, delta in sorted(adjacency[index]):
                expected = current_potential + delta
                if potentials[other] is None:
                    potentials[other] = expected
                    pending.append(other)
                elif potentials[other] != expected:
                    raise ValueError("CFO alias graph contains a contradictory finite cycle")
        raw_components.append(tuple(sorted(component_members)))
    if len(raw_components) > config.maximum_alias_components:
        raise ValueError("alias component inventory exceeds its configured bound")

    component_by_index: dict[int, Sha256Digest] = {}
    for indices in raw_components:
        trajectory_ids = tuple(sorted(retained[index].trajectory_id for index in indices))
        member_set = set(indices)
        edges = tuple(
            pair.model_dump(mode="json")
            for left, right, _, pair in accepted
            if left in member_set and right in member_set
        )
        component_id = canonical_digest({"trajectory_ids": trajectory_ids, "edges": edges})
        for index in indices:
            component_by_index[index] = component_id
    alias_members = tuple(
        sorted(
            (
                CfoAliasMemberV1(
                    trajectory_id=trajectory.trajectory_id,
                    component_id=component_by_index[index],
                    relative_alias_index=int(potentials[index] or 0),
                )
                for index, trajectory in enumerate(retained)
            ),
            key=lambda item: item.trajectory_id,
        )
    )
    document = {
        "config_digest": config.digest,
        "pilot_scan_digest": pilot_scan_digest,
        "raw_trajectory_bank_digest": raw_bank_digest,
        "source_representative_count": len(source),
        "returned_representative_count": len(retained),
        "truncated_representative_count": truncated,
        "component_count": len(raw_components),
        "members": [item.model_dump(mode="json") for item in alias_members],
        "pair_decisions": [
            item.model_dump(mode="json")
            for item in sorted(
                comparisons, key=lambda value: (value.left_trajectory_id, value.right_trajectory_id)
            )
        ],
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 1,
            "algorithm_version": "cfo-alias-map-v1",
            "alias_spacing_numerator_hz": 2_500_000,
            "alias_spacing_denominator": 11,
            **document,
        }
    )
    return CfoAliasMapV1.model_validate(document)


def fit_dealiased_trajectories(
    raw_observations: tuple[TrajectoryObservation, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    alias_map: CfoAliasMapV1,
    *,
    raw_bank_digest: Sha256Digest,
    config: CfoDealiasConfigV1,
    association_config: MultiTargetAssociationConfigV1,
) -> DealiasedTrajectoryBankV2:
    """Canonicalize raw observations, associate simultaneous branches, and fit 1/2/3."""

    if alias_map.config_digest != config.digest:
        raise ValueError("alias map configuration disagrees with de-alias configuration")
    member_by_id = {item.trajectory_id: item for item in alias_map.members}
    references = tuple(
        trajectory for _, trajectory in representatives if trajectory.trajectory_id in member_by_id
    )
    canonical = _canonical_observations(raw_observations, references, member_by_id, config)
    association_observations = _association_observations(canonical, references)
    association = associate_multi_target_observations(
        association_observations,
        config=association_config,
    )
    canonical_by_id = {item.observation_id: item for item in canonical}
    retained = tuple(canonical_by_id[item.observation_id] for item in association.observations)
    source_observation_count = association.source_observation_count
    observation_truncation = association.truncated_observation_count
    mutable = [
        _MutableBranch(
            branch.component_id,
            [canonical_by_id[item] for item in branch.observation_ids],
        )
        for branch in association.branches
        if branch.retained and association.converged
    ]
    source_branch_count = len(mutable) + association.truncated_branch_count
    mutable = sorted(
        mutable,
        key=lambda item: (
            item.observations[0].time_s,
            item.observations[-1].time_s,
            tuple(value.observation_id for value in item.observations),
        ),
    )
    branch_truncation = association.truncated_branch_count + max(
        0, len(mutable) - config.maximum_final_trajectories
    )
    branches = tuple(
        branch
        for item in mutable[: config.maximum_final_trajectories]
        if (branch := _fit_branch(item, config)) is not None
    )
    unfit = min(len(mutable), config.maximum_final_trajectories) - len(branches)
    branch_truncation += unfit
    status = (
        StandardScientificStatus.INSUFFICIENT_DATA
        if association.status is StandardScientificStatus.INSUFFICIENT_DATA
        else StandardScientificStatus.PARTIAL
        if observation_truncation
        or branch_truncation
        or association.status is StandardScientificStatus.PARTIAL
        else StandardScientificStatus.COMPLETE
        if branches
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "multi-target association did not converge within its declared bound"
        if status is StandardScientificStatus.INSUFFICIENT_DATA
        else "bounded de-aliasing omitted observations or unresolved branches"
        if status is StandardScientificStatus.PARTIAL
        else "de-aliasing produced replayable canonical branches"
        if status is StandardScientificStatus.COMPLETE
        else "complete de-aliasing produced no supported branch"
    )
    document = {
        "config_digest": config.digest,
        "association_config_digest": association_config.digest,
        "association": association.model_dump(mode="json"),
        "alias_map_digest": alias_map.content_digest,
        "raw_trajectory_bank_digest": raw_bank_digest,
        "source_observation_count": source_observation_count,
        "returned_observation_count": len(retained),
        "truncated_observation_count": observation_truncation,
        "source_branch_count": source_branch_count,
        "returned_branch_count": len(branches),
        "truncated_branch_count": branch_truncation,
        "observations": [item.model_dump(mode="json") for item in retained],
        "branches": [item.model_dump(mode="json") for item in branches],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 2, "algorithm_version": "dealiased-trajectory-bank-v2", **document}
    )
    return DealiasedTrajectoryBankV2.model_validate(document)


def select_final_trajectories(
    canonical_bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2,
    replay: CfoLiftReplayV1,
    *,
    config: CfoDealiasConfigV1,
) -> FinalTrajectoryBankV1:
    """Publish every bounded replay-supported absolute lift deterministically."""

    if (
        canonical_bank.config_digest != config.digest
        or replay.config_digest != config.digest
        or replay.dealiased_bank_digest != canonical_bank.content_digest
    ):
        raise ValueError("final selection predecessor/configuration digest mismatch")
    branch_by_id = {item.branch_id: item for item in canonical_bank.branches}
    candidates: list[FinalTrajectoryV1] = []
    for row in replay.rows:
        if row.status is not LiftReplayStatus.SUPPORTED:
            continue
        branch = branch_by_id.get(row.branch_id)
        if branch is None:
            raise ValueError("lift replay references an undeclared canonical branch")
        model = next(
            (item for item in branch.models if item.model_id == row.canonical_model_id), None
        )
        if model is None:
            raise ValueError("lift replay references an undeclared canonical model")
        absolute = list(model.coefficients_hz)
        absolute[-1] += row.alias_index * config.alias_spacing_hz
        identity = {
            "branch_id": branch.branch_id,
            "model_id": model.model_id,
            "alias_index": row.alias_index,
        }
        candidates.append(
            FinalTrajectoryV1(
                trajectory_id=canonical_digest(identity),
                component_id=branch.component_id,
                branch_id=branch.branch_id,
                canonical_model_id=model.model_id,
                alias_index=row.alias_index,
                polynomial_degree=model.polynomial_degree,
                reference_time_s=model.reference_time_s,
                canonical_coefficients_hz=model.coefficients_hz,
                absolute_coefficients_hz=tuple(absolute),
                start_s=model.start_s,
                end_s=model.end_s,
                observation_ids=model.observation_ids,
                replayed_probe_count=row.evaluated_probe_count,
                median_margin_delta=float(row.median_margin_delta or 0.0),
                median_control_separation=float(row.median_control_separation or 0.0),
            )
        )
    candidates.sort(key=lambda item: item.trajectory_id)
    source_count = len(candidates)
    retained = tuple(candidates[: config.maximum_final_trajectories])
    truncated = source_count - len(retained)
    predecessor_incomplete = (
        canonical_bank.status is StandardScientificStatus.PARTIAL
        or replay.status is StandardScientificStatus.PARTIAL
    )
    predecessor_insufficient = (
        canonical_bank.status is StandardScientificStatus.INSUFFICIENT_DATA
        or replay.status is StandardScientificStatus.INSUFFICIENT_DATA
    )
    status = (
        StandardScientificStatus.PARTIAL
        if truncated or predecessor_incomplete
        else StandardScientificStatus.COMPLETE
        if retained
        else StandardScientificStatus.INSUFFICIENT_DATA
        if predecessor_insufficient
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "bounded final selection omitted supported trajectories"
        if status is StandardScientificStatus.PARTIAL
        else "observed-lift replay supported final trajectories"
        if status is StandardScientificStatus.COMPLETE
        else "observed-lift replay had insufficient evidence for final selection"
        if status is StandardScientificStatus.INSUFFICIENT_DATA
        else "complete observed-lift replay supported no final trajectory"
    )
    document = {
        "config_digest": config.digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "lift_replay_digest": replay.content_digest,
        "source_trajectory_count": source_count,
        "returned_trajectory_count": len(retained),
        "truncated_trajectory_count": truncated,
        "trajectories": [item.model_dump(mode="json") for item in retained],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 1, "algorithm_version": "final-trajectory-bank-v1", **document}
    )
    return FinalTrajectoryBankV1.model_validate(document)


def build_final_trajectory_table(
    bank: FinalTrajectoryBankV1,
) -> Glrt64FinalTrajectoryTableV1:
    """Project the final bank into the bounded CLI/reducer/UI table contract."""

    document = {
        "final_trajectory_bank_digest": bank.content_digest,
        "source_trajectory_count": bank.source_trajectory_count,
        "returned_trajectory_count": bank.returned_trajectory_count,
        "truncated_trajectory_count": bank.truncated_trajectory_count,
        "trajectories": [item.model_dump(mode="json") for item in bank.trajectories],
        "status": bank.status,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 1,
            "algorithm_version": "glrt64-final-trajectory-table-v1",
            "frequency_model": ("cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"),
            "coefficient_order": "highest_polynomial_power_first",
            **document,
        }
    )
    return Glrt64FinalTrajectoryTableV1.model_validate(document)


def replay_observed_cfo_lifts(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2,
    feedback_config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    config: CfoDealiasConfigV1,
) -> CfoLiftReplayV1:
    """Replay only observed absolute lifts and classify the frozen GLRT64 gate."""

    if canonical_bank.config_digest != config.digest:
        raise ValueError("canonical bank configuration disagrees with replay configuration")
    candidates, source_count = _observed_lift_candidates(canonical_bank, config)
    representatives = tuple(
        (canonical_digest({"replay_trajectory_id": item.replay_trajectory_id}), item.trajectory)
        for item in candidates
    )
    raw_rows = replay_pilot_trajectories(
        iq,
        detections,
        representatives,
        feedback_config,
        edge=edge,
    )
    return classify_observed_lift_replay(
        candidates,
        tuple(dict(item) for item in raw_rows),
        source_lift_count=source_count,
        config=config,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        canonical_bank=canonical_bank,
    )


def classify_observed_lift_replay(
    candidates: tuple[_ObservedLiftCandidate, ...],
    raw_rows: tuple[dict[str, object], ...],
    *,
    source_lift_count: int,
    config: CfoDealiasConfigV1,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    canonical_bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2,
) -> CfoLiftReplayV1:
    """Purely classify replay rows; kept separate for exact positive/control tests."""

    if config.replay_gate_version != "glrt64-margin-control-v1":
        raise ValueError("unknown CFO lift replay gate")
    rows_by_trajectory: dict[str, list[dict[str, object]]] = {}
    for row in raw_rows:
        if row.get("detector_method") != PilotMethod.GLRT64.value:
            continue
        trajectory_id = row.get("trajectory_id")
        if not isinstance(trajectory_id, str):
            raise ValueError("replay row lacks a trajectory identity")
        rows_by_trajectory.setdefault(trajectory_id, []).append(row)
    declared = {item.replay_trajectory_id for item in candidates}
    if set(rows_by_trajectory) - declared:
        raise ValueError("replay rows contain an undeclared lift trajectory")
    classified = []
    for candidate in candidates:
        values = rows_by_trajectory.get(candidate.replay_trajectory_id, [])
        deltas = tuple(_finite_row_number(item, "margin_delta") for item in values)
        corrected = tuple(_finite_row_number(item, "corrected_margin") for item in values)
        if not values:
            status = LiftReplayStatus.INSUFFICIENT_DATA
            reason = "observed lift had no replayable probes"
            median_delta = None
            median_control = None
            improved = 0
        else:
            median_delta = float(np.median(deltas))
            median_control = float(np.median(corrected))
            improved = sum(value > 0 for value in deltas)
            supported = (
                len(values) >= 3
                and improved * 2 >= len(values)
                and median_delta > 0.0
                and median_control >= 0.05
            )
            status = LiftReplayStatus.SUPPORTED if supported else LiftReplayStatus.REJECTED
            reason = (
                "same-IQ GLRT64 replay passed the margin/control gate"
                if supported
                else "same-IQ GLRT64 replay did not pass the margin/control gate"
            )
        classified.append(
            CfoLiftReplayRowV1(
                branch_id=candidate.branch_id,
                canonical_model_id=candidate.model_id,
                alias_index=candidate.alias_index,
                status=status,
                evaluated_probe_count=len(values),
                improved_probe_count=improved,
                median_margin_delta=median_delta,
                median_control_separation=median_control,
                reason=reason,
            )
        )
    return build_lift_replay_document(
        classified,
        config=config,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        canonical_bank=canonical_bank,
        source_lift_count=source_lift_count,
    )


def build_lift_replay_document(
    rows: Iterable[CfoLiftReplayRowV1],
    *,
    config: CfoDealiasConfigV1,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    canonical_bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2,
    source_lift_count: int | None = None,
) -> CfoLiftReplayV1:
    """Close bounded replay rows into their immutable scientific contract."""

    ordered = tuple(sorted(rows, key=lambda item: (item.branch_id, item.alias_index)))
    total = len(ordered) if source_lift_count is None else source_lift_count
    if total < len(ordered):
        raise ValueError("lift replay source count is smaller than returned rows")
    supported = any(item.status is LiftReplayStatus.SUPPORTED for item in ordered)
    insufficient = any(item.status is LiftReplayStatus.INSUFFICIENT_DATA for item in ordered)
    status = (
        StandardScientificStatus.PARTIAL
        if total > len(ordered) or (supported and insufficient)
        else StandardScientificStatus.COMPLETE
        if supported
        else StandardScientificStatus.INSUFFICIENT_DATA
        if insufficient
        else StandardScientificStatus.NO_RESULT
    )
    document = {
        "config_digest": config.digest,
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "source_lift_count": total,
        "returned_lift_count": len(ordered),
        "truncated_lift_count": total - len(ordered),
        "rows": [item.model_dump(mode="json") for item in ordered],
        "status": status,
        "reason": (
            "bounded replay omitted observed lifts or mixed supported and insufficient evidence"
            if status is StandardScientificStatus.PARTIAL
            else "one or more observed lifts passed replay"
            if status is StandardScientificStatus.COMPLETE
            else "observed lifts had insufficient replayable evidence"
            if status is StandardScientificStatus.INSUFFICIENT_DATA
            else "complete observed-lift replay found no supported lift"
        ),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 1, "algorithm_version": "cfo-lift-replay-v1", **document}
    )
    return CfoLiftReplayV1.model_validate(document)


def _observed_lift_candidates(
    bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2,
    config: CfoDealiasConfigV1,
) -> tuple[tuple[_ObservedLiftCandidate, ...], int]:
    result = []
    source_count = sum(len(item.observed_alias_indices) for item in bank.branches)
    for branch in bank.branches:
        model = next(item for item in branch.models if item.model_id == branch.selected_model_id)
        for alias_index in branch.observed_alias_indices[
            : config.maximum_observed_lifts_per_component
        ]:
            coefficients = list(model.coefficients_hz)
            coefficients[-1] += alias_index * config.alias_spacing_hz
            replay_id = canonical_digest(
                {
                    "branch_id": branch.branch_id,
                    "model_id": model.model_id,
                    "alias_index": alias_index,
                }
            )
            result.append(
                _ObservedLiftCandidate(
                    branch.branch_id,
                    model.model_id,
                    alias_index,
                    replay_id,
                    PolynomialTrajectory(
                        trajectory_id=replay_id,
                        method=PilotMethod.GLRT64,
                        polynomial_degree=model.polynomial_degree,
                        reference_time_s=model.reference_time_s,
                        coefficients_hz=tuple(coefficients),
                        start_s=model.start_s,
                        end_s=model.end_s,
                        observation_ids=model.observation_ids,
                        point_count=len(model.observation_ids),
                        residual_rms_hz=model.residual_rms_hz,
                        bic=model.bic,
                        high_gate=0.0,
                        em_iterations=0,
                    ),
                )
            )
    return tuple(sorted(result, key=lambda item: (item.branch_id, item.alias_index))), source_count


def _finite_row_number(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"replay row {key} is not numerical")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"replay row {key} is not finite")
    return result


def _compare_representatives(
    left: PolynomialTrajectory,
    right: PolynomialTrajectory,
    config: CfoDealiasConfigV1,
) -> CfoAliasPairDecisionV1:
    left_id, right_id = sorted((left.trajectory_id, right.trajectory_id))
    overlap_start = max(left.start_s, right.start_s)
    overlap_end = min(left.end_s, right.end_s)
    overlap = max(0.0, overlap_end - overlap_start)
    if overlap < config.minimum_overlap_s:
        return CfoAliasPairDecisionV1(
            left_trajectory_id=left_id,
            right_trajectory_id=right_id,
            status=AliasPairStatus.NOT_COMPARED_NO_OVERLAP,
            overlap_s=overlap,
            alias_index_delta=None,
            residual_rms_hz=None,
            maximum_absolute_residual_hz=None,
            reason="measured temporal overlap is below the configured minimum",
        )
    times = np.linspace(overlap_start, overlap_end, config.comparison_point_count)
    difference = right.frequency_hz(times) - left.frequency_hz(times)
    delta = int(np.rint(float(np.median(difference)) / config.alias_spacing_hz))
    if (left.trajectory_id, right.trajectory_id) != (left_id, right_id):
        delta = -delta
        difference = -difference
    residual = difference - delta * config.alias_spacing_hz
    rms = float(np.sqrt(np.mean(residual**2)))
    maximum = float(np.max(np.abs(residual)))
    accepted = maximum <= config.maximum_alias_residual_hz
    return CfoAliasPairDecisionV1(
        left_trajectory_id=left_id,
        right_trajectory_id=right_id,
        status=(
            AliasPairStatus.ALIAS_EQUIVALENT if accepted else AliasPairStatus.REJECTED_RESIDUAL
        ),
        overlap_s=overlap,
        alias_index_delta=delta,
        residual_rms_hz=rms,
        maximum_absolute_residual_hz=maximum,
        reason=(
            "all comparison residuals satisfy the alias gate"
            if accepted
            else "one or more comparison residuals exceed the alias gate"
        ),
    )


def _canonical_observations(
    observations: tuple[TrajectoryObservation, ...],
    references: tuple[PolynomialTrajectory, ...],
    members: dict[str, CfoAliasMemberV1],
    config: CfoDealiasConfigV1,
) -> tuple[CanonicalObservationV1, ...]:
    assigned: list[tuple[TrajectoryObservation, CfoAliasMemberV1, int, float]] = []
    for observation in sorted(observations, key=lambda item: (item.time_s, item.observation_id)):
        choices = []
        for reference in references:
            if not reference.start_s <= observation.time_s <= reference.end_s:
                continue
            predicted = float(reference.frequency_hz(observation.time_s))
            local_alias = int(
                np.rint((observation.tracking_cfo_hz - predicted) / config.alias_spacing_hz)
            )
            residual = (
                observation.tracking_cfo_hz - local_alias * config.alias_spacing_hz - predicted
            )
            if abs(residual) <= config.maximum_alias_residual_hz:
                choices.append((abs(residual), reference.trajectory_id, local_alias, residual))
        if not choices:
            continue
        _, trajectory_id, local_alias, _ = min(choices)
        member = members[trajectory_id]
        total_alias = member.relative_alias_index + local_alias
        canonical_cfo = observation.tracking_cfo_hz - total_alias * config.alias_spacing_hz
        assigned.append((observation, member, total_alias, canonical_cfo))

    groups: list[list[tuple[TrajectoryObservation, CfoAliasMemberV1, int, float]]] = []
    for item in assigned:
        observation, member, _, canonical_cfo = item
        matched = None
        for group in groups:
            first_observation, first_member, _, first_canonical = group[0]
            if (
                member.component_id == first_member.component_id
                and observation.sample_start == first_observation.sample_start
                and abs(canonical_cfo - first_canonical) <= config.maximum_alias_residual_hz
                and abs(observation.tracking_cfo_hz - first_observation.tracking_cfo_hz)
                >= config.alias_spacing_hz / 2.0
            ):
                matched = group
                break
        if matched is None:
            matched = []
            groups.append(matched)
        matched.append(item)

    result = []
    for group in groups:
        raw_ids = tuple(sorted(item[0].observation_id for item in group))
        trajectory_ids = tuple(sorted({item[1].trajectory_id for item in group}))
        primary = min(group, key=lambda item: item[0].observation_id)
        observation, member, alias_index, canonical_cfo = primary
        result.append(
            CanonicalObservationV1(
                observation_id=canonical_digest({"source_observation_ids": raw_ids}),
                component_id=member.component_id,
                sample_start=observation.sample_start,
                time_s=observation.time_s,
                raw_cfo_hz=observation.tracking_cfo_hz,
                component_cfo_hz=canonical_cfo,
                residue_cfo_hz=centered_alias_residue_hz(canonical_cfo, config),
                alias_index=alias_index,
                source_alias_indices=tuple(sorted({item[2] for item in group})),
                source_observation_ids=raw_ids,
                source_trajectory_ids=trajectory_ids,
            )
        )
    return tuple(
        sorted(result, key=lambda item: (item.component_id, item.time_s, item.observation_id))
    )


def _association_observations(
    observations: tuple[CanonicalObservationV1, ...],
    references: tuple[PolynomialTrajectory, ...],
) -> tuple[MultiTargetObservationV1, ...]:
    reference_by_id = {item.trajectory_id: item for item in references}
    reference_kinematics: dict[Sha256Digest, tuple[float, float]] = {}
    for observation in observations:
        slopes = []
        accelerations = []
        for trajectory_id in observation.source_trajectory_ids:
            reference = reference_by_id.get(trajectory_id)
            if reference is None:
                continue
            relative_time = observation.time_s - reference.reference_time_s
            coefficients = np.asarray(reference.coefficients_hz, dtype=float)
            slopes.append(float(np.polyval(np.polyder(coefficients, 1), relative_time)))
            accelerations.append(
                float(np.polyval(np.polyder(coefficients, 2), relative_time))
                if reference.polynomial_degree >= 2
                else 0.0
            )
        if not slopes:
            raise ValueError("canonical observation lacks its declared source trajectory")
        reference_kinematics[observation.observation_id] = (
            float(np.median(slopes)),
            float(np.median(accelerations)),
        )
    local_kinematics = _local_observation_kinematics(
        observations,
        reference_kinematics,
    )
    result = []
    for observation in observations:
        slope, acceleration = local_kinematics[observation.observation_id]
        result.append(
            MultiTargetObservationV1(
                observation_id=observation.observation_id,
                component_id=observation.component_id,
                hypothesis_set_id=canonical_digest(
                    {
                        "sample_start": observation.sample_start,
                        "source_observation_ids": observation.source_observation_ids,
                    }
                ),
                time_s=observation.time_s,
                canonical_cfo_hz=observation.component_cfo_hz,
                slope_hint_hz_per_s=slope,
                acceleration_hint_hz_per_s2=acceleration,
            )
        )
    return tuple(sorted(result, key=lambda item: (item.time_s, item.observation_id)))


def _local_observation_kinematics(
    observations: tuple[CanonicalObservationV1, ...],
    reference: dict[Sha256Digest, tuple[float, float]],
) -> dict[Sha256Digest, tuple[float, float]]:
    """Estimate smooth local derivatives without assigning crossing identities."""

    result: dict[Sha256Digest, tuple[float, float]] = {}
    for component_id in sorted({item.component_id for item in observations}):
        component = tuple(item for item in observations if item.component_id == component_id)
        times = sorted({item.time_s for item in component})
        by_time = {
            time_s: tuple(
                sorted(
                    (item for item in component if item.time_s == time_s),
                    key=lambda item: item.observation_id,
                )
            )
            for time_s in times
        }
        time_index = {time_s: index for index, time_s in enumerate(times)}
        for observation in component:
            index = time_index[observation.time_s]
            prior = by_time[times[index - 1]] if index else ()
            following = by_time[times[index + 1]] if index + 1 < len(times) else ()
            reference_slope, reference_acceleration = reference[observation.observation_id]
            backward = tuple(
                (
                    (observation.component_cfo_hz - item.component_cfo_hz)
                    / (observation.time_s - item.time_s),
                    observation.time_s - item.time_s,
                    item.observation_id,
                )
                for item in prior
            )
            forward = tuple(
                (
                    (item.component_cfo_hz - observation.component_cfo_hz)
                    / (item.time_s - observation.time_s),
                    item.time_s - observation.time_s,
                    item.observation_id,
                )
                for item in following
            )
            if backward and forward:
                before, after = min(
                    ((before, after) for before in backward for after in forward),
                    key=lambda pair: (
                        abs(pair[1][0] - pair[0][0]),
                        abs((pair[0][0] + pair[1][0]) / 2.0 - reference_slope),
                        pair[0][2],
                        pair[1][2],
                    ),
                )
                slope = (before[0] + after[0]) / 2.0
                acceleration = (after[0] - before[0]) / ((before[1] + after[1]) / 2.0)
            else:
                candidates = backward or forward
                if candidates:
                    chosen = min(
                        candidates,
                        key=lambda item: (
                            abs(item[0] - reference_slope),
                            item[2],
                        ),
                    )
                    slope = chosen[0]
                    acceleration = reference_acceleration
                else:
                    slope = reference_slope
                    acceleration = reference_acceleration
            result[observation.observation_id] = (float(slope), float(acceleration))
    return result


def _associate_component(
    component_id: Sha256Digest,
    observations: tuple[CanonicalObservationV1, ...],
    config: CfoDealiasConfigV1,
) -> list[_MutableBranch]:
    branches: list[_MutableBranch] = []
    by_time: dict[float, list[CanonicalObservationV1]] = {}
    for observation in observations:
        by_time.setdefault(observation.time_s, []).append(observation)
    for time_s in sorted(by_time):
        current = sorted(by_time[time_s], key=lambda item: item.observation_id)
        active_indices = tuple(
            index
            for index, branch in enumerate(branches)
            if time_s - branch.observations[-1].time_s <= config.continuity_gap_s
        )
        choices = _minimum_cost_assignment(branches, active_indices, current, config)
        for observation, branch_index in zip(current, choices, strict=True):
            if branch_index is None:
                if len(branches) >= config.maximum_branches_per_component:
                    continue
                branches.append(_MutableBranch(component_id, [observation]))
            else:
                branches[branch_index].observations.append(observation)
    return branches


def _minimum_cost_assignment(
    branches: list[_MutableBranch],
    active_indices: tuple[int, ...],
    observations: list[CanonicalObservationV1],
    config: CfoDealiasConfigV1,
) -> tuple[int | None, ...]:
    costs = {
        (observation_index, local_branch_index): cost
        for observation_index, observation in enumerate(observations)
        for local_branch_index, branch_index in enumerate(active_indices)
        if (cost := _association_cost(branches[branch_index], observation, config)) is not None
    }

    @cache
    def solve(observation_index: int, used_mask: int):
        if observation_index == len(observations):
            return (0, 0.0, ())
        best = solve(observation_index + 1, used_mask)
        best = (best[0], best[1], (None, *best[2]))
        for local_index, branch_index in enumerate(active_indices):
            if used_mask & (1 << local_index):
                continue
            cost = costs.get((observation_index, local_index))
            if cost is None:
                continue
            tail = solve(observation_index + 1, used_mask | (1 << local_index))
            candidate = (tail[0] + 1, tail[1] + cost, (branch_index, *tail[2]))
            if (-candidate[0], candidate[1], _choice_key(candidate[2])) < (
                -best[0],
                best[1],
                _choice_key(best[2]),
            ):
                best = candidate
        return best

    return solve(0, 0)[2]


def _choice_key(values: tuple[int | None, ...]) -> tuple[int, ...]:
    return tuple(1_000_000 if item is None else item for item in values)


def _association_cost(
    branch: _MutableBranch,
    observation: CanonicalObservationV1,
    config: CfoDealiasConfigV1,
) -> float | None:
    previous = branch.observations[-1]
    dt = observation.time_s - previous.time_s
    if dt <= 0 or dt > config.continuity_gap_s:
        return None
    last_slope = 0.0
    predicted = previous.component_cfo_hz
    if len(branch.observations) >= 2:
        earlier = branch.observations[-2]
        previous_dt = previous.time_s - earlier.time_s
        if previous_dt > 0:
            last_slope = (previous.component_cfo_hz - earlier.component_cfo_hz) / previous_dt
            predicted += last_slope * dt
    frequency_error = abs(observation.component_cfo_hz - predicted)
    if frequency_error > config.association_frequency_gate_hz:
        return None
    slope = (observation.component_cfo_hz - previous.component_cfo_hz) / dt
    slope_error = abs(slope - last_slope) if len(branch.observations) >= 2 else 0.0
    if slope_error > config.association_slope_gate_hz_per_s:
        return None
    acceleration = slope_error / dt if len(branch.observations) >= 3 else 0.0
    if acceleration > config.association_acceleration_gate_hz_per_s2:
        return None
    return (
        frequency_error / config.association_frequency_gate_hz
        + slope_error / config.association_slope_gate_hz_per_s
        + acceleration / config.association_acceleration_gate_hz_per_s2
    )


def _fit_branch(branch: _MutableBranch, config: CfoDealiasConfigV1) -> CanonicalBranchV1 | None:
    ordered = tuple(
        sorted(branch.observations, key=lambda item: (item.time_s, item.observation_id))
    )
    if len(ordered) < 5:
        return None
    time = np.asarray([item.time_s for item in ordered], dtype=float)
    values = np.asarray([item.component_cfo_hz for item in ordered], dtype=float)
    reference_time = float(time[0])
    relative = time - reference_time
    observation_ids = tuple(sorted(item.observation_id for item in ordered))
    models = []
    for degree in config.polynomial_degrees:
        if len(ordered) < degree + 2:
            continue
        coefficients = np.polyfit(relative, values, degree)
        residual = values - np.polyval(coefficients, relative)
        rss = float(np.sum(residual**2))
        rms = float(np.sqrt(np.mean(residual**2)))
        maximum = float(np.max(np.abs(residual)))
        bic = float(
            len(values) * math.log(max(rss / len(values), np.finfo(float).tiny))
            + (degree + 1) * math.log(len(values))
        )
        identity = {
            "component_id": branch.component_id,
            "degree": degree,
            "observations": observation_ids,
            "coefficients_hz": [float(item) for item in coefficients],
        }
        models.append(
            CanonicalPolynomialV1(
                model_id=canonical_digest(identity),
                polynomial_degree=degree,
                reference_time_s=reference_time,
                coefficients_hz=tuple(float(item) for item in coefficients),
                start_s=float(time[0]),
                end_s=float(time[-1]),
                observation_ids=observation_ids,
                residual_rms_hz=rms,
                residual_max_hz=maximum,
                bic=bic,
            )
        )
    if tuple(item.polynomial_degree for item in models) != (1, 2, 3):
        return None
    selected = min(models, key=lambda item: (item.bic, item.polynomial_degree, item.model_id))
    branch_id = canonical_digest(
        {"component_id": branch.component_id, "observation_ids": observation_ids}
    )
    return CanonicalBranchV1(
        branch_id=branch_id,
        component_id=branch.component_id,
        observation_ids=observation_ids,
        observed_alias_indices=tuple(
            sorted({alias for item in ordered for alias in item.source_alias_indices})
        ),
        models=tuple(models),
        selected_model_id=selected.model_id,
        start_s=float(time[0]),
        end_s=float(time[-1]),
    )
