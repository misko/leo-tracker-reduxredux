"""Versioned external authority for calibrated adaptive dual-RX geometry phase."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.scanner.adaptive_hop import AdaptiveModel, SessionId
from leo.station.authority import UtcNs
from leo.station.geometry import CartesianVectorMetersV1, UnitVectorV1

EvidenceUri = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
PositiveFinite = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonnegativeFinite = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class AdaptiveDualRxFixturePoseV1(AdaptiveModel):
    """Surveyed orthonormal fixture axes expressed in local ENU."""

    schema_version: Literal[1] = 1
    fixture_x_axis_enu: UnitVectorV1
    fixture_y_axis_enu: UnitVectorV1
    fixture_z_axis_enu: UnitVectorV1
    baseline_standard_error_m: NonnegativeFinite
    evidence_uri: EvidenceUri
    evidence_sha256: Sha256Digest
    measurement_truth_verified: Literal[True]

    @model_validator(mode="after")
    def _right_handed_orthonormal(self) -> Self:
        axes = np.column_stack(
            [
                (axis.x, axis.y, axis.z)
                for axis in (
                    self.fixture_x_axis_enu,
                    self.fixture_y_axis_enu,
                    self.fixture_z_axis_enu,
                )
            ]
        )
        if not np.allclose(axes.T @ axes, np.eye(3), rtol=0, atol=1e-9) or not math.isclose(
            float(np.linalg.det(axes)), 1.0, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("fixture-to-ENU axes must be right-handed and orthonormal")
        return self


class AdaptiveDualRxChainCalibrationV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
    differential_group_delay_s: Finite
    group_delay_standard_error_s: NonnegativeFinite
    residual_double_difference_rad: Finite
    residual_standard_error_rad: NonnegativeFinite
    absolute_cycle_referenced: bool
    measurement_truth_verified: Literal[True]
    evidence_uri: EvidenceUri
    evidence_sha256: Sha256Digest
    calibration_digest: Sha256Digest

    @model_validator(mode="after")
    def _validity_and_digest(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("chain calibration validity interval must be non-empty")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"calibration_digest"}))
        if self.calibration_digest != expected:
            raise ValueError("chain calibration digest differs from its content")
        return self


class AdaptiveDualRxPhaseCenterPathV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(strict=True, ge=0, le=1)]
    physical_receiver_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    slot_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    phase_center_offset_from_mount_m: CartesianVectorMetersV1


class AdaptiveDualRxPhaseCenterRefinementV1(AdaptiveModel):
    """Surveyed phase centers and cable mapping refining one captured snapshot."""

    schema_version: Literal[1] = 1
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
    paths: Annotated[tuple[AdaptiveDualRxPhaseCenterPathV1, ...], Field(min_length=2, max_length=2)]
    evidence_uri: EvidenceUri
    evidence_sha256: Sha256Digest
    measurement_truth_verified: Literal[True]
    refinement_digest: Sha256Digest

    @model_validator(mode="after")
    def _canonical_paths_and_digest(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("phase-center refinement validity interval must be non-empty")
        if tuple(path.receiver_id for path in self.paths) != (0, 1):
            raise ValueError("phase-center refinement must use canonical RX0/RX1 order")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"refinement_digest"}))
        if self.refinement_digest != expected:
            raise ValueError("phase-center refinement digest differs from its content")
        return self


class AdaptiveDualRxDirectionRowV1(AdaptiveModel):
    """Independent source identity and direction for one retained hypothesis."""

    schema_version: Literal[1] = 1
    visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    hypothesis_index: Annotated[int, Field(strict=True, ge=0, lt=64)]
    low_rx0_tracking_cfo_hz: Finite
    high_rx0_tracking_cfo_hz: Finite
    low_source_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    high_source_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    low_rf_hz: PositiveFinite
    high_rf_hz: PositiveFinite
    low_direction_enu: UnitVectorV1
    high_direction_enu: UnitVectorV1
    direction_standard_error_rad: NonnegativeFinite
    association_method: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    association_uses_phase: Literal[False] = False
    source_identity_verified: Literal[True]

    @model_validator(mode="after")
    def _two_distinct_sources(self) -> Self:
        if self.low_source_id == self.high_source_id:
            raise ValueError("geometry direction row requires two distinct sources")
        return self


class AdaptiveDualRxGeometryInputV1(AdaptiveModel):
    """Content-addressed geometry/calibration/direction input for one GLRT binding."""

    schema_version: Literal[1] = 1
    kind: Literal["adaptive_dual_rx_geometry_input"] = "adaptive_dual_rx_geometry_input"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    glrt_binding_sha256: Sha256Digest
    receiver_geometry_binding_digest: Sha256Digest
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
    fixture_pose: AdaptiveDualRxFixturePoseV1
    phase_center_refinement: AdaptiveDualRxPhaseCenterRefinementV1 | None = None
    chain_calibration: AdaptiveDualRxChainCalibrationV1
    direction_evidence_uri: EvidenceUri
    direction_evidence_sha256: Sha256Digest
    directions: Annotated[tuple[AdaptiveDualRxDirectionRowV1, ...], Field(max_length=70_000)]
    input_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed_authority(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("geometry input validity interval must be non-empty")
        keys = tuple((row.visit_index, row.hypothesis_index) for row in self.directions)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("direction rows must be unique and canonically ordered")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"input_digest"}))
        if self.input_digest != expected:
            raise ValueError("geometry input digest differs from its content")
        return self
