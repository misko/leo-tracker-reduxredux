"""B7 joint-model publication; historical contracts remain unchanged."""

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.regional_position_products import (
    Finite,
    RegionalArtifactV1,
    RegionalEstimateV1,
    RegionalMethodV1,
    RegionalRfArmV1,
    SessionId,
)


class JointModelStateV3(ContractModel):
    stage: Literal["B3", "B4", "B4W", "B5", "C6", "B7"]
    vector: tuple[Finite, ...]
    clock_coefficients: tuple[Finite, ...]
    clock_nodes_s: tuple[Finite, ...]
    clock_knots_hz: tuple[tuple[Finite, ...], ...]
    receiver_baseline_hz: tuple[Finite, ...]
    rf_time_coefficients: tuple[Finite, Finite]
    satellite_centers_s: tuple[Finite, ...]
    satellite_offsets_hz: tuple[Finite, ...]
    satellite_slopes_hz_s: tuple[Finite, ...]
    likelihood_nll: Finite
    timing_penalty: Annotated[Finite, Field(ge=0)]
    nuisance_penalty: Annotated[Finite, Field(ge=0)]
    total_objective: Finite

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if not math.isclose(
            self.total_objective,
            self.likelihood_nll + self.timing_penalty + self.nuisance_penalty,
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise ValueError("joint objective components differ")
        if len(self.clock_knots_hz) != 2 or any(
            len(k) != len(self.clock_nodes_s) for k in self.clock_knots_hz
        ):
            raise ValueError("clock knot dimensions differ")
        return self


class RegionalEstimateV3(RegionalEstimateV1):
    # objective includes joint priors. calibration_penalty is external only and zero for joint fits.
    accepted_stage: Literal["B1", "B3", "B4", "B4W", "B5", "C6", "B7"]
    joint_state: JointModelStateV3 | None = None

    @model_validator(mode="after")
    def joint_coherent(self) -> Self:
        if (self.accepted_stage == "B1") != (self.joint_state is None):
            raise ValueError("joint stage requires model state")
        if self.joint_state:
            state = self.joint_state
            if self.calibration_penalty != 0 or not math.isclose(
                self.objective, state.total_objective, abs_tol=1e-8
            ):
                raise ValueError("joint prior must be counted exactly once")
            if state.stage != self.accepted_stage or len(state.vector) != 7 + len(self.satellites):
                raise ValueError("joint state differs from selection")
            if (
                tuple(state.vector[:2]) != (self.east_km, self.north_km)
                or state.vector[6] != self.coefficient_hz_per_ghz
            ):
                raise ValueError("joint vector differs from estimate")
            if state.stage == "B7" and any(
                len(v) != len(self.satellites)
                for v in (
                    state.satellite_centers_s,
                    state.satellite_offsets_hz,
                    state.satellite_slopes_hz_s,
                )
            ):
                raise ValueError("satellite state dimensions differ")
        return self


class RegionalRfArmV3(RegionalRfArmV1):
    selected: RegionalEstimateV3 | None = None

    @model_validator(mode="after")
    def rf_locked(self) -> Self:
        if (
            self.name == "zero-c"
            and self.selected
            and self.selected.joint_state
            and any(self.selected.joint_state.rf_time_coefficients)
        ):
            raise ValueError("zero-c requires locked RF-time coefficients")
        return self


class RegionalMethodV3(RegionalMethodV1):
    arms: tuple[RegionalRfArmV3, ...]


class RegionalPositionDocumentV3(ContractModel):
    schema_version: Literal[3] = 3
    analysis_id: Literal["scanner-regional-position-v3"] = "scanner-regional-position-v3"
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
    methods: tuple[RegionalMethodV3, ...]
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
            raise ValueError("V3 requires the Sacramento 250 km prior")
        if canonical_digest(self.configuration) != self.configuration_sha256:
            raise ValueError("configuration digest differs")
        if self.configuration.get("protocol") != "sacramento-hard60-b7-v1":
            raise ValueError("V3 requires Hard60 provenance")
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


class RegionalPositionManifestV3(ContractModel):
    document: RegionalPositionDocumentV3
    document_sha256: Sha256Digest
    artifacts: tuple[RegionalArtifactV1, ...]

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if tuple(a.name for a in self.artifacts) != ("V16",):
            raise ValueError("a PNG for each positioning method is required")
        if canonical_digest(self.document.model_dump(mode="json")) != self.document_sha256:
            raise ValueError("document digest differs")
        return self


class RegionalPositionStatusV3(ContractModel):
    session_id: SessionId
    state: Literal["pending", "complete"] = "pending"
    manifest: RegionalPositionManifestV3 | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.state == "complete") != (self.manifest is not None):
            raise ValueError("completion requires a sealed manifest")
        if self.manifest and self.manifest.document.session_id != self.session_id:
            raise ValueError("manifest session differs")
        return self


class RegionalPositionReaderV3(Protocol):
    def status(self, session_id: str) -> RegionalPositionStatusV3: ...
    def artifact(self, session_id: str, method: str) -> bytes | None: ...
