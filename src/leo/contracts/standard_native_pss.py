"""Candidate-only PSS timing evidence for one Standard-native receiver path."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.states import StarlinkEdge


class NativePssBlockDispositionV1(StrEnum):
    ANALYZED_CANDIDATE = "analyzed_candidate"
    ANALYZED_NO_CANDIDATE = "analyzed_no_candidate"
    INSUFFICIENT = "insufficient"


class NativePssSearchOriginV1(StrEnum):
    INDEPENDENT_BLIND = "independent_blind"
    GLRT_CONDITIONED = "glrt_conditioned"


class NativePssProjectionV1(ContractModel):
    schema_version: Literal[1] = 1
    projection_id: Sha256Digest
    input_sample_rate_hz: Annotated[int, Field(gt=0)]
    output_sample_rate_hz: Annotated[int, Field(gt=0)]
    input_center_frequency_hz: float
    output_center_frequency_hz: float
    channel_reference_hz: float
    slice_center_offset_hz: float
    decimation_factor: Annotated[int, Field(gt=0)]
    edge_trim_output_samples: Annotated[int, Field(ge=0)]
    projection_digest: Sha256Digest

    @field_validator(
        "input_center_frequency_hz",
        "output_center_frequency_hz",
        "channel_reference_hz",
        "slice_center_offset_hz",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native PSS projection value must be finite")
        return value

    @model_validator(mode="after")
    def _closes(self) -> Self:
        if self.input_sample_rate_hz != self.output_sample_rate_hz * self.decimation_factor:
            raise ValueError("native PSS projection sample rates do not close")
        if not math.isclose(
            self.slice_center_offset_hz,
            self.output_center_frequency_hz - self.channel_reference_hz,
            abs_tol=1e-9,
        ):
            raise ValueError("native PSS projection slice offset does not close")
        if self.projection_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"projection_digest"})
        ):
            raise ValueError("native PSS projection digest does not match")
        return self


class NativePssModeV1(ContractModel):
    schema_version: Literal[1] = 1
    mode_id: Sha256Digest
    block_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    projection_id: Sha256Digest
    origin: NativePssSearchOriginV1
    source_digest: Sha256Digest | None
    center_time_s: Annotated[float, Field(ge=0)]
    frame_phase_s: Annotated[float, Field(ge=0, lt=1.0 / 750.0)]
    nominal_frequency_offset_hz: float
    selected_frequency_offset_hz: float
    folded_score: Annotated[float, Field(ge=0)]
    folded_median: Annotated[float, Field(ge=0)]
    peak_to_median: Annotated[float, Field(ge=0)]
    robust_z: float
    frame_support: Annotated[int, Field(ge=0)]
    window_count: Annotated[int, Field(ge=0)]
    strong_window_count: Annotated[int, Field(ge=0)]
    mode_digest: Sha256Digest

    @field_validator(
        "center_time_s",
        "frame_phase_s",
        "nominal_frequency_offset_hz",
        "selected_frequency_offset_hz",
        "folded_score",
        "folded_median",
        "peak_to_median",
        "robust_z",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native PSS mode value must be finite")
        return value

    @model_validator(mode="after")
    def _closes(self) -> Self:
        conditioned = self.origin is NativePssSearchOriginV1.GLRT_CONDITIONED
        if conditioned != (self.source_digest is not None):
            raise ValueError("native PSS mode conditioned lineage does not close")
        if self.strong_window_count > self.window_count:
            raise ValueError("native PSS strong-window count exceeds all windows")
        if self.mode_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"mode_digest"})
        ):
            raise ValueError("native PSS mode digest does not match")
        return self


class NativePssSearchBlockV1(ContractModel):
    schema_version: Literal[1] = 1
    block_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    projection_id: Sha256Digest
    origin: NativePssSearchOriginV1
    source_digest: Sha256Digest | None
    input_device_sample_start: Annotated[int, Field(ge=0)]
    input_device_sample_stop: Annotated[int, Field(gt=0)]
    output_device_sample_start: Annotated[int, Field(ge=0)]
    output_sample_count: Annotated[int, Field(gt=0)]
    searched_frequency_offsets_hz: tuple[float, ...]
    complete_hypothesis_count: Annotated[int, Field(ge=0)]
    no_result_hypothesis_count: Annotated[int, Field(ge=0)]
    insufficient_hypothesis_count: Annotated[int, Field(ge=0)]
    raw_mode_count: Annotated[int, Field(ge=0)]
    retained_mode_ids: tuple[Sha256Digest, ...]
    disposition: NativePssBlockDispositionV1
    block_digest: Sha256Digest

    @field_validator("searched_frequency_offsets_hz")
    @classmethod
    def _frequencies_close(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if (
            not value
            or value != tuple(sorted(set(value)))
            or any(not math.isfinite(item) for item in value)
        ):
            raise ValueError("native PSS searched CFO inventory is not canonical")
        return value

    @model_validator(mode="after")
    def _closes(self) -> Self:
        if self.input_device_sample_stop <= self.input_device_sample_start:
            raise ValueError("native PSS block support is empty")
        conditioned = self.origin is NativePssSearchOriginV1.GLRT_CONDITIONED
        if conditioned != (self.source_digest is not None):
            raise ValueError("native PSS block conditioned lineage does not close")
        hypothesis_count = (
            self.complete_hypothesis_count
            + self.no_result_hypothesis_count
            + self.insufficient_hypothesis_count
        )
        if hypothesis_count != len(self.searched_frequency_offsets_hz):
            raise ValueError("native PSS block hypothesis accounting does not close")
        expected = (
            NativePssBlockDispositionV1.ANALYZED_CANDIDATE
            if self.retained_mode_ids
            else (
                NativePssBlockDispositionV1.INSUFFICIENT
                if self.insufficient_hypothesis_count == hypothesis_count
                else NativePssBlockDispositionV1.ANALYZED_NO_CANDIDATE
            )
        )
        if self.disposition is not expected:
            raise ValueError("native PSS block disposition does not close")
        if self.block_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"block_digest"})
        ):
            raise ValueError("native PSS block digest does not match")
        return self


class NativePssTimingTrackV1(ContractModel):
    schema_version: Literal[1] = 1
    track_id: Sha256Digest
    origin: NativePssSearchOriginV1
    mode_ids: tuple[Sha256Digest, ...]
    time_origin_s: Annotated[float, Field(ge=0)]
    coefficients_descending_s: tuple[float, float, float]
    time_start_s: Annotated[float, Field(ge=0)]
    time_stop_s: Annotated[float, Field(ge=0)]
    rms_residual_us: Annotated[float, Field(ge=0)]
    maximum_absolute_residual_us: Annotated[float, Field(ge=0)]
    residuals_us: tuple[float, ...]
    track_digest: Sha256Digest

    @field_validator(
        "time_origin_s",
        "time_start_s",
        "time_stop_s",
        "rms_residual_us",
        "maximum_absolute_residual_us",
    )
    @classmethod
    def _finite_nonnegative(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native PSS track value must be finite")
        return value

    @field_validator("coefficients_descending_s", "residuals_us")
    @classmethod
    def _finite_tuple(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("native PSS track vector must be finite")
        return value

    @model_validator(mode="after")
    def _closes(self) -> Self:
        if self.time_stop_s < self.time_start_s or len(self.mode_ids) != len(self.residuals_us):
            raise ValueError("native PSS track support does not close")
        if len(self.mode_ids) != len(set(self.mode_ids)):
            raise ValueError("native PSS track repeats a mode")
        if self.track_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"track_digest"})
        ):
            raise ValueError("native PSS track digest does not match")
        return self


class NativePssAccountingV1(ContractModel):
    schema_version: Literal[1] = 1
    blind_block_count: Annotated[int, Field(ge=0)]
    conditioned_block_count: Annotated[int, Field(ge=0)]
    candidate_block_count: Annotated[int, Field(ge=0)]
    no_candidate_block_count: Annotated[int, Field(ge=0)]
    insufficient_block_count: Annotated[int, Field(ge=0)]
    raw_mode_count: Annotated[int, Field(ge=0)]
    retained_mode_count: Annotated[int, Field(ge=0)]
    track_count: Annotated[int, Field(ge=0)]
    refined_window_count: Annotated[int, Field(ge=0)]
    strong_window_count: Annotated[int, Field(ge=0)]


class StandardNativePssFrameTimingV1(ContractModel):
    """Immutable blind and explicitly conditioned PSS timing evidence."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-native-pss-frame-timing-v1"] = (
        "standard-native-pss-frame-timing-v1"
    )
    source: StandardNativeSourceV2
    starlink_edge: StarlinkEdge
    channel_reference_hz: float
    science_configuration_digest: Sha256Digest
    projections: tuple[NativePssProjectionV1, ...]
    blocks: tuple[NativePssSearchBlockV1, ...]
    modes: tuple[NativePssModeV1, ...]
    tracks: tuple[NativePssTimingTrackV1, ...]
    accounting: NativePssAccountingV1
    result_digest: Sha256Digest
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    absolute_carrier_phase_resolved: Literal[False] = False

    @field_validator("channel_reference_hz")
    @classmethod
    def _reference_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native PSS channel reference must be finite")
        return value

    @model_validator(mode="after")
    def _result_closes(self) -> Self:
        projection_ids = tuple(item.projection_id for item in self.projections)
        if projection_ids != tuple(sorted(set(projection_ids))):
            raise ValueError("native PSS projection inventory is not canonical")
        block_keys = tuple((item.origin.value, item.block_index) for item in self.blocks)
        if block_keys != tuple(sorted(set(block_keys))):
            raise ValueError("native PSS block inventory is not canonical")
        mode_ids = tuple(item.mode_id for item in self.modes)
        if mode_ids != tuple(sorted(set(mode_ids))):
            raise ValueError("native PSS mode inventory is not canonical")
        mode_id_set = set(mode_ids)
        if any(
            item.projection_id not in projection_ids
            or not set(item.retained_mode_ids) <= mode_id_set
            for item in self.blocks
        ):
            raise ValueError("native PSS block references a foreign projection or mode")
        if any(not set(item.mode_ids) <= mode_id_set for item in self.tracks):
            raise ValueError("native PSS track references a foreign mode")
        dispositions = tuple(item.disposition for item in self.blocks)
        expected_accounting = NativePssAccountingV1(
            blind_block_count=sum(
                item.origin is NativePssSearchOriginV1.INDEPENDENT_BLIND for item in self.blocks
            ),
            conditioned_block_count=sum(
                item.origin is NativePssSearchOriginV1.GLRT_CONDITIONED for item in self.blocks
            ),
            candidate_block_count=dispositions.count(
                NativePssBlockDispositionV1.ANALYZED_CANDIDATE
            ),
            no_candidate_block_count=dispositions.count(
                NativePssBlockDispositionV1.ANALYZED_NO_CANDIDATE
            ),
            insufficient_block_count=dispositions.count(NativePssBlockDispositionV1.INSUFFICIENT),
            raw_mode_count=sum(item.raw_mode_count for item in self.blocks),
            retained_mode_count=len(self.modes),
            track_count=len(self.tracks),
            refined_window_count=sum(item.window_count for item in self.modes),
            strong_window_count=sum(item.strong_window_count for item in self.modes),
        )
        if self.accounting != expected_accounting:
            raise ValueError("native PSS accounting does not close")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("native PSS result digest does not match")
        return self
