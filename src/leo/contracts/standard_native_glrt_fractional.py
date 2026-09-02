"""Fractional GLRT epoch evidence attached to the existing Standard-native path."""

from __future__ import annotations

import math
import sys
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_pipeline import BoundedText
from leo.contracts.states import StarlinkEdge

FRACTIONAL_GLRT_EPOCH_OFFSETS_V1 = (-2, -1, 0, 1, 2)


class NativeGlrtFractionalEpochStatusV1(StrEnum):
    COMPLETE = "complete"
    UNBRACKETED = "unbracketed"
    UNAVAILABLE = "unavailable"


def fractional_log_peak_offset_v1(scores: tuple[float, ...]) -> float | None:
    """Contract oracle for the reviewed five-cell log-parabolic estimator."""

    if len(scores) != len(FRACTIONAL_GLRT_EPOCH_OFFSETS_V1):
        raise ValueError("fractional GLRT score grid has the wrong size")
    values = tuple(float(item) for item in scores)
    if any(not math.isfinite(item) or item < 0.0 for item in values):
        raise ValueError("fractional GLRT score grid must be finite and nonnegative")
    index = max(range(len(values)), key=values.__getitem__)
    if index == 0 or index == len(values) - 1:
        return None
    selected = tuple(
        math.log(max(item, sys.float_info.min)) for item in values[index - 1 : index + 2]
    )
    denominator = float(selected[0] - 2.0 * selected[1] + selected[2])
    if not math.isfinite(denominator) or denominator >= -sys.float_info.epsilon:
        return None
    fraction = min(0.5, max(-0.5, 0.5 * (selected[0] - selected[2]) / denominator))
    return float(FRACTIONAL_GLRT_EPOCH_OFFSETS_V1[index] + fraction)


class NativeGlrtFractionalEpochRefinementV1(ContractModel):
    """One fixed-CFO exact-GLRT timing refinement for a passing window."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    integer_global_epoch_device_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    integer_exact_score: Annotated[float, Field(ge=0)]
    status: NativeGlrtFractionalEpochStatusV1
    exact_score_grid: tuple[float, float, float, float, float] | None
    fractional_epoch_offset_samples: Annotated[float | None, Field(ge=-1.5, le=1.5)]
    fractional_global_epoch_device_sample: Annotated[float | None, Field(ge=0)]
    refinement_digest: Sha256Digest

    @field_validator("acquired_cfo_hz")
    @classmethod
    def _cfo_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("fractional GLRT acquired CFO must be finite")
        return value

    @field_validator("exact_score_grid")
    @classmethod
    def _score_grid_is_finite(
        cls, value: tuple[float, float, float, float, float] | None
    ) -> tuple[float, float, float, float, float] | None:
        if value is not None and (any(not math.isfinite(item) for item in value) or min(value) < 0):
            raise ValueError("fractional GLRT exact scores must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def _refinement_is_closed(self) -> Self:
        offset_present = self.fractional_epoch_offset_samples is not None
        global_present = self.fractional_global_epoch_device_sample is not None
        if offset_present != global_present:
            raise ValueError("fractional GLRT peak coordinates must be jointly present")
        fields_present = offset_present and global_present
        if self.status is NativeGlrtFractionalEpochStatusV1.UNAVAILABLE:
            if self.exact_score_grid is not None or fields_present:
                raise ValueError("unavailable fractional GLRT refinement carries measurements")
        else:
            if self.exact_score_grid is None:
                raise ValueError("evaluated fractional GLRT refinement lacks its score grid")
            if not math.isclose(
                self.exact_score_grid[2], self.integer_exact_score, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError("fractional GLRT center score differs from integer evidence")
            expected = fractional_log_peak_offset_v1(self.exact_score_grid)
            if self.status is NativeGlrtFractionalEpochStatusV1.COMPLETE:
                if expected is None or not fields_present:
                    raise ValueError("complete fractional GLRT refinement is not bracketed")
                assert self.fractional_epoch_offset_samples is not None
                assert self.fractional_global_epoch_device_sample is not None
                if not math.isclose(
                    self.fractional_epoch_offset_samples,
                    expected,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ) or not math.isclose(
                    self.fractional_global_epoch_device_sample,
                    self.integer_global_epoch_device_sample + expected,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    raise ValueError("fractional GLRT peak does not close its score grid")
            elif expected is not None or fields_present:
                raise ValueError("unbracketed fractional GLRT refinement carries a peak")
        if self.refinement_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"refinement_digest"})
        ):
            raise ValueError("fractional GLRT refinement digest does not match content")
        return self


class StandardNativeGlrtFractionalEpochV1(ContractModel):
    """Auditable fractional timing surfaces for passing full-capture GLRT windows."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-native-glrt-fractional-epoch-v1"] = (
        "standard-native-glrt-fractional-epoch-v1"
    )
    source: StandardNativeSourceV2
    source_glrt_product_digest: Sha256Digest
    source_glrt_result_digest: Sha256Digest
    configuration_digest: Sha256Digest
    starlink_edge: StarlinkEdge
    score_definition: Literal["conditioned-exact-glrt64-at-fixed-acquired-cfo"] = (
        "conditioned-exact-glrt64-at-fixed-acquired-cfo"
    )
    interpolation_method: Literal["three-cell-log-parabola-v1"] = "three-cell-log-parabola-v1"
    selection_policy: Literal["persisted-margin-pass-windows-only"] = (
        "persisted-margin-pass-windows-only"
    )
    score_grid_offsets_samples: tuple[int, int, int, int, int]
    refinement_count: Annotated[int, Field(ge=0)]
    complete_count: Annotated[int, Field(ge=0)]
    unbracketed_count: Annotated[int, Field(ge=0)]
    unavailable_count: Annotated[int, Field(ge=0)]
    refinements: tuple[NativeGlrtFractionalEpochRefinementV1, ...]
    limitations: tuple[BoundedText, ...]
    result_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        if self.score_grid_offsets_samples != FRACTIONAL_GLRT_EPOCH_OFFSETS_V1:
            raise ValueError("fractional GLRT score grid offsets differ from V1")
        indexes = tuple(item.opportunity_index for item in self.refinements)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("fractional GLRT refinements are not canonical")
        statuses = tuple(item.status for item in self.refinements)
        if (
            self.refinement_count != len(self.refinements)
            or self.complete_count != statuses.count(NativeGlrtFractionalEpochStatusV1.COMPLETE)
            or self.unbracketed_count
            != statuses.count(NativeGlrtFractionalEpochStatusV1.UNBRACKETED)
            or self.unavailable_count
            != statuses.count(NativeGlrtFractionalEpochStatusV1.UNAVAILABLE)
            or self.refinement_count
            != self.complete_count + self.unbracketed_count + self.unavailable_count
        ):
            raise ValueError("fractional GLRT refinement accounting does not close")
        segments = {item.segment_index: item for item in self.source.continuity_segments}
        for item in self.refinements:
            segment = segments.get(item.continuity_segment_index)
            if segment is None or not (
                segment.device_sample_start
                <= item.integer_global_epoch_device_sample
                < segment.device_sample_stop
            ):
                raise ValueError("fractional GLRT refinement escaped source continuity")
            if item.fractional_global_epoch_device_sample is not None and not (
                segment.device_sample_start
                <= item.fractional_global_epoch_device_sample
                < segment.device_sample_stop
            ):
                raise ValueError("fractional GLRT peak escaped source continuity")
        if not self.limitations:
            raise ValueError("fractional GLRT evidence must disclose limitations")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("fractional GLRT result digest does not match content")
        return self


