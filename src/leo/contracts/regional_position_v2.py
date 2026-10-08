"""Immutable single-method Hard60 publication; V1 historical comparisons stay unchanged."""

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.regional_position_products import (
    Finite,
    RegionalArtifactV1,
    RegionalMethodV1,
    SessionId,
)


class RegionalPositionDocumentV2(ContractModel):
    schema_version: Literal[2] = 2
    analysis_id: Literal["scanner-regional-position-v2"] = "scanner-regional-position-v2"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    configuration_sha256: Sha256Digest
    evidence_sha256: Sha256Digest
    prior_latitude_deg: Finite = 38.5816
    prior_longitude_deg: Finite = -121.4944
    prior_radius_km: Finite = 250.0
    configuration: dict[str, JsonValue]
    windows: Annotated[int, Field(ge=0)]
    methods: tuple[RegionalMethodV1, ...]
    refinement: Literal["off"] = "off"
    known_position_used_for_inference: Literal[False] = False
    position_fix_claimed: Literal[False] = False
    rf_ablation_scope: Literal["final-score-shared-fitted-c-calibration-and-association"] = (
        "final-score-shared-fitted-c-calibration-and-association"
    )
    reference_latitude_deg: Annotated[Finite, Field(ge=-90, le=90)]
    reference_longitude_deg: Annotated[Finite, Field(ge=-180, le=180)]
    reference_evidence: str
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(m.name for m in self.methods) != ("V16",):
            raise ValueError("Hard60 requires a single V16 result")
        if (self.prior_latitude_deg, self.prior_longitude_deg, self.prior_radius_km) != (
            38.5816,
            -121.4944,
            250.0,
        ):
            raise ValueError("V2 requires the Sacramento 250 km prior")
        if canonical_digest(self.configuration) != self.configuration_sha256:
            raise ValueError("configuration digest differs")
        if self.configuration.get("protocol") != "sacramento-hard60-v1":
            raise ValueError("V2 requires Hard60 provenance")
        if any(
            arm.selected is not None and not arm.selected.converged
            for method in self.methods
            for arm in method.arms
        ):
            raise ValueError("Hard60 selects only stationary estimates")
        # Reject non-finite values recursively, including unstructured diagnostics.
        canonical_digest(self.diagnostics)
        for method in self.methods:
            for point in method.points:
                if math.hypot(point.east_km, point.north_km) > self.prior_radius_km + 1e-6:
                    raise ValueError("search point outside prior")
            for arm in method.arms:
                if (
                    arm.selected
                    and math.hypot(arm.selected.east_km, arm.selected.north_km)
                    > self.prior_radius_km + 1e-6
                ):
                    raise ValueError("selected estimate outside prior")
                if arm.selected and (
                    arm.selected.associated_windows > self.windows
                    or arm.selected.signal_windows > self.windows + 1e-6
                ):
                    raise ValueError("support exceeds fixed observation inventory")
        return self


class RegionalPositionManifestV2(ContractModel):
    document: RegionalPositionDocumentV2
    document_sha256: Sha256Digest
    artifacts: tuple[RegionalArtifactV1, ...]

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if tuple(a.name for a in self.artifacts) != ("V16",):
            raise ValueError("a PNG for each positioning method is required")
        if canonical_digest(self.document.model_dump(mode="json")) != self.document_sha256:
            raise ValueError("document digest differs")
        return self


class RegionalPositionStatusV2(ContractModel):
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: RegionalPositionManifestV2 | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("completion requires a sealed manifest")
        if self.manifest and self.manifest.document.session_id != self.session_id:
            raise ValueError("manifest session differs")
        return self


class RegionalPositionReaderV2(Protocol):
    def status(self, session_id: str) -> RegionalPositionStatusV2: ...
    def artifact(self, session_id: str, method: str) -> bytes | None: ...
