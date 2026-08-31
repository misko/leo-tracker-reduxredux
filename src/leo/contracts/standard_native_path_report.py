"""Terminal evidence-only path report for the additive Standard-native lane.

The report closes the products emitted by one native path execution without
changing any frozen Standard contract.  Valid probe windows are distinguished
from schedule exclusions, QAM ratios are derived from mergeable sufficient
statistics, and every trajectory remains owned by one authoritative continuity
segment.
"""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.cfo_dealias import FinalTrajectoryV3
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import (
    NativeProbeWindowV3,
    NativeWindowDisposition,
    StandardNativeSourceV1,
    StandardNativeSourceV2,
)
from leo.contracts.standard_native_stateful_v2 import NativeStatefulSegmentDispositionV2
from leo.contracts.standard_pipeline import (
    BoundedText,
    ReceiverFrequencyReferenceV1,
    StandardScientificStatus,
)
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1

_QIN_SYMBOLS_PER_FRAME = 300 * 8


class NativeQamComputationStatusV1(StrEnum):
    """Outcome of QAM on the primary candidate of one valid probe."""

    COMPLETE = "complete"
    NO_RESULT = "no_result"
    INSUFFICIENT = "insufficient"
    NOT_EVALUATED = "not_evaluated"


class NativeProbeExecutionDispositionV1(StrEnum):
    """Terminal disposition of one persisted global probe opportunity."""

    ANALYZED_CANDIDATE = "analyzed_candidate"
    ANALYZED_NO_CANDIDATE = "analyzed_no_candidate"
    ANALYZED_INSUFFICIENT = "analyzed_insufficient"
    EXCLUDED_GAP = "excluded_gap"
    EXCLUDED_CONTINUITY_BOUNDARY = "excluded_continuity_boundary"
    EXCLUDED_OUTSIDE_SPAN = "excluded_outside_span"


class NativePathScientificDispositionV1(StrEnum):
    """Scientific terminal state, separate from processing completion."""

    CANDIDATE = "candidate"
    NO_CANDIDATE = "no_candidate"
    INSUFFICIENT = "insufficient"


class NativeQamSufficientStatisticsV1(ContractModel):
    """Exactly mergeable known-pilot QAM evidence.

    ``squared_error_sum`` and ``reference_energy_sum`` are persisted decimals,
    so reducers add numerators and denominators before deriving EVM.  Ratios are
    never averaged across probes or partitions.
    """

    schema_version: Literal[1] = 1
    algorithm_version: Literal["known-qin-primary-qam-sufficient-statistics-v1"] = (
        "known-qin-primary-qam-sufficient-statistics-v1"
    )
    qam_result_count: Annotated[int, Field(ge=0)]
    correct_symbol_count: Annotated[int, Field(ge=0)]
    symbol_count: Annotated[int, Field(ge=0)]
    frame_count: Annotated[int, Field(ge=0)]
    squared_error_sum: Annotated[Decimal, Field(ge=0)]
    reference_energy_sum: Annotated[Decimal, Field(ge=0)]
    hard_symbol_accuracy: Annotated[Decimal | None, Field(ge=0, le=1)]
    rms_evm: Annotated[Decimal | None, Field(ge=0)]
    known_symbols_only: Literal[True] = True
    invalid_device_axis_samples_included: Literal[False] = False

    @field_validator(
        "squared_error_sum",
        "reference_energy_sum",
        "hard_symbol_accuracy",
        "rms_evm",
    )
    @classmethod
    def _decimal_is_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("native QAM statistics must be finite")
        return value

    @model_validator(mode="after")
    def _statistics_close(self) -> Self:
        if self.correct_symbol_count > self.symbol_count:
            raise ValueError("native QAM correct-symbol count exceeds support")
        if not self.qam_result_count:
            if (
                any(
                    (
                        self.correct_symbol_count,
                        self.symbol_count,
                        self.frame_count,
                        self.squared_error_sum,
                        self.reference_energy_sum,
                    )
                )
                or self.hard_symbol_accuracy is not None
                or self.rms_evm is not None
            ):
                raise ValueError("empty native QAM statistics carry measured evidence")
            return self
        if (
            self.frame_count < self.qam_result_count
            or self.symbol_count != self.qam_result_count * _QIN_SYMBOLS_PER_FRAME
            or self.reference_energy_sum <= 0
            or self.hard_symbol_accuracy is None
            or self.rms_evm is None
        ):
            raise ValueError("complete native QAM statistics lack exact frame support")
        expected_accuracy = Decimal(self.correct_symbol_count) / Decimal(self.symbol_count)
        with localcontext() as context:
            context.prec = 34
            expected_evm = (self.squared_error_sum / self.reference_energy_sum).sqrt()
        if self.hard_symbol_accuracy != expected_accuracy or self.rms_evm != expected_evm:
            raise ValueError("native QAM derived metrics disagree with sufficient statistics")
        return self


