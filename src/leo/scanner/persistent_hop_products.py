"""Versioned, bounded products for persistent-hop scanner analysis."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.scanner.models import ScannerModel, ScanTarget

PERSISTENT_HOP_ANALYZER_ID = "persistent-hop-glrt64-cfo-v1"
PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID = "persistent-hop-fractional-glrt64-cfo-v2"


class PersistentHopAnalysisConfigurationV1(ScannerModel):
    """Persisted numerical policy, independent of the capture sample rate."""

    schema_version: Literal[1] = 1
    analyzer_id: Literal["persistent-hop-glrt64-cfo-v1"] = "persistent-hop-glrt64-cfo-v1"
    probe_ms: Literal[20] = 20
    probe_stride_ms: Annotated[int, Field(ge=10, le=120)] = 10
    glrt64_margin_gate: Annotated[float, Field(gt=0)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(ge=1, le=16)] = 8


class PersistentHopBestCandidateV1(ScannerModel):
    """The strongest GLRT64 candidate for one receiver/probe evaluation.

    Integer acquisition is retained as measured. Fractional refinement is an
    additive offset and is never folded back into the integer epoch field.
    """

    schema_version: Literal[1] = 1
    candidate_rank: Annotated[int, Field(ge=0)]
    integer_epoch_sample: Annotated[int, Field(ge=0)]
    fractional_epoch_status: Annotated[str, Field(min_length=1, max_length=64)]
    fractional_epoch_offset_samples: float | None = None
    integer_device_sample_counter: Annotated[int, Field(ge=0)]
    effective_device_sample_counter: Annotated[float, Field(ge=0)]
    integer_session_sample: Annotated[int, Field(ge=0)]
    effective_session_sample: Annotated[float, Field(ge=0)]
    effective_time_s: Annotated[float, Field(ge=0)]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    passed_margin_gate: bool

    @model_validator(mode="after")
    def _coordinates_are_coherent(self) -> Self:
        values = (
            self.effective_device_sample_counter,
            self.effective_session_sample,
            self.effective_time_s,
            self.acquired_cfo_hz,
            self.residual_cfo_hz,
            self.tracking_cfo_hz,
            self.exact_score,
            self.control_score,
            self.margin,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("persistent-hop best candidate values must be finite")
        offset = self.fractional_epoch_offset_samples
        if offset is None:
            if self.effective_device_sample_counter != self.integer_device_sample_counter:
                raise ValueError("integer-only candidate changed its device coordinate")
            if self.effective_session_sample != self.integer_session_sample:
                raise ValueError("integer-only candidate changed its session coordinate")
        else:
            if not math.isfinite(offset) or abs(offset) > 2.0:
                raise ValueError(
                    "persistent-hop fractional epoch offset is outside refinement grid"
                )
            if not math.isclose(
                self.effective_device_sample_counter,
                self.integer_device_sample_counter + offset,
                rel_tol=0.0,
                abs_tol=1e-9,
            ) or not math.isclose(
                self.effective_session_sample,
                self.integer_session_sample + offset,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("persistent-hop fractional and integer coordinates disagree")
        return self


class PersistentHopProbeMetricV1(ScannerModel):
    """One bounded row per receiver/probe; candidate fan-out is summarized."""

    schema_version: Literal[1] = 1
    visit_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0, le=7)]
    target: ScanTarget
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    candidate_count: Annotated[int, Field(ge=0, le=16)]
    best: PersistentHopBestCandidateV1 | None

    @model_validator(mode="after")
    def _best_matches_count(self) -> Self:
        if (self.candidate_count == 0) != (self.best is None):
            raise ValueError("persistent-hop probe candidate count and best candidate disagree")
        return self


class PersistentHopAnalysisChunkV1(ScannerModel):
    """All bounded GLRT rows for one independently restartable IQ sweep."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_persistent_hop_analysis_chunk"] = (
        "starlink_persistent_hop_analysis_chunk"
    )
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    input_manifest_sha256: Sha256Digest
    configuration: PersistentHopAnalysisConfigurationV1
    sweep_index: Annotated[int, Field(ge=0)]
    first_visit_index: Annotated[int, Field(ge=0)]
    visit_count: Annotated[int, Field(ge=1, le=8)]
    scheduled_probe_count_per_receiver_visit: Annotated[int, Field(ge=1)]
    receiver_ids: tuple[int, ...] = (0, 1)
    probes: tuple[PersistentHopProbeMetricV1, ...]

    @model_validator(mode="after")
    def _coverage_is_complete(self) -> Self:
        if self.receiver_ids != (0, 1):
            raise ValueError("persistent-hop analysis receiver geometry is not (0, 1)")
        expected = (
            self.visit_count
            * len(self.receiver_ids)
            * self.scheduled_probe_count_per_receiver_visit
        )
        if len(self.probes) != expected:
            raise ValueError("persistent-hop analysis chunk probe coverage is incomplete")
        visit_indexes = tuple(
            range(self.first_visit_index, self.first_visit_index + self.visit_count)
        )
        expected_keys = {
            (visit_index, receiver_id, probe_index)
            for visit_index in visit_indexes
            for probe_index in range(self.scheduled_probe_count_per_receiver_visit)
            for receiver_id in self.receiver_ids
        }
        actual_keys = {
            (item.visit_index, item.receiver_id, item.probe_index) for item in self.probes
        }
        if len(actual_keys) != len(self.probes) or actual_keys != expected_keys:
            raise ValueError("persistent-hop analysis chunk probe coverage is incomplete")
        if any(
            item.probe_start_ms != item.probe_index * self.configuration.probe_stride_ms
            for item in self.probes
        ):
            raise ValueError("persistent-hop analysis chunk probe timing is incoherent")
        if any(item.sweep_index != self.sweep_index for item in self.probes):
            raise ValueError("persistent-hop analysis chunk crosses a sweep boundary")
        return self


