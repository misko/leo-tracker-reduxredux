"""Immutable candidate-only alternate CFO line-finder products."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class AlternateCfoLineFinderConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm: Literal["weighted_alias_aware_hough"] = "weighted_alias_aware_hough"
    alias_spacing_hz: Annotated[float, Field(gt=0)]
    minimum_slope_hz_per_s: float
    maximum_slope_hz_per_s: float
    residual_gate_hz: Annotated[float, Field(gt=0)]
    maximum_gap_s: Annotated[float, Field(gt=0)]
    minimum_span_s: Annotated[float, Field(gt=0)]
    minimum_support: Annotated[int, Field(ge=2, le=256)]
    minimum_point_weight: Annotated[float, Field(ge=0, le=16)]
    slope_bins: Annotated[int, Field(ge=3, le=257)]
    intercept_bins: Annotated[int, Field(ge=16, le=1024)]
    peak_candidates: Annotated[int, Field(ge=1, le=64)]
    maximum_detected_tracks: Annotated[int, Field(ge=1, le=32)]
    maximum_published_tracks: Annotated[int, Field(ge=1, le=16)]
    maximum_input_points: Annotated[int, Field(ge=1, le=25_000)]

    @field_validator(
        "alias_spacing_hz",
        "minimum_slope_hz_per_s",
        "maximum_slope_hz_per_s",
        "residual_gate_hz",
        "maximum_gap_s",
        "minimum_span_s",
        "minimum_point_weight",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("line-finder configuration must be finite")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.minimum_slope_hz_per_s >= self.maximum_slope_hz_per_s:
            raise ValueError("line-finder slope bounds are not ordered")
        if self.maximum_published_tracks > self.maximum_detected_tracks:
            raise ValueError("published track bound exceeds detector bound")
        if self.residual_gate_hz >= self.alias_spacing_hz / 2:
            raise ValueError("residual gate must be below half the alias spacing")
        return self


class AlternateCfoTrackV1(ContractModel):
    schema_version: Literal[1] = 1
    track_id: Sha256Digest
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    span_s: Annotated[float, Field(ge=0)]
    support_count: Annotated[int, Field(ge=2, le=25_000)]
    weighted_support: Annotated[float, Field(ge=0)]
    slope_hz_per_s: float
    acceleration_hz_per_s2: Annotated[float, Field(ge=0, le=0)] = 0.0
    intercept_mod_alias_hz: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    maximum_gap_s: Annotated[float, Field(ge=0)]
    confidence: Literal["strong_geometry", "candidate_geometry"]
    status: Literal["research_only"] = "research_only"

    @field_validator(
        "start_s",
        "end_s",
        "span_s",
        "weighted_support",
        "slope_hz_per_s",
        "intercept_mod_alias_hz",
        "residual_rms_hz",
        "residual_max_hz",
        "maximum_gap_s",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("alternate track values must be finite")
        return value

    @model_validator(mode="after")
    def _geometry(self) -> Self:
        if self.end_s < self.start_s or not math.isclose(
            self.span_s, self.end_s - self.start_s, abs_tol=1e-9
        ):
            raise ValueError("alternate track span is inconsistent")
        if self.residual_rms_hz > self.residual_max_hz:
            raise ValueError("alternate track residual bounds are inconsistent")
        return self


class AlternateCfoTrackBankV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["alternate-cfo-hough-v1"] = "alternate-cfo-hough-v1"
    pilot_scan_content_digest: Sha256Digest
    configuration_digest: Sha256Digest
    configuration: AlternateCfoLineFinderConfigV1
    source_point_count: Annotated[int, Field(ge=0, le=25_000)]
    detected_track_count: Annotated[int, Field(ge=0, le=32)]
    returned_track_count: Annotated[int, Field(ge=0, le=16)]
    truncated_track_count: Annotated[int, Field(ge=0, le=32)]
    tracks: tuple[AlternateCfoTrackV1, ...] = Field(max_length=16)
    frequency_coordinate: Literal["baseband_cfo_hz"] = "baseband_cfo_hz"
    candidate_only: Literal[True] = True
    automatic_use_allowed: Literal[False] = False
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if self.configuration_digest != canonical_digest(
            self.configuration.model_dump(mode="json")
        ):
            raise ValueError("alternate-track configuration digest disagrees with configuration")
        if self.returned_track_count != len(self.tracks):
            raise ValueError("returned alternate-track count disagrees with rows")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("alternate-track truncation accounting is inconsistent")
        if self.source_point_count > self.configuration.maximum_input_points:
            raise ValueError("alternate-track source inventory exceeds configured bound")
        if self.detected_track_count > self.configuration.maximum_detected_tracks:
            raise ValueError("alternate-track detector inventory exceeds configured bound")
        if self.returned_track_count > self.configuration.maximum_published_tracks:
            raise ValueError("alternate-track output inventory exceeds configured bound")
        ids = tuple(item.track_id for item in self.tracks)
        if len(ids) != len(set(ids)):
            raise ValueError("alternate track identifiers must be unique")
        return self