class NativeQamProbeEvidenceV1(ContractModel):
    """QAM result from the same primary-candidate computation as detection."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    global_device_sample_start: Annotated[int, Field(ge=0)]
    detection_status: Literal["complete", "no_result", "insufficient"]
    primary_candidate_rank: Literal[0] | None
    primary_local_epoch_sample: Annotated[int | None, Field(ge=0)]
    primary_acquired_cfo_hz: float | None
    qam_status: NativeQamComputationStatusV1
    qam_absolute_cfo_hz: float | None
    qam_residual_cfo_refinement_hz: float | None
    statistics: NativeQamSufficientStatisticsV1
    reason: BoundedText
    evidence_digest: Sha256Digest

    @field_validator(
        "primary_acquired_cfo_hz",
        "qam_absolute_cfo_hz",
        "qam_residual_cfo_refinement_hz",
    )
    @classmethod
    def _cfo_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native QAM CFO evidence must be finite")
        return value

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        detection_complete = self.detection_status == "complete"
        primary_fields = (
            self.primary_candidate_rank,
            self.primary_local_epoch_sample,
            self.primary_acquired_cfo_hz,
        )
        if detection_complete and not all(item is not None for item in primary_fields):
            raise ValueError("native QAM evidence changed primary candidate coordinates")
        if not detection_complete and any(item is not None for item in primary_fields):
            raise ValueError("candidate-free native QAM evidence carries primary coordinates")
        not_evaluated = self.qam_status is NativeQamComputationStatusV1.NOT_EVALUATED
        if detection_complete and not_evaluated:
            raise ValueError("native QAM evaluation disagrees with primary detection")
        if not detection_complete and not not_evaluated:
            raise ValueError("candidate-free native QAM evidence claims an evaluation")
        measured = self.qam_status is NativeQamComputationStatusV1.COMPLETE
        qam_cfo_fields = (
            self.qam_absolute_cfo_hz,
            self.qam_residual_cfo_refinement_hz,
        )
        if measured and not all(item is not None for item in qam_cfo_fields):
            raise ValueError("native QAM completion disagrees with refined CFO evidence")
        if not measured and any(item is not None for item in qam_cfo_fields):
            raise ValueError("noncomplete native QAM evidence carries refined CFO evidence")
        if measured:
            assert self.primary_acquired_cfo_hz is not None
            assert self.qam_absolute_cfo_hz is not None
            assert self.qam_residual_cfo_refinement_hz is not None
            expected_absolute_cfo_hz = (
                self.primary_acquired_cfo_hz + self.qam_residual_cfo_refinement_hz
            )
            if self.qam_absolute_cfo_hz != expected_absolute_cfo_hz:
                raise ValueError(
                    "native QAM absolute CFO does not equal primary CFO plus refinement"
                )
        if measured != (self.statistics.qam_result_count == 1):
            raise ValueError("native QAM status disagrees with measured statistics")
        if not measured and self.statistics.qam_result_count:
            raise ValueError("noncomplete native QAM evidence carries measurements")
        if self.evidence_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"evidence_digest"})
        ):
            raise ValueError("native QAM probe evidence digest does not match")
        return self


class NativeProbeExecutionV1(ContractModel):
    """One schedule opportunity after terminal scientific execution."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    opportunity: NativeProbeWindowV3
    disposition: NativeProbeExecutionDispositionV1
    detection_status: Literal["complete", "no_result", "insufficient"] | None
    qam: NativeQamProbeEvidenceV1 | None
    execution_digest: Sha256Digest

    @model_validator(mode="after")
    def _execution_closes(self) -> Self:
        validity = self.opportunity.validity
        valid = validity.disposition is NativeWindowDisposition.VALID
        if valid != (self.detection_status is not None and self.qam is not None):
            raise ValueError("native probe execution changed validity admission")
        if valid:
            assert self.detection_status is not None
            expected = {
                "complete": NativeProbeExecutionDispositionV1.ANALYZED_CANDIDATE,
                "no_result": NativeProbeExecutionDispositionV1.ANALYZED_NO_CANDIDATE,
                "insufficient": NativeProbeExecutionDispositionV1.ANALYZED_INSUFFICIENT,
            }[self.detection_status]
            if self.disposition is not expected:
                raise ValueError("native probe disposition disagrees with detection")
            assert self.qam is not None
            if (
                self.qam.opportunity_index != self.opportunity_index
                or self.qam.global_device_sample_start != self.opportunity.probe.sample_start
                or self.qam.continuity_segment_index != validity.continuity_segment_index
                or self.qam.detection_status != self.detection_status
            ):
                raise ValueError("native QAM evidence changed probe coordinates or outcome")
        else:
            expected_exclusion = {
                NativeWindowDisposition.GAP_OVERLAP: (
                    NativeProbeExecutionDispositionV1.EXCLUDED_GAP
                ),
                NativeWindowDisposition.CONTINUITY_BOUNDARY: (
                    NativeProbeExecutionDispositionV1.EXCLUDED_CONTINUITY_BOUNDARY
                ),
                NativeWindowDisposition.OUTSIDE_SPAN: (
                    NativeProbeExecutionDispositionV1.EXCLUDED_OUTSIDE_SPAN
                ),
            }.get(validity.disposition)
            if expected_exclusion is None or self.disposition is not expected_exclusion:
                raise ValueError("native probe exclusion changed schedule evidence")
        if self.execution_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"execution_digest"})
        ):
            raise ValueError("native probe execution digest does not match")
        return self


