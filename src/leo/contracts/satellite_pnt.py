"""Additive contracts for transferable satellite corrections and blinded PNT.

The known-position calibration receipt and the solver-facing correction product
are deliberately different artifacts.  A calibration receipt contains the
reference-site coordinates and is restricted to calibration/audit code.  The
transferable product contains only satellite-side state and opaque lineage
digests.  This distinction is essential when a later blinded observation was
made at the same physical site: handing the receipt to the navigation solver
would disclose the answer.

The blinded-position boundary is likewise split into four artifacts:

* :class:`BlindedPositionTruthV1` is committed before a challenge is opened and
  remains inaccessible to the solver;
* :class:`BlindedPositionChallengeV1` is the complete solver-visible input;
* :class:`BlindedPositionEstimateV1` seals a truth-free posterior; and
* :class:`BlindedPositionRevealReceiptV1` joins those artifacts only after the
  estimate has been sealed.

Content digests provide deterministic tamper evidence.  They do not prove
process isolation or trustworthy wall-clock chronology; the runner must still
enforce separate truth and solver ports, derive raw-source fingerprints through
a trusted HMAC authority, deny the solver any calibration-lineage resolver, and
seal chronology externally.  Digest fields are commitments, not a defense
against a malicious producer using arbitrary bytes as a covert channel.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

BoundedName = Annotated[str, StringConstraints(min_length=1, max_length=128)]
CommitmentNonce = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]
Matrix2 = tuple[Vector2, Vector2]
Matrix3 = tuple[Vector3, Vector3, Vector3]

_WGS84_SEMI_MAJOR_AXIS_M = 6_378_137.0
_WGS84_FLATTENING = 1.0 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = _WGS84_FLATTENING * (2.0 - _WGS84_FLATTENING)
_MINIMUM_LOCAL_PRIOR_RADIUS_M = 100.0
_MINIMUM_LOCAL_PRIOR_AXIS_SIGMA_M = 25.0
_MINIMUM_GEODETIC_PRIOR_ANGULAR_SPAN_DEG = 0.001
_MINIMUM_GEODETIC_PRIOR_ALTITUDE_SPAN_M = 100.0
_SYNTHETIC_VALIDITY_HORIZON_NS = 30_000_000_000


class CorrectionEvidenceClass(StrEnum):
    SYNTHETIC_ORACLE = "synthetic_oracle"
    CALIBRATED_CANDIDATE = "calibrated_candidate"
    AMBIGUITY_MEMBER = "ambiguity_member"


class CorrectionExpiryReason(StrEnum):
    FIXED_VALIDITY_HORIZON = "fixed_validity_horizon"
    NEW_TLE_REQUIRED = "new_tle_required"
    ACTIVITY_EPOCH_END = "activity_epoch_end"


class SatelliteFrequencyScope(StrEnum):
    SATELLITE = "satellite"
    BEAM_CHANNEL = "beam_channel"


class NavigationLane(StrEnum):
    ORACLE_IDENTITY_FROZEN_CORRECTION = "oracle_identity_frozen_correction"
    UNKNOWN_IDENTITY_FROZEN_CORRECTION = "unknown_identity_frozen_correction"
    UNKNOWN_IDENTITY_JOINT_CORRECTION = "unknown_identity_joint_correction"
    RADIO_ONLY_NO_CORRECTION = "radio_only_no_correction"


class SatelliteCorrectionReasonCode(StrEnum):
    TRANSFERABLE_MODES_AVAILABLE = "transferable_modes_available"
    NO_NAVIGATION_ELIGIBLE_MODE = "no_navigation_eligible_mode"
    INSUFFICIENT_CALIBRATION_EVIDENCE = "insufficient_calibration_evidence"


class PositionEstimateReasonCode(StrEnum):
    POSTERIOR_MODES_AVAILABLE = "posterior_modes_available"
    NO_POSITION_SOLUTION = "no_position_solution"
    INSUFFICIENT_TARGET_EVIDENCE = "insufficient_target_evidence"


class CalibrationSourceSpanV1(ContractModel):
    """Non-resolving authority fingerprint and physical raw-sample coordinates."""

    schema_version: Literal[1] = 1
    source_fingerprint_authority_digest: Sha256Digest
    source_recording_fingerprint: Sha256Digest
    source_fingerprint_scheme: Literal["authority-hmac-sha256-nonresolving-v1"] = (
        "authority-hmac-sha256-nonresolving-v1"
    )
    source_stream_index: Annotated[int, Field(ge=0)]
    source_sample_start: Annotated[int, Field(ge=0)]
    source_sample_stop: Annotated[int, Field(gt=0)]
    start_utc_ns: Annotated[int, Field(gt=0)]
    end_utc_ns: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _interval_is_nonempty(self) -> Self:
        if self.source_sample_stop <= self.source_sample_start:
            raise ValueError("calibration source sample span must be non-empty")
        if self.end_utc_ns <= self.start_utc_ns:
            raise ValueError("calibration source UTC interval must be non-empty")
        return self


class PositionObservationSetRefV1(ContractModel):
    """One immutable, source-span-bound observation product.

    Product and source-binding digests alone do not prevent the same samples
    from being repackaged.  A trusted authority therefore derives a stable,
    non-resolving HMAC fingerprint from raw recording content, while the
    physical stream index and half-open sample span identify the exact region.
    """

    schema_version: Literal[1] = 1
    product_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    source_recording_fingerprint: Sha256Digest
    source_fingerprint_scheme: Literal["authority-hmac-sha256-nonresolving-v1"] = (
        "authority-hmac-sha256-nonresolving-v1"
    )
    source_stream_index: Annotated[int, Field(ge=0)]
    source_sample_start: Annotated[int, Field(ge=0)]
    source_sample_stop: Annotated[int, Field(gt=0)]
    start_utc_ns: Annotated[int, Field(gt=0)]
    end_utc_ns: Annotated[int, Field(gt=0)]
    observation_count: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def _interval_is_nonempty(self) -> Self:
        if self.source_sample_stop <= self.source_sample_start:
            raise ValueError("position observation sample span must be non-empty")
        if self.end_utc_ns <= self.start_utc_ns:
            raise ValueError("position observation UTC interval must be non-empty")
        return self


class EquivalentEpochCorrectionV1(ContractModel):
    """One bounded equivalent-epoch correction.

    V1 intentionally persists the scalar correction used by the first
    synthetic slice.  RTN position/velocity corrections require an additive
    future schema instead of an untyped variable-length vector.
    """

    schema_version: Literal[1] = 1
    model: Literal["equivalent-epoch-offset-v1"] = "equivalent-epoch-offset-v1"
    reference_utc_ns: Annotated[int, Field(gt=0)]
    offset_s: Annotated[float, Field(ge=-5.0, le=5.0)]
    variance_s2: Annotated[float, Field(ge=0.0)]
    support_lower_s: float = -5.0
    support_upper_s: float = 5.0
    boundary_hit: bool

    @field_validator("offset_s", "variance_s2", "support_lower_s", "support_upper_s")
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("equivalent-epoch correction values must be finite")
        return value

    @model_validator(mode="after")
    def _boundary_status_is_derived(self) -> Self:
        if self.support_lower_s != -5.0 or self.support_upper_s != 5.0:
            raise ValueError("equivalent-epoch V1 support must remain exactly [-5,+5] seconds")
        hit = math.isclose(
            self.offset_s, self.support_lower_s, rel_tol=0.0, abs_tol=1e-12
        ) or math.isclose(self.offset_s, self.support_upper_s, rel_tol=0.0, abs_tol=1e-12)
        if self.boundary_hit != hit:
            raise ValueError("equivalent-epoch boundary flag does not match the estimate")
        maximum_variance = (self.offset_s - self.support_lower_s) * (
            self.support_upper_s - self.offset_s
        )
        if maximum_variance == 0.0:
            if self.variance_s2 != 0.0:
                raise ValueError("an endpoint epoch correction must have zero variance")
        elif self.variance_s2 > maximum_variance and not math.isclose(
            self.variance_s2,
            maximum_variance,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("epoch-correction variance exceeds bounded-support moments")
        return self


class SatelliteFrequencyStateV1(ContractModel):
    """Transferable transmitter/clock-frequency state at one RF carrier."""

    schema_version: Literal[1] = 1
    activity_epoch_id: Identifier
    scope: SatelliteFrequencyScope
    beam_channel_id: Identifier | None = None
    reference_utc_ns: Annotated[int, Field(gt=0)]
    bias_hz: float
    drift_hz_s: float
    bias_variance_hz2: Annotated[float, Field(ge=0.0)]
    drift_variance_hz2_s2: Annotated[float, Field(ge=0.0)]
    bias_drift_covariance_hz2_s: float

    @field_validator(
        "bias_hz",
        "drift_hz_s",
        "bias_variance_hz2",
        "drift_variance_hz2_s2",
        "bias_drift_covariance_hz2_s",
    )
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("satellite-frequency state values must be finite")
        return value

    @model_validator(mode="after")
    def _scope_and_covariance_are_coherent(self) -> Self:
        if (self.scope is SatelliteFrequencyScope.BEAM_CHANNEL) != (
            self.beam_channel_id is not None
        ):
            raise ValueError("beam/channel frequency scope requires exactly one channel identity")
        _validate_matrix2(
            (
                (self.bias_variance_hz2, self.bias_drift_covariance_hz2_s),
                (self.bias_drift_covariance_hz2_s, self.drift_variance_hz2_s2),
            )
        )
        return self


class VerifiedTleMemberV1(ContractModel):
    """Authority-verified identity and epoch for one element in a TLE snapshot."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(ge=1)]
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: Annotated[int, Field(gt=0)]


