"""Gap-aware full-capture GLRT evidence for the Standard-native path."""

from __future__ import annotations

import math
import statistics
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import (
    NativeOpportunityAccountingV1,
    NativeWindowDisposition,
    NativeWindowEvidenceV1,
    StandardNativeSourceV1,
)
from leo.contracts.standard_pipeline import BoundedText
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1


class NativeFullCaptureGlrtSegmentDispositionV1(StrEnum):
    """Truthful execution state of one authoritative continuity segment."""

    ANALYZED = "analyzed"
    NO_VALID_WINDOWS = "no_valid_windows"
    EMPTY_TERMINAL = "empty_terminal"


class NativeFullCaptureGlrtOpportunityV1(ContractModel):
    """One global 20 ms opportunity, including every exclusion reason."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    validity: NativeWindowEvidenceV1


class NativeFullCaptureGlrtWindowV1(ContractModel):
    """One wholly-valid numerical result in global device-axis coordinates."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    global_device_sample_start: Annotated[int, Field(ge=0)]
    global_device_sample_stop: Annotated[int, Field(gt=0)]
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_center_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(gt=0)]
    acquisition_status: Literal["complete", "no_result", "insufficient"]
    candidate_count: Annotated[int, Field(ge=0)]
    best_candidate_rank: Annotated[int, Field(ge=0)] | None
    global_epoch_device_sample: Annotated[int, Field(ge=0)] | None
    acquired_cfo_hz: float | None
    residual_cfo_hz: float | None
    tracking_cfo_hz: float | None
    glrt_exact_score: float | None
    glrt_control_score: float | None
    glrt_margin: float | None
    passed_margin_gate: bool
    lattice_frame_count: Annotated[int, Field(ge=0)]
    measured_frame_count: Annotated[int, Field(ge=0)]
    robust_line_available: bool
    global_robust_reference_time_s: Annotated[float | None, Field(ge=0)]
    robust_cfo_at_reference_hz: float | None
    robust_slope_hz_s: float | None
    robust_slope_sigma_hz_s: float | None
    robust_residual_rms_hz: Annotated[float | None, Field(ge=0)]
    robust_median_absolute_residual_hz: Annotated[float | None, Field(ge=0)]
    robust_mad_scale_hz: Annotated[float | None, Field(ge=0)]
    robust_outlier_count: Annotated[int, Field(ge=0)]
    robust_converged: bool | None
    reason: BoundedText
    window_digest: Sha256Digest

    @field_validator(
        "global_start_time_s",
        "global_center_time_s",
        "global_end_time_s",
        "acquired_cfo_hz",
        "residual_cfo_hz",
        "tracking_cfo_hz",
        "glrt_exact_score",
        "glrt_control_score",
        "glrt_margin",
        "global_robust_reference_time_s",
        "robust_cfo_at_reference_hz",
        "robust_slope_hz_s",
        "robust_slope_sigma_hz_s",
        "robust_residual_rms_hz",
        "robust_median_absolute_residual_hz",
        "robust_mad_scale_hz",
    )
    @classmethod
    def _numerical_value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native full-capture GLRT value must be finite")
        return value

    @model_validator(mode="after")
    def _window_is_closed(self) -> Self:
        if self.global_device_sample_stop <= self.global_device_sample_start:
            raise ValueError("native GLRT window has empty or regressed support")
        if not (self.global_start_time_s < self.global_center_time_s < self.global_end_time_s):
            raise ValueError("native GLRT window times are not ordered")
        candidate_fields = (
            self.best_candidate_rank,
            self.global_epoch_device_sample,
            self.acquired_cfo_hz,
            self.residual_cfo_hz,
            self.tracking_cfo_hz,
            self.glrt_exact_score,
            self.glrt_control_score,
            self.glrt_margin,
        )
        if bool(self.candidate_count) != all(item is not None for item in candidate_fields):
            raise ValueError("native GLRT candidate fields do not close")
        if self.passed_margin_gate and self.glrt_margin is None:
            raise ValueError("native GLRT margin pass lacks a measured margin")
        robust_required = (
            self.global_robust_reference_time_s,
            self.robust_cfo_at_reference_hz,
            self.robust_slope_hz_s,
            self.robust_residual_rms_hz,
            self.robust_median_absolute_residual_hz,
            self.robust_mad_scale_hz,
            self.robust_converged,
        )
        if self.robust_line_available != all(item is not None for item in robust_required):
            raise ValueError("native GLRT robust-line fields do not close")
        if not self.robust_line_available and (
            self.robust_slope_sigma_hz_s is not None or self.robust_outlier_count
        ):
            raise ValueError("unavailable native GLRT line carries fit evidence")
        if self.window_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"window_digest"})
        ):
            raise ValueError("native GLRT window digest does not match content")
        return self


