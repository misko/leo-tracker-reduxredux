"""Immutable automatic T1AT/V16 comparison products; baseline remains separate."""

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[Finite, Field(ge=0)]
SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
Method = Literal["T1AT", "V16"]


class RegionalSearchPointV1(ContractModel):
    east_km: Finite
    north_km: Finite
    spacing_km: Annotated[Finite, Field(gt=0)]
    objective: Finite | None = None
    converged: bool = False
    reason: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.objective is None and (self.converged or not self.reason):
            raise ValueError("unscored point requires a reason and cannot converge")
        return self


class RegionalEstimateV1(ContractModel):
    latitude_deg: Annotated[Finite, Field(ge=-90, le=90)]
    longitude_deg: Annotated[Finite, Field(ge=-180, le=180)]
    east_km: Finite
    north_km: Finite
    objective: Finite
    calibration_penalty: Nonnegative
    selection_score: Finite
    posterior_rms_hz: Nonnegative | None
    signal_windows: Nonnegative
    stationarity: Nonnegative
    converged: bool
    boundary: bool
    coefficient_hz_per_ghz: Finite
    horizontal_error_m: Nonnegative
    satellites: tuple[Annotated[int, Field(gt=0)], ...]
    associated_windows: Annotated[int, Field(ge=0)]
    source_basin: str
    stop_reason: str

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not math.isclose(
            self.selection_score,
            self.objective + self.calibration_penalty,
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise ValueError("selection score omits calibration prior")
        if self.converged != (self.stationarity <= 0.001):
            raise ValueError("convergence must follow checked stationarity")
        if len(self.satellites) < 2 or len(set(self.satellites)) != len(self.satellites):
            raise ValueError("at least two unique satellite candidates required")
        return self


class RegionalRfArmV1(ContractModel):
    name: Literal["fitted-c", "zero-c"]
    selected: RegionalEstimateV1 | None = None
    completed_starts: Annotated[int, Field(ge=0)] = 0
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.selected is None and not self.reasons:
            raise ValueError("missing estimate requires an explicit reason")
        if self.selected is not None and self.completed_starts < 1:
            raise ValueError("estimate requires a completed start")
        if (
            self.name == "zero-c"
            and self.selected is not None
            and self.selected.coefficient_hz_per_ghz != 0
        ):
            raise ValueError("zero-c arm must fix c to zero")
        return self


class RegionalMethodV1(ContractModel):
    name: Method
    state: Literal["diagnostic", "insufficient"]
    points: tuple[RegionalSearchPointV1, ...] = ()
    search_stop_reason: str
    deferred_cells: Annotated[int, Field(ge=0)] = 0
    arms: tuple[RegionalRfArmV1, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if tuple(a.name for a in self.arms) != ("fitted-c", "zero-c"):
            raise ValueError("both matched final RF arms required")
        if (self.state == "diagnostic") != any(a.selected is not None for a in self.arms):
            raise ValueError("method state disagrees with fitted estimates")
        coords = {(p.east_km, p.north_km) for p in self.points}
        if len(coords) != len(self.points):
            raise ValueError("search repeats an evaluated point")
        return self


class RegionalPositionDocumentV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-regional-position-v1"] = "scanner-regional-position-v1"
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
        if tuple(m.name for m in self.methods) != ("T1AT", "V16"):
            raise ValueError("both T1AT and V16 results are required")
        if (self.prior_latitude_deg, self.prior_longitude_deg, self.prior_radius_km) != (
            38.5816,
            -121.4944,
            250.0,
        ):
            raise ValueError("V1 requires the Sacramento 250 km prior")
        if canonical_digest(self.configuration) != self.configuration_sha256:
            raise ValueError("configuration digest differs")
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


class RegionalArtifactV1(ContractModel):
    name: Method
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]


class RegionalPositionManifestV1(ContractModel):
    document: RegionalPositionDocumentV1
    document_sha256: Sha256Digest
    artifacts: tuple[RegionalArtifactV1, ...]

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if tuple(a.name for a in self.artifacts) != ("T1AT", "V16"):
            raise ValueError("a PNG for each positioning method is required")
        if canonical_digest(self.document.model_dump(mode="json")) != self.document_sha256:
            raise ValueError("document digest differs")
        return self


class RegionalPositionStatusV1(ContractModel):
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: RegionalPositionManifestV1 | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("completion requires a sealed manifest")
        if self.manifest and self.manifest.document.session_id != self.session_id:
            raise ValueError("manifest session differs")
        return self


class RegionalPositionReader(Protocol):
    def status(self, session_id: str) -> RegionalPositionStatusV1: ...
    def artifact(self, session_id: str, method: str) -> bytes | None: ...


class RegionalCheckpoints(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...
