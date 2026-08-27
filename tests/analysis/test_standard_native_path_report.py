from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.qam.pilot import PilotQamMetrics, PilotQamResult
from leo.analysis.standard.native_path_report import build_standard_native_path_report
from leo.analysis.standard.native_qam import (
    empty_native_qam_statistics,
    native_qam_sufficient_statistics,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.contracts.base import ContractModel
from leo.contracts.cfo_dealias import FinalTrajectoryV3, LiftReplayTierV3
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import (
    NativeOpportunityAccountingV1,
    NativeProbeWindowV3,
    NativeWindowDisposition,
    NativeWindowEvidenceV1,
    StandardNativeNumericalWaterfallV3,
    StandardNativePowerTimelineV3,
    StandardNativeQualityV2,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_native_path_report import (
    NativePathScientificDispositionV1,
    NativeQamComputationStatusV1,
    NativeQamProbeEvidenceV1,
    StandardNativePathReportV3,
)
from leo.contracts.standard_native_stateful import (
    NativePilotMethodScoreV1,
    NativePilotProbeDetectionV1,
    NativeSegmentLocalScienceV1,
)
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentDispositionV2,
    NativeStatefulSegmentV2,
    StandardNativeStatefulPathV2,
)
from leo.contracts.standard_pipeline import (
    FrequencyReference,
    ProbeWindowV2,
    ReceiverFrequencyReferenceV1,
    StandardPathInputBindV4,
    StandardScientificStatus,
)
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)

_RATE = 2_500_000
_LOGICAL = 150_000
_PROBE = 50_000


def _digest(label: str) -> str:
    return canonical_digest({"test": label})


def _inventory(*, gapped: bool, stream_id: str = "stream-0") -> ValidityInventoryV1:
    if not gapped:
        return ValidityInventoryV1(
            stream_id=stream_id,
            timeline_sha256=_digest("timeline"),
            gap_map_content_digest=_digest("gap-map"),
            first_device_sample_counter=100,
            logical_sample_count=_LOGICAL,
            observed_sample_count=_LOGICAL,
            missing_sample_count=0,
            continuity_boundary_count=0,
            runs=(
                ValidityRunV1(
                    run_index=0,
                    device_sample_start=0,
                    sample_count=_LOGICAL,
                    content_kind=DeviceAxisContentKind.OBSERVED,
                    stored_sample_start=0,
                    continuity_segment_index=0,
                ),
            ),
            segments=(
                ContinuitySegmentV1(
                    segment_index=0,
                    device_sample_start=0,
                    device_sample_stop=_LOGICAL,
                    stored_sample_start=0,
                    stored_sample_stop=_LOGICAL,
                ),
            ),
        )
    return ValidityInventoryV1(
        stream_id=stream_id,
        timeline_sha256=_digest("timeline"),
        gap_map_content_digest=_digest("gap-map"),
        first_device_sample_counter=100,
        logical_sample_count=_LOGICAL,
        observed_sample_count=140_000,
        missing_sample_count=10_000,
        continuity_boundary_count=1,
        runs=(
            ValidityRunV1(
                run_index=0,
                device_sample_start=0,
                sample_count=50_000,
                content_kind=DeviceAxisContentKind.OBSERVED,
                stored_sample_start=0,
                continuity_segment_index=0,
            ),
            ValidityRunV1(
                run_index=1,
                device_sample_start=50_000,
                sample_count=10_000,
                content_kind=DeviceAxisContentKind.ZERO_FILL,
            ),
            ValidityRunV1(
                run_index=2,
                device_sample_start=60_000,
                sample_count=90_000,
                content_kind=DeviceAxisContentKind.OBSERVED,
                stored_sample_start=50_000,
                continuity_segment_index=1,
            ),
        ),
        segments=(
            ContinuitySegmentV1(
                segment_index=0,
                device_sample_start=0,
                device_sample_stop=50_000,
                stored_sample_start=0,
                stored_sample_stop=50_000,
            ),
            ContinuitySegmentV1(
                segment_index=1,
                device_sample_start=60_000,
                device_sample_stop=150_000,
                stored_sample_start=50_000,
                stored_sample_stop=140_000,
                preceding_missing_sample_count=10_000,
                preceding_boundary_reason="counter_gap",
                preceding_boundary_header_sha256=_digest("gap-header"),
            ),
        ),
    )


