"""Additive validity-aware scientific contracts for Standard-native-v1."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import (
    BoundedText,
    Identifier,
    ProbeWindowV2,
    StandardNumericalWaterfallV2,
    StandardPathInputBindV4,
    StandardPowerTimelineV2,
    StreamTimingEvidenceV1,
)
from leo.contracts.validity import ContinuitySegmentV1


class NativeWindowDisposition(StrEnum):
    VALID = "valid"
    GAP_OVERLAP = "gap_overlap"
    CONTINUITY_BOUNDARY = "continuity_boundary"
    OUTSIDE_SPAN = "outside_span"


class StandardNativeSourceV1(ContractModel):
    """Exact logical IQ and validity authority shared by native products."""

    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    validity_inventory_digest: Sha256Digest
    tuned_center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    timing: StreamTimingEvidenceV1
    continuity_segments: tuple[ContinuitySegmentV1, ...]

    @model_validator(mode="after")
    def _source_is_closed(self) -> Self:
        if self.sample_rate_hz not in {2_500_000, 3_000_000, 5_000_000, 10_000_000}:
            raise ValueError("native product source sample rate is not reviewed")
        if self.logical_sample_count != self.observed_sample_count + self.missing_sample_count:
            raise ValueError("native product source counts do not close")
        if not self.continuity_segments:
            raise ValueError("native product source requires continuity segments")
        if tuple(item.segment_index for item in self.continuity_segments) != tuple(
            range(len(self.continuity_segments))
        ):
            raise ValueError("native product continuity segments are not canonical")
        if self.continuity_segments[-1].device_sample_stop != self.logical_sample_count:
            raise ValueError("native product continuity segments do not close the logical span")
        return self

    @classmethod
    def from_path_binding(cls, binding: StandardPathInputBindV4) -> Self:
        validity = binding.validity_inventory
        return cls(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            radio_id=binding.radio_id,
            receiver_id=binding.receiver_id,
            manifest_digest=binding.manifest_digest,
            synchronization_inventory_digest=binding.synchronization_inventory_digest,
            path_input_binding_digest=binding.binding_digest,
            validity_inventory_digest=validity.inventory_digest,
            tuned_center_frequency_hz=binding.tuned_center_frequency_hz,
            sample_rate_hz=binding.sample_rate_hz,
            logical_sample_count=binding.logical_sample_count,
            observed_sample_count=binding.observed_sample_count,
            missing_sample_count=binding.missing_sample_count,
            timing=binding.timing,
            continuity_segments=validity.segments,
        )


class NativeWindowEvidenceV1(ContractModel):
    """Validity disposition of one complete time-defined analysis window."""

    schema_version: Literal[1] = 1
    device_sample_start: int
    sample_count: Annotated[int, Field(gt=0)]
    disposition: NativeWindowDisposition
    missing_sample_count: Annotated[int, Field(ge=0)] = 0
    continuity_segment_index: Annotated[int, Field(ge=0)] | None = None
    crossed_segment_indexes: tuple[Annotated[int, Field(ge=0)], ...] = ()

    @model_validator(mode="after")
    def _classification_is_consistent(self) -> Self:
        if self.missing_sample_count > self.sample_count:
            raise ValueError("window missing samples exceed support")
        if self.crossed_segment_indexes != tuple(sorted(set(self.crossed_segment_indexes))):
            raise ValueError("window crossed segments must be unique and ordered")
        if self.disposition is NativeWindowDisposition.VALID:
            if (
                self.device_sample_start < 0
                or self.missing_sample_count
                or self.continuity_segment_index is None
                or self.crossed_segment_indexes
            ):
                raise ValueError("valid native window carries inconsistent evidence")
        elif self.continuity_segment_index is not None:
            raise ValueError("excluded native window cannot claim one segment")
        if (self.disposition is NativeWindowDisposition.GAP_OVERLAP) != bool(
            self.missing_sample_count
        ):
            raise ValueError("gap-overlap disposition disagrees with missing support")
        if (
            self.disposition is NativeWindowDisposition.CONTINUITY_BOUNDARY
            and not self.crossed_segment_indexes
        ):
            raise ValueError("continuity-boundary disposition requires crossed segments")
        return self


class NativeOpportunityAccountingV1(ContractModel):
    schema_version: Literal[1] = 1
    scheduled_count: Annotated[int, Field(ge=0)]
    valid_count: Annotated[int, Field(ge=0)]
    analyzed_count: Annotated[int, Field(ge=0)]
    passing_count: Annotated[int, Field(ge=0)] = 0
    gap_excluded_count: Annotated[int, Field(ge=0)]
    continuity_boundary_excluded_count: Annotated[int, Field(ge=0)]
    outside_span_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _opportunities_close(self) -> Self:
        if self.scheduled_count != (
            self.valid_count
            + self.gap_excluded_count
            + self.continuity_boundary_excluded_count
            + self.outside_span_count
        ):
            raise ValueError("native opportunity disposition inventory does not close")
        if self.analyzed_count > self.valid_count or self.passing_count > self.analyzed_count:
            raise ValueError("native analyzed/passing inventory exceeds eligible opportunities")
        return self


class NativeProbeWindowV3(ContractModel):
    schema_version: Literal[3] = 3
    probe: ProbeWindowV2
    validity: NativeWindowEvidenceV1

    @model_validator(mode="after")
    def _probe_and_validity_match(self) -> Self:
        if (
            self.probe.sample_start != self.validity.device_sample_start
            or self.probe.sample_count != self.validity.sample_count
        ):
            raise ValueError("native probe geometry disagrees with its validity evidence")
        return self


class StandardProbeScheduleV3(ContractModel):
    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-probe-schedule-v3"] = (
        "standard-native-probe-schedule-v3"
    )
    source: StandardNativeSourceV1
    coarse_window_ms: Literal[1000] = 1000
    subwindow_ms: Annotated[int, Field(gt=0, le=1000)]
    probe_ms: Annotated[int, Field(gt=0, le=1000)]
    probe_offsets_ms: tuple[Annotated[int, Field(ge=0, le=1000)], ...]
    maximum_coarse_windows: Annotated[int, Field(gt=0, le=86_400)]
    source_probe_count: Annotated[int, Field(ge=0)]
    returned_probe_count: Annotated[int, Field(ge=0)]
    truncated_probe_count: Annotated[int, Field(ge=0)]
    opportunities: tuple[NativeProbeWindowV3, ...]
    accounting: NativeOpportunityAccountingV1
    schedule_digest: Sha256Digest

    @model_validator(mode="after")
    def _schedule_is_closed(self) -> Self:
        if self.returned_probe_count != len(self.opportunities):
            raise ValueError("native returned probe count disagrees with opportunities")
        if self.returned_probe_count + self.truncated_probe_count != self.source_probe_count:
            raise ValueError("native probe truncation inventory does not close")
        if self.accounting.scheduled_count != self.returned_probe_count:
            raise ValueError("native probe accounting does not cover returned opportunities")
        starts = tuple(item.probe.sample_start for item in self.opportunities)
        if starts != tuple(sorted(set(starts))):
            raise ValueError("native probe starts must be unique and ordered")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"schedule_digest"}))
        if self.schedule_digest != expected:
            raise ValueError("native probe schedule digest does not match content")
        return self


class NativeQualityReceiverV2(ContractModel):
    schema_version: Literal[2] = 2
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    valid_sample_count: Annotated[int, Field(ge=0)]
    energy_sum_ci16_squared: Annotated[int, Field(ge=0)]
    clipped_component_count: Annotated[int, Field(ge=0)]
    clipped_complex_sample_count: Annotated[int, Field(ge=0)]
    clipped_complex_fraction: Annotated[float, Field(ge=0, le=1)]
    constant_iq: bool
    minimum_i: int | None
    maximum_i: int | None
    minimum_q: int | None
    maximum_q: int | None

    @model_validator(mode="after")
    def _quality_is_consistent(self) -> Self:
        expected = (
            self.clipped_complex_sample_count / self.valid_sample_count
            if self.valid_sample_count
            else 0.0
        )
        if not math.isclose(self.clipped_complex_fraction, expected, abs_tol=1e-15):
            raise ValueError("native clipping fraction disagrees with sufficient statistics")
        extrema = (self.minimum_i, self.maximum_i, self.minimum_q, self.maximum_q)
        if bool(self.valid_sample_count) != all(item is not None for item in extrema):
            raise ValueError("native quality extrema disagree with valid sample support")
        return self


class StandardNativeQualityV2(ContractModel):
    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-native-quality-v2"] = "standard-native-quality-v2"
    source: StandardNativeSourceV1
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    receivers: tuple[NativeQualityReceiverV2, ...]

    @model_validator(mode="after")
    def _quality_source_is_exact(self) -> Self:
        if len(self.receivers) != 1:
            raise ValueError("native path quality requires exactly one receiver")
        if self.receivers[0].valid_sample_count != self.source.observed_sample_count:
            raise ValueError("native quality valid count disagrees with source authority")
        return self


class StandardNativePowerTimelineV3(ContractModel):
    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-power-timeline-v3"] = (
        "standard-native-power-timeline-v3"
    )
    source: StandardNativeSourceV1
    timeline: StandardPowerTimelineV2

    @model_validator(mode="after")
    def _timeline_source_is_exact(self) -> Self:
        if (
            self.timeline.sample_rate_hz != self.source.sample_rate_hz
            or self.timeline.expected_sample_count != self.source.logical_sample_count
            or self.timeline.observed_sample_count != self.source.observed_sample_count
            or self.timeline.missing_sample_count != self.source.missing_sample_count
        ):
            raise ValueError("native power timeline disagrees with source authority")
        return self


class StandardNativeNumericalWaterfallV3(ContractModel):
    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-numerical-waterfall-v3"] = (
        "standard-native-numerical-waterfall-v3"
    )
    source: StandardNativeSourceV1
    waterfall: StandardNumericalWaterfallV2

    @model_validator(mode="after")
    def _waterfall_source_is_exact(self) -> Self:
        coverage = self.waterfall.coverage
        if (
            self.waterfall.sample_rate_hz != self.source.sample_rate_hz
            or coverage.expected_samples != self.source.logical_sample_count
            or coverage.observed_samples != self.source.observed_sample_count
            or coverage.missing_samples != self.source.missing_sample_count
        ):
            raise ValueError("native waterfall disagrees with source authority")
        return self


class NativeValidUtcIntervalV1(ContractModel):
    """Conservative UTC support guaranteed valid for one or more receiver paths."""

    schema_version: Literal[1] = 1
    start_utc_ns: Annotated[int, Field(ge=0)]
    stop_utc_ns: Annotated[int, Field(gt=0)]
    timing_basis: Literal["first-sample-bracket-nominal-rate-inner-v1"] = (
        "first-sample-bracket-nominal-rate-inner-v1"
    )

    @model_validator(mode="after")
    def _interval_is_positive(self) -> Self:
        if self.stop_utc_ns <= self.start_utc_ns:
            raise ValueError("native valid UTC interval must have positive extent")
        return self


class NativeSufficientStatisticsV1(ContractModel):
    """Exactly mergeable CI16 statistics; no invalid zero-fill contributes."""

    schema_version: Literal[1] = 1
    receiver_path_count: Annotated[int, Field(gt=0, le=4)]
    valid_complex_sample_count: Annotated[int, Field(gt=0)]
    energy_sum_ci16_squared: Annotated[int, Field(ge=0)]
    clipped_component_count: Annotated[int, Field(ge=0)]
    clipped_complex_sample_count: Annotated[int, Field(ge=0)]
    clipped_complex_fraction: Annotated[float, Field(ge=0, le=1)]
    mean_power_full_scale_squared: Annotated[float, Field(ge=0)]
    full_scale_component_magnitude: Literal[32768] = 32768
    constant_iq: bool
    minimum_i: int
    maximum_i: int
    minimum_q: int
    maximum_q: int

    @model_validator(mode="after")
    def _statistics_close(self) -> Self:
        if self.clipped_component_count > 2 * self.valid_complex_sample_count:
            raise ValueError("native clipped component count exceeds support")
        if self.clipped_complex_sample_count > self.valid_complex_sample_count:
            raise ValueError("native clipped complex count exceeds support")
        expected_clipped = self.clipped_complex_sample_count / self.valid_complex_sample_count
        expected_power = self.energy_sum_ci16_squared / (
            self.valid_complex_sample_count * self.full_scale_component_magnitude**2
        )
        if not math.isclose(self.clipped_complex_fraction, expected_clipped, abs_tol=1e-15):
            raise ValueError("native aggregate clipping fraction disagrees with counts")
        if not math.isclose(self.mean_power_full_scale_squared, expected_power, abs_tol=1e-15):
            raise ValueError("native aggregate mean power disagrees with energy sum")
        if self.minimum_i > self.maximum_i or self.minimum_q > self.maximum_q:
            raise ValueError("native aggregate extrema are reversed")
        expected_constant = self.minimum_i == self.maximum_i and self.minimum_q == self.maximum_q
        if self.constant_iq != expected_constant:
            raise ValueError("native aggregate constant-IQ flag disagrees with extrema")
        return self


class NativePathEvidenceV1(ContractModel):
    """One path's exact five-product evidence and path-local terminal outcome."""

    schema_version: Literal[1] = 1
    source: StandardNativeSourceV1
    stage_outcome: Literal["complete", "partial_coverage"]
    quality_product_digest: Sha256Digest
    power_timeline_product_digest: Sha256Digest
    numerical_waterfall_product_digest: Sha256Digest
    probe_schedule_product_digest: Sha256Digest
    stateful_path_product_digest: Sha256Digest
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    quality: NativeQualityReceiverV2
    opportunities: NativeOpportunityAccountingV1
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False

    @model_validator(mode="after")
    def _path_evidence_closes(self) -> Self:
        if (
            self.quality.receiver_id != self.source.receiver_id
            or self.quality.valid_sample_count != self.source.observed_sample_count
        ):
            raise ValueError("native path quality disagrees with source identity or support")
        _require_canonical_utc_intervals(self.valid_utc_intervals)
        return self


