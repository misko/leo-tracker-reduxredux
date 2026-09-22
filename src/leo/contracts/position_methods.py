"""Additive, conditional scanner position-method evidence."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest

SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
PositionMethod = Literal["expanded-doppler", "orbit-corrected", "identity-mixture"]
POSITION_METHODS: tuple[PositionMethod, ...] = (
    "expanded-doppler",
    "orbit-corrected",
    "identity-mixture",
)


class PositionMethodSourceV1(ContractModel):
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    analysis_sha256: Sha256Digest
    tracking_product_sha256: Sha256Digest


class ReferencePositionV1(ContractModel):
    source: Literal["user-provided-report-reference"] = "user-provided-report-reference"
    latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    longitude_deg: Annotated[float, Field(ge=-180.0, le=180.0)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if not math.isfinite(self.latitude_deg) or not math.isfinite(self.longitude_deg):
            raise ValueError("reference position must be finite")
        return self


class PositionMethodResultV1(ContractModel):
    method: PositionMethod
    state: Literal["insufficient", "diagnostic", "failed"]
    conditional_on_catalogue_identity: Literal[True] = True
    position_fix_claimed: Literal[False] = False
    latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)] | None = None
    longitude_deg: Annotated[float, Field(ge=-180.0, le=180.0)] | None = None
    horizontal_error_m: Annotated[float, Field(ge=0.0)] | None = None
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        located = self.latitude_deg is not None or self.longitude_deg is not None
        if located != (self.latitude_deg is not None and self.longitude_deg is not None):
            raise ValueError("position latitude and longitude must be published together")
        if (self.state == "diagnostic") != located:
            raise ValueError("only a diagnostic result may publish a position")
        if self.state != "diagnostic" and self.horizontal_error_m is not None:
            raise ValueError("only a diagnostic result may publish reference error")
        if self.state != "diagnostic" and not self.reasons:
            raise ValueError("non-diagnostic position result requires a reason")
        values = (self.latitude_deg, self.longitude_deg, self.horizontal_error_m)
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("position result numbers must be finite")
        if any(not key.strip() for key in self.diagnostics):
            raise ValueError("diagnostic names must be non-empty")

        def require_finite(value: JsonValue) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("diagnostic numbers must be finite")
            if isinstance(value, list):
                for child in value:
                    require_finite(child)
            elif isinstance(value, dict):
                for child in value.values():
                    require_finite(child)

        require_finite(self.diagnostics)
        return self


class PositionMethodsDocumentV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-position-methods-v1"] = "scanner-position-methods-v1"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    configuration_sha256: Sha256Digest
    source_rolling_cohort_sha256: Sha256Digest
    source_rolling_cohort: tuple[PositionMethodSourceV1, ...]
    reference_position: ReferencePositionV1 | None = None
    methods: tuple[PositionMethodResultV1, ...]

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if tuple(item.method for item in self.methods) != POSITION_METHODS:
            raise ValueError("position method inventory or order differs")
        if len({item.session_id for item in self.source_rolling_cohort}) != len(
            self.source_rolling_cohort
        ):
            raise ValueError("position source cohort contains duplicate sessions")
        if (
            canonical_digest([item.model_dump(mode="json") for item in self.source_rolling_cohort])
            != self.source_rolling_cohort_sha256
        ):
            raise ValueError("position source cohort digest differs")
        target = next(
            (item for item in self.source_rolling_cohort if item.session_id == self.session_id),
            None,
        )
        if target is None or target.input_manifest_sha256 != self.input_manifest_sha256:
            raise ValueError("target capture is not bound into the source cohort")
        if self.reference_position is None and any(
            item.horizontal_error_m is not None for item in self.methods
        ):
            raise ValueError("horizontal error requires a user-supplied reference position")
        return self


class PositionMethodArtifactV1(ContractModel):
    method: PositionMethod
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]


class PositionMethodsManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    document: PositionMethodsDocumentV1
    document_sha256: Sha256Digest
    artifacts: tuple[PositionMethodArtifactV1, ...]

    @model_validator(mode="after")
    def _artifact_inventory(self) -> Self:
        if tuple(item.method for item in self.artifacts) != POSITION_METHODS:
            raise ValueError("position artifact inventory or order differs")
        return self


class PositionMethodsStatusV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: PositionMethodsManifestV1 | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("position method status and manifest differ")
        if self.manifest is not None and self.manifest.document.session_id != self.session_id:
            raise ValueError("position method session binding differs")
        return self


class PositionMethodsReader(Protocol):
    def status(self, session_id: str) -> PositionMethodsStatusV1: ...

    def artifact(self, session_id: str, method: PositionMethod) -> bytes | None: ...