class NativeFullCaptureGlrtTrackObservationV1(ContractModel):
    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    global_device_sample: Annotated[int, Field(ge=0)]
    global_time_s: Annotated[float, Field(ge=0)]
    raw_cfo_hz: float
    alias_index: int

    @field_validator("global_time_s", "raw_cfo_hz")
    @classmethod
    def _observation_value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native Hough observation value must be finite")
        return value


class NativeFullCaptureGlrtHoughTrackV1(ContractModel):
    schema_version: Literal[1] = 1
    track_label: BoundedText
    global_device_sample_start: Annotated[int, Field(ge=0)]
    global_device_sample_end: Annotated[int, Field(ge=0)]
    global_reference_device_sample: Annotated[float, Field(ge=0)]
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(ge=0)]
    global_reference_time_s: Annotated[float, Field(ge=0)]
    slope_hz_s: float
    cfo_at_reference_hz: float
    observation_count: Annotated[int, Field(gt=0)]
    observations: tuple[NativeFullCaptureGlrtTrackObservationV1, ...]
    track_digest: Sha256Digest

    @field_validator(
        "global_reference_device_sample",
        "global_start_time_s",
        "global_end_time_s",
        "global_reference_time_s",
        "slope_hz_s",
        "cfo_at_reference_hz",
    )
    @classmethod
    def _track_value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native Hough track value must be finite")
        return value

    @model_validator(mode="after")
    def _track_is_closed(self) -> Self:
        if self.observation_count != len(self.observations):
            raise ValueError("native Hough track observation count does not close")
        indexes = tuple(item.opportunity_index for item in self.observations)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("native Hough track observations are not canonical")
        if (
            self.global_device_sample_start != self.observations[0].global_device_sample
            or self.global_device_sample_end != self.observations[-1].global_device_sample
            or self.global_start_time_s != self.observations[0].global_time_s
            or self.global_end_time_s != self.observations[-1].global_time_s
            or not self.global_start_time_s
            <= self.global_reference_time_s
            <= self.global_end_time_s
        ):
            raise ValueError("native Hough track global support does not close")
        if self.track_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"track_digest"})
        ):
            raise ValueError("native Hough track digest does not match content")
        return self


class NativeFullCaptureGlrtHoughV1(ContractModel):
    schema_version: Literal[1] = 1
    input_observation_count: Annotated[int, Field(ge=0)]
    raw_hough_track_count: Annotated[int, Field(ge=0)]
    truncated_hough_track_count: Annotated[int, Field(ge=0)]
    published_track_count: Annotated[int, Field(ge=0)]
    returned_observation_count: Annotated[int, Field(ge=0)]
    tracks: tuple[NativeFullCaptureGlrtHoughTrackV1, ...]
    hough_digest: Sha256Digest

    @model_validator(mode="after")
    def _hough_is_closed(self) -> Self:
        if self.published_track_count != len(self.tracks):
            raise ValueError("native Hough published-track count does not close")
        labels = tuple(item.track_label for item in self.tracks)
        if len(labels) != len(set(labels)):
            raise ValueError("native Hough track labels must be unique")
        ordering = tuple(
            (item.global_device_sample_start, item.global_device_sample_end, item.track_label)
            for item in self.tracks
        )
        if ordering != tuple(sorted(ordering)):
            raise ValueError("native Hough tracks are not globally ordered")
        if self.returned_observation_count > self.input_observation_count:
            raise ValueError("native Hough returned observations exceed its input")
        if self.hough_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"hough_digest"})
        ):
            raise ValueError("native Hough digest does not match content")
        return self


class NativeFullCaptureGlrtConstantRateV1(ContractModel):
    schema_version: Literal[1] = 1
    input_filter: Literal[
        "margin passes; within-window line RMS is at or below the display reference; "
        "Doppler rate lies inside +/-10 kHz/s"
    ]
    point_count: Annotated[int, Field(gt=0)]
    supporting_opportunity_indexes: tuple[Annotated[int, Field(ge=0)], ...]
    global_center_sample_start: Annotated[int, Field(ge=0)]
    global_center_sample_end: Annotated[int, Field(ge=0)]
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(ge=0)]
    constant_doppler_rate_hz_s: float
    median_absolute_deviation_hz_s: Annotated[float, Field(ge=0)]
    summary_digest: Sha256Digest

    @field_validator(
        "global_start_time_s",
        "global_end_time_s",
        "constant_doppler_rate_hz_s",
        "median_absolute_deviation_hz_s",
    )
    @classmethod
    def _rate_value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native constant-rate value must be finite")
        return value

    @model_validator(mode="after")
    def _summary_is_closed(self) -> Self:
        if self.point_count != len(
            self.supporting_opportunity_indexes
        ) or self.supporting_opportunity_indexes != tuple(
            sorted(set(self.supporting_opportunity_indexes))
        ):
            raise ValueError("native constant-rate support inventory does not close")
        if (
            self.global_center_sample_start > self.global_center_sample_end
            or self.global_start_time_s > self.global_end_time_s
        ):
            raise ValueError("native constant-rate support regressed")
        if self.summary_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"summary_digest"})
        ):
            raise ValueError("native constant-rate digest does not match content")
        return self