def _binding(
    *,
    gapped: bool,
    stream_id: str = "stream-0",
    radio_id: str = "radio-0",
    receiver_id: int = 0,
    sample_rate_hz: int = _RATE,
) -> StandardPathInputBindV4:
    inventory = _inventory(gapped=gapped, stream_id=stream_id)
    return StandardPathInputBindV4.model_construct(
        session_id="session-0",
        stream_id=stream_id,
        radio_id=radio_id,
        receiver_id=receiver_id,
        manifest_digest=_digest("manifest"),
        synchronization_inventory_digest=_digest("synchronization"),
        binding_digest=_digest(f"path-binding-{stream_id}-{radio_id}-{receiver_id}"),
        tuned_center_frequency_hz=959_687_500,
        sample_rate_hz=sample_rate_hz,
        logical_sample_count=_LOGICAL,
        observed_sample_count=inventory.observed_sample_count,
        missing_sample_count=inventory.missing_sample_count,
        timing={
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 1_060_000_000,
            "last_earliest_utc_ns": 1_059_999_900,
            "last_latest_utc_ns": 1_060_000_100,
        },
        frequency_reference=ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ),
        validity_inventory=inventory,
        starlink_edge=StarlinkEdge.LOWER,
    )


def _opportunity(
    index: int,
    *,
    disposition: NativeWindowDisposition,
    segment_index: int | None,
) -> NativeProbeWindowV3:
    start = index * _PROBE
    return NativeProbeWindowV3(
        probe=ProbeWindowV2(
            probe_id=_digest(f"probe-{index}"),
            coarse_window_index=0,
            subwindow_index=index,
            probe_offset_ms=0,
            sample_start=start,
            sample_count=_PROBE,
            time_s=start / _RATE,
        ),
        validity=NativeWindowEvidenceV1(
            device_sample_start=start,
            sample_count=_PROBE,
            disposition=disposition,
            missing_sample_count=(
                10_000 if disposition is NativeWindowDisposition.GAP_OVERLAP else 0
            ),
            continuity_segment_index=segment_index,
        ),
    )


def _schedule(source: StandardNativeSourceV1, *, gapped: bool) -> StandardProbeScheduleV3:
    opportunities = (
        _opportunity(0, disposition=NativeWindowDisposition.VALID, segment_index=0),
        _opportunity(
            1,
            disposition=(
                NativeWindowDisposition.GAP_OVERLAP if gapped else NativeWindowDisposition.VALID
            ),
            segment_index=None if gapped else 0,
        ),
        _opportunity(
            2,
            disposition=NativeWindowDisposition.VALID,
            segment_index=1 if gapped else 0,
        ),
    )
    accounting = NativeOpportunityAccountingV1(
        scheduled_count=3,
        valid_count=2 if gapped else 3,
        analyzed_count=0,
        passing_count=0,
        gap_excluded_count=1 if gapped else 0,
        continuity_boundary_excluded_count=0,
        outside_span_count=0,
    )
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-native-probe-schedule-v3",
        "source": source.model_dump(mode="json"),
        "coarse_window_ms": 1_000,
        "subwindow_ms": 50,
        "probe_ms": 20,
        "probe_offsets_ms": (0,),
        "maximum_coarse_windows": 1,
        "source_probe_count": 3,
        "returned_probe_count": 3,
        "truncated_probe_count": 0,
        "opportunities": tuple(item.model_dump(mode="json") for item in opportunities),
        "accounting": accounting.model_dump(mode="json"),
    }
    return StandardProbeScheduleV3.model_validate(
        {**values, "schedule_digest": canonical_digest(values)}
    )


