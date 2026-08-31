"""Builder for the terminal Standard-native path report.

The builder has no IQ access.  It closes already-published path products,
same-call QAM evidence, the exact global probe schedule, and reset-local final
trajectory inventories into one evidence-only report.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from leo.analysis.standard.native_qam import merge_native_qam_sufficient_statistics
from leo.contracts.base import ContractModel
from leo.contracts.cfo_dealias import FinalTrajectoryV3
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import (
    NativeProbeWindowV3,
    NativeWindowDisposition,
    StandardNativeNumericalWaterfallV3,
    StandardNativeNumericalWaterfallV4,
    StandardNativePowerTimelineV3,
    StandardNativePowerTimelineV4,
    StandardNativeQualityV2,
    StandardNativeQualityV3,
    StandardNativeSourceV1,
    StandardNativeSourceV2,
    StandardProbeScheduleV3,
    StandardProbeScheduleV4,
)
from leo.contracts.standard_native_glrt import (
    StandardNativeFullCaptureGlrt20msV1,
    StandardNativeFullCaptureGlrt20msV2,
)
from leo.contracts.standard_native_path_report import (
    NativePathProductDigestsV1,
    NativePathScientificDispositionV1,
    NativePathSegmentReportV1,
    NativeProbeExecutionAccountingV1,
    NativeProbeExecutionDispositionV1,
    NativeProbeExecutionV1,
    NativeProbeScheduleExecutionV1,
    NativeQamComputationStatusV1,
    NativeQamProbeEvidenceV1,
    StandardNativePathReportV3,
    StandardNativePathReportV4,
)
from leo.contracts.standard_native_stateful import NativePilotProbeDetectionV1
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentV2,
    StandardNativeStatefulPathV2,
    StandardNativeStatefulPathV3,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4, StandardPathInputBindV5


def build_standard_native_path_report(
    binding: StandardPathInputBindV4 | StandardPathInputBindV5,
    *,
    quality: StandardNativeQualityV2 | StandardNativeQualityV3,
    quality_product_digest: Sha256Digest,
    power_timeline: StandardNativePowerTimelineV3 | StandardNativePowerTimelineV4,
    power_timeline_product_digest: Sha256Digest,
    numerical_waterfall: StandardNativeNumericalWaterfallV3 | StandardNativeNumericalWaterfallV4,
    numerical_waterfall_product_digest: Sha256Digest,
    probe_schedule: StandardProbeScheduleV3 | StandardProbeScheduleV4,
    probe_schedule_product_digest: Sha256Digest,
    stateful_path: StandardNativeStatefulPathV2 | StandardNativeStatefulPathV3,
    stateful_path_product_digest: Sha256Digest,
    full_capture_glrt20ms: (
        StandardNativeFullCaptureGlrt20msV1 | StandardNativeFullCaptureGlrt20msV2
    ),
    full_capture_glrt20ms_product_digest: Sha256Digest,
    qam_probe_evidence: Iterable[NativeQamProbeEvidenceV1],
) -> StandardNativePathReportV3 | StandardNativePathReportV4:
    """Close one processing-complete path report from six executable products."""

    source = (
        StandardNativeSourceV2.from_path_binding(binding)
        if isinstance(binding, StandardPathInputBindV5)
        else StandardNativeSourceV1.from_path_binding(binding)
    )
    wideband = isinstance(source, StandardNativeSourceV2)
    _require_product(quality, quality_product_digest, source=source)
    _require_product(power_timeline, power_timeline_product_digest, source=source)
    _require_product(numerical_waterfall, numerical_waterfall_product_digest, source=source)
    _require_product(probe_schedule, probe_schedule_product_digest, source=source)
    _require_product(stateful_path, stateful_path_product_digest, source=source)
    _require_product(
        full_capture_glrt20ms,
        full_capture_glrt20ms_product_digest,
        source=source,
    )
    if (
        stateful_path.starlink_edge != binding.starlink_edge
        or full_capture_glrt20ms.starlink_edge != binding.starlink_edge
    ):
        raise ValueError("native path products changed the V4 Starlink edge authority")

    detections = _detections_by_opportunity(probe_schedule, stateful_path)
    qam_by_opportunity = _canonical_qam_evidence(qam_probe_evidence)
    valid_indexes = {
        index
        for index, opportunity in enumerate(probe_schedule.opportunities)
        if opportunity.validity.disposition is NativeWindowDisposition.VALID
    }
    if set(detections) != valid_indexes:
        raise ValueError("native stateful detections do not close every valid probe")
    if set(qam_by_opportunity) != valid_indexes:
        raise ValueError("native QAM evidence does not close every valid probe")

    executions = tuple(
        _build_probe_execution(
            index,
            opportunity,
            detection=detections.get(index),
            qam=qam_by_opportunity.get(index),
        )
        for index, opportunity in enumerate(probe_schedule.opportunities)
    )
    execution_accounting = _execution_accounting(executions)
    execution_values = {
        "schema_version": 1,
        "source_schedule_digest": probe_schedule.schedule_digest,
        "opportunities": tuple(item.model_dump(mode="json") for item in executions),
        "accounting": execution_accounting.model_dump(mode="json"),
        "processing_complete": True,
    }
    schedule_execution = NativeProbeScheduleExecutionV1.model_validate(
        {**execution_values, "execution_digest": canonical_digest(execution_values)}
    )
    segments = tuple(
        _build_segment_report(item, sample_rate_hz=source.sample_rate_hz)
        for item in stateful_path.segments
    )
    qam_statistics = merge_native_qam_sufficient_statistics(
        tuple(item.statistics for item in qam_by_opportunity.values())
    )

    product_values = {
        "schema_version": 1,
        "quality_product_digest": quality_product_digest,
        "power_timeline_product_digest": power_timeline_product_digest,
        "numerical_waterfall_product_digest": numerical_waterfall_product_digest,
        "probe_schedule_product_digest": probe_schedule_product_digest,
        "stateful_path_product_digest": stateful_path_product_digest,
        "full_capture_glrt20ms_product_digest": full_capture_glrt20ms_product_digest,
    }
    products = NativePathProductDigestsV1.model_validate(
        {**product_values, "product_set_digest": canonical_digest(product_values)}
    )
    scientific_disposition, scientific_reason = _scientific_disposition(execution_accounting)
    frequency_reference_digest = canonical_digest(
        binding.frequency_reference.model_dump(mode="json")
    )
    report_values = {
        "schema_version": 4 if wideband else 3,
        "algorithm_version": (
            "standard-native-path-report-v4" if wideband else "standard-native-path-report-v3"
        ),
        "source": source.model_dump(mode="json"),
        "starlink_edge": binding.starlink_edge.value,
        "frequency_reference": binding.frequency_reference.model_dump(mode="json"),
        "frequency_reference_digest": frequency_reference_digest,
        "products": products.model_dump(mode="json"),
        "schedule_execution": schedule_execution.model_dump(mode="json"),
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "qam_statistics": qam_statistics.model_dump(mode="json"),
        "processing_status": "complete",
        "scientific_disposition": scientific_disposition.value,
        "scientific_reason": scientific_reason,
        "cross_segment_association_permitted": False,
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    report_type = StandardNativePathReportV4 if wideband else StandardNativePathReportV3
    return report_type.model_validate(
        {**report_values, "report_digest": canonical_digest(report_values)}
    )


def _require_product(
    product: ContractModel,
    product_digest: Sha256Digest,
    *,
    source: StandardNativeSourceV1 | StandardNativeSourceV2,
) -> None:
    product_source = getattr(product, "source", None)
    if product_source != source:
        raise ValueError("native path report received a product with foreign source authority")
    if product_digest != canonical_digest(product.model_dump(mode="json")):
        raise ValueError("native path report product digest does not match exact product bytes")


def _detections_by_opportunity(
    schedule: StandardProbeScheduleV3 | StandardProbeScheduleV4,
    stateful: StandardNativeStatefulPathV2 | StandardNativeStatefulPathV3,
) -> dict[int, NativePilotProbeDetectionV1]:
    by_start = {
        opportunity.probe.sample_start: (index, opportunity)
        for index, opportunity in enumerate(schedule.opportunities)
    }
    completed: dict[int, NativePilotProbeDetectionV1] = {}
    for segment in stateful.segments:
        science = segment.local_science
        if science is None:
            continue
        for detection in science.detections:
            global_start = segment.global_device_sample_start + detection.sample_start
            resolved = by_start.get(global_start)
            if resolved is None:
                raise ValueError("native stateful detection is outside the global probe schedule")
            opportunity_index, opportunity = resolved
            validity = opportunity.validity
            if (
                validity.disposition is not NativeWindowDisposition.VALID
                or validity.continuity_segment_index != segment.continuity_segment_index
                or opportunity_index in completed
            ):
                raise ValueError("native stateful detection crossed or repeated a schedule probe")
            completed[opportunity_index] = detection
    return completed


def _canonical_qam_evidence(
    evidence: Iterable[NativeQamProbeEvidenceV1],
) -> dict[int, NativeQamProbeEvidenceV1]:
    values = tuple(evidence)
    indexes = tuple(item.opportunity_index for item in values)
    if indexes != tuple(sorted(set(indexes))):
        raise ValueError("native QAM probe evidence is not unique and ordered")
    return {item.opportunity_index: item for item in values}


def _build_probe_execution(
    opportunity_index: int,
    opportunity: NativeProbeWindowV3,
    *,
    detection: NativePilotProbeDetectionV1 | None,
    qam: NativeQamProbeEvidenceV1 | None,
) -> NativeProbeExecutionV1:
    validity = opportunity.validity
    if validity.disposition is NativeWindowDisposition.VALID:
        if detection is None or qam is None:
            raise ValueError("valid native probe lacks terminal execution evidence")
        if (
            qam.detection_status != detection.status
            or qam.primary_candidate_rank != (0 if detection.status == "complete" else None)
            or qam.primary_local_epoch_sample != detection.local_epoch_sample
            or qam.primary_acquired_cfo_hz != detection.acquired_cfo_hz
        ):
            raise ValueError("native QAM evidence changed the stateful primary candidate")
        _require_stateful_qam_metrics(detection, qam)
        detection_status: str | None = detection.status
        disposition = {
            "complete": NativeProbeExecutionDispositionV1.ANALYZED_CANDIDATE,
            "no_result": NativeProbeExecutionDispositionV1.ANALYZED_NO_CANDIDATE,
            "insufficient": NativeProbeExecutionDispositionV1.ANALYZED_INSUFFICIENT,
        }[detection.status]
    else:
        if detection is not None or qam is not None:
            raise ValueError("excluded native probe received scientific execution")
        detection_status = None
        disposition = {
            NativeWindowDisposition.GAP_OVERLAP: NativeProbeExecutionDispositionV1.EXCLUDED_GAP,
            NativeWindowDisposition.CONTINUITY_BOUNDARY: (
                NativeProbeExecutionDispositionV1.EXCLUDED_CONTINUITY_BOUNDARY
            ),
            NativeWindowDisposition.OUTSIDE_SPAN: (
                NativeProbeExecutionDispositionV1.EXCLUDED_OUTSIDE_SPAN
            ),
        }[validity.disposition]
    values = {
        "schema_version": 1,
        "opportunity_index": opportunity_index,
        "opportunity": opportunity.model_dump(mode="json"),
        "disposition": disposition.value,
        "detection_status": detection_status,
        "qam": None if qam is None else qam.model_dump(mode="json"),
    }
    return NativeProbeExecutionV1.model_validate(
        {**values, "execution_digest": canonical_digest(values)}
    )


def _require_stateful_qam_metrics(
    detection: NativePilotProbeDetectionV1,
    qam: NativeQamProbeEvidenceV1,
) -> None:
    measured = qam.qam_status is NativeQamComputationStatusV1.COMPLETE
    detection_metrics = (detection.qam_accuracy, detection.qam_evm)
    if measured:
        if not all(item is not None for item in detection_metrics):
            raise ValueError("complete stateful QAM detection lacks measured metrics")
        assert detection.qam_accuracy is not None
        assert detection.qam_evm is not None
        assert qam.statistics.hard_symbol_accuracy is not None
        assert qam.statistics.rms_evm is not None
        if not math.isclose(
            detection.qam_accuracy,
            float(qam.statistics.hard_symbol_accuracy),
            abs_tol=1e-15,
        ) or not math.isclose(
            detection.qam_evm,
            float(qam.statistics.rms_evm),
            rel_tol=1e-6,
            abs_tol=1e-12,
        ):
            raise ValueError("stateful QAM metrics disagree with same-call sufficient statistics")
    elif any(item is not None for item in detection_metrics):
        raise ValueError("noncomplete stateful QAM detection carries measured metrics")


def _execution_accounting(
    executions: tuple[NativeProbeExecutionV1, ...],
) -> NativeProbeExecutionAccountingV1:
    dispositions = tuple(item.disposition for item in executions)
    qam_statuses = tuple(item.qam.qam_status for item in executions if item.qam is not None)
    analyzed_count = sum(item.detection_status is not None for item in executions)
    return NativeProbeExecutionAccountingV1(
        scheduled_count=len(executions),
        valid_count=analyzed_count,
        analyzed_count=analyzed_count,
        candidate_count=dispositions.count(NativeProbeExecutionDispositionV1.ANALYZED_CANDIDATE),
        no_candidate_count=dispositions.count(
            NativeProbeExecutionDispositionV1.ANALYZED_NO_CANDIDATE
        ),
        insufficient_count=dispositions.count(
            NativeProbeExecutionDispositionV1.ANALYZED_INSUFFICIENT
        ),
        gap_excluded_count=dispositions.count(NativeProbeExecutionDispositionV1.EXCLUDED_GAP),
        continuity_boundary_excluded_count=dispositions.count(
            NativeProbeExecutionDispositionV1.EXCLUDED_CONTINUITY_BOUNDARY
        ),
        outside_span_count=dispositions.count(
            NativeProbeExecutionDispositionV1.EXCLUDED_OUTSIDE_SPAN
        ),
        qam_complete_count=qam_statuses.count(NativeQamComputationStatusV1.COMPLETE),
        qam_no_result_count=qam_statuses.count(NativeQamComputationStatusV1.NO_RESULT),
        qam_insufficient_count=qam_statuses.count(NativeQamComputationStatusV1.INSUFFICIENT),
        qam_not_evaluated_count=qam_statuses.count(NativeQamComputationStatusV1.NOT_EVALUATED),
    )


def _build_segment_report(
    segment: NativeStatefulSegmentV2,
    *,
    sample_rate_hz: int,
) -> NativePathSegmentReportV1:
    science = segment.local_science
    trajectories: tuple[FinalTrajectoryV3, ...]
    if science is None:
        bank_digest = None
        status = None
        reason = None
        source_count = returned_count = truncated_count = 0
        trajectories = ()
    else:
        bank = science.final_trajectory_bank
        duration_s = segment.continuity_segment.observed_sample_count / sample_rate_hz
        if any(item.start_s < 0 or item.end_s > duration_s for item in bank.trajectories):
            raise ValueError("native final trajectory escaped its reset-local segment")
        bank_digest = bank.content_digest
        status = bank.status.value
        reason = bank.reason
        source_count = bank.source_trajectory_count
        returned_count = bank.returned_trajectory_count
        truncated_count = bank.truncated_trajectory_count
        trajectories = bank.trajectories
    values = {
        "schema_version": 1,
        "continuity_segment": segment.continuity_segment.model_dump(mode="json"),
        "stateful_disposition": segment.disposition.value,
        "stateful_segment_digest": segment.segment_digest,
        "final_trajectory_bank_digest": bank_digest,
        "final_trajectory_status": status,
        "final_trajectory_reason": reason,
        "source_trajectory_count": source_count,
        "returned_trajectory_count": returned_count,
        "truncated_trajectory_count": truncated_count,
        "final_trajectories": tuple(item.model_dump(mode="json") for item in trajectories),
    }
    return NativePathSegmentReportV1.model_validate(
        {**values, "segment_report_digest": canonical_digest(values)}
    )


def _scientific_disposition(
    accounting: NativeProbeExecutionAccountingV1,
) -> tuple[NativePathScientificDispositionV1, str]:
    if accounting.candidate_count:
        return (
            NativePathScientificDispositionV1.CANDIDATE,
            "one or more wholly-valid probes produced candidate-only known-pilot evidence",
        )
    if not accounting.valid_count or accounting.insufficient_count:
        return (
            NativePathScientificDispositionV1.INSUFFICIENT,
            "valid probe support was absent or scientifically insufficient",
        )
    return (
        NativePathScientificDispositionV1.NO_CANDIDATE,
        "all wholly-valid probes completed without a candidate",
    )
