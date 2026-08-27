"""Terminal aggregate contracts for the evidence-only Standard-native lane.

These additive V4 reports preserve the published radio/paired V3 documents.
They consume the processing-complete V3 path report, retain every reset-local
trajectory inventory, and merge raw-IQ and known-pilot QAM sufficient
statistics without averaging derived ratios.
"""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import (
    NativeQualityReceiverV2,
    NativeSufficientStatisticsV1,
    NativeValidUtcIntervalV1,
    StandardNativeSourceV1,
)
from leo.contracts.standard_native_path_report import (
    NativePathScientificDispositionV1,
    NativeProbeExecutionAccountingV1,
    NativeQamSufficientStatisticsV1,
    StandardNativePathReportV3,
)
from leo.contracts.standard_pipeline import BoundedText, Identifier


class NativeTerminalTrackAccountingV1(ContractModel):
    """Exactly additive final-trajectory counts over reset-local segments."""

    schema_version: Literal[1] = 1
    segment_count: Annotated[int, Field(gt=0)]
    analyzed_segment_count: Annotated[int, Field(ge=0)]
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    cross_segment_association_permitted: Literal[False] = False

    @model_validator(mode="after")
    def _track_accounting_closes(self) -> Self:
        if self.analyzed_segment_count > self.segment_count:
            raise ValueError("native analyzed segment count exceeds inventory")
        if self.source_trajectory_count != (
            self.returned_trajectory_count + self.truncated_trajectory_count
        ):
            raise ValueError("native terminal trajectory counts do not close")
        return self


class NativeTerminalPathEvidenceV2(ContractModel):
    """One path's exact terminal report and validity-bound reducer inputs."""

    schema_version: Literal[2] = 2
    source: StandardNativeSourceV1
    stage_outcome: Literal["complete", "partial_coverage"]
    path_report_product_digest: Sha256Digest
    full_capture_glrt20ms_product_digest: Sha256Digest
    path_report: StandardNativePathReportV3
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    quality: NativeQualityReceiverV2
    terminal_opportunities: NativeProbeExecutionAccountingV1
    qam_statistics: NativeQamSufficientStatisticsV1
    terminal_tracks: NativeTerminalTrackAccountingV1
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    cross_path_association_permitted: Literal[False] = False

    @model_validator(mode="after")
    def _terminal_path_closes(self) -> Self:
        if (
            self.path_report_product_digest
            != canonical_digest(self.path_report.model_dump(mode="json"))
            or self.source != self.path_report.source
            or self.full_capture_glrt20ms_product_digest
            != self.path_report.products.full_capture_glrt20ms_product_digest
        ):
            raise ValueError("native terminal path lineage does not close")
        if (
            self.quality.receiver_id != self.source.receiver_id
            or self.quality.valid_sample_count != self.source.observed_sample_count
            or self.terminal_opportunities != self.path_report.schedule_execution.accounting
            or self.qam_statistics != self.path_report.qam_statistics
            or self.terminal_tracks != terminal_track_accounting(self.path_report)
        ):
            raise ValueError("native terminal path evidence disagrees with its path report")
        expected_outcome = (
            "complete"
            if self.source.missing_sample_count == 0 and len(self.source.continuity_segments) == 1
            else "partial_coverage"
        )
        if self.stage_outcome != expected_outcome:
            raise ValueError("native terminal path outcome disagrees with validity authority")
        _require_canonical_utc_intervals(self.valid_utc_intervals)
        return self