class StandardNativeRadioReportV3(ContractModel):
    """Evidence-only two-path reduction using integer sufficient statistics."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-radio-report-v3"] = (
        "standard-native-radio-report-v3"
    )
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    status: Literal["complete", "partial_coverage", "insufficient_data"]
    reason: BoundedText
    paths: tuple[NativePathEvidenceV1, NativePathEvidenceV1]
    aggregate_statistics: NativeSufficientStatisticsV1
    aggregate_opportunities: NativeOpportunityAccountingV1
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _radio_report_closes(self) -> Self:
        receiver_ids = tuple(item.source.receiver_id for item in self.paths)
        if receiver_ids != tuple(sorted(set(receiver_ids))):
            raise ValueError("native radio receiver paths must be unique and ordered")
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
                raise ValueError("native radio report contains a foreign path")
        left = self.paths[0].source.model_dump(
            mode="json", exclude={"path_input_binding_digest", "receiver_id"}
        )
        right = self.paths[1].source.model_dump(
            mode="json", exclude={"path_input_binding_digest", "receiver_id"}
        )
        if left != right:
            raise ValueError("native radio paths disagree on shared stream authority")
        _require_aggregate_statistics(
            self.aggregate_statistics,
            tuple(item.quality for item in self.paths),
        )
        _require_aggregate_opportunities(
            self.aggregate_opportunities,
            tuple(item.opportunities for item in self.paths),
        )
        expected_intervals = _intersect_utc_interval_sets(
            self.paths[0].valid_utc_intervals,
            self.paths[1].valid_utc_intervals,
        )
        if self.valid_utc_intervals != expected_intervals:
            raise ValueError("native radio valid UTC intersection is not exact")
        expected_status = (
            "insufficient_data"
            if not expected_intervals
            else (
                "complete"
                if all(item.stage_outcome == "complete" for item in self.paths)
                else "partial_coverage"
            )
        )
        if self.status != expected_status:
            raise ValueError("native radio status disagrees with path-local outcomes")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native radio report digest does not match content")
        return self


class StandardNativePairedReportV3(ContractModel):
    """Evidence-only two-radio report over exact intersections of valid UTC support."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-paired-report-v3"] = (
        "standard-native-paired-report-v3"
    )
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pair_input_binding_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    status: Literal["complete", "partial_coverage", "insufficient_data"]
    reason: BoundedText
    radios: tuple[StandardNativeRadioReportV3, StandardNativeRadioReportV3]
    aggregate_statistics: NativeSufficientStatisticsV1
    aggregate_opportunities: NativeOpportunityAccountingV1
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    report_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    phase_coherent: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _paired_report_closes(self) -> Self:
        radio_keys = tuple((item.stream_id, item.radio_id) for item in self.radios)
        if radio_keys != tuple(sorted(set(radio_keys))) or len(radio_keys) != 2:
            raise ValueError("native paired radio inventory must be exact and ordered")
        for item in self.radios:
            if (
                item.session_id != self.session_id
                or item.manifest_digest != self.manifest_digest
                or item.synchronization_inventory_digest != self.synchronization_inventory_digest
                or item.sample_rate_hz != self.sample_rate_hz
            ):
                raise ValueError("native paired report contains a foreign radio")
        _require_aggregate_statistics(
            self.aggregate_statistics,
            tuple(item.aggregate_statistics for item in self.radios),
        )
        _require_aggregate_opportunities(
            self.aggregate_opportunities,
            tuple(item.aggregate_opportunities for item in self.radios),
        )
        expected_intervals = _intersect_utc_interval_sets(
            self.radios[0].valid_utc_intervals,
            self.radios[1].valid_utc_intervals,
        )
        if self.valid_utc_intervals != expected_intervals:
            raise ValueError("native paired valid UTC intersection is not exact")
        expected_status = (
            "insufficient_data"
            if not expected_intervals
            else (
                "complete"
                if all(item.status == "complete" for item in self.radios)
                else "partial_coverage"
            )
        )
        if self.status != expected_status:
            raise ValueError("native paired status disagrees with radio outcomes")
        if self.report_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        ):
            raise ValueError("native paired report digest does not match content")
        return self