class NativeFullCaptureGlrtSegmentV1(ContractModel):
    """All numerical results reset and fitted within one continuity segment."""

    schema_version: Literal[1] = 1
    continuity_segment: ContinuitySegmentV1
    disposition: NativeFullCaptureGlrtSegmentDispositionV1
    valid_opportunity_indexes: tuple[Annotated[int, Field(ge=0)], ...]
    windows: tuple[NativeFullCaptureGlrtWindowV1, ...]
    hough: NativeFullCaptureGlrtHoughV1
    constant_rate: NativeFullCaptureGlrtConstantRateV1 | None
    segment_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        indexes = tuple(item.opportunity_index for item in self.windows)
        if self.valid_opportunity_indexes != indexes or indexes != tuple(sorted(set(indexes))):
            raise ValueError("native GLRT segment opportunity inventory does not close")
        expected_disposition = (
            NativeFullCaptureGlrtSegmentDispositionV1.EMPTY_TERMINAL
            if self.continuity_segment.observed_sample_count == 0
            else (
                NativeFullCaptureGlrtSegmentDispositionV1.ANALYZED
                if self.windows
                else NativeFullCaptureGlrtSegmentDispositionV1.NO_VALID_WINDOWS
            )
        )
        if self.disposition is not expected_disposition:
            raise ValueError("native GLRT segment disposition disagrees with its windows")
        passing = sum(item.passed_margin_gate for item in self.windows)
        if self.hough.input_observation_count != passing:
            raise ValueError("native Hough input count disagrees with passing windows")
        if self.constant_rate is not None and self.constant_rate.point_count > len(self.windows):
            raise ValueError("native constant-rate support exceeds analyzed windows")
        if self.segment_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_digest"})
        ):
            raise ValueError("native GLRT segment digest does not match content")
        return self