class StandardNativeRadioReportV4(ContractModel):
    """Terminal two-path reduction with QAM and segment-local track closure."""

    schema_version: Literal[4] = 4
    algorithm_version: Literal["standard-native-radio-report-v4"] = (
        "standard-native-radio-report-v4"
    )
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    status: Literal["complete", "partial_coverage", "insufficient_data"]
    reason: BoundedText
    paths: tuple[NativeTerminalPathEvidenceV2, NativeTerminalPathEvidenceV2]
    aggregate_statistics: NativeSufficientStatisticsV1
    aggregate_terminal_opportunities: NativeProbeExecutionAccountingV1
    aggregate_qam_statistics: NativeQamSufficientStatisticsV1
    aggregate_terminal_tracks: NativeTerminalTrackAccountingV1
    scientific_disposition: NativePathScientificDispositionV1
    scientific_reason: BoundedText
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    cross_path_association_permitted: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _radio_report_closes(self) -> Self:
        receiver_ids = tuple(item.source.receiver_id for item in self.paths)
        if receiver_ids != tuple(sorted(set(receiver_ids))):
            raise ValueError("native terminal radio paths must be unique and ordered")
        for item in self.paths:
            source = item.source
            if (
                source.session_id != self.session_id
                or source.stream_id != self.stream_id
                or source.radio_id != self.radio_id
                or source.manifest_digest != self.manifest_digest
                or source.synchronization_inventory_digest != self.synchronization_inventory_digest
                or source.sample_rate_hz != self.sample_rate_hz
            ):
                raise ValueError("native terminal radio report contains a foreign path")
        left = self.paths[0].source.model_dump(
            mode="json", exclude={"path_input_binding_digest", "receiver_id"}
        )
        right = self.paths[1].source.model_dump(
            mode="json", exclude={"path_input_binding_digest", "receiver_id"}
        )
        if left != right:
            raise ValueError("native terminal radio paths disagree on stream authority")
        _require_statistics(
            self.aggregate_statistics,
            tuple(item.quality for item in self.paths),
        )
        if (
            self.aggregate_terminal_opportunities
            != aggregate_native_probe_execution_accounting(
                tuple(item.terminal_opportunities for item in self.paths)
            )
            or self.aggregate_qam_statistics
            != aggregate_native_qam_statistics(tuple(item.qam_statistics for item in self.paths))
            or self.aggregate_terminal_tracks
            != aggregate_terminal_track_accounting(
                tuple(item.terminal_tracks for item in self.paths)
            )
        ):
            raise ValueError("native terminal radio sufficient statistics do not close")
        expected_intervals = _intersect_utc_interval_sets(
            self.paths[0].valid_utc_intervals,
            self.paths[1].valid_utc_intervals,
        )
        expected_status = _processing_status(
            expected_intervals,
            tuple(item.stage_outcome for item in self.paths),
        )
        if self.valid_utc_intervals != expected_intervals or self.status != expected_status:
            raise ValueError("native terminal radio support or status is inconsistent")
        expected_scientific = _scientific_disposition(
            tuple(item.path_report.scientific_disposition for item in self.paths)
        )
        if self.scientific_disposition is not expected_scientific:
            raise ValueError("native terminal radio scientific disposition is inconsistent")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native terminal radio report digest does not match content")
        return self


