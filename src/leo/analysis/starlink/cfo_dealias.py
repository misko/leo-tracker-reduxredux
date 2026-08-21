"""Pure bounded CFO de-aliasing, multi-branch association, and final selection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from leo.analysis.starlink.pilot_methods import PilotMethod, PilotProbeDetection
from leo.analysis.starlink.seeded_alias_em import (
    SeededAliasObservation,
    SeedTrajectory,
    fit_seeded_alias_em,
)
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
    AliasComponentStatus,
    AliasPairStatus,
    CanonicalBranchV1,
    CanonicalObservationV1,
    CanonicalPolynomialV1,
    CfoAliasComponentV2,
    CfoAliasMapV1,
    CfoAliasMapV2,
    CfoAliasMemberV1,
    CfoAliasPairDecisionV1,
    CfoDealiasConfigV1,
    CfoLiftReplayRowV2,
    CfoLiftReplayRowV3,
    CfoLiftReplayRowV4,
    CfoLiftReplayV2,
    CfoLiftReplayV3,
    CfoLiftReplayV4,
    DealiasedTrajectoryBankV1,
    DealiasedTrajectoryBankV2,
    DealiasedTrajectoryBankV3,
    FinalTrajectoryBankV2,
    FinalTrajectoryBankV3,
    FinalTrajectorySelectionConfigV1,
    FinalTrajectorySelectionConfigV2,
    FinalTrajectoryV1,
    FinalTrajectoryV2,
    FinalTrajectoryV3,
    Glrt64FinalTrajectoryTableV2,
    Glrt64FinalTrajectoryTableV3,
    LiftReplayTierV2,
    LiftReplayTierV3,
    ReplayBlockMetricV2,
    ReplayBlockMetricV3,
    ReplayBlockMetricV4,
    ReplayGateConfigV2,
    ReplayGateConfigV3,
    ReplayGateConfigV4,
    SeededAliasEmConfigV1,
    SeededAliasEmDispositionV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
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


def calibrate_replay_gate_v2(
    controls: dict[str, tuple[float, ...]],
    **overrides: Any,
) -> ReplayGateConfigV2:
    """Freeze an equivalence band from named block-level negative controls."""

    required = {"noise", "zero_iq", "wrong_edge", "wrong_alias", "time_shift", "unrelated_iq"}
    if set(controls) != required:
        raise ValueError("V2 calibration requires exactly the six reviewed negative controls")
    ordered = {name: tuple(float(value) for value in controls[name]) for name in sorted(controls)}
    values = np.asarray([value for rows in ordered.values() for value in rows], dtype=float)
    if values.size < 20 or not np.all(np.isfinite(values)):
        raise ValueError("V2 calibration requires at least 20 finite control blocks")
    p95 = float(np.quantile(np.abs(values), 0.95, method="higher"))
    if p95 <= 0.0:
        raise ValueError("V2 calibration cannot derive a zero-width equivalence band")
    return ReplayGateConfigV2(
        equivalence_control_receipt_digest=canonical_digest(
            {"kind": "glrt64-replay-equivalence-controls-v2", "controls": ordered}
        ),
        equivalence_control_block_count=int(values.size),
        equivalence_control_p95_absolute_delta=p95,
        **overrides,
    )


def default_replay_gate_v4(*, sample_rate_hz: int = 2_500_000) -> ReplayGateConfigV4:
    """Return the absolute-evidence gate whose harmful metrics are audit-only."""

    return ReplayGateConfigV4(sample_rate_hz=sample_rate_hz)


def default_final_trajectory_selection_config() -> FinalTrajectorySelectionConfigV1:
    return FinalTrajectorySelectionConfigV1()


def default_final_trajectory_selection_config_v2() -> FinalTrajectorySelectionConfigV2:
    return FinalTrajectorySelectionConfigV2()


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
) -> CfoAliasMapV2:
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
    component_contradictions: list[int] = []
    for root in range(len(retained)):
        if potentials[root] is not None:
            continue
        potentials[root] = 0
        pending = [root]
        component_members: list[int] = []
        contradictory_edges: set[tuple[int, int]] = set()
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
                    contradictory_edges.add((min(index, other), max(index, other)))
        raw_components.append(tuple(sorted(component_members)))
        component_contradictions.append(len(contradictory_edges))
    if len(raw_components) > config.maximum_alias_components:
        raise ValueError("alias component inventory exceeds its configured bound")

    component_by_index: dict[int, Sha256Digest] = {}
    components: list[CfoAliasComponentV2] = []
    for indices, contradiction_count in zip(raw_components, component_contradictions, strict=True):
        trajectory_ids = tuple(sorted(retained[index].trajectory_id for index in indices))
        member_set = set(indices)
        edges = tuple(
            pair.model_dump(mode="json")
            for _, _, _, pair in sorted(
                (item for item in accepted if item[0] in member_set and item[1] in member_set),
                key=lambda item: (
                    item[3].left_trajectory_id,
                    item[3].right_trajectory_id,
                ),
            )
        )
        component_id = canonical_digest({"trajectory_ids": trajectory_ids, "edges": edges})
        for index in indices:
            component_by_index[index] = component_id
        components.append(
            CfoAliasComponentV2(
                component_id=component_id,
                trajectory_ids=trajectory_ids,
                status=(
                    AliasComponentStatus.INSUFFICIENT_CONTRADICTORY_CYCLE
                    if contradiction_count
                    else AliasComponentStatus.RESOLVED
                ),
                contradictory_edge_count=contradiction_count,
                reason=(
                    "accepted alias constraints contain a contradictory finite cycle"
                    if contradiction_count
                    else "accepted alias constraints have one consistent integer potential"
                ),
            )
        )
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
    ordered_components = tuple(sorted(components, key=lambda item: item.component_id))
    insufficient_count = sum(
        item.status is AliasComponentStatus.INSUFFICIENT_CONTRADICTORY_CYCLE
        for item in ordered_components
    )
    status = (
        StandardScientificStatus.PARTIAL
        if insufficient_count and insufficient_count < len(ordered_components)
        else StandardScientificStatus.INSUFFICIENT_DATA
        if insufficient_count
        else StandardScientificStatus.COMPLETE
        if ordered_components
        else StandardScientificStatus.NO_RESULT
    )
    document = {
        "config_digest": config.digest,
        "pilot_scan_digest": pilot_scan_digest,
        "raw_trajectory_bank_digest": raw_bank_digest,
        "source_representative_count": len(source),
        "returned_representative_count": len(retained),
        "truncated_representative_count": truncated,
        "component_count": len(raw_components),
        "insufficient_component_count": insufficient_count,
        "components": [item.model_dump(mode="json") for item in ordered_components],
        "members": [item.model_dump(mode="json") for item in alias_members],
        "pair_decisions": [
            item.model_dump(mode="json")
            for item in sorted(
                comparisons, key=lambda value: (value.left_trajectory_id, value.right_trajectory_id)
            )
        ],
        "status": status,
        "reason": (
            "one or more alias components contain contradictory finite cycles"
            if insufficient_count
            else "all retained alias components have consistent integer potentials"
            if ordered_components
            else "complete alias comparison produced no retained component"
        ),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 2,
            "algorithm_version": "cfo-alias-map-v2",
            "alias_spacing_numerator_hz": 2_500_000,
            "alias_spacing_denominator": 11,
            **document,
        }
    )
    return CfoAliasMapV2.model_validate(document)


def fit_seed_preserving_dealiased_trajectories(
    raw_observations: tuple[TrajectoryObservation, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    alias_map: CfoAliasMapV1 | CfoAliasMapV2,
    *,
    raw_bank_digest: Sha256Digest,
    config: CfoDealiasConfigV1,
    seeded_em_config: SeededAliasEmConfigV1,
) -> DealiasedTrajectoryBankV3:
    """Refine each first-EM trajectory independently without rebuilding its path cover."""

    if alias_map.config_digest != config.digest:
        raise ValueError("alias map configuration disagrees with de-alias configuration")
    member_by_id = {item.trajectory_id: item for item in alias_map.members}
    observations_by_id = {item.observation_id: item for item in raw_observations}
    if len(observations_by_id) != len(raw_observations):
        raise ValueError("raw trajectory observations must have unique identities")
    canonical: list[CanonicalObservationV1] = []
    branches: list[CanonicalBranchV1] = []
    dispositions: list[SeededAliasEmDispositionV1] = []
    evidence = tuple(
        SeededAliasObservation(
            observation_id=item.observation_id,
            sample_start=item.sample_start,
            time_s=item.time_s,
            raw_cfo_hz=item.tracking_cfo_hz,
            weight=max(item.margin, 0.0) + 1e-3,
        )
        for item in raw_observations
    )
    for _, representative in sorted(representatives, key=lambda item: item[1].trajectory_id):
        member = member_by_id.get(representative.trajectory_id)
        if member is None:
            raise ValueError("seed trajectory is absent from the alias-map authority")
        missing = tuple(
            item for item in representative.observation_ids if item not in observations_by_id
        )
        if missing:
            raise ValueError("seed trajectory references absent raw observations")
        seed_coefficients = list(representative.coefficients_hz)
        seed_coefficients[-1] -= member.relative_alias_index * config.alias_spacing_hz
        seed = SeedTrajectory(
            trajectory_id=representative.trajectory_id,
            polynomial_degree=representative.polynomial_degree,
            reference_time_s=representative.reference_time_s,
            coefficients_hz=tuple(seed_coefficients),
            start_s=representative.start_s,
            end_s=representative.end_s,
            observation_ids=representative.observation_ids,
        )
        fit = fit_seeded_alias_em(
            evidence,
            seed,
            alias_spacing_hz=config.alias_spacing_hz,
            maximum_alias_index=seeded_em_config.maximum_alias_index,
            maximum_iterations=seeded_em_config.maximum_iterations,
            huber_scale_floor_hz=seeded_em_config.huber_scale_floor_hz,
        )
        branch_observations = []
        for point in fit.points:
            observation_id = canonical_digest(
                {
                    "seed_trajectory_id": representative.trajectory_id,
                    "source_observation_id": point.observation_id,
                }
            )
            branch_observations.append(
                CanonicalObservationV1(
                    observation_id=observation_id,
                    component_id=member.component_id,
                    sample_start=point.sample_start,
                    time_s=point.time_s,
                    raw_cfo_hz=point.raw_cfo_hz,
                    component_cfo_hz=point.canonical_cfo_hz,
                    residue_cfo_hz=centered_alias_residue_hz(point.canonical_cfo_hz, config),
                    alias_index=point.alias_index,
                    source_alias_indices=(point.alias_index,),
                    source_observation_ids=(point.observation_id,),
                    source_trajectory_ids=(representative.trajectory_id,),
                )
            )
        mutable = _MutableBranch(member.component_id, branch_observations)
        branch = _fit_branch(mutable, config)
        if branch is None:
            raise ValueError("seed-preserving refinement could not publish all degree models")
        canonical.extend(branch_observations)
        branches.append(branch)
        dispositions.append(
            SeededAliasEmDispositionV1(
                seed_trajectory_id=representative.trajectory_id,
                component_id=member.component_id,
                output_branch_id=branch.branch_id,
                source_observation_count=fit.source_observation_count,
                selected_probe_count=fit.selected_probe_count,
                iteration_count=fit.iterations,
                converged=fit.converged,
                observed_alias_indices=tuple(sorted({item.alias_index for item in fit.points})),
                residual_rms_hz=fit.residual_rms_hz,
                maximum_absolute_residual_hz=fit.maximum_absolute_residual_hz,
                reason=(
                    "seed membership preserved; one candidate and integer alias selected per probe"
                ),
            )
        )
    ordered_observations = tuple(
        sorted(canonical, key=lambda item: (item.component_id, item.time_s, item.observation_id))
    )
    ordered_branches = tuple(sorted(branches, key=lambda item: item.branch_id))
    ordered_dispositions = sorted(dispositions, key=lambda item: item.seed_trajectory_id)
    all_converged = all(item.converged for item in ordered_dispositions)
    status = (
        StandardScientificStatus.COMPLETE
        if ordered_branches and all_converged
        else StandardScientificStatus.PARTIAL
        if ordered_branches
        else StandardScientificStatus.NO_RESULT
    )
    document = {
        "config_digest": config.digest,
        "seeded_em_config_digest": seeded_em_config.digest,
        "alias_map_digest": alias_map.content_digest,
        "raw_trajectory_bank_digest": raw_bank_digest,
        "source_observation_count": len(ordered_observations),
        "returned_observation_count": len(ordered_observations),
        "truncated_observation_count": 0,
        "source_branch_count": len(representatives),
        "returned_branch_count": len(ordered_branches),
        "truncated_branch_count": 0,
        "observations": [item.model_dump(mode="json") for item in ordered_observations],
        "branches": [item.model_dump(mode="json") for item in ordered_branches],
        "seed_dispositions": [item.model_dump(mode="json") for item in ordered_dispositions],
        "status": status,
        "reason": (
            "every first-EM seed was independently refined and retained"
            if status is StandardScientificStatus.COMPLETE
            else "one or more retained first-EM seeds reached the bounded iteration limit"
            if status is StandardScientificStatus.PARTIAL
            else "complete seed-preserving refinement received no trajectory seeds"
        ),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 3,
            "algorithm_version": "seed-preserving-dealiased-trajectory-bank-v3",
            **document,
        }
    )
    return DealiasedTrajectoryBankV3.model_validate(document)


def select_final_trajectories_v2(
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    replay: CfoLiftReplayV2 | CfoLiftReplayV3,
    *,
    config: CfoDealiasConfigV1,
    selection_config: FinalTrajectorySelectionConfigV1 | None = None,
) -> FinalTrajectoryBankV2:
    """Retain credible geometry and derive the stricter correction subset.

    A V2 final row is displayable only when the replay contract independently
    declares its fitted geometry credible.  Automatic correction remains limited
    to ``replay_improved`` and ``replay_stable`` rows; geometry-only and harmful
    replay dispositions are never silently promoted.
    """

    if (
        canonical_bank.config_digest != config.digest
        or replay.dealiased_bank_digest != canonical_bank.content_digest
    ):
        raise ValueError("final V2 selection predecessor/configuration digest mismatch")
    branch_by_id = {item.branch_id: item for item in canonical_bank.branches}
    selection_config = selection_config or default_final_trajectory_selection_config()
    rows_by_branch: dict[Sha256Digest, list[CfoLiftReplayRowV2 | CfoLiftReplayRowV3]] = {}
    for row in replay.rows:
        rows_by_branch.setdefault(row.branch_id, []).append(row)
    selected_rows: list[CfoLiftReplayRowV2 | CfoLiftReplayRowV3] = []
    for branch_id in sorted(rows_by_branch):
        branch_rows = rows_by_branch[branch_id]
        automatic = [item for item in branch_rows if item.automatic_correction_eligible]
        if automatic:
            selected_rows.extend(automatic)
            continue
        fallback = [
            item
            for item in branch_rows
            if item.tier in {LiftReplayTierV2.GEOMETRY_ONLY, LiftReplayTierV3.GEOMETRY_ONLY}
            and item.geometry_display_eligible
            and item.evaluated_probe_count >= replay.gate_config.minimum_probe_count
            and item.block_coverage_ratio >= replay.gate_config.minimum_block_coverage_ratio
            and item.harmful_block_count == 0
            and item.maximum_consecutive_harmful_blocks == 0
            and (
                not isinstance(item, CfoLiftReplayRowV2)
                or (
                    item.median_block_margin_delta is not None
                    and item.median_block_margin_delta >= -item.equivalence_tolerance
                )
            )
            and item.median_block_corrected_margin is not None
            and item.median_block_corrected_margin >= selection_config.minimum_corrected_margin
        ]
        if fallback:
            selected_rows.append(
                min(
                    fallback,
                    key=lambda item: (
                        -float(item.median_block_corrected_margin or 0.0),
                        abs(item.alias_index),
                        item.alias_index,
                        item.canonical_model_id,
                    ),
                )
            )

    candidates: list[FinalTrajectoryV2] = []
    for row in selected_rows:
        branch = branch_by_id.get(row.branch_id)
        if branch is None:
            raise ValueError("V2 lift replay references an undeclared canonical branch")
        model = next(
            (item for item in branch.models if item.model_id == row.canonical_model_id), None
        )
        if model is None:
            raise ValueError("V2 lift replay references an undeclared canonical model")
        absolute = list(model.coefficients_hz)
        absolute[-1] += row.alias_index * config.alias_spacing_hz
        identity = {
            "branch_id": branch.branch_id,
            "model_id": model.model_id,
            "alias_index": row.alias_index,
        }
        candidates.append(
            FinalTrajectoryV2(
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
                replay_tier=row.tier,
                automatic_correction_eligible=row.automatic_correction_eligible,
                evaluated_probe_count=row.evaluated_probe_count,
                evaluated_block_count=row.evaluated_block_count,
                block_coverage_ratio=row.block_coverage_ratio,
                harmful_block_count=row.harmful_block_count,
                median_block_margin_delta=row.median_block_margin_delta,
                median_block_corrected_margin=row.median_block_corrected_margin,
            )
        )
    source_count = len(candidates)
    ranked = sorted(
        candidates,
        key=lambda item: (
            not item.automatic_correction_eligible,
            -float(item.median_block_corrected_margin or 0.0),
            -item.block_coverage_ratio,
            -len(item.observation_ids),
            item.trajectory_id,
        ),
    )
    retained = tuple(
        sorted(
            ranked[: config.maximum_final_trajectories],
            key=lambda item: item.trajectory_id,
        )
    )
    truncated = source_count - len(retained)
    predecessor_incomplete = (
        canonical_bank.status is StandardScientificStatus.PARTIAL or replay.truncated_lift_count > 0
    )
    predecessor_insufficient = canonical_bank.status is StandardScientificStatus.INSUFFICIENT_DATA
    status = (
        StandardScientificStatus.PARTIAL
        if truncated or predecessor_incomplete
        else StandardScientificStatus.COMPLETE
        if retained
        else StandardScientificStatus.INSUFFICIENT_DATA
        if predecessor_insufficient
        else StandardScientificStatus.NO_RESULT
    )
    automatic_ids = tuple(
        item.trajectory_id for item in retained if item.automatic_correction_eligible
    )
    reason = (
        "bounded final V2 selection omitted candidate geometry"
        if status is StandardScientificStatus.PARTIAL
        else "final V2 retained replay-classified candidate geometry and its correction subset"
        if status is StandardScientificStatus.COMPLETE
        else "de-aliased predecessor was insufficient for final V2 candidate geometry"
        if status is StandardScientificStatus.INSUFFICIENT_DATA
        else "complete V2 replay retained no credible candidate geometry"
    )
    document = {
        "config_digest": config.digest,
        "replay_gate_config_digest": replay.gate_config_digest,
        "selection_config": selection_config.model_dump(mode="json"),
        "selection_config_digest": selection_config.digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "lift_replay_digest": replay.content_digest,
        "source_trajectory_count": source_count,
        "returned_trajectory_count": len(retained),
        "truncated_trajectory_count": truncated,
        "trajectories": [item.model_dump(mode="json") for item in retained],
        "automatic_correction_trajectory_ids": list(automatic_ids),
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 2, "algorithm_version": "final-trajectory-bank-v2", **document}
    )
    return FinalTrajectoryBankV2.model_validate(document)


def build_final_trajectory_table_v2(
    bank: FinalTrajectoryBankV2,
) -> Glrt64FinalTrajectoryTableV2:
    """Project the explicit V2 display/correction split into the UI table."""

    document = {
        "final_trajectory_bank_digest": bank.content_digest,
        "source_trajectory_count": bank.source_trajectory_count,
        "returned_trajectory_count": bank.returned_trajectory_count,
        "truncated_trajectory_count": bank.truncated_trajectory_count,
        "trajectories": [item.model_dump(mode="json") for item in bank.trajectories],
        "automatic_correction_trajectory_ids": list(bank.automatic_correction_trajectory_ids),
        "status": bank.status,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 2,
            "algorithm_version": "glrt64-final-trajectory-table-v2",
            "frequency_model": ("cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"),
            "coefficient_order": "highest_polynomial_power_first",
            **document,
        }
    )
    return Glrt64FinalTrajectoryTableV2.model_validate(document)


def select_final_trajectories_v3(
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    replay: CfoLiftReplayV4,
    *,
    config: CfoDealiasConfigV1,
    selection_config: FinalTrajectorySelectionConfigV2 | None = None,
) -> FinalTrajectoryBankV3:
    """Retain automatic rows and one geometry-qualified fallback per branch.

    Corrected-margin and harmful-block metrics are copied into the final row
    for audit, but are not admission gates for automatic or fallback selection.
    """

    if (
        canonical_bank.config_digest != config.digest
        or replay.dealiased_bank_digest != canonical_bank.content_digest
    ):
        raise ValueError("final V3 selection predecessor/configuration digest mismatch")
    selection_config = selection_config or default_final_trajectory_selection_config_v2()
    branch_by_id = {item.branch_id: item for item in canonical_bank.branches}
    rows_by_branch: dict[Sha256Digest, list[CfoLiftReplayRowV4]] = {}
    for row in replay.rows:
        rows_by_branch.setdefault(row.branch_id, []).append(row)
    selected_rows: list[CfoLiftReplayRowV4] = []
    for branch_id in sorted(rows_by_branch):
        branch_rows = rows_by_branch[branch_id]
        automatic = [item for item in branch_rows if item.automatic_correction_eligible]
        if automatic:
            selected_rows.extend(automatic)
            continue
        fallback = [
            item
            for item in branch_rows
            if item.tier is LiftReplayTierV3.GEOMETRY_ONLY
            and item.geometry_display_eligible
            and item.evaluated_probe_count >= replay.gate_config.minimum_probe_count
            and item.block_coverage_ratio >= replay.gate_config.minimum_block_coverage_ratio
        ]
        if fallback:
            selected_rows.append(
                min(
                    fallback,
                    key=lambda item: (
                        -float(item.median_block_corrected_margin or 0.0),
                        abs(item.alias_index),
                        item.alias_index,
                        item.canonical_model_id,
                    ),
                )
            )

    candidates: list[FinalTrajectoryV3] = []
    for row in selected_rows:
        branch = branch_by_id.get(row.branch_id)
        if branch is None:
            raise ValueError("V4 lift replay references an undeclared canonical branch")
        model = next(
            (item for item in branch.models if item.model_id == row.canonical_model_id), None
        )
        if model is None:
            raise ValueError("V4 lift replay references an undeclared canonical model")
        absolute = list(model.coefficients_hz)
        absolute[-1] += row.alias_index * config.alias_spacing_hz
        identity = {
            "branch_id": branch.branch_id,
            "model_id": model.model_id,
            "alias_index": row.alias_index,
        }
        candidates.append(
            FinalTrajectoryV3(
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
                replay_tier=row.tier,
                automatic_correction_eligible=row.automatic_correction_eligible,
                evaluated_probe_count=row.evaluated_probe_count,
                evaluated_block_count=row.evaluated_block_count,
                block_coverage_ratio=row.block_coverage_ratio,
                harmful_block_count=row.harmful_block_count,
                maximum_consecutive_harmful_blocks=row.maximum_consecutive_harmful_blocks,
                median_block_margin_delta=row.median_block_margin_delta,
                median_block_corrected_margin=row.median_block_corrected_margin,
                replay_reasons=row.reasons,
            )
        )
    source_count = len(candidates)
    ranked = sorted(
        candidates,
        key=lambda item: (
            not item.automatic_correction_eligible,
            -float(item.median_block_corrected_margin or 0.0),
            -item.block_coverage_ratio,
            -len(item.observation_ids),
            item.trajectory_id,
        ),
    )
    retained = tuple(
        sorted(ranked[: config.maximum_final_trajectories], key=lambda item: item.trajectory_id)
    )
    truncated = source_count - len(retained)
    predecessor_incomplete = (
        canonical_bank.status is StandardScientificStatus.PARTIAL or replay.truncated_lift_count > 0
    )
    predecessor_insufficient = canonical_bank.status is StandardScientificStatus.INSUFFICIENT_DATA
    status = (
        StandardScientificStatus.PARTIAL
        if truncated or predecessor_incomplete
        else StandardScientificStatus.COMPLETE
        if retained
        else StandardScientificStatus.INSUFFICIENT_DATA
        if predecessor_insufficient
        else StandardScientificStatus.NO_RESULT
    )
    automatic_ids = tuple(
        item.trajectory_id for item in retained if item.automatic_correction_eligible
    )
    reason = (
        "bounded final V3 selection omitted candidate geometry"
        if status is StandardScientificStatus.PARTIAL
        else (
            "final V3 retained geometry-qualified candidates; corrected-margin and harmful "
            "metrics are audit-only"
        )
        if status is StandardScientificStatus.COMPLETE
        else "de-aliased predecessor was insufficient for final V3 candidate geometry"
        if status is StandardScientificStatus.INSUFFICIENT_DATA
        else "complete V4 replay retained no geometry-qualified candidate geometry"
    )
    document = {
        "config_digest": config.digest,
        "replay_gate_config_digest": replay.gate_config_digest,
        "selection_config": selection_config.model_dump(mode="json"),
        "selection_config_digest": selection_config.digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "lift_replay_digest": replay.content_digest,
        "source_trajectory_count": source_count,
        "returned_trajectory_count": len(retained),
        "truncated_trajectory_count": truncated,
        "trajectories": [item.model_dump(mode="json") for item in retained],
        "automatic_correction_trajectory_ids": list(automatic_ids),
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 3, "algorithm_version": "final-trajectory-bank-v3", **document}
    )
    return FinalTrajectoryBankV3.model_validate(document)


def build_final_trajectory_table_v3(
    bank: FinalTrajectoryBankV3,
) -> Glrt64FinalTrajectoryTableV3:
    document = {
        "final_trajectory_bank_digest": bank.content_digest,
        "source_trajectory_count": bank.source_trajectory_count,
        "returned_trajectory_count": bank.returned_trajectory_count,
        "truncated_trajectory_count": bank.truncated_trajectory_count,
        "trajectories": [item.model_dump(mode="json") for item in bank.trajectories],
        "automatic_correction_trajectory_ids": list(bank.automatic_correction_trajectory_ids),
        "status": bank.status,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {
            "schema_version": 3,
            "algorithm_version": "glrt64-final-trajectory-table-v3",
            "frequency_model": ("cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"),
            "coefficient_order": "highest_polynomial_power_first",
            **document,
        }
    )
    return Glrt64FinalTrajectoryTableV3.model_validate(document)


def project_final_trajectory_v1(
    trajectory: FinalTrajectoryV2 | FinalTrajectoryV3,
) -> FinalTrajectoryV1:
    """Compatibility projection used only by the existing aggregate report contract."""

    return FinalTrajectoryV1(
        trajectory_id=trajectory.trajectory_id,
        component_id=trajectory.component_id,
        branch_id=trajectory.branch_id,
        canonical_model_id=trajectory.canonical_model_id,
        alias_index=trajectory.alias_index,
        polynomial_degree=trajectory.polynomial_degree,
        reference_time_s=trajectory.reference_time_s,
        canonical_coefficients_hz=trajectory.canonical_coefficients_hz,
        absolute_coefficients_hz=trajectory.absolute_coefficients_hz,
        start_s=trajectory.start_s,
        end_s=trajectory.end_s,
        observation_ids=trajectory.observation_ids,
        replayed_probe_count=trajectory.evaluated_probe_count,
        median_margin_delta=float(trajectory.median_block_margin_delta or 0.0),
        median_control_separation=float(trajectory.median_block_corrected_margin or 0.0),
    )


def replay_observed_cfo_lifts_v2(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    feedback_config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    dealias_config: CfoDealiasConfigV1,
    gate_config: ReplayGateConfigV2,
) -> CfoLiftReplayV2:
    """Replay observed lifts and retain both correction and geometry inventories."""

    if canonical_bank.config_digest != dealias_config.digest:
        raise ValueError("canonical bank configuration disagrees with replay configuration")
    candidates, source_count = _observed_lift_candidates_v2(
        canonical_bank, dealias_config, gate_config
    )
    representatives = tuple(
        (canonical_digest({"replay_trajectory_id": item.replay_trajectory_id}), item.trajectory)
        for item in candidates
    )
    raw_rows = replay_pilot_trajectories(
        iq, detections, representatives, feedback_config, edge=edge
    )
    return classify_observed_lift_replay_v2(
        candidates,
        tuple(dict(item) for item in raw_rows),
        source_lift_count=source_count,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        canonical_bank=canonical_bank,
        gate_config=gate_config,
    )


def classify_observed_lift_replay_v2(
    candidates: tuple[_ObservedLiftCandidate, ...],
    raw_rows: tuple[dict[str, object], ...],
    *,
    source_lift_count: int,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    gate_config: ReplayGateConfigV2,
) -> CfoLiftReplayV2:
    """Classify exact same-IQ evidence at a correlation-resistant time-block level."""

    branches = {item.branch_id: item for item in canonical_bank.branches}
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

    classified: list[CfoLiftReplayRowV2] = []
    for candidate in candidates:
        branch = branches[candidate.branch_id]
        model = next(item for item in branch.models if item.model_id == candidate.model_id)
        values = rows_by_trajectory.get(candidate.replay_trajectory_id, [])
        blocks = _aggregate_replay_blocks_v2(values, gate_config)
        duration = max(0.0, model.end_s - model.start_s)
        first_block = math.floor(model.start_s / gate_config.block_duration_s)
        last_block = math.floor(model.end_s / gate_config.block_duration_s)
        eligible_blocks = max(1, last_block - first_block + 1)
        coverage = min(1.0, len(blocks) / eligible_blocks)
        geometry_ok = (
            len(model.observation_ids) >= gate_config.minimum_observation_count
            and duration >= gate_config.minimum_duration_s
            and model.residual_rms_hz <= gate_config.maximum_geometry_residual_rms_hz
            and model.residual_max_hz <= gate_config.maximum_geometry_residual_hz
        )
        enough_replay = (
            len(values) >= gate_config.minimum_probe_count
            and len(blocks) >= gate_config.minimum_block_count
            and coverage >= gate_config.minimum_block_coverage_ratio
        )
        deltas = np.asarray([item.median_margin_delta for item in blocks], dtype=float)
        corrected = np.asarray([item.median_corrected_margin for item in blocks], dtype=float)
        median_delta = float(np.median(deltas)) if deltas.size else None
        q10_delta = float(np.quantile(deltas, 0.10, method="lower")) if deltas.size else None
        median_corrected = float(np.median(corrected)) if corrected.size else None
        harmful_flags = tuple(
            item.median_margin_delta < gate_config.harmful_block_delta for item in blocks
        )
        harmful_count = sum(harmful_flags)
        harmful_run = _maximum_true_run(harmful_flags)
        tail_ok = bool(blocks) and (
            harmful_count / len(blocks) <= gate_config.maximum_harmful_block_fraction
            and harmful_run <= gate_config.maximum_consecutive_harmful_blocks
        )
        strong_absolute = (
            median_corrected is not None
            and median_corrected >= gate_config.minimum_median_corrected_margin
        )
        tolerance = gate_config.equivalence_tolerance
        tier, reasons = classify_replay_tier_v2(
            geometry_ok=geometry_ok,
            enough_replay=enough_replay,
            strong_absolute=strong_absolute,
            tail_ok=tail_ok,
            median_delta=median_delta,
            equivalence_tolerance=tolerance,
        )
        classified.append(
            CfoLiftReplayRowV2(
                branch_id=candidate.branch_id,
                canonical_model_id=candidate.model_id,
                alias_index=candidate.alias_index,
                tier=tier,
                automatic_correction_eligible=tier
                in {LiftReplayTierV2.REPLAY_IMPROVED, LiftReplayTierV2.REPLAY_STABLE},
                geometry_display_eligible=geometry_ok,
                observation_count=len(model.observation_ids),
                duration_s=duration,
                residual_rms_hz=model.residual_rms_hz,
                residual_max_hz=model.residual_max_hz,
                polynomial_degree=model.polynomial_degree,
                evaluated_probe_count=len(values),
                evaluated_block_count=len(blocks),
                eligible_block_count=eligible_blocks,
                block_coverage_ratio=coverage,
                improved_block_count=sum(item.median_margin_delta > 0.0 for item in blocks),
                harmful_block_count=harmful_count,
                maximum_consecutive_harmful_blocks=harmful_run,
                median_block_margin_delta=median_delta,
                q10_block_margin_delta=q10_delta,
                median_block_corrected_margin=median_corrected,
                equivalence_tolerance=tolerance,
                blocks=blocks,
                reasons=reasons,
            )
        )
    ordered = tuple(sorted(classified, key=lambda item: (item.branch_id, item.alias_index)))
    keys = tuple(f"{row.branch_id}:{row.alias_index}" for row in ordered)
    document = {
        "gate_config": gate_config.model_dump(mode="json"),
        "gate_config_digest": gate_config.digest,
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "source_lift_count": source_lift_count,
        "returned_lift_count": len(ordered),
        "truncated_lift_count": source_lift_count - len(ordered),
        "rows": [item.model_dump(mode="json") for item in ordered],
        "automatic_correction_lifts": [
            key for key, row in zip(keys, ordered, strict=True) if row.automatic_correction_eligible
        ],
        "geometry_display_lifts": [
            key for key, row in zip(keys, ordered, strict=True) if row.geometry_display_eligible
        ],
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 2, "algorithm_version": "cfo-lift-replay-v2", **document}
    )
    return CfoLiftReplayV2.model_validate(document)


def classify_replay_tier_v2(
    *,
    geometry_ok: bool,
    enough_replay: bool,
    strong_absolute: bool,
    tail_ok: bool,
    median_delta: float | None,
    equivalence_tolerance: float,
) -> tuple[LiftReplayTierV2, tuple[str, ...]]:
    """Apply the V2 tier ordering to already-aggregated, auditable gate facts."""

    if not math.isfinite(equivalence_tolerance) or equivalence_tolerance <= 0.0:
        raise ValueError("equivalence tolerance must be positive and finite")
    if median_delta is not None and not math.isfinite(median_delta):
        raise ValueError("median replay delta must be finite")
    if not geometry_ok:
        return LiftReplayTierV2.INSUFFICIENT, (
            "geometry did not meet observation, duration, or residual-quality gates",
        )
    if not enough_replay:
        return LiftReplayTierV2.GEOMETRY_ONLY, (
            "credible geometry retained, but replay coverage was insufficient",
        )
    if not strong_absolute:
        return LiftReplayTierV2.GEOMETRY_ONLY, (
            "credible geometry retained, but corrected GLRT64/control separation was weak",
        )
    if not tail_ok:
        return LiftReplayTierV2.REPLAY_REJECTED, (
            "strong median evidence was rejected by the harmful-block tail guard",
        )
    if median_delta is not None and median_delta >= equivalence_tolerance:
        return LiftReplayTierV2.REPLAY_IMPROVED, (
            "block-median replay improvement exceeded the calibrated equivalence band",
        )
    if median_delta is not None and median_delta >= -equivalence_tolerance:
        return LiftReplayTierV2.REPLAY_STABLE, (
            "strong corrected evidence was equivalent to the independently optimized baseline",
        )
    return LiftReplayTierV2.REPLAY_REJECTED, (
        "block-median replay degradation exceeded the calibrated equivalence band",
    )


def replay_observed_cfo_lifts_v4(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    feedback_config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    dealias_config: CfoDealiasConfigV1,
    gate_config: ReplayGateConfigV4,
) -> CfoLiftReplayV4:
    if canonical_bank.config_digest != dealias_config.digest:
        raise ValueError("canonical bank configuration disagrees with replay configuration")
    candidates, source_count = _observed_lift_candidates_v2(
        canonical_bank, dealias_config, gate_config
    )
    representatives = tuple(
        (canonical_digest({"replay_trajectory_id": item.replay_trajectory_id}), item.trajectory)
        for item in candidates
    )
    raw_rows = replay_pilot_trajectories(
        iq, detections, representatives, feedback_config, edge=edge
    )
    return classify_observed_lift_replay_v4(
        candidates,
        tuple(dict(item) for item in raw_rows),
        source_lift_count=source_count,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        canonical_bank=canonical_bank,
        gate_config=gate_config,
    )


def classify_observed_lift_replay_v4(
    candidates: tuple[_ObservedLiftCandidate, ...],
    raw_rows: tuple[dict[str, object], ...],
    *,
    source_lift_count: int,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    canonical_bank: DealiasedTrajectoryBankV1
    | DealiasedTrajectoryBankV2
    | DealiasedTrajectoryBankV3,
    gate_config: ReplayGateConfigV4,
) -> CfoLiftReplayV4:
    """Classify on geometry and replay coverage; margin metrics are audit-only."""

    branches = {item.branch_id: item for item in canonical_bank.branches}
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
    classified: list[CfoLiftReplayRowV4] = []
    for candidate in candidates:
        branch = branches[candidate.branch_id]
        model = next(item for item in branch.models if item.model_id == candidate.model_id)
        values = rows_by_trajectory.get(candidate.replay_trajectory_id, [])
        blocks = _aggregate_replay_blocks_v4(values, gate_config)
        duration = max(0.0, model.end_s - model.start_s)
        first_block = math.floor(model.start_s / gate_config.block_duration_s)
        last_block = math.floor(model.end_s / gate_config.block_duration_s)
        eligible_blocks = max(1, last_block - first_block + 1)
        coverage = min(1.0, len(blocks) / eligible_blocks)
        geometry_ok = (
            len(model.observation_ids) >= gate_config.minimum_observation_count
            and duration >= gate_config.minimum_duration_s
            and model.residual_rms_hz <= gate_config.maximum_geometry_residual_rms_hz
            and model.residual_max_hz <= gate_config.maximum_geometry_residual_hz
        )
        enough_replay = (
            len(values) >= gate_config.minimum_probe_count
            and coverage >= gate_config.minimum_block_coverage_ratio
        )
        deltas = np.asarray([item.median_margin_delta for item in blocks], dtype=float)
        corrected = np.asarray([item.median_corrected_margin for item in blocks], dtype=float)
        median_delta = float(np.median(deltas)) if deltas.size else None
        q10_delta = float(np.quantile(deltas, 0.10, method="lower")) if deltas.size else None
        median_corrected = float(np.median(corrected)) if corrected.size else None
        harmful_flags = tuple(
            item.median_margin_delta < gate_config.harmful_block_delta for item in blocks
        )
        harmful_count = sum(harmful_flags)
        harmful_run = _maximum_true_run(harmful_flags)
        tier, reasons = classify_replay_tier_v4(
            geometry_ok=geometry_ok,
            enough_replay=enough_replay,
            harmful_block_count=harmful_count,
            maximum_consecutive_harmful_blocks=harmful_run,
        )
        classified.append(
            CfoLiftReplayRowV4(
                branch_id=candidate.branch_id,
                canonical_model_id=candidate.model_id,
                alias_index=candidate.alias_index,
                tier=tier,
                automatic_correction_eligible=tier is LiftReplayTierV3.AUTOMATIC,
                geometry_display_eligible=geometry_ok,
                observation_count=len(model.observation_ids),
                duration_s=duration,
                residual_rms_hz=model.residual_rms_hz,
                residual_max_hz=model.residual_max_hz,
                polynomial_degree=model.polynomial_degree,
                evaluated_probe_count=len(values),
                evaluated_block_count=len(blocks),
                eligible_block_count=eligible_blocks,
                block_coverage_ratio=coverage,
                improved_block_count=sum(item.median_margin_delta > 0 for item in blocks),
                harmful_block_count=harmful_count,
                maximum_consecutive_harmful_blocks=harmful_run,
                median_block_margin_delta=median_delta,
                q10_block_margin_delta=q10_delta,
                median_block_corrected_margin=median_corrected,
                blocks=blocks,
                reasons=reasons,
            )
        )
    ordered = tuple(sorted(classified, key=lambda item: (item.branch_id, item.alias_index)))
    keys = tuple(f"{row.branch_id}:{row.alias_index}" for row in ordered)
    document = {
        "gate_config": gate_config.model_dump(mode="json"),
        "gate_config_digest": gate_config.digest,
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "source_lift_count": source_lift_count,
        "returned_lift_count": len(ordered),
        "truncated_lift_count": source_lift_count - len(ordered),
        "rows": [item.model_dump(mode="json") for item in ordered],
        "automatic_correction_lifts": [
            key for key, row in zip(keys, ordered, strict=True) if row.automatic_correction_eligible
        ],
        "geometry_display_lifts": [
            key for key, row in zip(keys, ordered, strict=True) if row.geometry_display_eligible
        ],
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    document["content_digest"] = canonical_digest(
        {"schema_version": 4, "algorithm_version": "cfo-lift-replay-v4", **document}
    )
    return CfoLiftReplayV4.model_validate(document)


def classify_replay_tier_v4(
    *,
    geometry_ok: bool,
    enough_replay: bool,
    harmful_block_count: int,
    maximum_consecutive_harmful_blocks: int,
) -> tuple[LiftReplayTierV3, tuple[str, ...]]:
    audit = (
        "harmful-block metrics are audit-only: "
        f"count={harmful_block_count}, run={maximum_consecutive_harmful_blocks}"
    )
    if not geometry_ok:
        return LiftReplayTierV3.INSUFFICIENT, (
            "geometry did not meet observation, duration, or residual-quality gates",
            audit,
        )
    if not enough_replay:
        return LiftReplayTierV3.GEOMETRY_ONLY, (
            "credible geometry retained, but probe count or replay coverage was insufficient",
            audit,
        )
    return LiftReplayTierV3.AUTOMATIC, (
        "geometry and replay coverage passed; corrected-margin and harmful-block metrics are "
        "audit-only",
        audit,
    )


def _aggregate_replay_blocks_v3(
    values: list[dict[str, object]], config: ReplayGateConfigV3 | ReplayGateConfigV4
) -> tuple[ReplayBlockMetricV3, ...]:
    grouped: dict[int, list[tuple[float, float]]] = {}
    for row in values:
        sample_start = row.get("sample_start")
        if isinstance(sample_start, bool) or not isinstance(sample_start, int) or sample_start < 0:
            raise ValueError("V3 replay row sample_start must be a non-negative integer")
        grouped.setdefault(sample_start // config.samples_per_block, []).append(
            (_finite_row_number(row, "margin_delta"), _finite_row_number(row, "corrected_margin"))
        )
    return tuple(
        ReplayBlockMetricV3(
            block_index=i,
            probe_count=len(rows),
            median_margin_delta=float(np.median([v[0] for v in rows])),
            median_corrected_margin=float(np.median([v[1] for v in rows])),
        )
        for i, rows in sorted(grouped.items())
    )


def _aggregate_replay_blocks_v4(
    values: list[dict[str, object]], config: ReplayGateConfigV4
) -> tuple[ReplayBlockMetricV4, ...]:
    return tuple(
        ReplayBlockMetricV4(
            block_index=item.block_index,
            probe_count=item.probe_count,
            median_margin_delta=item.median_margin_delta,
            median_corrected_margin=item.median_corrected_margin,
        )
        for item in _aggregate_replay_blocks_v3(values, config)
    )


def _aggregate_replay_blocks_v2(
    values: list[dict[str, object]], config: ReplayGateConfigV2
) -> tuple[ReplayBlockMetricV2, ...]:
    grouped: dict[int, list[tuple[float, float]]] = {}
    for row in values:
        sample_start = row.get("sample_start")
        if isinstance(sample_start, bool) or not isinstance(sample_start, int) or sample_start < 0:
            raise ValueError("V2 replay row sample_start must be a non-negative integer")
        grouped.setdefault(sample_start // config.samples_per_block, []).append(
            (
                _finite_row_number(row, "margin_delta"),
                _finite_row_number(row, "corrected_margin"),
            )
        )
    return tuple(
        ReplayBlockMetricV2(
            block_index=block_index,
            probe_count=len(rows),
            median_margin_delta=float(np.median([item[0] for item in rows])),
            median_corrected_margin=float(np.median([item[1] for item in rows])),
        )
        for block_index, rows in sorted(grouped.items())
    )


def _maximum_true_run(values: tuple[bool, ...]) -> int:
    maximum = current = 0
    for value in values:
        current = current + 1 if value else 0
        maximum = max(maximum, current)
    return maximum


def _observed_lift_candidates_v2(
    bank: DealiasedTrajectoryBankV1 | DealiasedTrajectoryBankV2 | DealiasedTrajectoryBankV3,
    config: CfoDealiasConfigV1,
    gate: ReplayGateConfigV2 | ReplayGateConfigV3 | ReplayGateConfigV4,
) -> tuple[tuple[_ObservedLiftCandidate, ...], int]:
    """Construct V2 candidates, preferring a simpler statistically equivalent model."""

    result = []
    source_count = sum(len(item.observed_alias_indices) for item in bank.branches)
    for branch in bank.branches:
        best_bic = min(model.bic for model in branch.models)
        model = min(
            (
                model
                for model in branch.models
                if model.bic <= best_bic + gate.simpler_model_bic_delta
            ),
            key=lambda item: (item.polynomial_degree, item.bic, item.model_id),
        )
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
                    "gate_version": gate.gate_version,
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