class NativeProbeExecutionAccountingV1(ContractModel):
    schema_version: Literal[1] = 1
    scheduled_count: Annotated[int, Field(ge=0)]
    valid_count: Annotated[int, Field(ge=0)]
    analyzed_count: Annotated[int, Field(ge=0)]
    candidate_count: Annotated[int, Field(ge=0)]
    no_candidate_count: Annotated[int, Field(ge=0)]
    insufficient_count: Annotated[int, Field(ge=0)]
    gap_excluded_count: Annotated[int, Field(ge=0)]
    continuity_boundary_excluded_count: Annotated[int, Field(ge=0)]
    outside_span_count: Annotated[int, Field(ge=0)]
    qam_complete_count: Annotated[int, Field(ge=0)]
    qam_no_result_count: Annotated[int, Field(ge=0)]
    qam_insufficient_count: Annotated[int, Field(ge=0)]
    qam_not_evaluated_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _accounting_closes(self) -> Self:
        if self.scheduled_count != (
            self.valid_count
            + self.gap_excluded_count
            + self.continuity_boundary_excluded_count
            + self.outside_span_count
        ):
            raise ValueError("terminal native schedule dispositions do not close")
        if self.analyzed_count != self.valid_count or self.analyzed_count != (
            self.candidate_count + self.no_candidate_count + self.insufficient_count
        ):
            raise ValueError("terminal native analyzed opportunities do not close")
        if self.analyzed_count != (
            self.qam_complete_count
            + self.qam_no_result_count
            + self.qam_insufficient_count
            + self.qam_not_evaluated_count
        ):
            raise ValueError("terminal native QAM opportunity accounting does not close")
        return self