class StandardNativePairedReportV4(ContractModel):
    """Terminal two-radio reduction without phase or cross-gap association claims."""

    schema_version: Literal[4] = 4
    algorithm_version: Literal["standard-native-paired-report-v4"] = (
        "standard-native-paired-report-v4"
    )
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pair_input_binding_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    status: Literal["complete", "partial_coverage", "insufficient_data"]
    reason: BoundedText
    radios: tuple[StandardNativeRadioReportV4, StandardNativeRadioReportV4]
    aggregate_statistics: NativeSufficientStatisticsV1
    aggregate_terminal_opportunities: NativeProbeExecutionAccountingV1
    aggregate_qam_statistics: NativeQamSufficientStatisticsV1
    aggregate_terminal_tracks: NativeTerminalTrackAccountingV1
    scientific_disposition: NativePathScientificDispositionV1
    scientific_reason: BoundedText
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    phase_coherent: Literal[False] = False
    cross_radio_association_permitted: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _paired_report_closes(self) -> Self:
        radio_keys = tuple((item.stream_id, item.radio_id) for item in self.radios)
        if radio_keys != tuple(sorted(set(radio_keys))) or len(radio_keys) != 2:
            raise ValueError("native terminal paired radio inventory is not exact")
        for item in self.radios:
            if (
                item.session_id != self.session_id
                or item.manifest_digest != self.manifest_digest
                or item.synchronization_inventory_digest != self.synchronization_inventory_digest
                or item.sample_rate_hz != self.sample_rate_hz
            ):
                raise ValueError("native terminal paired report contains a foreign radio")
        _require_statistics(
            self.aggregate_statistics,
            tuple(item.aggregate_statistics for item in self.radios),
        )
        if (
            self.aggregate_terminal_opportunities
            != aggregate_native_probe_execution_accounting(
                tuple(item.aggregate_terminal_opportunities for item in self.radios)
            )
            or self.aggregate_qam_statistics
            != aggregate_native_qam_statistics(
                tuple(item.aggregate_qam_statistics for item in self.radios)
            )
            or self.aggregate_terminal_tracks
            != aggregate_terminal_track_accounting(
                tuple(item.aggregate_terminal_tracks for item in self.radios)
            )
        ):
            raise ValueError("native terminal paired sufficient statistics do not close")
        expected_intervals = _intersect_utc_interval_sets(
            self.radios[0].valid_utc_intervals,
            self.radios[1].valid_utc_intervals,
        )
        expected_status = _processing_status(
            expected_intervals,
            tuple(item.status for item in self.radios),
        )
        if self.valid_utc_intervals != expected_intervals or self.status != expected_status:
            raise ValueError("native terminal paired support or status is inconsistent")
        expected_scientific = _scientific_disposition(
            tuple(item.scientific_disposition for item in self.radios)
        )
        if self.scientific_disposition is not expected_scientific:
            raise ValueError("native terminal paired scientific disposition is inconsistent")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native terminal paired report digest does not match content")
        return self


class StandardNativePairedReportV5(ContractModel):
    """Terminal two-radio reduction for equal- or mixed-native-rate inputs.

    V4 remains the immutable common-rate contract.  V5 retains each radio's
    native rate explicitly and still authorizes paired evidence only over the
    conservative UTC intersection, so no sample-axis equivalence or resampling
    is implied.
    """

    schema_version: Literal[5] = 5
    algorithm_version: Literal["standard-native-paired-report-v5"] = (
        "standard-native-paired-report-v5"
    )
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pair_input_binding_digest: Sha256Digest
    radio_sample_rates_hz: tuple[
        Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000],
        Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000],
    ]
    status: Literal["complete", "partial_coverage", "insufficient_data"]
    reason: BoundedText
    radios: tuple[StandardNativeRadioReportV4, StandardNativeRadioReportV4]
    aggregate_statistics: NativeSufficientStatisticsV1
    aggregate_terminal_opportunities: NativeProbeExecutionAccountingV1
    aggregate_qam_statistics: NativeQamSufficientStatisticsV1
    aggregate_terminal_tracks: NativeTerminalTrackAccountingV1
    scientific_disposition: NativePathScientificDispositionV1
    scientific_reason: BoundedText
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    phase_coherent: Literal[False] = False
    cross_radio_association_permitted: Literal[False] = False
    resampling_permitted: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _paired_report_closes(self) -> Self:
        radio_keys = tuple((item.stream_id, item.radio_id) for item in self.radios)
        if radio_keys != tuple(sorted(set(radio_keys))) or len(radio_keys) != 2:
            raise ValueError("native terminal paired radio inventory is not exact")
        if self.radio_sample_rates_hz != tuple(item.sample_rate_hz for item in self.radios):
            raise ValueError("native terminal paired rate inventory is not exact")
        for item in self.radios:
            if (
                item.session_id != self.session_id
                or item.manifest_digest != self.manifest_digest
                or item.synchronization_inventory_digest != self.synchronization_inventory_digest
            ):
                raise ValueError("native terminal paired report contains a foreign radio")
        _require_statistics(
            self.aggregate_statistics,
            tuple(item.aggregate_statistics for item in self.radios),
        )
        if (
            self.aggregate_terminal_opportunities
            != aggregate_native_probe_execution_accounting(
                tuple(item.aggregate_terminal_opportunities for item in self.radios)
            )
            or self.aggregate_qam_statistics
            != aggregate_native_qam_statistics(
                tuple(item.aggregate_qam_statistics for item in self.radios)
            )
            or self.aggregate_terminal_tracks
            != aggregate_terminal_track_accounting(
                tuple(item.aggregate_terminal_tracks for item in self.radios)
            )
        ):
            raise ValueError("native terminal paired sufficient statistics do not close")
        expected_intervals = _intersect_utc_interval_sets(
            self.radios[0].valid_utc_intervals,
            self.radios[1].valid_utc_intervals,
        )
        expected_status = _processing_status(
            expected_intervals,
            tuple(item.status for item in self.radios),
        )
        if self.valid_utc_intervals != expected_intervals or self.status != expected_status:
            raise ValueError("native terminal paired support or status is inconsistent")
        expected_scientific = _scientific_disposition(
            tuple(item.scientific_disposition for item in self.radios)
        )
        if self.scientific_disposition is not expected_scientific:
            raise ValueError("native terminal paired scientific disposition is inconsistent")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native terminal paired report digest does not match content")
        return self