def _detection(
    status: Literal["complete", "no_result", "insufficient"],
    *,
    local_start: int,
    forced_qam_metrics: tuple[float | None, float | None] | None = None,
) -> NativePilotProbeDetectionV1:
    complete = status == "complete"
    qam_accuracy, qam_evm = (
        forced_qam_metrics
        if forced_qam_metrics is not None
        else ((1.0, 0.1) if complete else (None, None))
    )
    scores = (
        (
            NativePilotMethodScoreV1(
                method="glrt64",
                exact_score=0.8,
                control_score=0.1,
                margin=0.7,
                residual_cfo_hz=0.0,
                tracking_cfo_hz=10_000.0,
            ),
        )
        if complete
        else ()
    )
    return NativePilotProbeDetectionV1(
        status=status,
        sample_start=local_start,
        time_s=local_start / _RATE,
        local_epoch_sample=5 if complete else None,
        acquired_cfo_hz=10_000.0 if complete else None,
        scores=scores,
        qam_accuracy=qam_accuracy,
        qam_evm=qam_evm,
        reason="test terminal detection",
    )


def _track() -> FinalTrajectoryV3:
    observation_ids = tuple(_digest(f"observation-{index}") for index in range(3))
    return FinalTrajectoryV3(
        trajectory_id=_digest("trajectory"),
        component_id=_digest("component"),
        branch_id=_digest("branch"),
        canonical_model_id=_digest("model"),
        alias_index=0,
        polynomial_degree=1,
        reference_time_s=0.01,
        canonical_coefficients_hz=(0.0, 10_000.0),
        absolute_coefficients_hz=(0.0, 10_000.0),
        start_s=0.005,
        end_s=0.015,
        observation_ids=tuple(sorted(observation_ids)),
        replay_tier=LiftReplayTierV3.AUTOMATIC,
        automatic_correction_eligible=True,
        evaluated_probe_count=3,
        evaluated_block_count=3,
        block_coverage_ratio=1.0,
        harmful_block_count=0,
        median_block_margin_delta=0.1,
        median_block_corrected_margin=0.2,
        maximum_consecutive_harmful_blocks=0,
        replay_reasons=("test automatic replay",),
    )


def _stateful(
    source: StandardNativeSourceV1,
    *,
    gapped: bool,
    detection_statuses: tuple[Literal["complete", "no_result", "insufficient"], ...],
    forced_detection_qam_metrics: tuple[float | None, float | None] | None = None,
    include_tracks: bool = True,
) -> StandardNativeStatefulPathV2:
    valid_starts = (0, 100_000) if gapped else (0, 50_000, 100_000)
    detections_by_segment: dict[int, list[NativePilotProbeDetectionV1]] = {}
    for global_start, status in zip(valid_starts, detection_statuses, strict=True):
        segment = next(
            item
            for item in source.continuity_segments
            if item.device_sample_start <= global_start < item.device_sample_stop
        )
        detections_by_segment.setdefault(segment.segment_index, []).append(
            _detection(
                status,
                local_start=global_start - segment.device_sample_start,
                forced_qam_metrics=forced_detection_qam_metrics,
            )
        )
    segments: list[NativeStatefulSegmentV2] = []
    for authority in source.continuity_segments:
        detections = tuple(detections_by_segment[authority.segment_index])
        track = (_track(),) if include_tracks and authority.segment_index == 0 else ()
        bank = type("_Bank", (), {})()
        bank.content_digest = _digest(f"final-bank-{authority.segment_index}")
        bank.status = (
            StandardScientificStatus.COMPLETE if track else StandardScientificStatus.NO_RESULT
        )
        bank.reason = "retained reset-local candidate" if track else "no final candidate"
        bank.source_trajectory_count = len(track)
        bank.returned_trajectory_count = len(track)
        bank.truncated_trajectory_count = 0
        bank.trajectories = track
        science = NativeSegmentLocalScienceV1.model_construct(
            detections=detections,
            final_trajectory_bank=bank,
        )
        segments.append(
            NativeStatefulSegmentV2.model_construct(
                continuity_segment=authority,
                continuity_segment_index=authority.segment_index,
                global_device_sample_start=authority.device_sample_start,
                global_device_sample_stop=authority.device_sample_stop,
                disposition=NativeStatefulSegmentDispositionV2.ANALYZED,
                local_science=science,
                segment_digest=_digest(f"stateful-segment-{authority.segment_index}"),
            )
        )
    return StandardNativeStatefulPathV2.model_construct(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
        science_configuration_digest=_digest("science-config"),
        stateful_science_status="partial_coverage" if gapped else "complete",
        segments=tuple(segments),
        stateful_path_digest=_digest("stateful-path"),
    )


