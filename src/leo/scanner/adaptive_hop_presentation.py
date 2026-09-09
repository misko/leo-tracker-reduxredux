"""Additive overview artifacts and read models, separate from immutable history V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import AdaptiveModel, Count, SessionId
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1

AdaptiveOverviewArtifact = Literal["coverage", "glrt64-response", "cfo-trajectories"]
OVERVIEW_ARTIFACTS: tuple[AdaptiveOverviewArtifact, ...] = (
    "coverage",
    "glrt64-response",
    "cfo-trajectories",
)
MAX_OVERVIEW_PNG_BYTES = 16 * 1024 * 1024


class AdaptiveHopFigureV1(AdaptiveModel):
    name: AdaptiveOverviewArtifact
    content_type: Literal["image/png"] = "image/png"
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(strict=True, gt=0, le=MAX_OVERVIEW_PNG_BYTES)]


class AdaptiveHopOverviewManifestV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_fractional_overview"] = "adaptive_hop_fractional_overview"
    presentation_id: Literal["adaptive-actual-visit-glrt64-overview-v1"] = (
        "adaptive-actual-visit-glrt64-overview-v1"
    )
    session_id: SessionId
    binding_sha256: Sha256Digest
    metrics_manifest_sha256: Sha256Digest
    finalized_utc_ns: U64
    artifacts: Annotated[tuple[AdaptiveHopFigureV1, ...], Field(min_length=3, max_length=3)]
    trajectory_configuration_sha256: Sha256Digest
    trajectory_input_policy: Literal["strongest-passed-fractional-candidate-per-visit-rx"] = (
        "strongest-passed-fractional-candidate-per-visit-rx"
    )
    trajectory_scope: Literal["separate-target-and-receiver-candidate-associations"] = (
        "separate-target-and-receiver-candidate-associations"
    )
    selected_observation_count: Annotated[int, Field(strict=True, ge=0, le=5000)]
    association_count: Annotated[int, Field(strict=True, ge=0, le=1024)]
    truncated_association_count: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def _figures(self) -> Self:
        if tuple(a.name for a in self.artifacts) != OVERVIEW_ARTIFACTS:
            raise ValueError("adaptive overview must contain all three ordered figures")
        return self


class AdaptiveHopAnalysisStatusV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_analysis_status"] = "adaptive_hop_analysis_status"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    binding_sha256: Sha256Digest
    configuration: AdaptiveHopAnalysisConfigurationV1
    total_visits: Count
    checkpoint_visits: Count
    state: Literal["not_started", "partial", "metrics_complete", "figures_ready"]
    progress_basis: Literal["no_checkpoints", "file_inventory", "sealed_metrics_manifest"]
    # Read endpoints do not infer a running job from stale files or start one.
    worker_activity: Literal["not_observed"] = "not_observed"
    metrics_manifest_sha256: Sha256Digest | None
    overview: AdaptiveHopOverviewManifestV1 | None

    @model_validator(mode="after")
    def _status_is_honest(self) -> Self:
        complete = self.state in ("metrics_complete", "figures_ready")
        if (
            self.checkpoint_visits > self.total_visits
            or complete != (self.metrics_manifest_sha256 is not None)
            or (complete and self.checkpoint_visits != self.total_visits)
            or (self.state == "not_started" and self.checkpoint_visits != 0)
            or (self.state == "figures_ready") != (self.overview is not None)
            or self.progress_basis
            != (
                "sealed_metrics_manifest"
                if complete
                else "no_checkpoints"
                if self.state == "not_started"
                else "file_inventory"
            )
        ):
            raise ValueError("adaptive analysis progress contradicts published evidence")
        if self.overview is not None and (
            self.overview.session_id != self.session_id
            or self.overview.binding_sha256 != self.binding_sha256
            or self.overview.metrics_manifest_sha256 != self.metrics_manifest_sha256
        ):
            raise ValueError("adaptive overview is bound to different metrics")
        return self


@dataclass(frozen=True, slots=True)
class RenderedAdaptiveOverview:
    artifacts: dict[str, bytes]
    trajectory_configuration_sha256: str
    selected_observation_count: int
    association_count: int
    truncated_association_count: int


class AdaptiveHopAnalysisPresentationReader(Protocol):
    def status(
        self, session_id: str, *, probe_stride_ms: int = 10
    ) -> AdaptiveHopAnalysisStatusV1 | None: ...

    def artifact(
        self,
        session_id: str,
        artifact: AdaptiveOverviewArtifact,
        *,
        binding_sha256: str,
        artifact_sha256: str,
        probe_stride_ms: int = 10,
    ) -> bytes | None: ...