def terminal_track_accounting(
    report: StandardNativePathReportV3,
) -> NativeTerminalTrackAccountingV1:
    return NativeTerminalTrackAccountingV1(
        segment_count=len(report.segments),
        analyzed_segment_count=sum(
            item.final_trajectory_bank_digest is not None for item in report.segments
        ),
        source_trajectory_count=sum(item.source_trajectory_count for item in report.segments),
        returned_trajectory_count=sum(item.returned_trajectory_count for item in report.segments),
        truncated_trajectory_count=sum(item.truncated_trajectory_count for item in report.segments),
    )


def aggregate_terminal_track_accounting(
    children: tuple[NativeTerminalTrackAccountingV1, ...],
) -> NativeTerminalTrackAccountingV1:
    if not children:
        raise ValueError("native terminal track aggregation requires children")
    return NativeTerminalTrackAccountingV1(
        segment_count=sum(item.segment_count for item in children),
        analyzed_segment_count=sum(item.analyzed_segment_count for item in children),
        source_trajectory_count=sum(item.source_trajectory_count for item in children),
        returned_trajectory_count=sum(item.returned_trajectory_count for item in children),
        truncated_trajectory_count=sum(item.truncated_trajectory_count for item in children),
    )


def aggregate_native_probe_execution_accounting(
    children: tuple[NativeProbeExecutionAccountingV1, ...],
) -> NativeProbeExecutionAccountingV1:
    if not children:
        raise ValueError("native terminal opportunity aggregation requires children")
    fields = (
        "scheduled_count",
        "valid_count",
        "analyzed_count",
        "candidate_count",
        "no_candidate_count",
        "insufficient_count",
        "gap_excluded_count",
        "continuity_boundary_excluded_count",
        "outside_span_count",
        "qam_complete_count",
        "qam_no_result_count",
        "qam_insufficient_count",
        "qam_not_evaluated_count",
    )
    return NativeProbeExecutionAccountingV1.model_validate(
        {field: sum(getattr(item, field) for item in children) for field in fields}
    )


def aggregate_native_qam_statistics(
    children: tuple[NativeQamSufficientStatisticsV1, ...],
) -> NativeQamSufficientStatisticsV1:
    if not children:
        raise ValueError("native QAM aggregation requires children")
    result_count = sum(item.qam_result_count for item in children)
    correct_count = sum(item.correct_symbol_count for item in children)
    symbol_count = sum(item.symbol_count for item in children)
    frame_count = sum(item.frame_count for item in children)
    squared_error = sum((item.squared_error_sum for item in children), Decimal(0))
    reference_energy = sum((item.reference_energy_sum for item in children), Decimal(0))
    if not result_count:
        accuracy = None
        evm = None
    else:
        accuracy = Decimal(correct_count) / Decimal(symbol_count)
        with localcontext() as context:
            context.prec = 34
            evm = (squared_error / reference_energy).sqrt()
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


