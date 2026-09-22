"""V1 immutable relative-phase sidecar; separate from double-difference products."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.scanner.adaptive_hop import AdaptiveModel, SessionId

ANALYSIS_ID = "adaptive-broadband-pilot-relative-phase-v1"
MAXIMUM_VISITS = 64


def relative_phase_binding(input_digest: str, glrt_digest: str) -> str:
    return canonical_digest(
        dict(
            analysis_id=ANALYSIS_ID,
            input_manifest=input_digest,
            glrt_binding=glrt_digest,
            maximum_visits=MAXIMUM_VISITS,
            selection="strongest-phase-blind-paired-margin-v1",
        )
    )


class RelativePhaseVisitV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    binding_sha256: Sha256Digest
    visit_index: Annotated[int, Field(ge=0, lt=2500)]
    state: Literal["supported", "insufficient_signal"]
    reason: str
    evidence: dict[str, JsonValue]


class RelativePhaseArtifactV1(AdaptiveModel):
    name: Literal["relative-phase-overview", "relative-phase-dwells"]
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=8 * 1024 * 1024)]


class RelativePhaseManifestV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["adaptive-broadband-pilot-relative-phase-v1"] = (
        "adaptive-broadband-pilot-relative-phase-v1"
    )
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    glrt_binding_sha256: Sha256Digest
    binding_sha256: Sha256Digest
    state: Literal["ready", "insufficient_signal", "not_applicable"]
    total_visit_count: Annotated[int, Field(ge=0, le=2500)]
    selected_visits: Annotated[tuple[int, ...], Field(max_length=64)]
    supported_visit_count: Annotated[int, Field(ge=0, le=64)]
    pilot_checked_visit_count: Annotated[int, Field(ge=0, le=64)]
    receiver_geometry_digest: Sha256Digest | None
    artifacts: Annotated[tuple[RelativePhaseArtifactV1, ...], Field(min_length=2, max_length=2)]
    receiver_product: Literal["rx1_times_conjugate_rx0"] = "rx1_times_conjugate_rx0"
    phase_continuity_across_retunes: Literal[False] = False
    geometric_phase_claimed: Literal[False] = False

    @model_validator(mode="after")
    def consistent_coverage(self):
        if (
            self.selected_visits != tuple(sorted(set(self.selected_visits)))
            or any(i < 0 or i >= 2500 for i in self.selected_visits)
            or len(self.selected_visits) > self.total_visit_count
            or self.supported_visit_count > len(self.selected_visits)
            or self.pilot_checked_visit_count > len(self.selected_visits)
            or (self.state == "ready") != (self.supported_visit_count > 0)
            or (self.state == "not_applicable" and self.selected_visits)
            or {a.name for a in self.artifacts}
            != {"relative-phase-overview", "relative-phase-dwells"}
        ):
            raise ValueError("Relative phase manifest contradicts its coverage")
        return self


class RelativePhaseStatusV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    binding_sha256: Sha256Digest
    state: Literal["pending", "ready", "insufficient_signal", "not_applicable"]
    manifest: RelativePhaseManifestV1 | None
