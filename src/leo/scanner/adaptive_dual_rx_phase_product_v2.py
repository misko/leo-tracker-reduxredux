"""Additive measured double-difference phase-versus-time contract."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_dual_rx_phase_product import MAX_ADAPTIVE_PHASE_PNG_BYTES
from leo.scanner.adaptive_hop import AdaptiveModel, Count, SessionId

Finite = Annotated[float, Field(allow_inf_nan=False)]


class AdaptiveDualRxDoubleDifferenceHypothesisV2(AdaptiveModel):
    """One phase-blind two-signal hypothesis; aliases remain alternatives."""

    hypothesis_index: Annotated[int, Field(strict=True, ge=0, lt=64)]
    low_rx0_tracking_cfo_hz: Finite
    high_rx0_tracking_cfo_hz: Finite
    alias_aware_signal_separation_hz: Annotated[float, Field(ge=5_000, allow_inf_nan=False)]
    receiver_offset_hz: Finite
    wrapped_high_minus_low_rad: Annotated[
        float, Field(ge=-math.pi, le=math.pi, allow_inf_nan=False)
    ]
    standard_error_rad: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    common_session_time_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    low_center_session_time_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    high_center_session_time_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    asynchronous_center_separation_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    asynchronous_correction_standard_error_rad: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    asynchronous_common_mode_model: Literal["separate_local_receiver_product_rates"] = (
        "separate_local_receiver_product_rates"
    )
    direct_common_frame_count: Annotated[int, Field(strict=True, ge=0, le=129)]
    phase_resultant_floor: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    exact_to_control_power_ratio_floor: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    association_uses_phase: Literal[False] = False
    alias_resolved: Literal[False] = False

    @model_validator(mode="after")
    def _time_separation_closes(self) -> Self:
        expected = abs(self.high_center_session_time_s - self.low_center_session_time_s)
        if not math.isclose(
            self.asynchronous_center_separation_s, expected, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("double-difference asynchronous time does not close")
        return self


class AdaptiveDualRxPhaseVisitV2(AdaptiveModel):
    schema_version: Literal[2] = 2
    kind: Literal["adaptive_dual_rx_phase_visit"] = "adaptive_dual_rx_phase_visit"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    glrt_binding_sha256: Sha256Digest
    visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    target_index: Annotated[int, Field(strict=True, ge=0, le=7)]
    edge: Literal["lower", "upper"]
    state: Literal["qualified", "insufficient_signal"]
    reason: Literal[
        "phase_blind_two_signal_hypotheses",
        "fewer_than_two_phase_blind_receiver_pairs",
        "fewer_than_two_phase_quality_pairs",
        "no_alias_distinct_two_signal_hypothesis",
    ]
    consistent_receiver_pair_count: Annotated[int, Field(strict=True, ge=0, le=8)]
    phase_quality_pair_count: Annotated[int, Field(strict=True, ge=0, le=8)]
    hypotheses: Annotated[
        tuple[AdaptiveDualRxDoubleDifferenceHypothesisV2, ...], Field(max_length=28)
    ]

    @model_validator(mode="after")
    def _evidence_matches_state(self) -> Self:
        qualified = self.state == "qualified"
        indexes = tuple(item.hypothesis_index for item in self.hypotheses)
        expected_target = self.target_index % 4 + (0 if self.edge == "lower" else 4)
        if (
            qualified != bool(self.hypotheses)
            or qualified != (self.reason == "phase_blind_two_signal_hypotheses")
            or self.phase_quality_pair_count > self.consistent_receiver_pair_count
            or (qualified and self.phase_quality_pair_count < 2)
            or indexes != tuple(range(len(indexes)))
            or self.target_index != expected_target
        ):
            raise ValueError("adaptive phase visit contradicts its evidence")
        return self


class AdaptiveDualRxPhaseTimeFigureV2(AdaptiveModel):
    name: Literal["dual-rx-double-difference-time"] = "dual-rx-double-difference-time"
    content_type: Literal["image/png"] = "image/png"
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(strict=True, gt=0, le=MAX_ADAPTIVE_PHASE_PNG_BYTES)]


class AdaptiveDualRxGeometrySummaryV2(AdaptiveModel):
    input_digest: Sha256Digest
    receiver_geometry_binding_digest: Sha256Digest
    geometry_digest: Sha256Digest
    calibration_digest: Sha256Digest
    direction_evidence_sha256: Sha256Digest
    state: Literal["unavailable", "ambiguous", "conditionally_unique"]
    reasons: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]
    point_count: Count
    ambiguity_candidate_count: Annotated[int, Field(strict=True, ge=0, le=1_190_000)]
    residual_rms_rad: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def _evidence_matches_state(self) -> Self:
        available = self.state != "unavailable"
        if available != (self.point_count > 0 and self.residual_rms_rad is not None):
            raise ValueError("geometry summary state contradicts its points")
        return self


class AdaptiveDualRxPhaseManifestV2(AdaptiveModel):
    schema_version: Literal[2] = 2
    kind: Literal["adaptive_dual_rx_phase_manifest"] = "adaptive_dual_rx_phase_manifest"
    analysis_id: Literal["adaptive-qin-pilot-double-difference-v2"] = (
        "adaptive-qin-pilot-double-difference-v2"
    )
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    glrt_binding_sha256: Sha256Digest
    glrt_metrics_manifest_sha256: Sha256Digest
    state: Literal["ready", "insufficient_signal"]
    reason: Literal["published_phase_time_hypotheses", "no_qualified_double_difference"]
    total_visit_count: Count
    checkpoint_visit_count: Count
    qualified_visit_count: Count
    hypothesis_count: Annotated[int, Field(strict=True, ge=0, le=70_000)]
    geometry_phase_state: Literal["unavailable", "ambiguous", "conditionally_unique"]
    geometry_phase_reason: str
    geometry: AdaptiveDualRxGeometrySummaryV2 | None = None
    receiver_product: Literal["rx1_times_conjugate_rx0"] = "rx1_times_conjugate_rx0"
    phase_continuity_across_retunes: Literal[False] = False
    association_uses_phase: Literal[False] = False
    aliases_resolved: Literal[False] = False
    artifact: AdaptiveDualRxPhaseTimeFigureV2 | None
    finalized_utc_ns: U64

    @model_validator(mode="after")
    def _honest_result(self) -> Self:
        ready = self.state == "ready"
        if (
            self.checkpoint_visit_count != self.total_visit_count
            or ready != (self.artifact is not None)
            or ready != (self.reason == "published_phase_time_hypotheses")
            or ready != (self.qualified_visit_count > 0 and self.hypothesis_count > 0)
            or self.qualified_visit_count > self.checkpoint_visit_count
            or not self.geometry_phase_reason
            or (self.geometry_phase_state != "unavailable" and self.geometry is None)
            or (self.geometry is not None and self.geometry.state != self.geometry_phase_state)
        ):
            raise ValueError("adaptive phase V2 state contradicts its evidence")
        return self


class AdaptiveDualRxPhaseStatusV2(AdaptiveModel):
    schema_version: Literal[2] = 2
    kind: Literal["adaptive_dual_rx_phase_status"] = "adaptive_dual_rx_phase_status"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    receiver_ids: tuple[Literal[0, 1], ...]
    state: Literal["pending", "ready", "insufficient_signal", "not_applicable"]
    reason: Literal[
        "awaiting_phase_analysis",
        "published_phase_time_hypotheses",
        "no_qualified_double_difference",
        "requires_simultaneous_rx0_rx1",
    ]
    checkpoint_visit_count: Count
    total_visit_count: Count
    worker_activity: Literal["not_observed"] = "not_observed"
    manifest: AdaptiveDualRxPhaseManifestV2 | None

    @model_validator(mode="after")
    def _honest_status(self) -> Self:
        dual = self.receiver_ids == (0, 1)
        published = self.state in ("ready", "insufficient_signal")
        expected = {
            "pending": "awaiting_phase_analysis",
            "ready": "published_phase_time_hypotheses",
            "insufficient_signal": "no_qualified_double_difference",
            "not_applicable": "requires_simultaneous_rx0_rx1",
        }[self.state]
        if (
            (self.state == "not_applicable") != (not dual)
            or published != (self.manifest is not None)
            or self.reason != expected
            or self.checkpoint_visit_count > self.total_visit_count
        ):
            raise ValueError("adaptive phase V2 status contradicts source eligibility")
        if self.manifest is not None and (
            self.manifest.session_id != self.session_id
            or self.manifest.input_manifest_sha256 != self.input_manifest_sha256
            or self.manifest.state != self.state
        ):
            raise ValueError("adaptive phase V2 manifest is bound to another source")
        return self