def _require_statistics(
    aggregate: NativeSufficientStatisticsV1,
    children: tuple[NativeQualityReceiverV2 | NativeSufficientStatisticsV1, ...],
) -> None:
    path_count = sum(
        1 if isinstance(item, NativeQualityReceiverV2) else item.receiver_path_count
        for item in children
    )
    valid_count = sum(
        item.valid_sample_count
        if isinstance(item, NativeQualityReceiverV2)
        else item.valid_complex_sample_count
        for item in children
    )
    energy_sum = sum(item.energy_sum_ci16_squared for item in children)
    clipped_components = sum(item.clipped_component_count for item in children)
    clipped_samples = sum(item.clipped_complex_sample_count for item in children)
    minimum_i = min(item.minimum_i for item in children if item.minimum_i is not None)
    maximum_i = max(item.maximum_i for item in children if item.maximum_i is not None)
    minimum_q = min(item.minimum_q for item in children if item.minimum_q is not None)
    maximum_q = max(item.maximum_q for item in children if item.maximum_q is not None)
    if (
        aggregate.receiver_path_count != path_count
        or aggregate.valid_complex_sample_count != valid_count
        or aggregate.energy_sum_ci16_squared != energy_sum
        or aggregate.clipped_component_count != clipped_components
        or aggregate.clipped_complex_sample_count != clipped_samples
        or not math.isclose(
            aggregate.clipped_complex_fraction,
            clipped_samples / valid_count,
            abs_tol=1e-15,
        )
        or not math.isclose(
            aggregate.mean_power_full_scale_squared,
            energy_sum / (valid_count * 32_768**2),
            abs_tol=1e-15,
        )
        or aggregate.minimum_i != minimum_i
        or aggregate.maximum_i != maximum_i
        or aggregate.minimum_q != minimum_q
        or aggregate.maximum_q != maximum_q
        or aggregate.constant_iq != (minimum_i == maximum_i and minimum_q == maximum_q)
    ):
        raise ValueError("native terminal raw-IQ sufficient statistics do not close")


def _scientific_disposition(
    children: tuple[NativePathScientificDispositionV1, ...],
) -> NativePathScientificDispositionV1:
    if any(item is NativePathScientificDispositionV1.CANDIDATE for item in children):
        return NativePathScientificDispositionV1.CANDIDATE
    if any(item is NativePathScientificDispositionV1.INSUFFICIENT for item in children):
        return NativePathScientificDispositionV1.INSUFFICIENT
    return NativePathScientificDispositionV1.NO_CANDIDATE


def _processing_status(
    intervals: tuple[NativeValidUtcIntervalV1, ...],
    outcomes: tuple[str, ...],
) -> Literal["complete", "partial_coverage", "insufficient_data"]:
    if not intervals:
        return "insufficient_data"
    if all(item == "complete" for item in outcomes):
        return "complete"
    return "partial_coverage"


def _require_canonical_utc_intervals(
    intervals: tuple[NativeValidUtcIntervalV1, ...],
) -> None:
    identities = tuple((item.start_utc_ns, item.stop_utc_ns) for item in intervals)
    if identities != tuple(sorted(identities)) or any(
        left.stop_utc_ns >= right.start_utc_ns
        for left, right in zip(intervals, intervals[1:], strict=False)
    ):
        raise ValueError("native terminal UTC intervals are not canonical")


def _intersect_utc_interval_sets(
    left: tuple[NativeValidUtcIntervalV1, ...],
    right: tuple[NativeValidUtcIntervalV1, ...],
) -> tuple[NativeValidUtcIntervalV1, ...]:
    _require_canonical_utc_intervals(left)
    _require_canonical_utc_intervals(right)
    output: list[NativeValidUtcIntervalV1] = []
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        start = max(left[left_index].start_utc_ns, right[right_index].start_utc_ns)
        stop = min(left[left_index].stop_utc_ns, right[right_index].stop_utc_ns)
        if stop > start:
            if output and output[-1].stop_utc_ns == start:
                output[-1] = output[-1].model_copy(update={"stop_utc_ns": stop})
            else:
                output.append(NativeValidUtcIntervalV1(start_utc_ns=start, stop_utc_ns=stop))
        if left[left_index].stop_utc_ns <= right[right_index].stop_utc_ns:
            left_index += 1
        else:
            right_index += 1
    return tuple(output)
