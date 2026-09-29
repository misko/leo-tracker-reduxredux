"""Opt-in saved-input ARM GLRT contracts.

These contracts deliberately do not extend scanner or fractional tracking
products.  A strided native search is separate candidate evidence.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest


class ArmGlrtConfigurationV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_id: Literal["wave8-gate314-source-v1"] = "wave8-gate314-source-v1"
    rate_hz: Literal[2_500_000, 5_000_000, 7_500_000, 10_000_000]
    dwell_ms: Literal[120, 240, 360] = 120
    probe_ms: Literal[20] = 20
    probe_stride_ms: Literal[10, 20, 120] = 10

    @property
    def probe_count(self) -> int:
        return (self.dwell_ms - self.probe_ms) // self.probe_stride_ms + 1


class ArmGlrtDwellBindingV1(ContractModel):
    """Source geometry for one contiguous CI16 dwell in the supplied file."""

    dwell_index: Annotated[int, Field(ge=0)]
    source_sample_start: Annotated[int, Field(ge=0)]
    source_device_sample_start: Annotated[int, Field(ge=0)] | None = None
    channel: Annotated[int, Field(ge=1, le=4)]
    edge: Literal["lower", "upper"]
    actual_rf_hz: Annotated[float, Field(gt=0)]
    capture_start_utc_ns: Annotated[int, Field(ge=0)] | None = None
    capture_end_utc_ns: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _time_is_ordered(self) -> Self:
        if not math.isfinite(self.actual_rf_hz):
            raise ValueError("ARM GLRT dwell RF center must be finite")
        if (
            self.capture_start_utc_ns is not None
            and self.capture_end_utc_ns is not None
            and self.capture_end_utc_ns < self.capture_start_utc_ns
        ):
            raise ValueError("ARM GLRT dwell capture interval is reversed")
        return self


class ArmGlrtInputBindingV1(ContractModel):
    """Hash-bound saved CI16 input; paths are intentionally not persisted."""

    input_sha256: Sha256Digest
    ci16_sha256: Sha256Digest
    sample_layout: Literal["sample-receiver-iq-ci16le"] = "sample-receiver-iq-ci16le"
    receiver_ids: Annotated[tuple[int, ...], Field(min_length=1, max_length=8)]
    dwells: Annotated[tuple[ArmGlrtDwellBindingV1, ...], Field(min_length=1, max_length=1)]

    @model_validator(mode="after")
    def _unique_geometry(self) -> Self:
        if self.receiver_ids != (0, 1):
            raise ValueError("ARM GLRT native V1 requires receiver IDs (0, 1)")
        indexes = tuple(item.dwell_index for item in self.dwells)
        if indexes != tuple(range(len(self.dwells))):
            raise ValueError("ARM GLRT dwell indexes must be contiguous and ordered")
        starts = tuple(item.source_sample_start for item in self.dwells)
        if starts != tuple(sorted(starts)) or len(set(starts)) != len(starts):
            raise ValueError("ARM GLRT dwell source starts must be unique and ordered")
        return self


class ArmGlrtCandidateV1(ContractModel):
    candidate_rank: Annotated[int, Field(ge=0)]
    coarse_epoch: Annotated[int, Field(ge=0)]
    coarse_bin: int
    refined_epoch: Annotated[int, Field(ge=0)]
    frame_support: Annotated[int, Field(ge=0)]
    glrt_complete: bool
    refinement_skipped: bool
    conditioned_fallback: bool
    coarse_cfo_hz: float
    fine_cfo_hz: float | None = None
    conditioned_cfo_hz: float | None = None
    epoch: int
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    acquire_score: float | None = None
    verify_score: float | None = None
    verify_control_score: float | None = None
    conditioned_score: float | None = None
    coarse_score: float | None = None

    @model_validator(mode="after")
    def _finite_values(self) -> Self:
        values = (
            self.coarse_cfo_hz, self.fine_cfo_hz, self.conditioned_cfo_hz,
            self.acquired_cfo_hz, self.tracking_cfo_hz,
            self.exact_score, self.control_score, self.margin, self.acquire_score,
            self.verify_score, self.verify_control_score, self.conditioned_score,
            self.coarse_score,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("ARM GLRT candidate values must be finite")
        return self


class ArmGlrtRowV1(ContractModel):
    dwell_index: Annotated[int, Field(ge=0)]
    receiver_id: int
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    proposal_executed: Annotated[int, Field(ge=0)]
    proposal_tracking_fallback: Annotated[int, Field(ge=0)]
    proposal_neighbor_matches: Annotated[int, Field(ge=0)]
    candidate_count: Annotated[int, Field(ge=0)]
    retained_peak_count: Annotated[int, Field(ge=0)]
    coarse_gate_skipped_count: Annotated[int, Field(ge=0)]
    conditioned_fallback_count: Annotated[int, Field(ge=0)]
    actual_executed_glrt_calls: Annotated[int, Field(ge=0)]
    glrt_cache_hits: Annotated[int, Field(ge=0)]
    conditioned_cache_hits: Annotated[int, Field(ge=0)]
    fine_fft_cache_entries: Annotated[int, Field(ge=0)]
    fine_fft_cache_hits: Annotated[int, Field(ge=0)]
    fine_precision_calls: Annotated[int, Field(ge=0)]
    fine_precision_guard_checks: Annotated[int, Field(ge=0)]
    fine_precision_fallbacks: Annotated[int, Field(ge=0)]
    fine_precision_nonfinite_fallbacks: Annotated[int, Field(ge=0)]
    fine_precision_near_tie_fallbacks: Annotated[int, Field(ge=0)]
    fine_precision_interpolation_fallbacks: Annotated[int, Field(ge=0)]
    conditioned_bins_screened: Annotated[int, Field(ge=0)]
    conditioned_bins_rechecked: Annotated[int, Field(ge=0)]
    timings_ms: ArmGlrtRowTimingsV1
    candidates: tuple[ArmGlrtCandidateV1, ...]

    @model_validator(mode="after")
    def _candidate_count_is_exact(self) -> Self:
        if self.candidate_count != len(self.candidates):
            raise ValueError("ARM GLRT row candidate count disagrees")
        return self


class ArmGlrtRowTimingsV1(ContractModel):
    total_cpu: Annotated[float, Field(ge=0)]
    proposal: Annotated[float, Field(ge=0)]
    stage_sum: Annotated[float, Field(ge=0)]
    proposal_fold: Annotated[float, Field(ge=0)]
    proposal_correlation: Annotated[float, Field(ge=0)]
    proposal_ranking: Annotated[float, Field(ge=0)]
    coarse: Annotated[float, Field(ge=0)]
    acquisition: Annotated[float, Field(ge=0)]
    fine_fft: Annotated[float, Field(ge=0)]
    conditioned: Annotated[float, Field(ge=0)]
    verification: Annotated[float, Field(ge=0)]
    glrt: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if any(not math.isfinite(value) for value in self.__dict__.values()):
            raise ValueError("ARM GLRT row timings must be finite")
        return self


class ArmGlrtTimingsV1(ContractModel):
    """CPU milliseconds measured by the native process, never wall time.

    ``detector_cpu`` includes prepared-dwell allocation, proposals and searches;
    it excludes input read, context setup, output serialization and capture.
    ``io`` is CPU spent reading the three input files, not storage wall latency.
    """

    setup: Annotated[float, Field(ge=0)]
    detector_cpu: Annotated[float, Field(ge=0)]
    io: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if any(not math.isfinite(value) for value in self.__dict__.values()):
            raise ValueError("ARM GLRT timings must be finite")
        return self


class ArmGlrtNativeOutputV1(ContractModel):
    """The C executable's JSON document, before Python binds file identities."""

    schema_name: Literal["leo-native-glrt/v1"] = Field(
        default="leo-native-glrt/v1", alias="schema", serialization_alias="schema"
    )
    algorithm_id: Literal["wave8-gate314-source-v1"] = "wave8-gate314-source-v1"
    sample_rate_hz: Literal[2_500_000, 5_000_000, 7_500_000, 10_000_000]
    dwell_ms: Literal[120, 240, 360]
    probe_ms: Literal[20] = 20
    probe_stride_ms: Literal[10, 20, 120]
    receiver_count: Literal[2]
    input_complex_times: Annotated[int, Field(gt=0)]
    template_complex_count: Annotated[int, Field(gt=0)]
    thread_safety: Literal["process-serialized"]
    rows: tuple[ArmGlrtRowV1, ...]
    timings_ms: ArmGlrtTimingsV1

    @model_validator(mode="after")
    def _native_shape_is_exact(self) -> Self:
        expected_templates = (self.sample_rate_hz + 375) // 750
        if self.template_complex_count != expected_templates:
            raise ValueError("native ARM GLRT template length disagrees with sample rate")
        return self


