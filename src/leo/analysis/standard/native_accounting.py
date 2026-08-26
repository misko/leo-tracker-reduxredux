"""IQ-free trajectory accounting projection for sealed Standard-native science."""

from __future__ import annotations

from leo.analysis.standard.trajectory_accounting import (
    build_trajectory_conditioned_accounting_v2,
    render_trajectory_conditioned_accounting_v2_png,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import PolynomialTrajectory
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native_accounting import (
    StandardNativeTrajectoryAccountingSegmentV3,
    StandardNativeTrajectoryConditionedAccountingV3,
)
from leo.contracts.standard_native_stateful import (
    NativePilotCandidateV1,
    NativePilotMethodScoreV1,
    NativePilotProbeDetectionV1,
    NativePolynomialTrajectoryV1,
)
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.trajectory_accounting import (
    ReplayTransitionCountsV1,
    TrajectoryAccountingConfigV2,
    TrajectoryConditionedEvaluationV2,
    TrajectoryConditionedReplayAccountingV2,
    TrajectoryReplayComparisonSummaryV2,
)


def _runtime_score(value: NativePilotMethodScoreV1) -> PilotMethodScore:
    return PilotMethodScore(
        method=PilotMethod(value.method),
        exact_score=value.exact_score,
        control_score=value.control_score,
        margin=value.margin,
        residual_cfo_hz=value.residual_cfo_hz,
        tracking_cfo_hz=value.tracking_cfo_hz,
    )


def _runtime_candidate(value: NativePilotCandidateV1) -> PilotMethodCandidate:
    return PilotMethodCandidate(
        rank=value.rank,
        local_epoch_sample=value.local_epoch_sample,
        acquired_cfo_hz=value.acquired_cfo_hz,
        scores=tuple(_runtime_score(item) for item in value.scores),
        qam_accuracy=value.qam_accuracy,
        qam_evm=value.qam_evm,
    )


def _runtime_detection(value: NativePilotProbeDetectionV1) -> PilotProbeDetection:
    return PilotProbeDetection(
        status=NumericalStatus(value.status),
        sample_start=value.sample_start,
        time_s=value.time_s,
        local_epoch_sample=value.local_epoch_sample,
        acquired_cfo_hz=value.acquired_cfo_hz,
        scores=tuple(_runtime_score(item) for item in value.scores),
        qam_accuracy=value.qam_accuracy,
        qam_evm=value.qam_evm,
        reason=value.reason,
        source_candidate_count=value.source_candidate_count,
        truncated_candidate_count=value.truncated_candidate_count,
        candidates=tuple(_runtime_candidate(item) for item in value.candidates),
    )


def _runtime_trajectory(value: NativePolynomialTrajectoryV1) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id=value.trajectory_id,
        method=PilotMethod(value.method),
        polynomial_degree=value.polynomial_degree,
        reference_time_s=value.reference_time_s,
        coefficients_hz=value.coefficients_hz,
        start_s=value.start_s,
        end_s=value.end_s,
        observation_ids=value.observation_ids,
        point_count=value.point_count,
        residual_rms_hz=value.residual_rms_hz,
        bic=value.bic,
        high_gate=value.high_gate,
        em_iterations=value.em_iterations,
        candidate_only=True,
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


def build_standard_native_trajectory_accounting_v3(
    stateful: StandardNativeStatefulPathV2,
    *,
    configuration: TrajectoryAccountingConfigV2,
) -> StandardNativeTrajectoryConditionedAccountingV3:
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
            alias_spacing_hz = (
                science.cfo_alias_map.alias_spacing_numerator_hz
                / science.cfo_alias_map.alias_spacing_denominator
            )
            accounting = build_trajectory_conditioned_accounting_v2(
                tuple(_runtime_detection(item) for item in science.detections),
                tuple(
                    (item.family_id, _runtime_trajectory(item.trajectory))
                    for item in science.residual_hough_representatives
                ),
                tuple(item.model_dump(mode="json") for item in science.conditioned_hough_replay),
                frequency_offsets_hz={
                    item.trajectory_id: item.relative_alias_index * alias_spacing_hz
                    for item in science.cfo_alias_map.members
                },
                pilot_scan_digest=science.pilot_scan_digest,
                trajectory_bank_digest=science.raw_trajectory_bank_digest,
                trajectory_feedback_digest=feedback_digest,
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
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-native-trajectory-accounting-v3",
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
    return StandardNativeTrajectoryConditionedAccountingV3.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )


def _aggregate_for_render(
    product: StandardNativeTrajectoryConditionedAccountingV3,
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
    product: StandardNativeTrajectoryConditionedAccountingV3,
    *,
    path_label: str,
) -> bytes:
    """Reuse the reviewed Standard V2 view over one globalized reset-local inventory."""

    aggregate = _aggregate_for_render(product)
    return render_trajectory_conditioned_accounting_v2_png(
        ((path_label, aggregate.model_dump(mode="json")),),
        session_id=product.source.session_id,
    )