class NativeProbeScheduleExecutionV1(ContractModel):
    schema_version: Literal[1] = 1
    source_schedule_digest: Sha256Digest
    opportunities: tuple[NativeProbeExecutionV1, ...]
    accounting: NativeProbeExecutionAccountingV1
    processing_complete: Literal[True] = True
    execution_digest: Sha256Digest

    @model_validator(mode="after")
    def _schedule_execution_closes(self) -> Self:
        indexes = tuple(item.opportunity_index for item in self.opportunities)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("terminal native opportunity indexes are not canonical")
        dispositions = tuple(item.disposition for item in self.opportunities)
        qam_statuses = tuple(
            item.qam.qam_status for item in self.opportunities if item.qam is not None
        )
        expected = NativeProbeExecutionAccountingV1(
            scheduled_count=len(self.opportunities),
            valid_count=sum(item.detection_status is not None for item in self.opportunities),
            analyzed_count=sum(item.detection_status is not None for item in self.opportunities),
            candidate_count=dispositions.count(
                NativeProbeExecutionDispositionV1.ANALYZED_CANDIDATE
            ),
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
        if self.accounting != expected:
            raise ValueError("terminal native schedule accounting disagrees with executions")
        if self.execution_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"execution_digest"})
        ):
            raise ValueError("terminal native schedule execution digest does not match")
        return self


class NativePathProductDigestsV1(ContractModel):
    """Exact emitted bytes consumed by the terminal path report."""

    schema_version: Literal[1] = 1
    quality_product_digest: Sha256Digest
    power_timeline_product_digest: Sha256Digest
    numerical_waterfall_product_digest: Sha256Digest
    probe_schedule_product_digest: Sha256Digest
    stateful_path_product_digest: Sha256Digest
    full_capture_glrt20ms_product_digest: Sha256Digest
    product_set_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_set_closes(self) -> Self:
        if self.product_set_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"product_set_digest"})
        ):
            raise ValueError("native path product-set digest does not match")
        return self


class NativePathSegmentReportV1(ContractModel):
    """Final candidate inventory retained within one reset-local segment."""

    schema_version: Literal[1] = 1
    continuity_segment: ContinuitySegmentV1
    stateful_disposition: NativeStatefulSegmentDispositionV2
    stateful_segment_digest: Sha256Digest
    final_trajectory_bank_digest: Sha256Digest | None
    final_trajectory_status: StandardScientificStatus | None
    final_trajectory_reason: BoundedText | None
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    final_trajectories: tuple[FinalTrajectoryV3, ...]
    segment_report_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_report_closes(self) -> Self:
        analyzed = self.stateful_disposition is NativeStatefulSegmentDispositionV2.ANALYZED
        bank_fields = (
            self.final_trajectory_bank_digest,
            self.final_trajectory_status,
            self.final_trajectory_reason,
        )
        if analyzed != all(item is not None for item in bank_fields):
            raise ValueError("native path segment bank disagrees with stateful disposition")
        if not analyzed and any(
            (
                self.source_trajectory_count,
                self.returned_trajectory_count,
                self.truncated_trajectory_count,
                len(self.final_trajectories),
            )
        ):
            raise ValueError("unanalyzed native path segment carries final trajectories")
        if self.source_trajectory_count != (
            self.returned_trajectory_count + self.truncated_trajectory_count
        ) or self.returned_trajectory_count != len(self.final_trajectories):
            raise ValueError("native path segment trajectory accounting does not close")
        trajectory_ids = tuple(item.trajectory_id for item in self.final_trajectories)
        if trajectory_ids != tuple(sorted(set(trajectory_ids))):
            raise ValueError("native path segment trajectories are not canonical")
        if self.segment_report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_report_digest"})
        ):
            raise ValueError("native path segment report digest does not match")
        return self