class SatelliteCorrectionModeV1(ContractModel):
    """One catalogue-conditioned satellite-side correction hypothesis."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(ge=1)]
    posterior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    evidence_class: CorrectionEvidenceClass
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: Annotated[int, Field(gt=0)]
    element_age_s_at_reference: Annotated[float, Field(ge=0.0)]
    ephemeris: EquivalentEpochCorrectionV1
    frequency: SatelliteFrequencyStateV1
    valid_from_utc_ns: Annotated[int, Field(gt=0)]
    valid_until_utc_ns: Annotated[int, Field(gt=0)]
    expiry_reason: CorrectionExpiryReason
    navigation_eligible: bool
    mode_digest: Sha256Digest

    @field_validator("posterior_probability", "element_age_s_at_reference")
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("satellite correction values must be finite")
        return value

    @model_validator(mode="after")
    def _mode_is_coherent(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("satellite correction validity interval must be non-empty")
        if self.ephemeris.reference_utc_ns != self.frequency.reference_utc_ns:
            raise ValueError("ephemeris and frequency corrections need one reference instant")
        expected_age = abs(self.ephemeris.reference_utc_ns - self.element_epoch_utc_ns) / 1e9
        if not math.isclose(
            self.element_age_s_at_reference,
            expected_age,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("element age does not match its epoch and correction reference")
        if self.ephemeris.boundary_hit and self.navigation_eligible:
            raise ValueError("an epoch-boundary correction cannot be navigation eligible")
        if self.mode_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"mode_digest"})
        ):
            raise ValueError("satellite correction mode digest does not match content")
        return self


class SatelliteCorrectionProductV1(ContractModel):
    """Solver-safe satellite correction product with no calibration-site truth."""

    schema_version: Literal[1] = 1
    kind: Literal["satellite-correction-product"] = "satellite-correction-product"
    algorithm_version: Literal["known-position-reference-calibration-v1"] = (
        "known-position-reference-calibration-v1"
    )
    calibration_protocol_digest: Sha256Digest
    calibration_evidence_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    calibration_source_spans: Annotated[
        tuple[CalibrationSourceSpanV1, ...], Field(min_length=1, max_length=4096)
    ]
    calibration_lineage_access_policy: Literal["opaque-nonresolving-fingerprints-v1"] = (
        "opaque-nonresolving-fingerprints-v1"
    )
    calibration_start_utc_ns: Annotated[int, Field(gt=0)]
    calibration_end_utc_ns: Annotated[int, Field(gt=0)]
    produced_utc_ns: Annotated[int, Field(gt=0)]
    tle_snapshot: TleSnapshotRefV1
    tle_membership_authority_digest: Sha256Digest
    verified_tle_members: Annotated[tuple[VerifiedTleMemberV1, ...], Field(max_length=512)]
    propagation_model: Literal["sgp4-vallado-2006"] = "sgp4-vallado-2006"
    validity_policy: Literal["synthetic-fixed-30s-recent-tle-v1"] = (
        "synthetic-fixed-30s-recent-tle-v1"
    )
    validity_horizon_s: Literal[30] = 30
    maximum_tle_age_s: Literal[86_400] = 86_400
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    association_hypothesis_digest: Sha256Digest
    modes: Annotated[tuple[SatelliteCorrectionModeV1, ...], Field(max_length=512)]
    unassigned_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    status: StandardScientificStatus
    reason_code: SatelliteCorrectionReasonCode
    calibration_site_disclosed: Literal[False] = False
    receiver_local_state_excluded: Literal[True] = True
    local_state_treatment: Literal["marginalized-not-exported-v1"] = "marginalized-not-exported-v1"
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("downlink_frequency_hz", "unassigned_probability")
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("satellite correction product values must be finite")
        return value

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        if self.calibration_end_utc_ns <= self.calibration_start_utc_ns:
            raise ValueError("calibration interval must be non-empty")
        if self.produced_utc_ns < self.calibration_end_utc_ns:
            raise ValueError("a correction product cannot predate calibration completion")
        if self.tle_snapshot.collected_utc_ns > self.calibration_start_utc_ns:
            raise ValueError("calibration TLE snapshot must be causal")
        if self.produced_utc_ns - self.tle_snapshot.collected_utc_ns > self.maximum_tle_age_s * 1e9:
            raise ValueError("navigation TLE snapshot exceeds the synthetic freshness policy")
        source_span_keys = tuple(_source_span_key(item) for item in self.calibration_source_spans)
        if source_span_keys != tuple(sorted(set(source_span_keys))):
            raise ValueError("calibration source spans must be unique and ordered")
        _validate_nonoverlapping_source_spans(self.calibration_source_spans, label="calibration")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.calibration_source_spans
        ):
            raise ValueError("calibration source fingerprints use the wrong authority namespace")
        if any(
            item.start_utc_ns < self.calibration_start_utc_ns
            or item.end_utc_ns > self.calibration_end_utc_ns
            for item in self.calibration_source_spans
        ):
            raise ValueError("calibration source spans must lie inside calibration")
        verified_member_keys = tuple(_tle_member_key(item) for item in self.verified_tle_members)
        if verified_member_keys != tuple(sorted(set(verified_member_keys))):
            raise ValueError("verified TLE members must be unique and ordered")
        mode_keys = tuple(
            (
                item.catalog_number,
                item.frequency.activity_epoch_id,
                item.frequency.scope.value,
                item.frequency.beam_channel_id or "",
            )
            for item in self.modes
        )
        if mode_keys != tuple(sorted(set(mode_keys))):
            raise ValueError("satellite correction modes must be unique and canonically ordered")
        if len({item.mode_digest for item in self.modes}) != len(self.modes):
            raise ValueError("satellite correction mode digests must be unique")
        total_probability = self.unassigned_probability + sum(
            item.posterior_probability for item in self.modes
        )
        if not math.isclose(total_probability, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("satellite correction probabilities must sum to one")
        for mode in self.modes:
            reference = mode.ephemeris.reference_utc_ns
            if not self.calibration_start_utc_ns <= reference <= self.calibration_end_utc_ns:
                raise ValueError("correction reference instant lies outside calibration")
            mode_member_key = (
                mode.catalog_number,
                mode.selected_element_digest,
                mode.element_epoch_utc_ns,
            )
            if mode_member_key not in set(verified_member_keys):
                raise ValueError("selected element lacks verified TLE-snapshot membership")
            if (
                mode.navigation_eligible
                and mode.element_age_s_at_reference > self.maximum_tle_age_s
            ):
                raise ValueError("navigation-eligible element exceeds the freshness policy")
            if (
                mode.valid_from_utc_ns != self.produced_utc_ns
                or mode.valid_until_utc_ns != self.produced_utc_ns + _SYNTHETIC_VALIDITY_HORIZON_NS
                or mode.expiry_reason is not CorrectionExpiryReason.FIXED_VALIDITY_HORIZON
            ):
                raise ValueError("mode validity does not match the fixed synthetic policy")
        if set(verified_member_keys) != {
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.modes
        }:
            raise ValueError("verified TLE membership inventory must exactly cover product modes")
        if self.tle_snapshot.object_count < len(self.verified_tle_members):
            raise ValueError("verified TLE membership exceeds the snapshot object count")
        usable = any(item.navigation_eligible for item in self.modes)
        if self.status is StandardScientificStatus.COMPLETE and not usable:
            raise ValueError("a complete correction product needs a navigation-eligible mode")
        if self.status in {
            StandardScientificStatus.NO_RESULT,
            StandardScientificStatus.INSUFFICIENT_DATA,
        } and (self.modes or self.unassigned_probability != 1.0):
            raise ValueError("a correction no-result must contain only unassigned probability")
        expected_reason = (
            SatelliteCorrectionReasonCode.TRANSFERABLE_MODES_AVAILABLE
            if usable
            else SatelliteCorrectionReasonCode.NO_NAVIGATION_ELIGIBLE_MODE
            if self.modes
            else SatelliteCorrectionReasonCode.INSUFFICIENT_CALIBRATION_EVIDENCE
        )
        if self.reason_code is not expected_reason:
            raise ValueError("satellite correction reason code does not match its result")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("satellite correction product digest does not match content")
        return self


class KnownPositionCalibrationReceiptV1(ContractModel):
    """Access-controlled calibration truth and its transferable projection."""

    schema_version: Literal[1] = 1
    kind: Literal["known-position-calibration-receipt"] = "known-position-calibration-receipt"
    calibration_site: ObserverSiteV1
    calibration_site_authority_digest: Sha256Digest
    full_joint_state_digest: Sha256Digest
    receiver_local_state_digest: Sha256Digest
    correction_product: SatelliteCorrectionProductV1
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    site_access_policy: Literal["calibration-and-reveal-only-v1"] = "calibration-and-reveal-only-v1"
    receiver_local_state_exported: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_closed(self) -> Self:
        if self.sealed_utc_ns < self.correction_product.produced_utc_ns:
            raise ValueError("calibration receipt cannot predate its correction product")
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("known-position calibration receipt digest does not match content")
        return self


class LocalEcefGaussianPriorV1(ContractModel):
    """A declared local initialization prior, not position truth."""

    schema_version: Literal[1] = 1
    kind: Literal["local-ecef-gaussian"] = "local-ecef-gaussian"
    prior_provenance_digest: Sha256Digest
    selection_policy: Literal["response-free-precommitted-v1"] = "response-free-precommitted-v1"
    mean_ecef_m: Vector3
    covariance_ecef_m2: Matrix3
    maximum_radius_m: Annotated[float, Field(gt=0.0, le=1_000_000.0)]
    breadth_policy: Literal["minimum-100m-radius-and-25m-axis-sigma-v1"] = (
        "minimum-100m-radius-and-25m-axis-sigma-v1"
    )

    @field_validator("maximum_radius_m")
    @classmethod
    def _finite_radius(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("local prior radius must be finite")
        return value

    @model_validator(mode="after")
    def _prior_is_physical(self) -> Self:
        _validate_ecef(self.mean_ecef_m, "local prior")
        _validate_matrix3(self.covariance_ecef_m2, positive_definite=True)
        floor_variance = _MINIMUM_LOCAL_PRIOR_AXIS_SIGMA_M**2
        covariance = self.covariance_ecef_m2
        floor_shifted: Matrix3 = (
            (covariance[0][0] - floor_variance, covariance[0][1], covariance[0][2]),
            (covariance[1][0], covariance[1][1] - floor_variance, covariance[1][2]),
            (covariance[2][0], covariance[2][1], covariance[2][2] - floor_variance),
        )
        _validate_matrix3(floor_shifted, positive_definite=False)
        if self.maximum_radius_m < _MINIMUM_LOCAL_PRIOR_RADIUS_M:
            raise ValueError("local prior radius is below the non-leaking 100 m minimum")
        if self.maximum_radius_m < 3.0 * math.sqrt(
            _largest_eigenvalue_symmetric3(self.covariance_ecef_m2)
        ):
            raise ValueError("local prior radius must cover the full three-sigma ellipsoid")
        return self


class BoundedGeodeticPriorV1(ContractModel):
    """A response-free continental or global WGS84 search box."""

    schema_version: Literal[1] = 1
    kind: Literal["bounded-wgs84-geodetic"] = "bounded-wgs84-geodetic"
    prior_provenance_digest: Sha256Digest
    selection_policy: Literal["response-free-precommitted-v1"] = "response-free-precommitted-v1"
    breadth_policy: Literal["minimum-0.001deg-and-100m-altitude-span-v1"] = (
        "minimum-0.001deg-and-100m-altitude-span-v1"
    )
    latitude_lower_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    latitude_upper_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    longitude_lower_deg: Annotated[float, Field(ge=-180.0, le=180.0)]
    longitude_upper_deg: Annotated[float, Field(ge=-180.0, le=180.0)]
    altitude_lower_m: Annotated[float, Field(ge=-500.0, le=100_000.0)]
    altitude_upper_m: Annotated[float, Field(ge=-500.0, le=100_000.0)]

    @model_validator(mode="after")
    def _bounds_are_finite_and_ordered(self) -> Self:
        values = (
            self.latitude_lower_deg,
            self.latitude_upper_deg,
            self.longitude_lower_deg,
            self.longitude_upper_deg,
            self.altitude_lower_m,
            self.altitude_upper_m,
        )
        if any(not math.isfinite(item) for item in values):
            raise ValueError("geodetic prior bounds must be finite")
        if (
            self.latitude_upper_deg <= self.latitude_lower_deg
            or self.longitude_upper_deg <= self.longitude_lower_deg
            or self.altitude_upper_m <= self.altitude_lower_m
        ):
            raise ValueError("geodetic prior bounds must have positive extent")
        if (
            self.latitude_upper_deg - self.latitude_lower_deg
            < _MINIMUM_GEODETIC_PRIOR_ANGULAR_SPAN_DEG
            or self.longitude_upper_deg - self.longitude_lower_deg
            < _MINIMUM_GEODETIC_PRIOR_ANGULAR_SPAN_DEG
            or self.altitude_upper_m - self.altitude_lower_m
            < _MINIMUM_GEODETIC_PRIOR_ALTITUDE_SPAN_M
        ):
            raise ValueError("geodetic prior is narrower than the non-leaking minimum breadth")
        return self


PositionPriorV1 = Annotated[
    LocalEcefGaussianPriorV1 | BoundedGeodeticPriorV1,
    Field(discriminator="kind"),
]


class EarthAltitudeConstraintV1(ContractModel):
    """Explicit WGS84 ellipsoidal-height constraint for navigation."""

    schema_version: Literal[1] = 1
    model: Literal["wgs84-ellipsoidal-height-band-v1"] = "wgs84-ellipsoidal-height-band-v1"
    minimum_altitude_m: Annotated[float, Field(ge=-500.0, le=100_000.0)]
    maximum_altitude_m: Annotated[float, Field(ge=-500.0, le=100_000.0)]

    @model_validator(mode="after")
    def _constraint_is_ordered(self) -> Self:
        if not math.isfinite(self.minimum_altitude_m) or not math.isfinite(self.maximum_altitude_m):
            raise ValueError("altitude constraint must be finite")
        if self.maximum_altitude_m <= self.minimum_altitude_m:
            raise ValueError("altitude constraint must have positive extent")
        return self


class OracleIdentityFrozenCorrectionLaneV1(ContractModel):
    schema_version: Literal[1] = 1
    lane: Literal[NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION] = (
        NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION
    )
    oracle_assignment_digest: Sha256Digest
    correction_product: SatelliteCorrectionProductV1


class UnknownIdentityFrozenCorrectionLaneV1(ContractModel):
    schema_version: Literal[1] = 1
    lane: Literal[NavigationLane.UNKNOWN_IDENTITY_FROZEN_CORRECTION] = (
        NavigationLane.UNKNOWN_IDENTITY_FROZEN_CORRECTION
    )
    candidate_likelihood_bank_digest: Sha256Digest
    correction_product: SatelliteCorrectionProductV1


class UnknownIdentityJointCorrectionLaneV1(ContractModel):
    schema_version: Literal[1] = 1
    lane: Literal[NavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION] = (
        NavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION
    )
    candidate_likelihood_bank_digest: Sha256Digest
    joint_refinement_config_digest: Sha256Digest
    starting_correction_product: SatelliteCorrectionProductV1


class RadioOnlyNoCorrectionLaneV1(ContractModel):
    schema_version: Literal[1] = 1
    lane: Literal[NavigationLane.RADIO_ONLY_NO_CORRECTION] = NavigationLane.RADIO_ONLY_NO_CORRECTION
    radio_only_model_digest: Sha256Digest


NavigationLaneInputV1 = Annotated[
    OracleIdentityFrozenCorrectionLaneV1
    | UnknownIdentityFrozenCorrectionLaneV1
    | UnknownIdentityJointCorrectionLaneV1
    | RadioOnlyNoCorrectionLaneV1,
    Field(discriminator="lane"),
]


class BlindedPositionChallengeV1(ContractModel):
    """Complete solver-visible challenge; exact receiver truth is absent."""

    schema_version: Literal[1] = 1
    kind: Literal["blinded-position-challenge"] = "blinded-position-challenge"
    challenge_id: Identifier
    challenge_group_id: Identifier
    protocol_digest: Sha256Digest
    created_utc_ns: Annotated[int, Field(gt=0)]
    truth_commitment_digest: Sha256Digest
    truth_commitment_scheme: Literal["sha256-canonical-json-with-256-bit-nonce-v1"] = (
        "sha256-canonical-json-with-256-bit-nonce-v1"
    )
    target_evidence_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    observations: Annotated[
        tuple[PositionObservationSetRefV1, ...], Field(min_length=1, max_length=4096)
    ]
    motion_model: Literal["stationary"] = "stationary"
    reference_utc_ns: Annotated[int, Field(gt=0)]
    prior: PositionPriorV1
    earth_constraint: EarthAltitudeConstraintV1
    lane_inputs: NavigationLaneInputV1
    truth_access_policy: Literal["truth-inaccessible-until-estimate-sealed-v1"] = (
        "truth-inaccessible-until-estimate-sealed-v1"
    )
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _challenge_is_closed(self) -> Self:
        keys = tuple(_observation_key(item) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("position observation references must be unique and ordered")
        _validate_unique_observation_authorities(self.observations, label="target")
        _validate_nonoverlapping_source_spans(self.observations, label="target")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.observations
        ):
            raise ValueError("target source fingerprints use the wrong authority namespace")
        expected_evidence = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.observations)
        )
        if self.target_evidence_digest != expected_evidence:
            raise ValueError("target evidence digest does not match observation references")
        target_start = min(item.start_utc_ns for item in self.observations)
        target_end = max(item.end_utc_ns for item in self.observations)
        if not any(
            item.start_utc_ns <= self.reference_utc_ns < item.end_utc_ns
            for item in self.observations
        ):
            raise ValueError("position reference instant must lie inside target observations")
        _validate_prior_and_constraint(self.prior, self.earth_constraint)
        correction = _lane_correction(self.lane_inputs)
        if correction is not None:
            if (
                correction.source_fingerprint_authority_digest
                != self.source_fingerprint_authority_digest
            ):
                raise ValueError(
                    "calibration and target source fingerprints need one authority namespace"
                )
            if correction.status is not StandardScientificStatus.COMPLETE:
                raise ValueError("a navigation challenge requires a complete correction product")
            for target in self.observations:
                for calibration in correction.calibration_source_spans:
                    if _source_sample_spans_overlap(target, calibration):
                        raise ValueError("target and calibration raw-source spans must be disjoint")
                    if (
                        _same_source_stream(target, calibration)
                        and target.source_sample_start < calibration.source_sample_stop
                    ):
                        raise ValueError(
                            "target raw samples must follow calibration on a shared source stream"
                        )
            if target_start < correction.produced_utc_ns:
                raise ValueError("target observations cannot predate correction production")
            if self.created_utc_ns < correction.produced_utc_ns:
                raise ValueError("challenge cannot predate correction production")
            usable = tuple(item for item in correction.modes if item.navigation_eligible)
            if not usable:
                raise ValueError("navigation challenge has no eligible satellite correction")
            if any(
                item.valid_from_utc_ns > target_start or item.valid_until_utc_ns < target_end
                for item in usable
            ):
                raise ValueError("target observations fall outside correction validity")
            if isinstance(
                self.lane_inputs,
                (
                    UnknownIdentityFrozenCorrectionLaneV1,
                    UnknownIdentityJointCorrectionLaneV1,
                ),
            ) and any(
                item.evidence_class is CorrectionEvidenceClass.SYNTHETIC_ORACLE
                for item in correction.modes
            ):
                raise ValueError("unknown-identity lanes cannot consume oracle-derived correction")
        lane_digests = _lane_evidence_digests(self.lane_inputs)
        if len(set(lane_digests)) != len(lane_digests):
            raise ValueError("lane evidence/configuration digests must be distinct")
        protected_digests = {
            self.protocol_digest,
            self.truth_commitment_digest,
            self.target_evidence_digest,
            self.source_fingerprint_authority_digest,
        }
        for observation in self.observations:
            protected_digests.update(
                {
                    observation.product_digest,
                    observation.source_binding_digest,
                    observation.source_recording_fingerprint,
                }
            )
        if correction is not None:
            protected_digests.update(
                {
                    correction.content_digest,
                    correction.calibration_protocol_digest,
                    correction.calibration_evidence_digest,
                    correction.association_hypothesis_digest,
                    correction.tle_snapshot.digest,
                    correction.tle_membership_authority_digest,
                }
            )
            protected_digests.update(
                item.source_recording_fingerprint for item in correction.calibration_source_spans
            )
            protected_digests.update(item.selected_element_digest for item in correction.modes)
            protected_digests.update(item.mode_digest for item in correction.modes)
        if self.prior.prior_provenance_digest in protected_digests:
            raise ValueError("position-prior provenance is not isolated from response artifacts")
        protected_digests.add(self.prior.prior_provenance_digest)
        if protected_digests.intersection(lane_digests):
            raise ValueError("lane evidence digests are not isolated from protected artifacts")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("blinded-position challenge digest does not match content")
        return self


class BlindedPositionTruthV1(ContractModel):
    """Salted, precommitted position truth unavailable to the solver."""

    schema_version: Literal[1] = 1
    kind: Literal["blinded-position-truth"] = "blinded-position-truth"
    challenge_group_id: Identifier
    target_evidence_digest: Sha256Digest
    reference_utc_ns: Annotated[int, Field(gt=0)]
    position: ObserverSiteV1
    truth_authority_digest: Sha256Digest
    commitment_nonce_hex: CommitmentNonce
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _truth_is_committed(self) -> Self:
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("blinded-position truth commitment does not match content")
        return self


class ReceiverClockPosteriorV1(ContractModel):
    """Optional receiver timing state associated with one position mode."""

    schema_version: Literal[1] = 1
    reference_utc_ns: Annotated[int, Field(gt=0)]
    bias_s: float
    drift_s_s: float
    covariance: Matrix2

    @model_validator(mode="after")
    def _clock_state_is_finite(self) -> Self:
        if not math.isfinite(self.bias_s) or not math.isfinite(self.drift_s_s):
            raise ValueError("receiver-clock posterior values must be finite")
        _validate_matrix2(self.covariance)
        return self


class PositionPosteriorModeV1(ContractModel):
    """One sealed Gaussian mode in ECEF coordinates."""

    schema_version: Literal[1] = 1
    mode_id: Sha256Digest
    rank: Annotated[int, Field(ge=1, le=256)]
    posterior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    mean_ecef_m: Vector3
    covariance_ecef_m2: Matrix3
    consumed_correction_mode_digests: Annotated[
        tuple[Sha256Digest, ...], Field(max_length=512)
    ] = ()
    associated_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=512)]
    association_hypothesis_digest: Sha256Digest | None = None
    receiver_clock: ReceiverClockPosteriorV1 | None = None

    @field_validator("posterior_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("posterior probability must be finite")
        return value

    @model_validator(mode="after")
    def _mode_is_physical(self) -> Self:
        _validate_ecef(self.mean_ecef_m, "position posterior")
        _validate_matrix3(self.covariance_ecef_m2, positive_definite=False)
        if self.associated_catalog_numbers != tuple(sorted(set(self.associated_catalog_numbers))):
            raise ValueError("associated catalogue numbers must be unique and ordered")
        if self.consumed_correction_mode_digests != tuple(
            sorted(set(self.consumed_correction_mode_digests))
        ):
            raise ValueError("consumed correction-mode digests must be unique and ordered")
        if any(item <= 0 for item in self.associated_catalog_numbers):
            raise ValueError("associated catalogue numbers must be positive")
        return self


class BlindedPositionEstimateV1(ContractModel):
    """Truth-free posterior sealed before the reveal boundary opens."""

    schema_version: Literal[1] = 1
    kind: Literal["blinded-position-estimate"] = "blinded-position-estimate"
    challenge_id: Identifier
    challenge_group_id: Identifier
    challenge_content_digest: Sha256Digest
    truth_commitment_digest: Sha256Digest
    lane: NavigationLane
    reference_utc_ns: Annotated[int, Field(gt=0)]
    consumed_correction_product_digest: Sha256Digest | None = None
    consumed_candidate_likelihood_bank_digest: Sha256Digest | None = None
    consumed_oracle_assignment_digest: Sha256Digest | None = None
    consumed_joint_refinement_config_digest: Sha256Digest | None = None
    consumed_radio_only_model_digest: Sha256Digest | None = None
    joint_association_result_digest: Sha256Digest | None = None
    solver_algorithm_version: BoundedName
    solver_config_digest: Sha256Digest
    solver_execution_digest: Sha256Digest
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    status: StandardScientificStatus
    reason_code: PositionEstimateReasonCode
    source_mode_count: Annotated[int, Field(ge=0)]
    returned_mode_count: Annotated[int, Field(ge=0, le=256)]
    truncated_mode_count: Annotated[int, Field(ge=0)]
    modes: Annotated[tuple[PositionPosteriorModeV1, ...], Field(max_length=256)]
    reported_mode_id: Sha256Digest | None
    unresolved_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    truth_accessed: Literal[False] = False
    truth_metrics_included: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("unresolved_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("unresolved posterior probability must be finite")
        return value

    @model_validator(mode="after")
    def _estimate_is_closed(self) -> Self:
        _validate_estimate_lane_shape(self)
        consumed_digests = tuple(
            item
            for item in (
                self.consumed_correction_product_digest,
                self.consumed_candidate_likelihood_bank_digest,
                self.consumed_oracle_assignment_digest,
                self.consumed_joint_refinement_config_digest,
                self.consumed_radio_only_model_digest,
                self.joint_association_result_digest,
            )
            if item is not None
        )
        if len(set(consumed_digests)) != len(consumed_digests):
            raise ValueError("consumed lane evidence digests must be distinct")
        if {
            self.challenge_content_digest,
            self.truth_commitment_digest,
            self.solver_config_digest,
            self.solver_execution_digest,
        }.intersection(consumed_digests):
            raise ValueError("consumed lane evidence is not isolated from solver artifacts")
        if any(
            item.receiver_clock is not None
            and item.receiver_clock.reference_utc_ns != self.reference_utc_ns
            for item in self.modes
        ):
            raise ValueError("receiver-clock posterior reference must match position reference")
        radio_only = self.lane is NavigationLane.RADIO_ONLY_NO_CORRECTION
        if radio_only and any(
            item.consumed_correction_mode_digests
            or item.associated_catalog_numbers
            or item.association_hypothesis_digest is not None
            for item in self.modes
        ):
            raise ValueError("radio-only position modes cannot contain catalogue association")
        if not radio_only and any(
            not item.consumed_correction_mode_digests
            or not item.associated_catalog_numbers
            or item.association_hypothesis_digest is None
            for item in self.modes
        ):
            raise ValueError("catalogue navigation modes require explicit association evidence")
        if (
            self.returned_mode_count + self.truncated_mode_count != self.source_mode_count
            or self.returned_mode_count != len(self.modes)
        ):
            raise ValueError("position posterior mode accounting is inconsistent")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise ValueError("position posterior modes must have contiguous canonical ranks")
        if len({item.mode_id for item in self.modes}) != len(self.modes):
            raise ValueError("position posterior mode identities must be unique")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("position posterior modes must be ordered by probability")
        if not math.isclose(
            sum(probabilities) + self.unresolved_probability,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("position posterior probabilities must sum to one")
        reported = next(
            (item for item in self.modes if item.mode_id == self.reported_mode_id), None
        )
        if self.modes:
            if reported is None or reported.rank != 1:
                raise ValueError("the predeclared reported position must be the rank-one mode")
            if self.status in {
                StandardScientificStatus.NO_RESULT,
                StandardScientificStatus.INSUFFICIENT_DATA,
            }:
                raise ValueError("a position no-result cannot contain posterior modes")
        elif self.reported_mode_id is not None or self.unresolved_probability != 1.0:
            raise ValueError("an empty position posterior must remain completely unresolved")
        if self.status is StandardScientificStatus.COMPLETE and not self.modes:
            raise ValueError("a complete position estimate requires a posterior mode")
        expected_reason = (
            PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE
            if self.modes
            else PositionEstimateReasonCode.INSUFFICIENT_TARGET_EVIDENCE
            if self.status is StandardScientificStatus.INSUFFICIENT_DATA
            else PositionEstimateReasonCode.NO_POSITION_SOLUTION
        )
        if self.reason_code is not expected_reason:
            raise ValueError("position estimate reason code does not match its result")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("blinded-position estimate digest does not match content")
        return self


class BlindedPositionRevealReceiptV1(ContractModel):
    """Reveal-side join; position-error evaluation is a later pure analyzer."""

    schema_version: Literal[1] = 1
    kind: Literal["blinded-position-reveal-receipt"] = "blinded-position-reveal-receipt"
    challenge: BlindedPositionChallengeV1
    estimate: BlindedPositionEstimateV1
    truth: BlindedPositionTruthV1
    revealed_utc_ns: Annotated[int, Field(gt=0)]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _reveal_is_exact_and_chronological(self) -> Self:
        challenge = self.challenge
        estimate = self.estimate
        truth = self.truth
        if not (
            truth.sealed_utc_ns
            <= challenge.created_utc_ns
            <= estimate.sealed_utc_ns
            < self.revealed_utc_ns
        ):
            raise ValueError("blinded-position seal and reveal chronology is invalid")
        if estimate.sealed_utc_ns < max(item.end_utc_ns for item in challenge.observations):
            raise ValueError("position estimate was sealed before target evidence was complete")
        if (
            truth.content_digest != challenge.truth_commitment_digest
            or truth.challenge_group_id != challenge.challenge_group_id
            or truth.target_evidence_digest != challenge.target_evidence_digest
            or truth.reference_utc_ns != challenge.reference_utc_ns
        ):
            raise ValueError("revealed truth does not match the blinded challenge commitment")
        if (
            estimate.challenge_id != challenge.challenge_id
            or estimate.challenge_group_id != challenge.challenge_group_id
            or estimate.challenge_content_digest != challenge.content_digest
            or estimate.truth_commitment_digest != challenge.truth_commitment_digest
            or estimate.lane is not NavigationLane(challenge.lane_inputs.lane)
            or estimate.reference_utc_ns != challenge.reference_utc_ns
        ):
            raise ValueError("sealed position estimate is not bound to this exact challenge")
        _validate_estimate_against_lane(estimate, challenge.lane_inputs)
        truth_ecef = _geodetic_to_ecef_m(truth.position)
        _validate_position_against_prior_and_constraint(
            truth_ecef,
            challenge.prior,
            challenge.earth_constraint,
            label="revealed truth",
        )
        for mode in estimate.modes:
            _validate_position_against_prior_and_constraint(
                mode.mean_ecef_m,
                challenge.prior,
                challenge.earth_constraint,
                label="position posterior mode",
            )
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("blinded-position reveal receipt digest does not match content")
        return self


def _lane_correction(
    lane: NavigationLaneInputV1,
) -> SatelliteCorrectionProductV1 | None:
    if isinstance(lane, RadioOnlyNoCorrectionLaneV1):
        return None
    if isinstance(lane, UnknownIdentityJointCorrectionLaneV1):
        return lane.starting_correction_product
    return lane.correction_product


def _observation_key(
    observation: PositionObservationSetRefV1,
) -> tuple[str, int, int, int, str]:
    return (*_source_span_key(observation), observation.product_digest)


def _source_span_key(
    observation: PositionObservationSetRefV1 | CalibrationSourceSpanV1,
) -> tuple[str, int, int, int]:
    return (
        observation.source_recording_fingerprint,
        observation.source_stream_index,
        observation.source_sample_start,
        observation.source_sample_stop,
    )


def _tle_member_key(member: VerifiedTleMemberV1) -> tuple[int, str, int]:
    return (
        member.catalog_number,
        member.selected_element_digest,
        member.element_epoch_utc_ns,
    )


def _validate_unique_observation_authorities(
    observations: tuple[PositionObservationSetRefV1, ...], *, label: str
) -> None:
    product_digests = tuple(item.product_digest for item in observations)
    source_bindings = tuple(item.source_binding_digest for item in observations)
    if len(set(product_digests)) != len(product_digests):
        raise ValueError(f"{label} observation product digests must be unique")
    if len(set(source_bindings)) != len(source_bindings):
        raise ValueError(f"{label} observation source bindings must be unique")


def _validate_nonoverlapping_source_spans(
    observations: Sequence[PositionObservationSetRefV1 | CalibrationSourceSpanV1],
    *,
    label: str,
) -> None:
    latest_stop_by_stream: dict[tuple[str, int], int] = {}
    latest_end_utc_by_stream: dict[tuple[str, int], int] = {}
    ordered = sorted(
        observations,
        key=lambda item: (
            item.source_recording_fingerprint,
            item.source_stream_index,
            item.source_sample_start,
            item.source_sample_stop,
        ),
    )
    for observation in ordered:
        stream_key = (
            observation.source_recording_fingerprint,
            observation.source_stream_index,
        )
        latest_stop = latest_stop_by_stream.get(stream_key)
        if latest_stop is not None and observation.source_sample_start < latest_stop:
            raise ValueError(f"{label} raw-source sample spans must not overlap")
        latest_end_utc = latest_end_utc_by_stream.get(stream_key)
        if latest_end_utc is not None and observation.start_utc_ns < latest_end_utc:
            raise ValueError(f"{label} raw-sample and UTC span ordering must agree")
        latest_stop_by_stream[stream_key] = observation.source_sample_stop
        latest_end_utc_by_stream[stream_key] = observation.end_utc_ns


def _source_sample_spans_overlap(
    left: PositionObservationSetRefV1 | CalibrationSourceSpanV1,
    right: PositionObservationSetRefV1 | CalibrationSourceSpanV1,
) -> bool:
    return (
        _same_source_stream(left, right)
        and left.source_sample_start < right.source_sample_stop
        and right.source_sample_start < left.source_sample_stop
    )


def _same_source_stream(
    left: PositionObservationSetRefV1 | CalibrationSourceSpanV1,
    right: PositionObservationSetRefV1 | CalibrationSourceSpanV1,
) -> bool:
    return (
        left.source_recording_fingerprint == right.source_recording_fingerprint
        and left.source_stream_index == right.source_stream_index
    )


def _lane_evidence_digests(lane: NavigationLaneInputV1) -> tuple[str, ...]:
    if isinstance(lane, OracleIdentityFrozenCorrectionLaneV1):
        return (lane.oracle_assignment_digest,)
    if isinstance(lane, UnknownIdentityFrozenCorrectionLaneV1):
        return (lane.candidate_likelihood_bank_digest,)
    if isinstance(lane, UnknownIdentityJointCorrectionLaneV1):
        return (
            lane.candidate_likelihood_bank_digest,
            lane.joint_refinement_config_digest,
        )
    return (lane.radio_only_model_digest,)


def _validate_estimate_lane_shape(estimate: BlindedPositionEstimateV1) -> None:
    present = (
        estimate.consumed_correction_product_digest is not None,
        estimate.consumed_candidate_likelihood_bank_digest is not None,
        estimate.consumed_oracle_assignment_digest is not None,
        estimate.consumed_joint_refinement_config_digest is not None,
        estimate.consumed_radio_only_model_digest is not None,
        estimate.joint_association_result_digest is not None,
    )
    expected = {
        NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION: (
            True,
            False,
            True,
            False,
            False,
            False,
        ),
        NavigationLane.UNKNOWN_IDENTITY_FROZEN_CORRECTION: (
            True,
            True,
            False,
            False,
            False,
            False,
        ),
        NavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION: (
            True,
            True,
            False,
            True,
            False,
            True,
        ),
        NavigationLane.RADIO_ONLY_NO_CORRECTION: (
            False,
            False,
            False,
            False,
            True,
            False,
        ),
    }[estimate.lane]
    if present != expected:
        raise ValueError("consumed evidence digests do not match the navigation lane")


def _validate_estimate_against_lane(
    estimate: BlindedPositionEstimateV1, lane: NavigationLaneInputV1
) -> None:
    correction = _lane_correction(lane)
    if correction is None:
        assert isinstance(lane, RadioOnlyNoCorrectionLaneV1)
        if estimate.consumed_radio_only_model_digest != lane.radio_only_model_digest:
            raise ValueError("radio-only estimate consumed the wrong model artifact")
        return
    if estimate.consumed_correction_product_digest != correction.content_digest:
        raise ValueError("position estimate consumed the wrong correction product")
    eligible_modes = {
        item.mode_digest: item for item in correction.modes if item.navigation_eligible
    }
    for mode in estimate.modes:
        consumed_mode_digests = set(mode.consumed_correction_mode_digests)
        if not consumed_mode_digests.issubset(eligible_modes):
            raise ValueError(
                "position mode references a correction mode outside eligible inventory"
            )
        derived_catalogues = tuple(
            sorted({eligible_modes[item].catalog_number for item in consumed_mode_digests})
        )
        if mode.associated_catalog_numbers != derived_catalogues:
            raise ValueError("position catalogue labels do not match exact correction modes")
    if isinstance(lane, OracleIdentityFrozenCorrectionLaneV1):
        if estimate.consumed_oracle_assignment_digest != lane.oracle_assignment_digest:
            raise ValueError("oracle lane estimate consumed the wrong assignment artifact")
        if any(
            item.association_hypothesis_digest != lane.oracle_assignment_digest
            for item in estimate.modes
        ):
            raise ValueError("oracle position modes are not bound to the oracle assignment")
        return
    assert isinstance(
        lane,
        (UnknownIdentityFrozenCorrectionLaneV1, UnknownIdentityJointCorrectionLaneV1),
    )
    if estimate.consumed_candidate_likelihood_bank_digest != lane.candidate_likelihood_bank_digest:
        raise ValueError("unknown-identity estimate consumed the wrong candidate bank")
    if isinstance(lane, UnknownIdentityFrozenCorrectionLaneV1):
        if any(
            item.association_hypothesis_digest != correction.association_hypothesis_digest
            for item in estimate.modes
        ):
            raise ValueError("frozen-correction modes are not bound to the frozen association")
        return
    assert isinstance(lane, UnknownIdentityJointCorrectionLaneV1)
    if estimate.consumed_joint_refinement_config_digest != lane.joint_refinement_config_digest:
        raise ValueError("joint-correction estimate consumed the wrong refinement configuration")
    if any(
        item.association_hypothesis_digest != estimate.joint_association_result_digest
        for item in estimate.modes
    ):
        raise ValueError("joint-correction modes are not bound to the generated association result")


def _validate_prior_and_constraint(
    prior: PositionPriorV1, constraint: EarthAltitudeConstraintV1
) -> None:
    if isinstance(prior, BoundedGeodeticPriorV1):
        if max(prior.altitude_lower_m, constraint.minimum_altitude_m) >= min(
            prior.altitude_upper_m, constraint.maximum_altitude_m
        ):
            raise ValueError("position prior and Earth-altitude constraint do not intersect")
        return
    _, _, altitude_m = _ecef_to_geodetic(prior.mean_ecef_m)
    if not constraint.minimum_altitude_m <= altitude_m <= constraint.maximum_altitude_m:
        raise ValueError("local-prior center lies outside the Earth-altitude constraint")


def _validate_position_against_prior_and_constraint(
    ecef_m: Vector3,
    prior: PositionPriorV1,
    constraint: EarthAltitudeConstraintV1,
    *,
    label: str,
) -> None:
    latitude_deg, longitude_deg, altitude_m = _ecef_to_geodetic(ecef_m)
    if not constraint.minimum_altitude_m <= altitude_m <= constraint.maximum_altitude_m:
        raise ValueError(f"{label} lies outside the declared Earth-altitude constraint")
    if isinstance(prior, BoundedGeodeticPriorV1):
        if not (
            prior.latitude_lower_deg <= latitude_deg <= prior.latitude_upper_deg
            and prior.longitude_lower_deg <= longitude_deg <= prior.longitude_upper_deg
            and prior.altitude_lower_m <= altitude_m <= prior.altitude_upper_m
        ):
            raise ValueError(f"{label} lies outside the declared geodetic prior")
        return
    distance_m = math.sqrt(
        sum((value - center) ** 2 for value, center in zip(ecef_m, prior.mean_ecef_m, strict=True))
    )
    if distance_m > prior.maximum_radius_m:
        raise ValueError(f"{label} lies outside the declared local prior radius")


def _geodetic_to_ecef_m(site: ObserverSiteV1) -> Vector3:
    latitude = math.radians(site.latitude_deg)
    longitude = math.radians(site.longitude_deg)
    sin_latitude = math.sin(latitude)
    cos_latitude = math.cos(latitude)
    prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    return (
        (prime_vertical + site.altitude_m) * cos_latitude * math.cos(longitude),
        (prime_vertical + site.altitude_m) * cos_latitude * math.sin(longitude),
        (prime_vertical * (1.0 - _WGS84_ECCENTRICITY_SQUARED) + site.altitude_m) * sin_latitude,
    )


def _ecef_to_geodetic(ecef_m: Vector3) -> tuple[float, float, float]:
    _validate_ecef(ecef_m, "position")
    x_m, y_m, z_m = ecef_m
    horizontal_m = math.hypot(x_m, y_m)
    semi_minor_m = _WGS84_SEMI_MAJOR_AXIS_M * (1.0 - _WGS84_FLATTENING)
    if horizontal_m < 1e-9:
        latitude_deg = math.copysign(90.0, z_m)
        return latitude_deg, 0.0, abs(z_m) - semi_minor_m
    latitude = math.atan2(z_m, horizontal_m * (1.0 - _WGS84_ECCENTRICITY_SQUARED))
    altitude_m = 0.0
    for _iteration in range(12):
        sin_latitude = math.sin(latitude)
        prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
            1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
        )
        altitude_m = horizontal_m / math.cos(latitude) - prime_vertical
        updated = math.atan2(
            z_m,
            horizontal_m
            * (1.0 - _WGS84_ECCENTRICITY_SQUARED * prime_vertical / (prime_vertical + altitude_m)),
        )
        if abs(updated - latitude) <= 1e-14:
            latitude = updated
            break
        latitude = updated
    sin_latitude = math.sin(latitude)
    prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    altitude_m = horizontal_m / math.cos(latitude) - prime_vertical
    return math.degrees(latitude), math.degrees(math.atan2(y_m, x_m)), altitude_m


def _validate_ecef(values: Vector3, label: str) -> None:
    if any(not math.isfinite(item) for item in values):
        raise ValueError(f"{label} ECEF coordinates must be finite")
    radius = math.sqrt(sum(item * item for item in values))
    if not 5_000_000.0 <= radius <= 8_000_000.0:
        raise ValueError(f"{label} ECEF coordinates are outside the terrestrial domain")


def _validate_matrix2(matrix: Matrix2) -> None:
    values = tuple(item for row in matrix for item in row)
    if any(not math.isfinite(item) for item in values):
        raise ValueError("covariance values must be finite")
    if not math.isclose(matrix[0][1], matrix[1][0], rel_tol=1e-12, abs_tol=1e-15):
        raise ValueError("covariance must be symmetric")
    left_variance = matrix[0][0]
    right_variance = matrix[1][1]
    cross_covariance = matrix[0][1]
    if left_variance < 0.0 or right_variance < 0.0:
        raise ValueError("covariance diagonal must be nonnegative")
    if (left_variance == 0.0 or right_variance == 0.0) and cross_covariance != 0.0:
        raise ValueError("zero-variance covariance rows cannot contain cross-covariance")
    if left_variance == 0.0 or right_variance == 0.0:
        return
    correlation = cross_covariance / (math.sqrt(left_variance) * math.sqrt(right_variance))
    if abs(correlation) > 1.0 and not math.isclose(
        abs(correlation), 1.0, rel_tol=1e-12, abs_tol=0.0
    ):
        raise ValueError("covariance must be positive semidefinite")


def _validate_matrix3(matrix: Matrix3, *, positive_definite: bool) -> None:
    values = tuple(item for row in matrix for item in row)
    if any(not math.isfinite(item) for item in values):
        raise ValueError("covariance values must be finite")
    for row in range(3):
        for column in range(row + 1, 3):
            if not math.isclose(
                matrix[row][column],
                matrix[column][row],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("covariance must be symmetric")
    diagonals = tuple(matrix[index][index] for index in range(3))
    if any(item < 0.0 for item in diagonals):
        raise ValueError("covariance diagonal must be nonnegative")
    if positive_definite and any(item <= 0.0 for item in diagonals):
        raise ValueError("local-prior covariance must be positive definite")
    for index, variance in enumerate(diagonals):
        if variance == 0.0 and any(matrix[index][other] != 0.0 for other in range(3)):
            raise ValueError("zero-variance covariance rows cannot contain cross-covariance")
    active = tuple(index for index, variance in enumerate(diagonals) if variance > 0.0)
    correlations: dict[tuple[int, int], float] = {}
    for offset, left in enumerate(active):
        for right in active[offset + 1 :]:
            correlation = matrix[left][right] / (
                math.sqrt(diagonals[left]) * math.sqrt(diagonals[right])
            )
            if abs(correlation) > 1.0 and not math.isclose(
                abs(correlation), 1.0, rel_tol=1e-12, abs_tol=0.0
            ):
                raise ValueError("covariance must be positive semidefinite")
            correlations[(left, right)] = correlation
    if len(active) == 3:
        r01 = correlations[(0, 1)]
        r02 = correlations[(0, 2)]
        r12 = correlations[(1, 2)]
        determinant = 1.0 + 2.0 * r01 * r02 * r12 - r01**2 - r02**2 - r12**2
        if positive_definite:
            if 1.0 - r01**2 <= 1e-12 or determinant <= 1e-12:
                raise ValueError("local-prior covariance must be positive definite")
        elif determinant < -1e-12:
            raise ValueError("covariance must be positive semidefinite")


def _largest_eigenvalue_symmetric3(matrix: Matrix3) -> float:
    """Return λmax with a scale-normalized closed form for a symmetric 3x3 matrix."""

    scale = max(abs(item) for row in matrix for item in row)
    if scale == 0.0:
        return 0.0
    normalized = tuple(tuple(item / scale for item in row) for row in matrix)
    off_diagonal_energy = normalized[0][1] ** 2 + normalized[0][2] ** 2 + normalized[1][2] ** 2
    if off_diagonal_energy == 0.0:
        return max(normalized[index][index] for index in range(3)) * scale
    center = sum(normalized[index][index] for index in range(3)) / 3.0
    spread = math.sqrt(
        (
            sum((normalized[index][index] - center) ** 2 for index in range(3))
            + 2.0 * off_diagonal_energy
        )
        / 6.0
    )
    centered_scaled: Matrix3 = (
        (
            (normalized[0][0] - center) / spread,
            normalized[0][1] / spread,
            normalized[0][2] / spread,
        ),
        (
            normalized[1][0] / spread,
            (normalized[1][1] - center) / spread,
            normalized[1][2] / spread,
        ),
        (
            normalized[2][0] / spread,
            normalized[2][1] / spread,
            (normalized[2][2] - center) / spread,
        ),
    )
    determinant = (
        centered_scaled[0][0]
        * (
            centered_scaled[1][1] * centered_scaled[2][2]
            - centered_scaled[1][2] * centered_scaled[2][1]
        )
        - centered_scaled[0][1]
        * (
            centered_scaled[1][0] * centered_scaled[2][2]
            - centered_scaled[1][2] * centered_scaled[2][0]
        )
        + centered_scaled[0][2]
        * (
            centered_scaled[1][0] * centered_scaled[2][1]
            - centered_scaled[1][1] * centered_scaled[2][0]
        )
    )
    angle = math.acos(max(-1.0, min(1.0, determinant / 2.0))) / 3.0
    return max(0.0, center + 2.0 * spread * math.cos(angle)) * scale
