"""Additive global-schedule stateful evidence for Standard-native paths.

Version 1 remains the immutable lossless-or-unavailable contract.  Version 2
adds truthful partial coverage for a persisted global probe schedule without
changing any V1 enum, validator, or serialized byte.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_native_stateful import NativeSegmentLocalScienceV1
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1


class NativeStatefulSegmentDispositionV2(StrEnum):
    """Truthful V2 disposition for one authoritative continuity segment."""

    ANALYZED = "analyzed"
    EMPTY_TERMINAL = "empty_terminal"
    NO_COMPLETE_OUTER_WINDOW = "no_complete_outer_window"
    OUTER_WINDOW_BUDGET_EXHAUSTED = "outer_window_budget_exhausted"
    NO_VALID_GLOBAL_PROBE = "no_valid_global_probe"
    GLOBAL_SCHEDULE_UNAVAILABLE = "global_schedule_unavailable"


class NativeStatefulSegmentV2(ContractModel):
    """One reset-local segment under the V2 global-schedule authority."""

    schema_version: Literal[2] = 2
    continuity_segment: ContinuitySegmentV1
    continuity_segment_index: Annotated[int, Field(ge=0)]
    global_device_sample_start: Annotated[int, Field(ge=0)]
    global_device_sample_stop: Annotated[int, Field(ge=0)]
    disposition: NativeStatefulSegmentDispositionV2
    local_science: NativeSegmentLocalScienceV1 | None
    segment_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        segment = self.continuity_segment
        if (
            self.continuity_segment_index != segment.segment_index
            or self.global_device_sample_start != segment.device_sample_start
            or self.global_device_sample_stop != segment.device_sample_stop
        ):
            raise ValueError("native stateful V2 segment changed authoritative global bounds")
        analyzed = self.disposition is NativeStatefulSegmentDispositionV2.ANALYZED
        if analyzed != (self.local_science is not None):
            raise ValueError("native stateful V2 segment disposition disagrees with science")
        empty = segment.observed_sample_count == 0
        if (self.disposition is NativeStatefulSegmentDispositionV2.EMPTY_TERMINAL) != empty:
            raise ValueError("native stateful V2 empty-terminal disposition disagrees with support")
        if self.segment_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_digest"})
        ):
            raise ValueError("native stateful V2 segment digest does not match content")
        return self


class StandardNativeStatefulPathV2(ContractModel):
    """Digest-bound stateful chain driven by canonical global opportunities."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-native-stateful-path-v2"] = (
        "standard-native-stateful-path-v2"
    )
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    science_configuration_digest: Sha256Digest
    stateful_science_status: Literal[
        "complete",
        "partial_coverage",
        "unavailable_global_schedule",
    ]
    maximum_outer_window_count: Annotated[int, Field(gt=0)]
    analyzed_outer_window_count: Annotated[int, Field(ge=0)]
    segments: tuple[NativeStatefulSegmentV2, ...]
    stateful_path_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _stateful_path_is_closed(self) -> Self:
        if len(self.segments) != len(self.source.continuity_segments):
            raise ValueError("native stateful V2 path omitted an authoritative segment")
        for persisted, authoritative in zip(
            self.segments,
            self.source.continuity_segments,
            strict=True,
        ):
            if persisted.continuity_segment != authoritative:
                raise ValueError("native stateful V2 path segment inventory changed")
            science = persisted.local_science
            if science is None:
                continue
            expected_binding = canonical_digest(
                {
                    "kind": "standard-native-segment-local-binding-v1",
                    "path_input_binding_digest": self.source.path_input_binding_digest,
                    "validity_inventory_digest": self.source.validity_inventory_digest,
                    "segment": authoritative.model_dump(mode="json"),
                    "science_configuration_digest": self.science_configuration_digest,
                    "effective_maximum_outer_windows": science.scheduled_outer_window_count,
                }
            )
            if science.segment_path_binding_digest != expected_binding:
                raise ValueError("native stateful V2 segment-local binding digest does not close")
            duration_s = authoritative.observed_sample_count / self.source.sample_rate_hz
            for detection in science.detections:
                if detection.sample_start > authoritative.observed_sample_count or not math.isclose(
                    detection.time_s,
                    detection.sample_start / self.source.sample_rate_hz,
                    abs_tol=1e-12,
                ):
                    raise ValueError("native V2 pilot detection escaped segment-local coordinates")
            for row in science.conditioned_hough_replay:
                if row.sample_start > authoritative.observed_sample_count or not math.isclose(
                    row.time_s,
                    row.sample_start / self.source.sample_rate_hz,
                    abs_tol=1e-12,
                ):
                    raise ValueError("native V2 replay row escaped segment-local coordinates")
            if any(
                item.start_s > duration_s or item.end_s > duration_s
                for item in science.residual_hough_bank.trajectories
            ):
                raise ValueError("native V2 trajectory escaped segment-local time support")
        analyzed = sum(
            item.local_science.scheduled_outer_window_count
            for item in self.segments
            if item.local_science is not None
        )
        if (
            analyzed != self.analyzed_outer_window_count
            or analyzed > self.maximum_outer_window_count
        ):
            raise ValueError("native stateful V2 outer-window accounting does not close")
        globally_schedulable = (
            self.source.missing_sample_count == 0
            and len(self.source.continuity_segments) == 1
            and self.source.continuity_segments[0].device_sample_start == 0
            and self.source.continuity_segments[0].device_sample_stop
            == self.source.logical_sample_count
        )
        if globally_schedulable:
            if self.stateful_science_status != "complete":
                raise ValueError("lossless native stateful V2 status must be complete")
        elif self.stateful_science_status == "unavailable_global_schedule":
            if self.analyzed_outer_window_count or any(
                item.local_science is not None for item in self.segments
            ):
                raise ValueError("unavailable native stateful V2 evidence carries local science")
            if any(
                item.disposition
                not in {
                    NativeStatefulSegmentDispositionV2.GLOBAL_SCHEDULE_UNAVAILABLE,
                    NativeStatefulSegmentDispositionV2.EMPTY_TERMINAL,
                }
                for item in self.segments
            ):
                raise ValueError("unavailable native stateful V2 evidence has a false claim")
        elif self.stateful_science_status == "partial_coverage":
            if any(
                item.disposition
                not in {
                    NativeStatefulSegmentDispositionV2.ANALYZED,
                    NativeStatefulSegmentDispositionV2.NO_VALID_GLOBAL_PROBE,
                    NativeStatefulSegmentDispositionV2.EMPTY_TERMINAL,
                }
                for item in self.segments
            ):
                raise ValueError("global-schedule native stateful V2 disposition is invalid")
        else:
            raise ValueError("gapped native stateful V2 status must describe schedule coverage")
        if self.segments[-1].global_device_sample_stop != self.source.logical_sample_count:
            raise ValueError("native stateful V2 segments do not close the global logical span")
        if self.stateful_path_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"stateful_path_digest"})
        ):
            raise ValueError("native stateful V2 path digest does not match content")
        return self