class PersistentHopAnalysisChunkReferenceV1(ScannerModel):
    schema_version: Literal[1] = 1
    chunk_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    first_visit_index: Annotated[int, Field(ge=0)]
    visit_count: Annotated[int, Field(ge=1, le=8)]
    probe_count: Annotated[int, Field(gt=0)]
    passed_best_count: Annotated[int, Field(ge=0)]
    relative_path: Annotated[str, Field(pattern=r"^metrics-sweep-[0-9]{6}\.v1\.json\.zst$")]
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest


class PersistentHopAnalysisArtifactV1(ScannerModel):
    schema_version: Literal[1] = 1
    name: Literal["coverage", "glrt64-response", "cfo-trajectories"]
    relative_path: Annotated[
        str,
        Field(
            pattern=r"^presentation/persistent-hop-(?:coverage|glrt64-response|cfo-trajectories)\.v1\.png$"
        ),
    ]
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class PersistentHopAnalysisManifestV1(ScannerModel):
    """Immutable publication point for a complete long-session analysis."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_persistent_hop_analysis"] = "starlink_persistent_hop_analysis"
    analysis_id: Literal["persistent-hop-glrt64-cfo-v1"] = "persistent-hop-glrt64-cfo-v1"
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    input_uri: Annotated[str, Field(min_length=1)]
    input_manifest_sha256: Sha256Digest
    checkpoint_binding_relative_path: Literal["work-manifest.v1.json"] = "work-manifest.v1.json"
    checkpoint_binding_sha256: Sha256Digest
    created_at: datetime
    completed_at: datetime
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    bandwidth_hz: Literal[2_500_000, 5_000_000]
    configuration: PersistentHopAnalysisConfigurationV1
    visit_count: Annotated[int, Field(ge=0, le=2_500)]
    sweep_count: Annotated[int, Field(ge=0, le=313)]
    probe_count: Annotated[int, Field(ge=0)]
    passed_best_count: Annotated[int, Field(ge=0)]
    chunks: tuple[PersistentHopAnalysisChunkReferenceV1, ...]
    artifacts: Annotated[
        tuple[PersistentHopAnalysisArtifactV1, ...], Field(min_length=3, max_length=3)
    ]

    @model_validator(mode="after")
    def _publication_is_closed(self) -> Self:
        if self.completed_at < self.created_at:
            raise ValueError("persistent-hop analysis completion precedes creation")
        if self.bandwidth_hz != self.sample_rate_hz:
            raise ValueError("persistent-hop analysis bandwidth disagrees with sample rate")
        if len(self.chunks) != self.sweep_count:
            raise ValueError("persistent-hop analysis sweep count disagrees with chunks")
        if sum(item.visit_count for item in self.chunks) != self.visit_count:
            raise ValueError("persistent-hop analysis visit count disagrees with chunks")
        if sum(item.probe_count for item in self.chunks) != self.probe_count:
            raise ValueError("persistent-hop analysis probe count disagrees with chunks")
        if sum(item.passed_best_count for item in self.chunks) != self.passed_best_count:
            raise ValueError("persistent-hop analysis pass count disagrees with chunks")
        if tuple(item.chunk_index for item in self.chunks) != tuple(range(len(self.chunks))):
            raise ValueError("persistent-hop analysis chunks are not ordered")
        next_visit_index = 0
        for chunk_index, chunk in enumerate(self.chunks):
            if chunk.sweep_index != chunk_index or chunk.first_visit_index != next_visit_index:
                raise ValueError("persistent-hop analysis chunk coordinates are not contiguous")
            next_visit_index += chunk.visit_count
        if {item.name for item in self.artifacts} != {
            "coverage",
            "glrt64-response",
            "cfo-trajectories",
        }:
            raise ValueError("persistent-hop analysis artifact inventory is incomplete")
        return self


class PersistentHopAnalysisStatusV1(ScannerModel):
    """Small mutable operational projection; scientific products remain immutable."""

    schema_version: Literal[1] = 1
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    analysis_id: Literal["persistent-hop-glrt64-cfo-v1"] = "persistent-hop-glrt64-cfo-v1"
    state: Literal["pending", "running", "complete", "failed"]
    total_visits: Annotated[int, Field(ge=0, le=2_500)]
    analyzed_visits: Annotated[int, Field(ge=0, le=2_500)]
    updated_at: datetime
    failure_summary: Annotated[str | None, Field(max_length=512)] = None

    @model_validator(mode="after")
    def _progress_is_coherent(self) -> Self:
        if self.analyzed_visits > self.total_visits:
            raise ValueError("persistent-hop analysis progress exceeds total visits")
        if self.state == "complete" and self.analyzed_visits != self.total_visits:
            raise ValueError("complete persistent-hop analysis has incomplete progress")
        if (self.state == "failed") != (self.failure_summary is not None):
            raise ValueError("persistent-hop analysis failure state and summary disagree")
        return self


class PersistentHopAnalysisConfigurationV2(ScannerModel):
    """V2 numerical policy: every decision value is evaluated at fractional time."""

    schema_version: Literal[2] = 2
    analyzer_id: Literal["persistent-hop-fractional-glrt64-cfo-v2"] = (
        "persistent-hop-fractional-glrt64-cfo-v2"
    )
    probe_ms: Literal[20] = 20
    probe_stride_ms: Annotated[int, Field(ge=10, le=120)] = 10
    glrt64_margin_gate: Annotated[float, Field(gt=0)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(ge=1, le=16)] = 8
    timing_refinement: Literal["circular-five-cell-log-parabola-plus-lanczos16-v1"] = (
        "circular-five-cell-log-parabola-plus-lanczos16-v1"
    )
    decision_score: Literal["fractional-epoch-conditioned-glrt64-v1"] = (
        "fractional-epoch-conditioned-glrt64-v1"
    )
    require_fractional_epoch_for_decision: Literal[True] = True


class PersistentHopCandidateV2(ScannerModel):
    """One fractionally scored candidate with its immutable integer anchor."""

    schema_version: Literal[2] = 2
    candidate_rank: Annotated[int, Field(ge=0)]
    integer_epoch_sample: Annotated[int, Field(ge=0)]
    fractional_epoch_status: Literal["complete"] = "complete"
    fractional_epoch_offset_samples: Annotated[float, Field(ge=-2.0, le=2.0)]
    integer_device_sample_counter: Annotated[int, Field(ge=0)]
    fractional_device_sample_counter: Annotated[float, Field(ge=0)]
    integer_session_sample: Annotated[int, Field(ge=0)]
    fractional_session_sample: Annotated[float, Field(ge=0)]
    fractional_time_s: Annotated[float, Field(ge=0)]
    acquired_cfo_hz: float
    integer_residual_cfo_hz: float
    integer_tracking_cfo_hz: float
    integer_exact_score: float
    integer_control_score: float
    integer_margin: float
    passed_integer_margin_gate: bool
    fractional_residual_cfo_hz: float
    fractional_tracking_cfo_hz: float
    fractional_exact_score: float
    fractional_control_score: float
    fractional_margin: float
    passed_fractional_margin_gate: bool

    @model_validator(mode="after")
    def _fractional_evidence_closes(self) -> Self:
        values = (
            self.fractional_epoch_offset_samples,
            self.fractional_device_sample_counter,
            self.fractional_session_sample,
            self.fractional_time_s,
            self.acquired_cfo_hz,
            self.integer_residual_cfo_hz,
            self.integer_tracking_cfo_hz,
            self.integer_exact_score,
            self.integer_control_score,
            self.integer_margin,
            self.fractional_residual_cfo_hz,
            self.fractional_tracking_cfo_hz,
            self.fractional_exact_score,
            self.fractional_control_score,
            self.fractional_margin,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("persistent-hop V2 candidate values must be finite")
        if not math.isclose(
            self.fractional_device_sample_counter,
            self.integer_device_sample_counter + self.fractional_epoch_offset_samples,
            rel_tol=0.0,
            abs_tol=1e-9,
        ) or not math.isclose(
            self.fractional_session_sample,
            self.integer_session_sample + self.fractional_epoch_offset_samples,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("persistent-hop V2 fractional coordinate changed its integer anchor")
        if not math.isclose(
            self.integer_margin,
            self.integer_exact_score - self.integer_control_score,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.fractional_margin,
            self.fractional_exact_score - self.fractional_control_score,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("persistent-hop V2 GLRT margin does not close")
        return self


class PersistentHopProbeMetricV2(ScannerModel):
    """One bounded receiver/probe row retaining every complete fractional basin."""

    schema_version: Literal[2] = 2
    visit_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0, le=7)]
    target: ScanTarget
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    candidate_count: Annotated[int, Field(ge=0, le=16)]
    fractionally_scored_candidate_count: Annotated[int, Field(ge=0, le=16)]
    fractional_candidates: tuple[PersistentHopCandidateV2, ...]
    winning_candidate_rank: Annotated[int, Field(ge=0)] | None

    @property
    def best(self) -> PersistentHopCandidateV2 | None:
        if self.winning_candidate_rank is None:
            return None
        return next(
            item
            for item in self.fractional_candidates
            if item.candidate_rank == self.winning_candidate_rank
        )

    @model_validator(mode="after")
    def _best_matches_fractional_count(self) -> Self:
        if self.fractionally_scored_candidate_count > self.candidate_count:
            raise ValueError("fractional candidate count exceeds acquisition candidates")
        if self.fractionally_scored_candidate_count != len(self.fractional_candidates):
            raise ValueError("fractional candidate inventory does not close")
        ranks = tuple(item.candidate_rank for item in self.fractional_candidates)
        if len(ranks) != len(set(ranks)):
            raise ValueError("fractional candidate ranks are not unique")
        if (self.fractionally_scored_candidate_count == 0) != (self.winning_candidate_rank is None):
            raise ValueError("persistent-hop V2 winner disagrees with fractional coverage")
        if self.winning_candidate_rank is not None:
            if self.winning_candidate_rank not in ranks:
                raise ValueError("persistent-hop V2 winning rank is absent")
            expected = max(
                self.fractional_candidates,
                key=lambda item: (item.fractional_margin, -item.candidate_rank),
            )
            if self.winning_candidate_rank != expected.candidate_rank:
                raise ValueError("persistent-hop V2 winning rank is not strongest")
        return self


class PersistentHopAnalysisChunkV2(ScannerModel):
    schema_version: Literal[2] = 2
    kind: Literal["starlink_persistent_hop_analysis_chunk_v2"] = (
        "starlink_persistent_hop_analysis_chunk_v2"
    )
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    input_manifest_sha256: Sha256Digest
    configuration: PersistentHopAnalysisConfigurationV2
    sweep_index: Annotated[int, Field(ge=0)]
    first_visit_index: Annotated[int, Field(ge=0)]
    visit_count: Annotated[int, Field(ge=1, le=8)]
    scheduled_probe_count_per_receiver_visit: Annotated[int, Field(ge=1)]
    receiver_ids: tuple[int, ...] = (0, 1)
    probes: tuple[PersistentHopProbeMetricV2, ...]

    @model_validator(mode="after")
    def _coverage_is_complete(self) -> Self:
        if self.receiver_ids != (0, 1):
            raise ValueError("persistent-hop V2 receiver geometry is not (0, 1)")
        expected = (
            self.visit_count
            * len(self.receiver_ids)
            * self.scheduled_probe_count_per_receiver_visit
        )
        if len(self.probes) != expected:
            raise ValueError("persistent-hop V2 chunk probe coverage is incomplete")
        visit_indexes = tuple(
            range(self.first_visit_index, self.first_visit_index + self.visit_count)
        )
        expected_keys = {
            (visit_index, receiver_id, probe_index)
            for visit_index in visit_indexes
            for probe_index in range(self.scheduled_probe_count_per_receiver_visit)
            for receiver_id in self.receiver_ids
        }
        actual_keys = {
            (item.visit_index, item.receiver_id, item.probe_index) for item in self.probes
        }
        if len(actual_keys) != len(self.probes) or actual_keys != expected_keys:
            raise ValueError("persistent-hop V2 chunk probe coverage is incomplete")
        if any(
            item.probe_start_ms != item.probe_index * self.configuration.probe_stride_ms
            for item in self.probes
        ) or any(item.sweep_index != self.sweep_index for item in self.probes):
            raise ValueError("persistent-hop V2 chunk coordinates are incoherent")
        for item in self.probes:
            for candidate in item.fractional_candidates:
                if candidate.passed_integer_margin_gate != (
                    candidate.integer_margin >= self.configuration.glrt64_margin_gate
                ) or candidate.passed_fractional_margin_gate != (
                    candidate.fractional_margin >= self.configuration.glrt64_margin_gate
                ):
                    raise ValueError("persistent-hop V2 decision gate disagrees with scores")
        return self


class PersistentHopAnalysisChunkReferenceV2(ScannerModel):
    schema_version: Literal[2] = 2
    chunk_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    first_visit_index: Annotated[int, Field(ge=0)]
    visit_count: Annotated[int, Field(ge=1, le=8)]
    probe_count: Annotated[int, Field(gt=0)]
    fractionally_scored_candidate_count: Annotated[int, Field(ge=0)]
    passed_fractional_candidate_count: Annotated[int, Field(ge=0)]
    fractionally_scored_best_count: Annotated[int, Field(ge=0)]
    passed_fractional_best_count: Annotated[int, Field(ge=0)]
    relative_path: Annotated[str, Field(pattern=r"^metrics-sweep-[0-9]{6}\.v2\.json\.zst$")]
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest


class PersistentHopAnalysisArtifactV2(ScannerModel):
    schema_version: Literal[2] = 2
    name: Literal["coverage", "glrt64-response", "cfo-trajectories"]
    relative_path: Annotated[
        str,
        Field(
            pattern=r"^presentation/persistent-hop-(?:coverage|glrt64-response|cfo-trajectories)\.v2\.png$"
        ),
    ]
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class PersistentHopAnalysisManifestV2(ScannerModel):
    schema_version: Literal[2] = 2
    kind: Literal["starlink_persistent_hop_analysis_v2"] = "starlink_persistent_hop_analysis_v2"
    analysis_id: Literal["persistent-hop-fractional-glrt64-cfo-v2"] = (
        "persistent-hop-fractional-glrt64-cfo-v2"
    )
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    input_uri: Annotated[str, Field(min_length=1)]
    input_manifest_sha256: Sha256Digest
    checkpoint_binding_relative_path: Literal["work-manifest.v2.json"] = "work-manifest.v2.json"
    checkpoint_binding_sha256: Sha256Digest
    created_at: datetime
    completed_at: datetime
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    bandwidth_hz: Literal[2_500_000, 5_000_000]
    configuration: PersistentHopAnalysisConfigurationV2
    visit_count: Annotated[int, Field(ge=0, le=2_500)]
    sweep_count: Annotated[int, Field(ge=0, le=313)]
    probe_count: Annotated[int, Field(ge=0)]
    fractionally_scored_candidate_count: Annotated[int, Field(ge=0)]
    passed_fractional_candidate_count: Annotated[int, Field(ge=0)]
    fractionally_scored_best_count: Annotated[int, Field(ge=0)]
    passed_fractional_best_count: Annotated[int, Field(ge=0)]
    chunks: tuple[PersistentHopAnalysisChunkReferenceV2, ...]
    artifacts: Annotated[
        tuple[PersistentHopAnalysisArtifactV2, ...], Field(min_length=3, max_length=3)
    ]

    @model_validator(mode="after")
    def _publication_is_closed(self) -> Self:
        if self.completed_at < self.created_at:
            raise ValueError("persistent-hop V2 completion precedes creation")
        if self.bandwidth_hz != self.sample_rate_hz:
            raise ValueError("persistent-hop V2 bandwidth disagrees with sample rate")
        if len(self.chunks) != self.sweep_count:
            raise ValueError("persistent-hop V2 sweep count disagrees with chunks")
        if sum(item.visit_count for item in self.chunks) != self.visit_count:
            raise ValueError("persistent-hop V2 visit count disagrees with chunks")
        if sum(item.probe_count for item in self.chunks) != self.probe_count:
            raise ValueError("persistent-hop V2 probe count disagrees with chunks")
        if (
            sum(item.fractionally_scored_candidate_count for item in self.chunks)
            != self.fractionally_scored_candidate_count
        ):
            raise ValueError("persistent-hop V2 candidate coverage disagrees with chunks")
        if (
            sum(item.passed_fractional_candidate_count for item in self.chunks)
            != self.passed_fractional_candidate_count
        ):
            raise ValueError("persistent-hop V2 candidate pass count disagrees with chunks")
        if (
            sum(item.fractionally_scored_best_count for item in self.chunks)
            != self.fractionally_scored_best_count
        ):
            raise ValueError("persistent-hop V2 fractional coverage disagrees with chunks")
        if (
            sum(item.passed_fractional_best_count for item in self.chunks)
            != self.passed_fractional_best_count
        ):
            raise ValueError("persistent-hop V2 pass count disagrees with chunks")
        if tuple(item.chunk_index for item in self.chunks) != tuple(range(len(self.chunks))):
            raise ValueError("persistent-hop V2 chunks are not ordered")
        next_visit_index = 0
        for chunk_index, chunk in enumerate(self.chunks):
            if chunk.sweep_index != chunk_index or chunk.first_visit_index != next_visit_index:
                raise ValueError("persistent-hop V2 chunks are not contiguous")
            next_visit_index += chunk.visit_count
        if {item.name for item in self.artifacts} != {
            "coverage",
            "glrt64-response",
            "cfo-trajectories",
        }:
            raise ValueError("persistent-hop V2 artifact inventory is incomplete")
        return self


class PersistentHopAnalysisStatusV2(ScannerModel):
    schema_version: Literal[2] = 2
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    analysis_id: Literal["persistent-hop-fractional-glrt64-cfo-v2"] = (
        "persistent-hop-fractional-glrt64-cfo-v2"
    )
    state: Literal["pending", "running", "complete", "failed"]
    total_visits: Annotated[int, Field(ge=0, le=2_500)]
    analyzed_visits: Annotated[int, Field(ge=0, le=2_500)]
    updated_at: datetime
    failure_summary: Annotated[str | None, Field(max_length=512)] = None

    @model_validator(mode="after")
    def _progress_is_coherent(self) -> Self:
        if self.analyzed_visits > self.total_visits:
            raise ValueError("persistent-hop V2 progress exceeds total visits")
        if self.state == "complete" and self.analyzed_visits != self.total_visits:
            raise ValueError("complete persistent-hop V2 analysis has incomplete progress")
        if (self.state == "failed") != (self.failure_summary is not None):
            raise ValueError("persistent-hop V2 failure state and summary disagree")
        return self