class NativeStatefulGlrtFractionalEpochRefinementV1(ContractModel):
    """One additive fractional timing result for a retained stateful basin."""

    schema_version: Literal[1] = 1
    opportunity_index: Annotated[int, Field(ge=0)]
    continuity_segment_index: Annotated[int, Field(ge=0)]
    candidate_rank: Annotated[int, Field(ge=0)]
    integer_global_epoch_device_sample: Annotated[int, Field(ge=0)]
    integer_frame_phase_sample: Annotated[int, Field(ge=0)]
    frame_period_samples: Annotated[float, Field(gt=0)]
    acquired_cfo_hz: float
    status: NativeGlrtFractionalEpochStatusV1
    wrapped_epoch_samples: tuple[int, int, int, int, int]
    exact_score_grid: tuple[float, float, float, float, float]
    control_score_grid: tuple[float, float, float, float, float]
    fractional_epoch_offset_samples: Annotated[float | None, Field(ge=-1.5, le=1.5)]
    fractional_frame_phase_sample: Annotated[float | None, Field(ge=0)]
    first_supported_global_epoch_device_sample: Annotated[float | None, Field(ge=0)]
    log_curvature: Annotated[float | None, Field(lt=0)]
    fractional_exact_score: Annotated[float | None, Field(ge=0)]
    fractional_control_score: Annotated[float | None, Field(ge=0)]
    refinement_digest: Sha256Digest

    @field_validator(
        "frame_period_samples",
        "acquired_cfo_hz",
        "fractional_frame_phase_sample",
        "first_supported_global_epoch_device_sample",
        "log_curvature",
        "fractional_exact_score",
        "fractional_control_score",
    )
    @classmethod
    def _number_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("stateful fractional GLRT value must be finite")
        return value

    @field_validator("exact_score_grid", "control_score_grid")
    @classmethod
    def _grid_is_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) or item < 0.0 for item in value):
            raise ValueError("stateful fractional GLRT scores must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def _refinement_is_closed(self) -> Self:
        epoch_count = round(self.frame_period_samples)
        if self.integer_frame_phase_sample >= epoch_count:
            raise ValueError("stateful fractional GLRT anchor escaped the phase ring")
        expected_wrapped = tuple(
            (self.integer_frame_phase_sample + offset) % epoch_count
            for offset in FRACTIONAL_GLRT_EPOCH_OFFSETS_V1
        )
        if self.wrapped_epoch_samples != expected_wrapped:
            raise ValueError("stateful fractional GLRT grid did not wrap the frame seam")
        present = (
            self.fractional_epoch_offset_samples,
            self.fractional_frame_phase_sample,
            self.first_supported_global_epoch_device_sample,
            self.log_curvature,
            self.fractional_exact_score,
            self.fractional_control_score,
        )
        if self.status is NativeGlrtFractionalEpochStatusV1.COMPLETE:
            if any(item is None for item in present):
                raise ValueError("complete stateful fractional GLRT result is partial")
            assert self.fractional_epoch_offset_samples is not None
            assert self.fractional_frame_phase_sample is not None
            expected_phase = (
                self.integer_frame_phase_sample + self.fractional_epoch_offset_samples
            ) % round(self.frame_period_samples)
            if not math.isclose(
                self.fractional_frame_phase_sample,
                expected_phase,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("stateful fractional GLRT frame phase does not close")
        elif self.status is NativeGlrtFractionalEpochStatusV1.UNBRACKETED:
            if any(item is not None for item in present):
                raise ValueError("unbracketed stateful fractional GLRT carries a peak")
        else:
            raise ValueError("stateful fractional GLRT refinement cannot be unavailable")
        if self.refinement_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"refinement_digest"})
        ):
            raise ValueError("stateful fractional GLRT refinement digest does not match")
        return self


