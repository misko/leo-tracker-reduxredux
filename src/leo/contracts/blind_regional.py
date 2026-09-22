"""Additive blind broad-region association and position evidence."""

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
ArtifactName = Literal["blind-association", "blind-position", "blind-position-modes"]


class BlindRegionV1(ContractModel):
    center_latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    center_longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    width_km: Annotated[float, Field(gt=0, le=20_000)]
    height_km: Annotated[float, Field(gt=0, le=20_000)]
    altitude_m: Annotated[float, Field(ge=-1000, le=20_000)] = 0
    grid_policy: Annotated[str, Field(min_length=1, max_length=256)]
    refinement_policy: Annotated[str, Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if not all(
            math.isfinite(x)
            for x in (
                self.center_latitude_deg,
                self.center_longitude_deg,
                self.width_km,
                self.height_km,
                self.altitude_m,
            )
        ):
            raise ValueError("blind region values must be finite")
        return self


class BlindSnapshotRefV1(ContractModel):
    digest: Sha256Digest
    collected_utc_ns: Annotated[int, Field(ge=0)]
    provider: Annotated[str, Field(min_length=1, max_length=128)]
    object_count: Annotated[
        int,
        Field(ge=0, description="Eligible propagated objects; digest identifies the raw snapshot"),
    ]


class BlindExclusionV1(ContractModel):
    scope_id: Annotated[str, Field(min_length=1, max_length=256)]
    reason: Annotated[str, Field(min_length=1, max_length=256)]
    detail: Annotated[str, Field(max_length=1024)] = ""


class BlindCandidateV1(ContractModel):
    catalog_number: Annotated[int, Field(gt=0)]
    training_score: float
    heldout_score: float
    soft_weight: Annotated[float, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if not all(
            math.isfinite(x) for x in (self.training_score, self.heldout_score, self.soft_weight)
        ):
            raise ValueError("blind candidate values must be finite")
        return self


class BlindTrackAssociationV1(ContractModel):
    track_id: Annotated[str, Field(min_length=1, max_length=256)]
    state: Literal["associated", "unresolved", "unassigned", "insufficient", "failed"]
    catalogue_size: Annotated[int, Field(ge=0)]
    candidates: Annotated[tuple[BlindCandidateV1, ...], Field(max_length=64)] = ()
    unassigned_weight: Annotated[float, Field(ge=0, le=1)]
    reasons: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    observation_utc_ns: tuple[int, ...] = ()
    observed_hz: tuple[float, ...] = ()
    predicted_hz: tuple[float, ...] = ()
    residual_hz: tuple[float, ...] = ()
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _mass(self) -> Self:
        if len({x.catalog_number for x in self.candidates}) != len(self.candidates):
            raise ValueError("blind track repeats a candidate")
        if sum(x.soft_weight for x in self.candidates) + self.unassigned_weight > 1.000001:
            raise ValueError("blind association mass exceeds one")
        sizes = (
            len(self.observation_utc_ns),
            len(self.observed_hz),
            len(self.predicted_hz),
            len(self.residual_hz),
        )
        if len(set(sizes)) != 1:
            raise ValueError("blind track diagnostic arrays differ")
        if not all(
            math.isfinite(x)
            for values in (self.observed_hz, self.predicted_hz, self.residual_hz)
            for x in values
        ):
            raise ValueError("blind track diagnostic arrays must be finite")
        return self


class BlindPositionModeV1(ContractModel):
    rank: Annotated[int, Field(ge=1, le=32)]
    state: Literal["diagnostic", "insufficient", "failed"]
    latitude_deg: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude_deg: Annotated[float, Field(ge=-180, le=180)] | None = None
    training_score: float | None = None
    heldout_score: float | None = None
    soft_weight: Annotated[float, Field(ge=0, le=1)] | None = None
    major_95_m: Annotated[float, Field(ge=0)] | None = None
    reasons: Annotated[tuple[str, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def _position(self) -> Self:
        located = self.latitude_deg is not None or self.longitude_deg is not None
        if located != (self.latitude_deg is not None and self.longitude_deg is not None):
            raise ValueError("blind position coordinates must be paired")
        if (self.state == "diagnostic") != located:
            raise ValueError("only diagnostic blind mode may publish coordinates")
        if any(
            x is not None and not math.isfinite(x)
            for x in (
                self.latitude_deg,
                self.longitude_deg,
                self.training_score,
                self.heldout_score,
                self.soft_weight,
                self.major_95_m,
            )
        ):
            raise ValueError("blind position values must be finite")
        return self


class BlindReferenceV1(ContractModel):
    source: Literal["user-provided-report-reference"] = "user-provided-report-reference"
    latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]


class BlindModeEvaluationV1(ContractModel):
    rank: Annotated[int, Field(ge=1, le=32)]
    horizontal_error_m: Annotated[float, Field(ge=0)]


class BlindEvaluationV1(ContractModel):
    reference: BlindReferenceV1
    modes: Annotated[tuple[BlindModeEvaluationV1, ...], Field(max_length=32)]


class BlindAccountingV1(ContractModel):
    session_count: Annotated[int, Field(ge=1)] = 1
    saved_observation_count: Annotated[int, Field(ge=0)]
    eligible_observation_count: Annotated[int, Field(ge=0)]
    track_count: Annotated[int, Field(ge=0)]
    associated_track_count: Annotated[int, Field(ge=0)]
    excluded_count: Annotated[int, Field(ge=0)]
    recorded_exclusion_count: Annotated[int, Field(ge=0)]
    propagation_evaluation_count: Annotated[int, Field(ge=0)] = 0
    objective_evaluation_count: Annotated[int, Field(ge=0)] = 0
    runtime_ms: Annotated[int, Field(ge=0)] = 0


class BlindRegionalDocumentV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-blind-regional-v1"] = "scanner-blind-regional-v1"
    mode: Literal["blind-denver-broad-v1"] = "blind-denver-broad-v1"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    configuration_sha256: Sha256Digest
    region: BlindRegionV1
    known_position_used_for_association: Literal[False] = False
    known_position_used_for_inference: Literal[False] = False
    site_conditioned_candidates: Literal[False] = False
    weights_are_calibrated_probabilities: Literal[False] = False
    causal_snapshots: Annotated[tuple[BlindSnapshotRefV1, ...], Field(max_length=64)]
    accounting: BlindAccountingV1
    exclusions: Annotated[tuple[BlindExclusionV1, ...], Field(max_length=8192)] = ()
    tracks: Annotated[tuple[BlindTrackAssociationV1, ...], Field(max_length=4096)] = ()
    position_modes: Annotated[tuple[BlindPositionModeV1, ...], Field(max_length=32)] = ()
    evaluation: BlindEvaluationV1 | None = None
    state: Literal["diagnostic", "insufficient", "failed"]
    reasons: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        def finite(value: JsonValue) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("blind diagnostics must be finite")
            if isinstance(value, list):
                for child in value:
                    finite(child)
            elif isinstance(value, dict):
                for child in value.values():
                    finite(child)

        finite(self.diagnostics)
        for track in self.tracks:
            finite(track.diagnostics)
        if tuple(x.rank for x in self.position_modes) != tuple(
            range(1, len(self.position_modes) + 1)
        ):
            raise ValueError("blind position ranks are not canonical")
        if self.evaluation is not None and tuple(x.rank for x in self.evaluation.modes) != tuple(
            x.rank for x in self.position_modes if x.state == "diagnostic"
        ):
            raise ValueError("blind evaluation does not match diagnostic modes")
        if self.accounting.track_count != len(self.tracks):
            raise ValueError("blind track accounting differs")
        if len({x.track_id for x in self.tracks}) != len(self.tracks):
            raise ValueError("blind track IDs repeat")
        if self.accounting.associated_track_count != sum(
            x.state == "associated" for x in self.tracks
        ):
            raise ValueError("blind associated-track accounting differs")
        if self.accounting.recorded_exclusion_count != len(
            self.exclusions
        ) or self.accounting.excluded_count < len(self.exclusions):
            raise ValueError("blind exclusion accounting differs")
        return self


class BlindArtifactV1(ContractModel):
    name: ArtifactName
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]


class BlindRegionalManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    document: BlindRegionalDocumentV1
    document_sha256: Sha256Digest
    artifacts: tuple[BlindArtifactV1, ...]

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if tuple(x.name for x in self.artifacts) != (
            "blind-association",
            "blind-position",
            "blind-position-modes",
        ):
            raise ValueError("blind artifact inventory differs")
        return self


class BlindRegionalStatusV1(ContractModel):
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: BlindRegionalManifestV1 | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("blind status and manifest differ")
        if self.manifest is not None and self.manifest.document.session_id != self.session_id:
            raise ValueError("blind status session differs")
        return self


class BlindRegionalReader(Protocol):
    def status(self, session_id: str) -> BlindRegionalStatusV1: ...
    def artifact(self, session_id: str, name: ArtifactName) -> bytes | None: ...