def _qam_evidence(
    schedule: StandardProbeScheduleV3,
    stateful: StandardNativeStatefulPathV2,
) -> tuple[NativeQamProbeEvidenceV1, ...]:
    detections: dict[int, NativePilotProbeDetectionV1] = {}
    for segment in stateful.segments:
        assert segment.local_science is not None
        for detection in segment.local_science.detections:
            detections[segment.global_device_sample_start + detection.sample_start] = detection
    result: list[NativeQamProbeEvidenceV1] = []
    for index, opportunity in enumerate(schedule.opportunities):
        if opportunity.validity.disposition is not NativeWindowDisposition.VALID:
            continue
        detection = detections[opportunity.probe.sample_start]
        if detection.status == "complete":
            statistics = native_qam_sufficient_statistics(
                PilotQamResult(
                    status=NumericalStatus.COMPLETE,
                    metrics=PilotQamMetrics(1.0, 0.1, 0.01, 1.0, 1.0, 1, 1.0),
                    absolute_cfo_hz=10_125.0,
                    residual_cfo_refinement_hz=125.0,
                    reason="same-call test QAM",
                    expected=_EXPECTED,
                    equalized=_EQUALIZED,
                    frame_equalized=_EQUALIZED[None, :, :],
                )
            )
            qam_status = NativeQamComputationStatusV1.COMPLETE
            reason = "same-call test QAM"
            primary_rank = 0
            primary_epoch = detection.local_epoch_sample
            primary_cfo = detection.acquired_cfo_hz
            qam_absolute_cfo = 10_125.0
            qam_residual_cfo = 125.0
        else:
            statistics = empty_native_qam_statistics()
            qam_status = NativeQamComputationStatusV1.NOT_EVALUATED
            reason = "QAM was not evaluated because primary acquisition produced no candidate"
            primary_rank = None
            primary_epoch = None
            primary_cfo = None
            qam_absolute_cfo = None
            qam_residual_cfo = None
        values = {
            "schema_version": 1,
            "opportunity_index": index,
            "continuity_segment_index": opportunity.validity.continuity_segment_index,
            "global_device_sample_start": opportunity.probe.sample_start,
            "detection_status": detection.status,
            "primary_candidate_rank": primary_rank,
            "primary_local_epoch_sample": primary_epoch,
            "primary_acquired_cfo_hz": primary_cfo,
            "qam_status": qam_status.value,
            "qam_absolute_cfo_hz": qam_absolute_cfo,
            "qam_residual_cfo_refinement_hz": qam_residual_cfo,
            "statistics": statistics.model_dump(mode="json"),
            "reason": reason,
        }
        result.append(
            NativeQamProbeEvidenceV1.model_validate(
                {**values, "evidence_digest": canonical_digest(values)}
            )
        )
    return tuple(result)


_EXPECTED = np.exp(0.5j * np.pi * (np.arange(300 * 8) % 4 + 0.5)).reshape(300, 8)
_EQUALIZED = 0.9 * _EXPECTED


def _product_digest(product: ContractModel) -> str:
    return canonical_digest(product.model_dump(mode="json"))


