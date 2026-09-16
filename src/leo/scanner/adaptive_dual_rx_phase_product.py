"""Additive publication contract for adaptive dual-receiver phase evidence."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import AdaptiveModel, Count, SessionId

MAX_ADAPTIVE_PHASE_PNG_BYTES = 16 * 1024 * 1024


class AdaptiveDualRxPhaseFigureV1(AdaptiveModel):
    name: Literal["dual-rx-phase-progression"] = "dual-rx-phase-progression"
    content_type: Literal["image/png"] = "image/png"
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(strict=True, gt=0, le=MAX_ADAPTIVE_PHASE_PNG_BYTES)]


class AdaptiveDualRxPhaseManifestV1(AdaptiveModel):
    """Sealed phase result. Existing adaptive contracts remain unchanged."""

    schema_version: Literal[1] = 1
    kind: Literal["adaptive_dual_rx_phase_manifest"] = "adaptive_dual_rx_phase_manifest"
    analysis_id: Literal["adaptive-qin-pilot-double-difference-v1"] = (
        "adaptive-qin-pilot-double-difference-v1"
    )
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    glrt_binding_sha256: Sha256Digest
    glrt_metrics_manifest_sha256: Sha256Digest
    state: Literal["ready", "insufficient_signal"]
    reason: Literal["published_phase_evidence", "no_qualified_double_difference"]
    qualified_phase_count: Count
    association_count: Annotated[int, Field(strict=True, ge=0, le=1024)]
    artifact: AdaptiveDualRxPhaseFigureV1 | None
    finalized_utc_ns: U64

    @model_validator(mode="after")
    def _honest_result(self) -> Self:
        ready = self.state == "ready"
        if (
            ready != (self.artifact is not None)
            or ready != (self.reason == "published_phase_evidence")
            or (ready and self.qualified_phase_count == 0)
            or (not ready and (self.qualified_phase_count != 0 or self.association_count != 0))
        ):
            raise ValueError("adaptive phase state contradicts its evidence")
        return self


class AdaptiveDualRxPhaseStatusV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_dual_rx_phase_status"] = "adaptive_dual_rx_phase_status"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    receiver_ids: tuple[Literal[0, 1], ...]
    state: Literal["pending", "ready", "insufficient_signal", "not_applicable"]
    reason: Literal[
        "awaiting_phase_analysis",
        "published_phase_evidence",
        "no_qualified_double_difference",
        "requires_simultaneous_rx0_rx1",
    ]
    worker_activity: Literal["not_observed"] = "not_observed"
    manifest: AdaptiveDualRxPhaseManifestV1 | None

    @model_validator(mode="after")
    def _honest_status(self) -> Self:
        dual = self.receiver_ids == (0, 1)
        published = self.state in ("ready", "insufficient_signal")
        if (
            (self.state == "not_applicable") != (not dual)
            or published != (self.manifest is not None)
            or (self.state == "pending" and not dual)
            or self.reason
            != {
                "pending": "awaiting_phase_analysis",
                "ready": "published_phase_evidence",
                "insufficient_signal": "no_qualified_double_difference",
                "not_applicable": "requires_simultaneous_rx0_rx1",
            }[self.state]
        ):
            raise ValueError("adaptive phase status contradicts source eligibility")
        if self.manifest is not None and (
            self.manifest.session_id != self.session_id
            or self.manifest.input_manifest_sha256 != self.input_manifest_sha256
            or self.manifest.state != self.state
        ):
            raise ValueError("adaptive phase manifest is bound to another source")
        return self


class AdaptiveDualRxPhasePresentationReader(Protocol):
    def phase_status(
        self, session_id: str, *, probe_stride_ms: int = 120
    ) -> AdaptiveDualRxPhaseStatusV1 | None: ...

    def phase_artifact(
        self,
        session_id: str,
        *,
        glrt_binding_sha256: str,
        artifact_sha256: str,
        probe_stride_ms: int = 120,
    ) -> bytes | None: ...
