"""Lossless projection of persisted Standard-native residual-Hough tracks.

This contract deliberately carries the segment-local trajectories already
sealed inside ``standard.native-stateful-path``.  It is not authority to fit,
join, de-alias, or otherwise reinterpret those trajectories.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1, StandardNativeSourceV2
from leo.contracts.standard_native_stateful import NativePolynomialTrajectoryV1
from leo.contracts.standard_native_stateful_v2 import NativeStatefulSegmentDispositionV2
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1


class NativeAlternateTrackProjectionDispositionV1(StrEnum):
    """Truthful projection result for one authoritative continuity segment."""

    PROJECTED = "projected"
    NO_CANDIDATE_TRACKS = "no_candidate_tracks"
    NO_STATEFUL_SCIENCE = "no_stateful_science"
    EMPTY_TERMINAL = "empty_terminal"


class NativeAlternateTrackSegmentV1(ContractModel):
    """Exact tracks copied from one segment-local residual-Hough bank."""

    schema_version: Literal[1] = 1
    continuity_segment: ContinuitySegmentV1
    continuity_segment_index: Annotated[int, Field(ge=0)]
    stateful_segment_digest: Sha256Digest
    stateful_disposition: NativeStatefulSegmentDispositionV2
    projection_disposition: NativeAlternateTrackProjectionDispositionV1
    source_science_digest: Sha256Digest | None
    source_pilot_scan_digest: Sha256Digest | None
    source_residual_hough_bank_digest: Sha256Digest | None
    source_residual_hough_configuration_digest: Sha256Digest | None
    source_observation_count: Annotated[int, Field(ge=0)]
    detected_track_count: Annotated[int, Field(ge=0)]
    returned_track_count: Annotated[int, Field(ge=0)]
    truncated_track_count: Annotated[int, Field(ge=0)]
    tracks: tuple[NativePolynomialTrajectoryV1, ...]
    segment_projection_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_projection_is_closed(self) -> Self:
        if self.continuity_segment_index != self.continuity_segment.segment_index:
            raise ValueError("native alternate-track segment index changed")
        if self.returned_track_count != len(self.tracks):
            raise ValueError("native alternate-track returned count does not close")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("native alternate-track detected count does not close")

        source_fields = (
            self.source_science_digest,
            self.source_pilot_scan_digest,
            self.source_residual_hough_bank_digest,
            self.source_residual_hough_configuration_digest,
        )
        has_science = all(item is not None for item in source_fields)
        if any(item is not None for item in source_fields) != has_science:
            raise ValueError("native alternate-track source science fields are partial")
        if has_science != (
            self.stateful_disposition is NativeStatefulSegmentDispositionV2.ANALYZED
        ):
            raise ValueError("native alternate-track source science disagrees with disposition")

        empty = self.continuity_segment.observed_sample_count == 0
        if empty != (
            self.stateful_disposition is NativeStatefulSegmentDispositionV2.EMPTY_TERMINAL
        ):
            raise ValueError("native alternate-track empty support disagrees with disposition")
        if empty:
            expected = NativeAlternateTrackProjectionDispositionV1.EMPTY_TERMINAL
        elif not has_science:
            expected = NativeAlternateTrackProjectionDispositionV1.NO_STATEFUL_SCIENCE
        elif self.tracks:
            expected = NativeAlternateTrackProjectionDispositionV1.PROJECTED
        else:
            expected = NativeAlternateTrackProjectionDispositionV1.NO_CANDIDATE_TRACKS
        if self.projection_disposition is not expected:
            raise ValueError("native alternate-track projection disposition is false")
        if not has_science and (
            self.source_observation_count
            or self.detected_track_count
            or self.returned_track_count
            or self.truncated_track_count
            or self.tracks
        ):
            raise ValueError("native alternate-track segment without science carries evidence")

        ordering = tuple(
            (
                item.start_s,
                item.end_s,
                item.method,
                item.polynomial_degree,
                item.trajectory_id,
            )
            for item in self.tracks
        )
        if ordering != tuple(sorted(ordering)):
            raise ValueError("native alternate tracks are not in source canonical order")
        if len({item.trajectory_id for item in self.tracks}) != len(self.tracks):
            raise ValueError("native alternate-track IDs repeat within a segment")
        if any(item.method != "glrt64" or item.polynomial_degree != 1 for item in self.tracks):
            raise ValueError("native alternate projection only accepts residual-Hough GLRT64 lines")
        if self.segment_projection_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_projection_digest"})
        ):
            raise ValueError("native alternate-track segment digest does not match content")
        return self


class StandardNativeAlternateCfoTrackBankV4(ContractModel):
    """Evidence-only view of exact segment-local residual-Hough candidates."""

    schema_version: Literal[4] = 4
    algorithm_version: Literal["standard-native-alternate-cfo-track-bank-v4"] = (
        "standard-native-alternate-cfo-track-bank-v4"
    )
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    source_stateful_product_digest: Sha256Digest
    source_stateful_path_digest: Sha256Digest
    science_configuration_digest: Sha256Digest
    stateful_science_status: Literal[
        "complete",
        "partial_coverage",
        "unavailable_global_schedule",
    ]
    projection_status: Literal[
        "complete",
        "no_result",
        "partial_coverage",
        "insufficient_data",
    ]
    coordinate_basis: Literal["segment-local-device-axis-v1"] = "segment-local-device-axis-v1"
    frequency_model: Literal["cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"] = (
        "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
    )
    segments: tuple[NativeAlternateTrackSegmentV1, ...]
    source_observation_count: Annotated[int, Field(ge=0)]
    detected_track_count: Annotated[int, Field(ge=0)]
    returned_track_count: Annotated[int, Field(ge=0)]
    truncated_track_count: Annotated[int, Field(ge=0)]
    bank_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    automatic_use_allowed: Literal[False] = False
    cross_segment_association_permitted: Literal[False] = False
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _bank_is_closed(self) -> Self:
        globally_schedulable = (
            self.source.missing_sample_count == 0
            and len(self.source.continuity_segments) == 1
            and self.source.continuity_segments[0].device_sample_start == 0
            and self.source.continuity_segments[0].device_sample_stop
            == self.source.logical_sample_count
        )
        if globally_schedulable != (self.stateful_science_status == "complete"):
            raise ValueError("native alternate-track stateful coverage disagrees with source")
        if len(self.segments) != len(self.source.continuity_segments):
            raise ValueError("native alternate-track bank omitted a continuity segment")
        for projected, authoritative in zip(
            self.segments,
            self.source.continuity_segments,
            strict=True,
        ):
            if projected.continuity_segment != authoritative:
                raise ValueError("native alternate-track bank changed segment authority")
            duration_s = authoritative.observed_sample_count / self.source.sample_rate_hz
            if any(
                item.reference_time_s > duration_s
                or item.start_s > duration_s
                or item.end_s > duration_s
                for item in projected.tracks
            ):
                raise ValueError("native alternate track escaped segment-local support")

        if self.source_observation_count != sum(
            item.source_observation_count for item in self.segments
        ):
            raise ValueError("native alternate-track observation accounting does not close")
        if self.detected_track_count != sum(item.detected_track_count for item in self.segments):
            raise ValueError("native alternate-track detected accounting does not close")
        if self.returned_track_count != sum(item.returned_track_count for item in self.segments):
            raise ValueError("native alternate-track returned accounting does not close")
        if self.truncated_track_count != sum(item.truncated_track_count for item in self.segments):
            raise ValueError("native alternate-track truncation accounting does not close")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("native alternate-track aggregate detected count does not close")

        scoped_ids = tuple(
            (segment.continuity_segment_index, track.trajectory_id)
            for segment in self.segments
            for track in segment.tracks
        )
        if len(set(scoped_ids)) != len(scoped_ids):
            raise ValueError("native alternate-track scoped identities repeat")

        analyzed = any(
            item.stateful_disposition is NativeStatefulSegmentDispositionV2.ANALYZED
            for item in self.segments
        )
        if not analyzed:
            expected_status = "insufficient_data"
        elif self.stateful_science_status == "partial_coverage":
            expected_status = "partial_coverage"
        elif self.stateful_science_status == "unavailable_global_schedule":
            raise ValueError("unavailable native stateful schedule cannot carry analyzed science")
        elif self.returned_track_count:
            expected_status = "complete"
        else:
            expected_status = "no_result"
        if self.projection_status != expected_status:
            raise ValueError("native alternate-track projection status is false")

        if self.bank_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"bank_digest"})
        ):
            raise ValueError("native alternate-track bank digest does not match content")
        return self


class StandardNativeAlternateCfoTrackBankV5(StandardNativeAlternateCfoTrackBankV4):
    """Additive alternate-track bank carrying StandardNativeSourceV2."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    algorithm_version: Literal["standard-native-alternate-cfo-track-bank-v5"] = (
        "standard-native-alternate-cfo-track-bank-v5"  # type: ignore[assignment]
    )
    source: StandardNativeSourceV2  # type: ignore[assignment]