def _build(
    *,
    gapped: bool,
    detection_statuses: tuple[Literal["complete", "no_result", "insufficient"], ...],
    stream_id: str = "stream-0",
    radio_id: str = "radio-0",
    receiver_id: int = 0,
    sample_rate_hz: int = _RATE,
    forced_detection_qam_metrics: tuple[float | None, float | None] | None = None,
    include_tracks: bool = True,
) -> StandardNativePathReportV3:
    binding = _binding(
        gapped=gapped,
        stream_id=stream_id,
        radio_id=radio_id,
        receiver_id=receiver_id,
        sample_rate_hz=sample_rate_hz,
    )
    source = StandardNativeSourceV1.from_path_binding(binding)
    schedule = _schedule(source, gapped=gapped)
    stateful = _stateful(
        source,
        gapped=gapped,
        detection_statuses=detection_statuses,
        forced_detection_qam_metrics=forced_detection_qam_metrics,
        include_tracks=include_tracks,
    )
    quality = StandardNativeQualityV2.model_construct(source=source)
    power = StandardNativePowerTimelineV3.model_construct(source=source)
    waterfall = StandardNativeNumericalWaterfallV3.model_construct(source=source)
    glrt = StandardNativeFullCaptureGlrt20msV1.model_construct(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
    )
    return build_standard_native_path_report(
        binding,
        quality=quality,
        quality_product_digest=_product_digest(quality),
        power_timeline=power,
        power_timeline_product_digest=_product_digest(power),
        numerical_waterfall=waterfall,
        numerical_waterfall_product_digest=_product_digest(waterfall),
        probe_schedule=schedule,
        probe_schedule_product_digest=_product_digest(schedule),
        stateful_path=stateful,
        stateful_path_product_digest=_product_digest(stateful),
        full_capture_glrt20ms=glrt,
        full_capture_glrt20ms_product_digest=_product_digest(glrt),
        qam_probe_evidence=_qam_evidence(schedule, stateful),
    )


def test_lossless_path_report_closes_candidate_qam_and_reset_local_tracks() -> None:
    report = _build(gapped=False, detection_statuses=("complete", "no_result", "complete"))

    assert report.processing_status == "complete"
    assert report.scientific_disposition is NativePathScientificDispositionV1.CANDIDATE
    assert report.schedule_execution.accounting.scheduled_count == 3
    assert report.schedule_execution.accounting.analyzed_count == 3
    assert report.schedule_execution.accounting.candidate_count == 2
    assert report.qam_statistics.qam_result_count == 2
    assert report.qam_statistics.frame_count == 2
    first_qam = report.schedule_execution.opportunities[0].qam
    assert first_qam is not None
    assert first_qam.primary_acquired_cfo_hz is not None
    assert first_qam.qam_absolute_cfo_hz is not None
    assert first_qam.qam_residual_cfo_refinement_hz is not None
    assert first_qam.statistics.hard_symbol_accuracy is not None
    assert first_qam.statistics.rms_evm is not None
    assert first_qam.qam_absolute_cfo_hz == (
        first_qam.primary_acquired_cfo_hz + first_qam.qam_residual_cfo_refinement_hz
    )
    assert float(first_qam.statistics.hard_symbol_accuracy) == 1.0
    assert float(first_qam.statistics.rms_evm) == pytest.approx(0.1)
    assert report.segments[0].final_trajectories == (_track(),)
    assert report.cross_segment_association_permitted is False
    assert StandardNativePathReportV3.model_validate(report.model_dump(mode="json")) == report


def test_gapped_report_keeps_exclusion_and_no_candidate_distinct_from_processing() -> None:
    report = _build(gapped=True, detection_statuses=("no_result", "no_result"))

    accounting = report.schedule_execution.accounting
    assert report.processing_status == "complete"
    assert report.scientific_disposition is NativePathScientificDispositionV1.NO_CANDIDATE
    assert accounting.scheduled_count == 3
    assert accounting.valid_count == accounting.analyzed_count == 2
    assert accounting.gap_excluded_count == 1
    excluded = report.schedule_execution.opportunities[1]
    assert excluded.disposition.value == "excluded_gap"
    assert excluded.detection_status is None
    assert excluded.qam is None
    assert report.qam_statistics.qam_result_count == 0


def test_insufficient_valid_probe_is_not_mislabeled_no_candidate() -> None:
    report = _build(gapped=True, detection_statuses=("insufficient", "no_result"))

    assert report.processing_status == "complete"
    assert report.scientific_disposition is NativePathScientificDispositionV1.INSUFFICIENT
    assert report.schedule_execution.accounting.insufficient_count == 1