class StandardNativeGlrtFractionalEpochV2(ContractModel):
    """Full-capture plus every retained stateful GLRT fractional surface."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-native-glrt-fractional-epoch-v2"] = (
        "standard-native-glrt-fractional-epoch-v2"
    )
    source: StandardNativeSourceV2
    source_full_capture_fractional_product_digest: Sha256Digest
    source_full_capture_fractional_result_digest: Sha256Digest
    source_stateful_path_product_digest: Sha256Digest
    source_stateful_path_digest: Sha256Digest
    configuration_digest: Sha256Digest
    starlink_edge: StarlinkEdge
    score_definition: Literal["conditioned-exact-and-control-glrt64-at-fixed-acquired-cfo"] = (
        "conditioned-exact-and-control-glrt64-at-fixed-acquired-cfo"
    )
    interpolation_method: Literal["circular-five-cell-log-parabola-plus-lanczos16-v1"] = (
        "circular-five-cell-log-parabola-plus-lanczos16-v1"
    )
    selection_policy: Literal["all-retained-stateful-candidates"] = (
        "all-retained-stateful-candidates"
    )
    score_grid_offsets_samples: tuple[int, int, int, int, int]
    opportunity_count: Annotated[int, Field(ge=0)]
    candidate_refinement_count: Annotated[int, Field(ge=0)]
    complete_count: Annotated[int, Field(ge=0)]
    unbracketed_count: Annotated[int, Field(ge=0)]
    refinements: tuple[NativeStatefulGlrtFractionalEpochRefinementV1, ...]
    limitations: tuple[BoundedText, ...]
    result_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        if self.score_grid_offsets_samples != FRACTIONAL_GLRT_EPOCH_OFFSETS_V1:
            raise ValueError("fractional GLRT V2 score offsets differ from the reviewed grid")
        identities = tuple(
            (item.opportunity_index, item.candidate_rank) for item in self.refinements
        )
        if identities != tuple(sorted(set(identities))):
            raise ValueError("stateful fractional GLRT refinements are not canonical")
        statuses = tuple(item.status for item in self.refinements)
        if (
            self.candidate_refinement_count != len(self.refinements)
            or self.complete_count != statuses.count(NativeGlrtFractionalEpochStatusV1.COMPLETE)
            or self.unbracketed_count
            != statuses.count(NativeGlrtFractionalEpochStatusV1.UNBRACKETED)
            or self.candidate_refinement_count != self.complete_count + self.unbracketed_count
            or self.opportunity_count != len({item.opportunity_index for item in self.refinements})
        ):
            raise ValueError("stateful fractional GLRT accounting does not close")
        segments = {item.segment_index: item for item in self.source.continuity_segments}
        for item in self.refinements:
            segment = segments.get(item.continuity_segment_index)
            if segment is None or not (
                segment.device_sample_start
                <= item.integer_global_epoch_device_sample
                < segment.device_sample_stop
            ):
                raise ValueError("stateful fractional GLRT anchor escaped continuity")
            if item.first_supported_global_epoch_device_sample is not None and not (
                segment.device_sample_start
                <= item.first_supported_global_epoch_device_sample
                < segment.device_sample_stop
            ):
                raise ValueError("stateful fractional GLRT peak escaped continuity")
        if not self.limitations:
            raise ValueError("fractional GLRT V2 must disclose limitations")
        if self.result_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("fractional GLRT V2 result digest does not match")
        return self