class StandardNativeFullCaptureGlrt20msV1(ContractModel):
    """Evidence-only global schedule with segment-local fits and no gap bridging."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-native-full-capture-glrt20ms-v1"] = (
        "standard-native-full-capture-glrt20ms-v1"
    )
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    science_configuration_digest: Sha256Digest
    window_ms: Literal[20] = 20
    stride_ms: Literal[10] = 10
    window_samples: Annotated[int, Field(gt=0)]
    stride_samples: Annotated[int, Field(gt=0)]
    opportunities: tuple[NativeFullCaptureGlrtOpportunityV1, ...]
    accounting: NativeOpportunityAccountingV1
    schedule_digest: Sha256Digest
    segments: tuple[NativeFullCaptureGlrtSegmentV1, ...]
    segment_results_digest: Sha256Digest
    result_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        expected_window = self.source.sample_rate_hz * self.window_ms // 1_000
        expected_stride = self.source.sample_rate_hz * self.stride_ms // 1_000
        if (
            self.source.sample_rate_hz * self.window_ms % 1_000
            or self.source.sample_rate_hz * self.stride_ms % 1_000
            or self.window_samples != expected_window
            or self.stride_samples != expected_stride
        ):
            raise ValueError("native GLRT window geometry disagrees with source rate")
        expected_starts = tuple(
            range(
                0,
                self.source.logical_sample_count - self.window_samples + 1,
                self.stride_samples,
            )
        )
        if tuple(item.opportunity_index for item in self.opportunities) != tuple(
            range(len(self.opportunities))
        ) or tuple(item.validity.device_sample_start for item in self.opportunities) != (
            expected_starts
        ):
            raise ValueError("native GLRT global opportunity schedule is not canonical")
        for opportunity in self.opportunities:
            expected = _classify_source_window(
                self.source,
                opportunity.validity.device_sample_start,
                self.window_samples,
            )
            if opportunity.validity != expected:
                raise ValueError("native GLRT opportunity validity disagrees with source")
        dispositions = tuple(item.validity.disposition for item in self.opportunities)
        expected_accounting = NativeOpportunityAccountingV1(
            scheduled_count=len(self.opportunities),
            valid_count=dispositions.count(NativeWindowDisposition.VALID),
            analyzed_count=dispositions.count(NativeWindowDisposition.VALID),
            passing_count=sum(
                window.passed_margin_gate for segment in self.segments for window in segment.windows
            ),
            gap_excluded_count=dispositions.count(NativeWindowDisposition.GAP_OVERLAP),
            continuity_boundary_excluded_count=dispositions.count(
                NativeWindowDisposition.CONTINUITY_BOUNDARY
            ),
            outside_span_count=dispositions.count(NativeWindowDisposition.OUTSIDE_SPAN),
        )
        if self.accounting != expected_accounting:
            raise ValueError("native GLRT opportunity accounting does not close")
        schedule_values = {
            "kind": "standard-native-full-capture-glrt20ms-schedule-v1",
            "path_input_binding_digest": self.source.path_input_binding_digest,
            "validity_inventory_digest": self.source.validity_inventory_digest,
            "sample_rate_hz": self.source.sample_rate_hz,
            "logical_sample_count": self.source.logical_sample_count,
            "window_samples": self.window_samples,
            "stride_samples": self.stride_samples,
            "opportunities": tuple(item.model_dump(mode="json") for item in self.opportunities),
        }
        if self.schedule_digest != canonical_digest(schedule_values):
            raise ValueError("native GLRT schedule digest does not match content")
        if len(self.segments) != len(self.source.continuity_segments):
            raise ValueError("native GLRT result omitted an authoritative segment")
        by_opportunity = {item.opportunity_index: item for item in self.opportunities}
        retained_valid: list[int] = []
        for result, segment in zip(
            self.segments,
            self.source.continuity_segments,
            strict=True,
        ):
            if result.continuity_segment != segment:
                raise ValueError("native GLRT segment changed validity authority")
            if (
                not segment.observed_sample_count
                and segment.segment_index != len(self.source.continuity_segments) - 1
            ):
                raise ValueError("native GLRT encountered a nonterminal empty segment")
            for window in result.windows:
                resolved_opportunity = by_opportunity.get(window.opportunity_index)
                if (
                    resolved_opportunity is None
                    or resolved_opportunity.validity.disposition
                    is not NativeWindowDisposition.VALID
                    or resolved_opportunity.validity.continuity_segment_index
                    != segment.segment_index
                    or window.continuity_segment_index != segment.segment_index
                    or window.global_device_sample_start
                    != resolved_opportunity.validity.device_sample_start
                    or window.global_device_sample_stop
                    != resolved_opportunity.validity.device_sample_start + self.window_samples
                ):
                    raise ValueError("native GLRT window escaped its valid opportunity")
                _validate_window_global_coordinates(window, self.source.sample_rate_hz)
                retained_valid.append(window.opportunity_index)
            valid_by_index = {item.opportunity_index for item in result.windows}
            for track in result.hough.tracks:
                if not math.isclose(
                    track.global_reference_device_sample,
                    track.global_reference_time_s * self.source.sample_rate_hz,
                    abs_tol=1e-9,
                ):
                    raise ValueError("native Hough reference is not on the global device axis")
                for observation in track.observations:
                    resolved_window = next(
                        (
                            item
                            for item in result.windows
                            if item.opportunity_index == observation.opportunity_index
                        ),
                        None,
                    )
                    if (
                        resolved_window is None
                        or not resolved_window.passed_margin_gate
                        or observation.global_device_sample
                        != resolved_window.global_device_sample_start
                        or not math.isclose(
                            observation.global_time_s,
                            resolved_window.global_start_time_s,
                            abs_tol=1e-12,
                        )
                    ):
                        raise ValueError("native Hough observation escaped its continuity segment")
                if not set(item.opportunity_index for item in track.observations) <= valid_by_index:
                    raise ValueError("native Hough track references another segment")
            if result.constant_rate is not None:
                windows_by_index = {window.opportunity_index: window for window in result.windows}
                support_indexes = result.constant_rate.supporting_opportunity_indexes
                if not support_indexes or any(
                    index not in windows_by_index for index in support_indexes
                ):
                    raise ValueError("native constant-rate summary escaped its segment windows")
                support = tuple(windows_by_index[index] for index in support_indexes)
                support_rates = tuple(item.robust_slope_hz_s for item in support)
                if any(
                    not item.passed_margin_gate
                    or not item.robust_line_available
                    or item.robust_slope_hz_s is None
                    for item in support
                ):
                    raise ValueError("native constant-rate support is not scientifically valid")
                rates = tuple(float(item) for item in support_rates if item is not None)
                expected_rate = statistics.median(rates)
                expected_mad = statistics.median(abs(item - expected_rate) for item in rates)
                if (
                    result.constant_rate.global_center_sample_start
                    != (
                        support[0].global_device_sample_start + support[0].global_device_sample_stop
                    )
                    // 2
                    or result.constant_rate.global_center_sample_end
                    != (
                        support[-1].global_device_sample_start
                        + support[-1].global_device_sample_stop
                    )
                    // 2
                    or not math.isclose(
                        result.constant_rate.constant_doppler_rate_hz_s,
                        expected_rate,
                        abs_tol=1e-12,
                    )
                    or not math.isclose(
                        result.constant_rate.median_absolute_deviation_hz_s,
                        expected_mad,
                        abs_tol=1e-12,
                    )
                ):
                    raise ValueError("native constant-rate summary escaped its segment windows")
        expected_valid_indexes = tuple(
            item.opportunity_index
            for item in self.opportunities
            if item.validity.disposition is NativeWindowDisposition.VALID
        )
        if tuple(retained_valid) != expected_valid_indexes:
            raise ValueError("native GLRT result omitted or duplicated a valid opportunity")
        segment_values = tuple(item.model_dump(mode="json") for item in self.segments)
        if self.segment_results_digest != canonical_digest(segment_values):
            raise ValueError("native GLRT segment-results digest does not match content")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("native full-capture GLRT digest does not match content")
        return self


def _classify_source_window(
    source: StandardNativeSourceV1,
    device_sample_start: int,
    sample_count: int,
) -> NativeWindowEvidenceV1:
    device_sample_stop = device_sample_start + sample_count
    if device_sample_start < 0 or device_sample_stop > source.logical_sample_count:
        return NativeWindowEvidenceV1(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            disposition=NativeWindowDisposition.OUTSIDE_SPAN,
        )
    missing = 0
    cursor = 0
    for segment in source.continuity_segments:
        if segment.device_sample_start > cursor:
            missing += _overlap(
                device_sample_start,
                device_sample_stop,
                cursor,
                segment.device_sample_start,
            )
        cursor = segment.device_sample_stop
    crossed = tuple(
        segment.segment_index
        for segment in source.continuity_segments[1:]
        if device_sample_start < segment.device_sample_start < device_sample_stop
    )
    if missing:
        return NativeWindowEvidenceV1(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            disposition=NativeWindowDisposition.GAP_OVERLAP,
            missing_sample_count=missing,
            crossed_segment_indexes=crossed,
        )
    if crossed:
        return NativeWindowEvidenceV1(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            disposition=NativeWindowDisposition.CONTINUITY_BOUNDARY,
            crossed_segment_indexes=crossed,
        )
    resolved_segment = next(
        (
            item
            for item in source.continuity_segments
            if item.device_sample_start <= device_sample_start
            and device_sample_stop <= item.device_sample_stop
        ),
        None,
    )
    if resolved_segment is None:
        raise ValueError("native GLRT opportunity lies outside source segments")
    return NativeWindowEvidenceV1(
        device_sample_start=device_sample_start,
        sample_count=sample_count,
        disposition=NativeWindowDisposition.VALID,
        continuity_segment_index=resolved_segment.segment_index,
    )


def _overlap(left_start: int, left_stop: int, right_start: int, right_stop: int) -> int:
    return max(0, min(left_stop, right_stop) - max(left_start, right_start))


def _validate_window_global_coordinates(
    window: NativeFullCaptureGlrtWindowV1,
    sample_rate_hz: int,
) -> None:
    start = window.global_device_sample_start / sample_rate_hz
    stop = window.global_device_sample_stop / sample_rate_hz
    center = (start + stop) / 2
    if not (
        math.isclose(window.global_start_time_s, start, abs_tol=1e-12)
        and math.isclose(window.global_end_time_s, stop, abs_tol=1e-12)
        and math.isclose(window.global_center_time_s, center, abs_tol=1e-12)
    ):
        raise ValueError("native GLRT window time is not on the global device axis")
    if window.global_epoch_device_sample is not None and not (
        window.global_device_sample_start
        <= window.global_epoch_device_sample
        < window.global_device_sample_stop
    ):
        raise ValueError("native GLRT epoch escaped its global window")
    if window.global_robust_reference_time_s is not None and not (
        window.global_start_time_s
        <= window.global_robust_reference_time_s
        <= window.global_end_time_s
    ):
        raise ValueError("native GLRT robust reference escaped its global window")