def _require_canonical_utc_intervals(
    intervals: tuple[NativeValidUtcIntervalV1, ...],
) -> None:
    identities = tuple((item.start_utc_ns, item.stop_utc_ns) for item in intervals)
    if identities != tuple(sorted(identities)):
        raise ValueError("native valid UTC intervals must be ordered")
    if any(
        left.stop_utc_ns >= right.start_utc_ns
        for left, right in zip(intervals, intervals[1:], strict=False)
    ):
        raise ValueError("native valid UTC intervals must be disjoint and maximally merged")


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
        left_item = left[left_index]
        right_item = right[right_index]
        start = max(left_item.start_utc_ns, right_item.start_utc_ns)
        stop = min(left_item.stop_utc_ns, right_item.stop_utc_ns)
        if stop > start:
            if output and output[-1].stop_utc_ns == start:
                output[-1] = output[-1].model_copy(update={"stop_utc_ns": stop})
            else:
                output.append(NativeValidUtcIntervalV1(start_utc_ns=start, stop_utc_ns=stop))
        if left_item.stop_utc_ns <= right_item.stop_utc_ns:
            left_index += 1
        else:
            right_index += 1
    return tuple(output)


def _require_aggregate_statistics(
    aggregate: NativeSufficientStatisticsV1,
    children: tuple[NativeQualityReceiverV2 | NativeSufficientStatisticsV1, ...],
) -> None:
    valid_counts = tuple(
        item.valid_sample_count
        if isinstance(item, NativeQualityReceiverV2)
        else item.valid_complex_sample_count
        for item in children
    )
    minimum_i = tuple(item.minimum_i for item in children if item.minimum_i is not None)
    maximum_i = tuple(item.maximum_i for item in children if item.maximum_i is not None)
    minimum_q = tuple(item.minimum_q for item in children if item.minimum_q is not None)
    maximum_q = tuple(item.maximum_q for item in children if item.maximum_q is not None)
    if not all((minimum_i, maximum_i, minimum_q, maximum_q)):
        raise ValueError("native aggregate children require observed extrema")
    if (
        aggregate.receiver_path_count
        != sum(
            1 if isinstance(item, NativeQualityReceiverV2) else item.receiver_path_count
            for item in children
        )
        or aggregate.valid_complex_sample_count != sum(valid_counts)
        or aggregate.energy_sum_ci16_squared
        != sum(item.energy_sum_ci16_squared for item in children)
        or aggregate.clipped_component_count
        != sum(item.clipped_component_count for item in children)
        or aggregate.clipped_complex_sample_count
        != sum(item.clipped_complex_sample_count for item in children)
        or aggregate.minimum_i != min(minimum_i)
        or aggregate.maximum_i != max(maximum_i)
        or aggregate.minimum_q != min(minimum_q)
        or aggregate.maximum_q != max(maximum_q)
    ):
        raise ValueError("native aggregate sufficient statistics do not equal child sums")


def _require_aggregate_opportunities(
    aggregate: NativeOpportunityAccountingV1,
    children: tuple[NativeOpportunityAccountingV1, ...],
) -> None:
    fields = (
        "scheduled_count",
        "valid_count",
        "analyzed_count",
        "passing_count",
        "gap_excluded_count",
        "continuity_boundary_excluded_count",
        "outside_span_count",
    )
    if any(
        getattr(aggregate, field) != sum(getattr(item, field) for item in children)
        for field in fields
    ):
        raise ValueError("native aggregate opportunity accounting does not equal child sums")
