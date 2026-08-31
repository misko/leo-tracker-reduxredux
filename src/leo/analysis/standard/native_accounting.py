"""IQ-free trajectory accounting projection for sealed Standard-native science."""

from __future__ import annotations

import math
from collections import defaultdict

from leo.analysis.standard.trajectory_accounting import (
    render_trajectory_conditioned_accounting_v2_png,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native_accounting import (
    StandardNativeTrajectoryAccountingSegmentV3,
    StandardNativeTrajectoryConditionedAccountingV3,
    StandardNativeTrajectoryConditionedAccountingV4,
)
from leo.contracts.standard_native_stateful import (
    NativeConditionedHoughReplayRowV1,
    NativePilotCandidateV1,
    NativePilotMethodScoreV1,
    NativePilotProbeDetectionV1,
    NativePolynomialTrajectoryV1,
)
from leo.contracts.standard_native_stateful_v2 import (
    StandardNativeStatefulPathV2,
    StandardNativeStatefulPathV3,
)
from leo.contracts.trajectory_accounting import (
    ReplayTransitionCountsV1,
    TrajectoryAccountingConfigV2,
    TrajectoryConditionedEvaluationV2,
    TrajectoryConditionedReplayAccountingV2,
    TrajectoryReplayComparisonSummaryV2,
)


def _sum_transitions(
    values: tuple[ReplayTransitionCountsV1, ...],
) -> ReplayTransitionCountsV1:
    return ReplayTransitionCountsV1(
        positive_to_positive=sum(item.positive_to_positive for item in values),
        positive_to_negative=sum(item.positive_to_negative for item in values),
        negative_to_positive=sum(item.negative_to_positive for item in values),
        negative_to_negative=sum(item.negative_to_negative for item in values),
    )


def _transition_counts(pairs: list[tuple[bool, bool]]) -> ReplayTransitionCountsV1:
    return ReplayTransitionCountsV1(
        positive_to_positive=pairs.count((True, True)),
        positive_to_negative=pairs.count((True, False)),
        negative_to_positive=pairs.count((False, True)),
        negative_to_negative=pairs.count((False, False)),
    )


def _glrt64_score(
    scores: tuple[NativePilotMethodScoreV1, ...],
) -> NativePilotMethodScoreV1 | None:
    return next((item for item in scores if item.method == "glrt64"), None)


def _conditioned_candidate(
    detection: NativePilotProbeDetectionV1,
    row: NativeConditionedHoughReplayRowV1,
    trajectory: NativePolynomialTrajectoryV1,
    *,
    alias_spacing_hz: float,
) -> NativePilotCandidateV1:
    assert row.conditioned_epoch_sample is not None
    candidates = detection.candidates
    if not candidates:
        if (
            detection.local_epoch_sample is None
            or detection.acquired_cfo_hz is None
            or not detection.scores
        ):
            raise ValueError("conditioned replay has no persisted baseline candidate inventory")
        candidates = (
            NativePilotCandidateV1(
                rank=0,
                local_epoch_sample=detection.local_epoch_sample,
                acquired_cfo_hz=detection.acquired_cfo_hz,
                scores=detection.scores,
                qam_accuracy=detection.qam_accuracy,
                qam_evm=detection.qam_evm,
            ),
        )
    matches = tuple(
        item
        for item in candidates
        if item.local_epoch_sample == row.conditioned_epoch_sample
        and _glrt64_score(item.scores) is not None
    )
    if not matches:
        raise ValueError("conditioned replay epoch does not name one persisted GLRT64 candidate")
    if not math.isfinite(alias_spacing_hz) or alias_spacing_hz <= 0.0:
        raise ValueError("native conditioned replay alias spacing must be finite and positive")
    assert row.conditioned_seed_cfo_hz is not None
    relative_time_s = row.time_s - trajectory.reference_time_s
    trajectory_frequency_hz = 0.0
    for coefficient in trajectory.coefficients_hz:
        trajectory_frequency_hz = trajectory_frequency_hz * relative_time_s + coefficient
    ranked: list[tuple[float, int, int, NativePilotCandidateV1]] = []
    for item in matches:
        item_score = _glrt64_score(item.scores)
        assert item_score is not None
        inferred_offset_hz = (
            item_score.tracking_cfo_hz - trajectory_frequency_hz - row.conditioned_seed_cfo_hz
        )
        alias_index = round(inferred_offset_hz / alias_spacing_hz)
        residual_hz = abs(inferred_offset_hz - alias_index * alias_spacing_hz)
        ranked.append((residual_hz, alias_index, item.rank, item))
    ranked.sort(key=lambda value: (value[0], value[2]))
    tolerance_hz = max(1e-6, alias_spacing_hz * 1e-12)
    if ranked[0][0] > tolerance_hz:
        raise ValueError("conditioned replay candidate does not close to an integer alias lift")
    equivalent = tuple(item for item in ranked if item[0] <= ranked[0][0] + tolerance_hz)
    if len({item[1] for item in equivalent}) != 1:
        raise ValueError("conditioned replay epoch names ambiguous persisted alias lifts")
    return min((item[3] for item in equivalent), key=lambda item: item.rank)


def _accounting_from_sealed_replay(
    detections: tuple[NativePilotProbeDetectionV1, ...],
    representatives: tuple[NativePolynomialTrajectoryV1, ...],
    replay: tuple[NativeConditionedHoughReplayRowV1, ...],
    *,
    pilot_scan_digest: str,
    trajectory_bank_digest: str,
    trajectory_feedback_digest: str,
    alias_spacing_hz: float,
    config: TrajectoryAccountingConfigV2,
) -> TrajectoryConditionedReplayAccountingV2:
    """Project exact persisted replay association without recomputing alias geometry."""

    detections_by_sample = {item.sample_start: item for item in detections}
    if len(detections_by_sample) != len(detections):
        raise ValueError("native accounting detections must have unique sample starts")
    trajectories_by_id = {item.trajectory_id: item for item in representatives}
    if len(trajectories_by_id) != len(representatives):
        raise ValueError("native accounting representatives must be unique")
    selected = tuple(item for item in replay if item.detector_method == "glrt64")
    identities = tuple((item.trajectory_id, item.sample_start) for item in selected)
    if len(set(identities)) != len(identities):
        raise ValueError("native conditioned GLRT64 replay rows must be unique")

    evaluations: list[TrajectoryConditionedEvaluationV2] = []
    for row in selected:
        trajectory = trajectories_by_id.get(row.trajectory_id)
        if trajectory is None:
            raise ValueError("native conditioned replay names an unknown representative")
        detection = detections_by_sample.get(row.sample_start)
        if detection is None:
            raise ValueError("native conditioned replay lies outside the detection inventory")
        global_score = _glrt64_score(detection.scores)
        candidate = None
        candidate_score = None
        association_error_hz = None
        if row.conditioned_corrected_margin is not None:
            candidate = _conditioned_candidate(
                detection,
                row,
                trajectory,
                alias_spacing_hz=alias_spacing_hz,
            )
            candidate_score = _glrt64_score(candidate.scores)
            assert candidate_score is not None
            assert row.conditioned_seed_cfo_hz is not None
            association_error_hz = abs(row.conditioned_seed_cfo_hz)
            if association_error_hz > config.association_gate_hz + 1e-12:
                raise ValueError("persisted conditioned replay exceeds its association gate")
        evaluations.append(
            TrajectoryConditionedEvaluationV2(
                trajectory_id=row.trajectory_id,
                sample_start=row.sample_start,
                time_s=row.time_s,
                detector_method="glrt64",
                reacquired_winner_margin=row.corrected_margin,
                reacquired_winner_tracking_cfo_hz=row.corrected_residual_cfo_hz,
                conditioned_corrected_margin=row.conditioned_corrected_margin,
                conditioned_tracking_cfo_hz=row.conditioned_tracking_cfo_hz,
                conditioned_epoch_sample=row.conditioned_epoch_sample,
                conditioned_seed_cfo_hz=row.conditioned_seed_cfo_hz,
                global_baseline_margin=(None if global_score is None else global_score.margin),
                baseline_candidate_rank=None if candidate is None else candidate.rank,
                baseline_candidate_epoch_sample=(
                    None if candidate is None else candidate.local_epoch_sample
                ),
                baseline_candidate_acquired_cfo_hz=(
                    None if candidate is None else candidate.acquired_cfo_hz
                ),
                baseline_association_error_hz=association_error_hz,
                baseline_tracking_cfo_hz=(
                    None if candidate_score is None else candidate_score.tracking_cfo_hz
                ),
                baseline_margin=None if candidate_score is None else candidate_score.margin,
            )
        )
    ordered = tuple(
        sorted(
            evaluations,
            key=lambda item: (item.trajectory_id, item.sample_start, item.detector_method),
        )
    )
    threshold = config.positive_margin
    matched = tuple(item for item in ordered if item.baseline_margin is not None)

    def associated_pairs(field: str) -> list[tuple[bool, bool]]:
        result: list[tuple[bool, bool]] = []
        for item in matched:
            corrected = getattr(item, field)
            assert item.baseline_margin is not None
            if corrected is None:
                raise ValueError("matched native conditioned replay row has no corrected score")
            result.append((item.baseline_margin >= threshold, corrected >= threshold))
        return result

    by_trajectory: dict[str, list[TrajectoryConditionedEvaluationV2]] = defaultdict(list)
    by_sample: dict[int, list[TrajectoryConditionedEvaluationV2]] = defaultdict(list)
    for item in ordered:
        by_trajectory[item.trajectory_id].append(item)
        by_sample[item.sample_start].append(item)
    trajectory_summaries: list[TrajectoryReplayComparisonSummaryV2] = []
    for trajectory_id, rows in sorted(by_trajectory.items()):
        associated = [item for item in rows if item.baseline_margin is not None]
        reacquired_pairs: list[tuple[bool, bool]] = []
        conditioned_pairs: list[tuple[bool, bool]] = []
        for item in associated:
            assert item.baseline_margin is not None
            assert item.conditioned_corrected_margin is not None
            baseline_positive = item.baseline_margin >= threshold
            reacquired_pairs.append((baseline_positive, item.reacquired_winner_margin >= threshold))
            conditioned_pairs.append(
                (baseline_positive, item.conditioned_corrected_margin >= threshold)
            )
        unassociated = [item for item in rows if item.baseline_margin is None]
        trajectory_summaries.append(
            TrajectoryReplayComparisonSummaryV2(
                trajectory_id=trajectory_id,
                evaluation_count=len(rows),
                associated_count=len(associated),
                unassociated_count=len(unassociated),
                unassociated_reacquired_positive_count=sum(
                    item.reacquired_winner_margin >= threshold for item in unassociated
                ),
                reacquired_transitions=_transition_counts(reacquired_pairs),
                conditioned_transitions=_transition_counts(conditioned_pairs),
            )
        )
    reacquired_unique_pairs: list[tuple[bool, bool]] = []
    conditioned_unique_pairs: list[tuple[bool, bool]] = []
    for rows in by_sample.values():
        global_margins = [
            item.global_baseline_margin for item in rows if item.global_baseline_margin is not None
        ]
        if not global_margins:
            continue
        baseline_positive = max(global_margins) >= threshold
        reacquired_unique_pairs.append(
            (baseline_positive, max(item.reacquired_winner_margin for item in rows) >= threshold)
        )
        conditioned_margins = [
            item.conditioned_corrected_margin
            for item in rows
            if item.conditioned_corrected_margin is not None
        ]
        conditioned_unique_pairs.append(
            (
                baseline_positive,
                bool(conditioned_margins) and max(conditioned_margins) >= threshold,
            )
        )
    return TrajectoryConditionedReplayAccountingV2(
        pilot_scan_digest=pilot_scan_digest,
        trajectory_bank_digest=trajectory_bank_digest,
        trajectory_feedback_digest=trajectory_feedback_digest,
        configuration_digest=config.digest,
        configuration=config,
        evaluation_count=len(ordered),
        associated_evaluation_count=len(matched),
        unassociated_evaluation_count=len(ordered) - len(matched),
        evaluations=ordered,
        trajectories=tuple(trajectory_summaries),
        reacquired_associated_transitions=_transition_counts(
            associated_pairs("reacquired_winner_margin")
        ),
        conditioned_associated_transitions=_transition_counts(
            associated_pairs("conditioned_corrected_margin")
        ),
        reacquired_unique_probe_transitions=_transition_counts(reacquired_unique_pairs),
        conditioned_unique_probe_transitions=_transition_counts(conditioned_unique_pairs),
    )


def build_standard_native_trajectory_accounting_v3(
    stateful: StandardNativeStatefulPathV2 | StandardNativeStatefulPathV3,
    *,
    configuration: TrajectoryAccountingConfigV2,
) -> (
    StandardNativeTrajectoryConditionedAccountingV3
    | StandardNativeTrajectoryConditionedAccountingV4
):
    """Derive reset-local accounting only from the sealed stateful document."""

    segments: list[StandardNativeTrajectoryAccountingSegmentV3] = []
    for segment in stateful.segments:
        science = segment.local_science
        accounting: TrajectoryConditionedReplayAccountingV2 | None = None
        feedback_digest = None
        if science is not None:
            feedback_digest = canonical_digest(
                {
                    "kind": "standard-native-segment-local-trajectory-feedback-v1",
                    "segment_path_binding_digest": science.segment_path_binding_digest,
                    "pilot_scan_digest": science.pilot_scan_digest,
                    "raw_trajectory_bank_digest": science.raw_trajectory_bank_digest,
                    "conditioned_hough_replay": tuple(
                        item.model_dump(mode="json") for item in science.conditioned_hough_replay
                    ),
                }
            )
            accounting = _accounting_from_sealed_replay(
                science.detections,
                tuple(item.trajectory for item in science.residual_hough_representatives),
                science.conditioned_hough_replay,
                pilot_scan_digest=science.pilot_scan_digest,
                trajectory_bank_digest=science.raw_trajectory_bank_digest,
                trajectory_feedback_digest=feedback_digest,
                alias_spacing_hz=(
                    science.cfo_alias_map.alias_spacing_numerator_hz
                    / science.cfo_alias_map.alias_spacing_denominator
                ),
                config=configuration,
            )
        values = {
            "schema_version": 3,
            "continuity_segment_index": segment.continuity_segment_index,
            "global_device_sample_start": segment.global_device_sample_start,
            "global_device_sample_stop": segment.global_device_sample_stop,
            "stateful_segment_digest": segment.segment_digest,
            "stateful_disposition": segment.disposition.value,
            "local_science_digest": None if science is None else science.science_digest,
            "trajectory_feedback_digest": feedback_digest,
            "accounting": None if accounting is None else accounting.model_dump(mode="json"),
        }
        segments.append(
            StandardNativeTrajectoryAccountingSegmentV3.model_validate(
                {**values, "segment_digest": canonical_digest(values)}
            )
        )
    accounted = tuple(item.accounting for item in segments if item.accounting is not None)
    transition_fields = (
        "reacquired_associated_transitions",
        "conditioned_associated_transitions",
        "reacquired_unique_probe_transitions",
        "conditioned_unique_probe_transitions",
    )
    wideband = isinstance(stateful, StandardNativeStatefulPathV3)
    values = {
        "schema_version": 4 if wideband else 3,
        "algorithm_version": (
            "standard-native-trajectory-accounting-v4"
            if wideband
            else "standard-native-trajectory-accounting-v3"
        ),
        "source": stateful.source.model_dump(mode="json"),
        "stateful_path_digest": stateful.stateful_path_digest,
        "science_configuration_digest": stateful.science_configuration_digest,
        "configuration": configuration.model_dump(mode="json"),
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "accounted_segment_count": len(accounted),
        "evaluation_count": sum(item.evaluation_count for item in accounted),
        "associated_evaluation_count": sum(item.associated_evaluation_count for item in accounted),
        "unassociated_evaluation_count": sum(
            item.unassociated_evaluation_count for item in accounted
        ),
        **{
            field: _sum_transitions(tuple(getattr(item, field) for item in accounted)).model_dump(
                mode="json"
            )
            for field in transition_fields
        },
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "cross_segment_association_permitted": False,
    }
    product_type = (
        StandardNativeTrajectoryConditionedAccountingV4
        if wideband
        else StandardNativeTrajectoryConditionedAccountingV3
    )
    return product_type.model_validate({**values, "content_digest": canonical_digest(values)})


def _aggregate_for_render(
    product: (
        StandardNativeTrajectoryConditionedAccountingV3
        | StandardNativeTrajectoryConditionedAccountingV4
    ),
) -> TrajectoryConditionedReplayAccountingV2:
    evaluations: list[TrajectoryConditionedEvaluationV2] = []
    trajectories: list[TrajectoryReplayComparisonSummaryV2] = []
    for segment in product.segments:
        accounting = segment.accounting
        if accounting is None:
            continue
        offset_samples = segment.global_device_sample_start
        offset_s = offset_samples / product.source.sample_rate_hz
        identities = {
            item.trajectory_id: canonical_digest(
                {
                    "kind": "standard-native-global-accounting-trajectory-v1",
                    "continuity_segment_index": segment.continuity_segment_index,
                    "trajectory_id": item.trajectory_id,
                }
            )
            for item in accounting.trajectories
        }
        evaluations.extend(
            item.model_copy(
                update={
                    "trajectory_id": identities[item.trajectory_id],
                    "sample_start": item.sample_start + offset_samples,
                    "time_s": item.time_s + offset_s,
                }
            )
            for item in accounting.evaluations
        )
        trajectories.extend(
            item.model_copy(update={"trajectory_id": identities[item.trajectory_id]})
            for item in accounting.trajectories
        )
    ordered_evaluations = tuple(
        sorted(
            evaluations,
            key=lambda item: (item.trajectory_id, item.sample_start, item.detector_method),
        )
    )
    ordered_trajectories = tuple(sorted(trajectories, key=lambda item: item.trajectory_id))
    return TrajectoryConditionedReplayAccountingV2(
        pilot_scan_digest=canonical_digest(
            {
                "kind": "standard-native-global-accounting-pilot-inventory-v1",
                "segments": tuple(item.segment_digest for item in product.segments),
            }
        ),
        trajectory_bank_digest=canonical_digest(
            {
                "kind": "standard-native-global-accounting-trajectory-inventory-v1",
                "trajectory_ids": tuple(item.trajectory_id for item in ordered_trajectories),
            }
        ),
        trajectory_feedback_digest=canonical_digest(
            {
                "kind": "standard-native-global-accounting-feedback-inventory-v1",
                "segments": tuple(
                    item.trajectory_feedback_digest
                    for item in product.segments
                    if item.trajectory_feedback_digest is not None
                ),
            }
        ),
        configuration_digest=product.configuration.digest,
        configuration=product.configuration,
        evaluation_count=product.evaluation_count,
        associated_evaluation_count=product.associated_evaluation_count,
        unassociated_evaluation_count=product.unassociated_evaluation_count,
        evaluations=ordered_evaluations,
        trajectories=ordered_trajectories,
        reacquired_associated_transitions=product.reacquired_associated_transitions,
        conditioned_associated_transitions=product.conditioned_associated_transitions,
        reacquired_unique_probe_transitions=product.reacquired_unique_probe_transitions,
        conditioned_unique_probe_transitions=product.conditioned_unique_probe_transitions,
    )


def render_standard_native_trajectory_accounting_png(
    product: (
        StandardNativeTrajectoryConditionedAccountingV3
        | StandardNativeTrajectoryConditionedAccountingV4
    ),
    *,
    path_label: str,
) -> bytes:
    """Reuse the reviewed Standard V2 view over one globalized reset-local inventory."""

    aggregate = _aggregate_for_render(product)
    return render_trajectory_conditioned_accounting_v2_png(
        ((path_label, aggregate.model_dump(mode="json")),),
        session_id=product.source.session_id,
    )