class ArmGlrtResultV1(ContractModel):
    """Validated, provenance-complete ARM output for one saved CI16 input."""

    schema_version: Literal[1] = 1
    kind: Literal["arm_glrt_result"] = "arm_glrt_result"
    configuration: ArmGlrtConfigurationV1
    input_binding: ArmGlrtInputBindingV1
    native_binary_sha256: Sha256Digest
    exact_template_sha256: Sha256Digest
    control_template_sha256: Sha256Digest
    native_output_sha256: Sha256Digest
    rows: tuple[ArmGlrtRowV1, ...]
    timings: ArmGlrtTimingsV1

    @model_validator(mode="after")
    def _inventory_is_complete(self) -> Self:
        expected = [
            (
                dwell.dwell_index,
                receiver_id,
                probe_index,
                probe_index * self.configuration.probe_stride_ms,
            )
            for dwell in self.input_binding.dwells
            for probe_index in range(self.configuration.probe_count)
            for receiver_id in self.input_binding.receiver_ids
        ]
        actual = [
            (row.dwell_index, row.receiver_id, row.probe_index, row.probe_start_ms)
            for row in self.rows
        ]
        if actual != expected:
            raise ValueError("ARM GLRT rows do not cover the declared schedule exactly")
        for row in self.rows:
            ranks = tuple(item.candidate_rank for item in row.candidates)
            if ranks != tuple(range(len(ranks))):
                raise ValueError("ARM GLRT candidate ranks must be contiguous and ordered")
            if len(row.candidates) > 8:
                raise ValueError("ARM GLRT row exceeds the eight-candidate bound")
            period = (self.configuration.rate_hz + 375) // 750
            for candidate in row.candidates:
                if not 0 <= candidate.coarse_epoch < period:
                    raise ValueError("ARM GLRT coarse epoch lies outside one frame period")
                if not 0 <= candidate.refined_epoch < period or not 0 <= candidate.epoch < period:
                    raise ValueError("ARM GLRT candidate epoch lies outside one frame period")
                if not math.isclose(
                    candidate.margin,
                    candidate.exact_score - candidate.control_score,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise ValueError("ARM GLRT candidate margin disagrees with its scores")
        return self