class StandardNativePathReportV3(ContractModel):
    """Terminal, processing-complete evidence for one Standard-native path."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-path-report-v3"] = "standard-native-path-report-v3"
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    frequency_reference: ReceiverFrequencyReferenceV1
    frequency_reference_digest: Sha256Digest
    products: NativePathProductDigestsV1
    schedule_execution: NativeProbeScheduleExecutionV1
    segments: tuple[NativePathSegmentReportV1, ...]
    qam_statistics: NativeQamSufficientStatisticsV1
    processing_status: Literal["complete"] = "complete"
    scientific_disposition: NativePathScientificDispositionV1
    scientific_reason: BoundedText
    cross_segment_association_permitted: Literal[False] = False
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _path_report_closes(self) -> Self:
        expected_frequency_digest = canonical_digest(
            self.frequency_reference.model_dump(mode="json")
        )
        if self.frequency_reference_digest != expected_frequency_digest:
            raise ValueError("native path report changed V4 frequency authority")
        if tuple(item.continuity_segment for item in self.segments) != (
            self.source.continuity_segments
        ):
            raise ValueError("native path report changed continuity-segment authority")
        for segment in self.segments:
            duration_s = (
                segment.continuity_segment.observed_sample_count / self.source.sample_rate_hz
            )
            if any(
                trajectory.start_s < 0
                or trajectory.end_s > duration_s
                or trajectory.reference_time_s > duration_s
                for trajectory in segment.final_trajectories
            ):
                raise ValueError("native path final trajectory escaped its reset-local segment")
        expected_qam = _merge_qam_statistics(
            tuple(
                item.qam.statistics
                for item in self.schedule_execution.opportunities
                if item.qam is not None
            )
        )
        if self.qam_statistics != expected_qam:
            raise ValueError("native path report QAM aggregate does not close")
        accounting = self.schedule_execution.accounting
        expected_disposition = (
            NativePathScientificDispositionV1.CANDIDATE
            if accounting.candidate_count
            else (
                NativePathScientificDispositionV1.INSUFFICIENT
                if not accounting.valid_count or accounting.insufficient_count
                else NativePathScientificDispositionV1.NO_CANDIDATE
            )
        )
        if self.scientific_disposition is not expected_disposition:
            raise ValueError("native path scientific disposition disagrees with probe outcomes")
        expected_reason = {
            NativePathScientificDispositionV1.CANDIDATE: (
                "one or more wholly-valid probes produced candidate-only known-pilot evidence"
            ),
            NativePathScientificDispositionV1.NO_CANDIDATE: (
                "all wholly-valid probes completed without a candidate"
            ),
            NativePathScientificDispositionV1.INSUFFICIENT: (
                "valid probe support was absent or scientifically insufficient"
            ),
        }[expected_disposition]
        if self.scientific_reason != expected_reason:
            raise ValueError("native path scientific reason disagrees with disposition")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native path report digest does not match content")
        return self


class StandardNativePathReportV4(StandardNativePathReportV3):
    """Additive terminal path report carrying StandardNativeSourceV2."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    algorithm_version: Literal["standard-native-path-report-v4"] = "standard-native-path-report-v4"  # type: ignore[assignment]
    source: StandardNativeSourceV2  # type: ignore[assignment]


def _merge_qam_statistics(
    values: tuple[NativeQamSufficientStatisticsV1, ...],
) -> NativeQamSufficientStatisticsV1:
    result_count = sum(item.qam_result_count for item in values)
    correct_count = sum(item.correct_symbol_count for item in values)
    symbol_count = sum(item.symbol_count for item in values)
    frame_count = sum(item.frame_count for item in values)
    squared_error = sum((item.squared_error_sum for item in values), Decimal(0))
    reference_energy = sum((item.reference_energy_sum for item in values), Decimal(0))
    if result_count:
        accuracy: Decimal | None = Decimal(correct_count) / Decimal(symbol_count)
        with localcontext() as context:
            context.prec = 34
            evm: Decimal | None = (squared_error / reference_energy).sqrt()
    else:
        accuracy = None
        evm = None
    return NativeQamSufficientStatisticsV1(
        qam_result_count=result_count,
        correct_symbol_count=correct_count,
        symbol_count=symbol_count,
        frame_count=frame_count,
        squared_error_sum=squared_error,
        reference_energy_sum=reference_energy,
        hard_symbol_accuracy=accuracy,
        rms_evm=evm,
    )
