"""Blind bounded best-first TLE position-selection evidence."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


class AdaptiveTleRegionV1(ContractModel):
    center_latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    center_longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    radius_km: Literal[500.0] = 500.0
    altitude_m: Literal[0.0] = 0.0


class AdaptiveTleCandidateV1(ContractModel):
    latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    east_km: float
    north_km: float
    spacing_km: Annotated[float, Field(gt=0, le=100)]
    capped_weighted_rmse_hz: Annotated[float, Field(ge=0, le=800)]
    uncapped_weighted_rmse_hz: Annotated[float, Field(ge=0)] | None = None
    matched_track_count: Annotated[int, Field(ge=0)]
    unmatched_track_count: Annotated[int, Field(ge=0)]
    qualifying_observation_count: Annotated[int, Field(ge=0)]
    horizontal_error_m: Annotated[float, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _finite(self) -> Self:
        values = (
            self.latitude_deg,
            self.longitude_deg,
            self.east_km,
            self.north_km,
            self.spacing_km,
            self.capped_weighted_rmse_hz,
            self.uncapped_weighted_rmse_hz,
            self.horizontal_error_m,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("adaptive TLE candidate values must be finite")
        return self


class AdaptiveTleAccountingV1(ContractModel):
    reconstructed_track_count: Annotated[int, Field(ge=0)]
    eligible_track_count: Annotated[int, Field(ge=0)]
    eligible_observation_count: Annotated[int, Field(ge=0)]
    evaluated_point_count: Annotated[int, Field(ge=0)]
    finest_evaluated_point_count: Annotated[int, Field(ge=0)]
    deferred_cell_count: Annotated[int, Field(ge=0)]
    runtime_ms: Annotated[int, Field(ge=0)]


class AdaptiveTlePriorResultV1(ContractModel):
    name: Literal["sacramento", "reno"]
    region: AdaptiveTleRegionV1
    search_complete: bool
    stop_reason: Annotated[str, Field(min_length=1, max_length=128)]
    accounting: AdaptiveTleAccountingV1
    selected: AdaptiveTleCandidateV1 | None = None
    finest: AdaptiveTleCandidateV1 | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.finest is not None and self.selected is None:
            raise ValueError("finest candidate requires a selected candidate")
        return self


class AdaptiveTlePositionDocumentV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-adaptive-tle-position-v1"] = (
        "scanner-adaptive-tle-position-v1"
    )
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    configuration_sha256: Sha256Digest
    evidence_sha256: Sha256Digest
    known_position_used_for_inference: Literal[False] = False
    position_fix_claimed: Literal[False] = False
    identity_selection: Literal["randomized-evaluation-rms-v1"] = (
        "randomized-evaluation-rms-v1"
    )
    objective: Literal["duration-weighted-capped-rmse-800hz-v1"] = (
        "duration-weighted-capped-rmse-800hz-v1"
    )
    state: Literal["diagnostic", "insufficient", "failed"]
    priors: Annotated[tuple[AdaptiveTlePriorResultV1, ...], Field(max_length=2)]
    reasons: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        def finite(value: JsonValue) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("adaptive TLE diagnostics must be finite")
            if isinstance(value, list):
                for child in value:
                    finite(child)
            elif isinstance(value, dict):
                for child in value.values():
                    finite(child)

        finite(self.diagnostics)
        if tuple(prior.name for prior in self.priors) not in ((), ("sacramento", "reno")):
            raise ValueError("adaptive TLE prior inventory differs")
        if (self.state == "diagnostic") != bool(self.priors):
            raise ValueError("diagnostic state and prior results differ")
        if self.state != "diagnostic" and not self.reasons:
            raise ValueError("non-diagnostic adaptive TLE evidence requires a reason")
        for prior in self.priors:
            if prior.selected is None or prior.finest is None:
                raise ValueError("diagnostic prior requires selected and finest candidates")
            if prior.accounting.eligible_track_count > prior.accounting.reconstructed_track_count:
                raise ValueError("eligible track accounting exceeds reconstructed tracks")
        return self


class AdaptiveTleArtifactV1(ContractModel):
    name: Literal["map"] = "map"
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]


class AdaptiveTlePositionManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    document: AdaptiveTlePositionDocumentV1
    document_sha256: Sha256Digest
    artifacts: tuple[AdaptiveTleArtifactV1, ...]

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if tuple(item.name for item in self.artifacts) != ("map",):
            raise ValueError("adaptive TLE position artifact inventory differs")
        return self


class AdaptiveTlePositionStatusV1(ContractModel):
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: AdaptiveTlePositionManifestV1 | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("adaptive TLE position status and manifest differ")
        if self.manifest is not None and self.manifest.document.session_id != self.session_id:
            raise ValueError("adaptive TLE position session binding differs")
        return self


class AdaptiveTlePositionReader(Protocol):
    def status(self, session_id: str) -> AdaptiveTlePositionStatusV1: ...

    def artifact(self, session_id: str) -> bytes | None: ...