def test_qam_probe_contract_rejects_cfo_composition_and_partial_null_tamper() -> None:
    report = _build(gapped=False, detection_statuses=("complete", "no_result", "complete"))
    measured = report.schedule_execution.opportunities[0].qam
    candidate_free = report.schedule_execution.opportunities[1].qam
    assert measured is not None
    assert candidate_free is not None

    cfo_values: dict[str, Any] = measured.model_dump(mode="json")
    cfo_values["qam_absolute_cfo_hz"] = 10_126.0
    cfo_values["evidence_digest"] = canonical_digest(
        {key: value for key, value in cfo_values.items() if key != "evidence_digest"}
    )
    with pytest.raises(ValidationError, match="primary CFO plus refinement"):
        NativeQamProbeEvidenceV1.model_validate(cfo_values)

    primary_values: dict[str, Any] = candidate_free.model_dump(mode="json")
    primary_values["primary_acquired_cfo_hz"] = 10_000.0
    primary_values["evidence_digest"] = canonical_digest(
        {key: value for key, value in primary_values.items() if key != "evidence_digest"}
    )
    with pytest.raises(ValidationError, match="candidate-free.*primary coordinates"):
        NativeQamProbeEvidenceV1.model_validate(primary_values)

    refinement_values: dict[str, Any] = candidate_free.model_dump(mode="json")
    refinement_values["qam_residual_cfo_refinement_hz"] = 0.0
    refinement_values["evidence_digest"] = canonical_digest(
        {key: value for key, value in refinement_values.items() if key != "evidence_digest"}
    )
    with pytest.raises(ValidationError, match="noncomplete.*refined CFO"):
        NativeQamProbeEvidenceV1.model_validate(refinement_values)


@pytest.mark.parametrize(
    "metrics",
    (
        (0.5, 0.1),
        (1.0, 0.5),
    ),
)
def test_path_report_rejects_stateful_qam_metric_tamper(
    metrics: tuple[float | None, float | None],
) -> None:
    with pytest.raises(ValueError, match="same-call sufficient statistics"):
        _build(
            gapped=False,
            detection_statuses=("complete", "complete", "complete"),
            forced_detection_qam_metrics=metrics,
        )


def test_path_report_requires_measured_metrics_only_for_complete_qam() -> None:
    with pytest.raises(ValueError, match="lacks measured metrics"):
        _build(
            gapped=False,
            detection_statuses=("complete", "complete", "complete"),
            forced_detection_qam_metrics=(None, None),
        )
    with pytest.raises(ValueError, match="noncomplete.*carries measured metrics"):
        _build(
            gapped=False,
            detection_statuses=("no_result", "no_result", "no_result"),
            forced_detection_qam_metrics=(1.0, 0.1),
        )


def test_report_rejects_product_digest_tamper_and_changed_frequency_authority() -> None:
    binding = _binding(gapped=False)
    source = StandardNativeSourceV1.from_path_binding(binding)
    schedule = _schedule(source, gapped=False)
    stateful = _stateful(
        source,
        gapped=False,
        detection_statuses=("complete", "no_result", "complete"),
    )
    quality = StandardNativeQualityV2.model_construct(source=source)
    power = StandardNativePowerTimelineV3.model_construct(source=source)
    waterfall = StandardNativeNumericalWaterfallV3.model_construct(source=source)
    glrt = StandardNativeFullCaptureGlrt20msV1.model_construct(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
    )
    with pytest.raises(ValueError, match="product digest"):
        build_standard_native_path_report(
            binding,
            quality=quality,
            quality_product_digest=_digest("wrong"),
            power_timeline=power,
            power_timeline_product_digest=_product_digest(power),
            numerical_waterfall=waterfall,
            numerical_waterfall_product_digest=_product_digest(waterfall),
            probe_schedule=schedule,
            probe_schedule_product_digest=_product_digest(schedule),
            stateful_path=stateful,
            stateful_path_product_digest=_product_digest(stateful),
            full_capture_glrt20ms=glrt,
            full_capture_glrt20ms_product_digest=_product_digest(glrt),
            qam_probe_evidence=_qam_evidence(schedule, stateful),
        )

    report = _build(gapped=False, detection_statuses=("complete", "no_result", "complete"))
    values: dict[str, Any] = report.model_dump(mode="json")
    values["frequency_reference"] = {
        "schema_version": 1,
        "reference": "calibrated",
        "center_frequency_hz": 959_687_500.0,
        "uncertainty_hz": 1.0,
        "calibration_digest": _digest("calibration"),
    }
    values["report_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "report_digest"}
    )
    with pytest.raises(ValidationError, match="frequency authority"):
        StandardNativePathReportV3.model_validate(values)
