"""Solver-safe joint satellite corrections from one catalogue association fit.

The exact catalogue association marginalizes continuity-component offsets and
hardware drift.  Those states are receiver-local and gauge-dependent, so they
must never be relabelled as satellite clock corrections.  This additive
contract instead preserves every reported ``K=0,1,2`` association mode and
accepts only a separately calibrated, gauge-resolved satellite-frequency state
for each non-null mode.  Cross-satellite frequency covariance is retained.
"""

from __future__ import annotations

import itertools
import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.catalogue_association import EpisodeCatalogueAssignmentV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    EquivalentEpochCorrectionV1,
    SatelliteFrequencyStateV1,
    VerifiedTleMemberV1,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_MAXIMUM_JOINT_MODES = 4096


class JointCalibratedSatelliteStateV1(ContractModel):
    """One satellite-side state inside a joint association mode."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: Annotated[int, Field(gt=0)]
    element_age_s_at_reference: Annotated[float, Field(ge=0.0)]
    ephemeris: EquivalentEpochCorrectionV1
    frequency: SatelliteFrequencyStateV1

    @field_validator("element_age_s_at_reference")
    @classmethod
    def _finite_age(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("joint correction element age must be finite")
        return value

    @model_validator(mode="after")
    def _state_is_closed(self) -> Self:
        if self.ephemeris.reference_utc_ns != self.frequency.reference_utc_ns:
            raise ValueError("joint ephemeris and frequency states need one reference instant")
        expected_age = abs(self.ephemeris.reference_utc_ns - self.element_epoch_utc_ns) / 1e9
        if not math.isclose(
            self.element_age_s_at_reference,
            expected_age,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("joint correction element age does not match its reference")
        return self


class JointSatelliteCorrectionModeV1(ContractModel):
    """One discrete catalogue mode plus its satellite-side joint covariance."""

    schema_version: Literal[1] = 1
    association_mode_digest: Sha256Digest
    posterior_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    assignments: Annotated[tuple[EpisodeCatalogueAssignmentV1, ...], Field(min_length=1)]
    active_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=2)]
    satellite_states: Annotated[tuple[JointCalibratedSatelliteStateV1, ...], Field(max_length=2)]
    frequency_covariance: tuple[tuple[float, ...], ...]
    receiver_frequency_gauge_resolved: bool
    frequency_calibration_evidence_eligible: bool
    navigation_eligible: bool
    mode_digest: Sha256Digest

    @field_validator("posterior_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("joint correction mode probability must be finite")
        return value

    @model_validator(mode="after")
    def _mode_is_closed(self) -> Self:
        if self.active_catalog_numbers != tuple(sorted(set(self.active_catalog_numbers))):
            raise ValueError("joint correction active catalogues must be unique and ordered")
        assigned = {
            item.catalog_number for item in self.assignments if item.catalog_number is not None
        }
        if assigned != set(self.active_catalog_numbers):
            raise ValueError("joint correction assignments do not match active catalogues")
        state_numbers = tuple(item.catalog_number for item in self.satellite_states)
        if state_numbers != self.active_catalog_numbers:
            raise ValueError("joint satellite states do not match the active catalogue inventory")
        dimension = 2 * len(self.satellite_states)
        _validate_covariance(self.frequency_covariance, dimension=dimension)
        for index, state in enumerate(self.satellite_states):
            block = self.frequency_covariance[2 * index : 2 * index + 2]
            if not math.isclose(
                block[0][2 * index],
                state.frequency.bias_variance_hz2,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ) or not math.isclose(
                block[1][2 * index + 1],
                state.frequency.drift_variance_hz2_s2,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("joint covariance diagonal disagrees with satellite states")
            if not math.isclose(
                block[0][2 * index + 1],
                state.frequency.bias_drift_covariance_hz2_s,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("joint covariance block disagrees with satellite state")
        if not self.satellite_states and self.navigation_eligible:
            raise ValueError("the null association mode cannot be navigation eligible")
        if self.navigation_eligible and (
            not self.receiver_frequency_gauge_resolved
            or not self.frequency_calibration_evidence_eligible
        ):
            raise ValueError("navigation eligibility requires a resolved frequency calibration")
        if (
            any(item.ephemeris.boundary_hit for item in self.satellite_states)
            and self.navigation_eligible
        ):
            raise ValueError("a tau-boundary joint mode cannot be navigation eligible")
        if self.mode_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"mode_digest"})
        ):
            raise ValueError("joint correction mode digest does not match content")
        return self


class JointSatelliteCorrectionProductV1(ContractModel):
    """Complete joint correction posterior with receiver nuisance excluded."""

    schema_version: Literal[1] = 1
    kind: Literal["joint-satellite-correction-product"] = "joint-satellite-correction-product"
    algorithm_version: Literal["known-position-joint-calibration-v1"] = (
        "known-position-joint-calibration-v1"
    )
    calibration_protocol_digest: Sha256Digest
    calibration_evidence_digest: Sha256Digest
    association_result_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    frequency_calibration_authority_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    calibration_source_spans: Annotated[
        tuple[CalibrationSourceSpanV1, ...], Field(min_length=1, max_length=4096)
    ]
    calibration_start_utc_ns: Annotated[int, Field(gt=0)]
    calibration_end_utc_ns: Annotated[int, Field(gt=0)]
    produced_utc_ns: Annotated[int, Field(gt=0)]
    valid_from_utc_ns: Annotated[int, Field(gt=0)]
    valid_until_utc_ns: Annotated[int, Field(gt=0)]
    tle_snapshot: TleSnapshotRefV1
    tle_membership_authority_digest: Sha256Digest
    verified_tle_members: Annotated[tuple[VerifiedTleMemberV1, ...], Field(max_length=512)]
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    modes: Annotated[
        tuple[JointSatelliteCorrectionModeV1, ...],
        Field(min_length=1, max_length=_MAXIMUM_JOINT_MODES),
    ]
    status: StandardScientificStatus
    calibration_site_disclosed: Literal[False] = False
    receiver_local_state_excluded: Literal[True] = True
    association_nuisance_treatment: Literal["marginalized-in-mode-evidence-not-exported-v1"] = (
        "marginalized-in-mode-evidence-not-exported-v1"
    )
    satellite_frequency_gauge_resolution_required_for_navigation: Literal[True] = True
    cross_satellite_frequency_covariance_retained: Literal[True] = True
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False
    navigation_fix_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("downlink_frequency_hz")
    @classmethod
    def _finite_rf(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("joint correction RF must be finite")
        return value

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        if self.calibration_end_utc_ns <= self.calibration_start_utc_ns:
            raise ValueError("joint calibration interval must be non-empty")
        if self.produced_utc_ns < self.calibration_end_utc_ns:
            raise ValueError("joint correction cannot predate calibration completion")
        if self.valid_from_utc_ns != self.produced_utc_ns or self.valid_until_utc_ns != (
            self.produced_utc_ns + 30_000_000_000
        ):
            raise ValueError("joint correction validity must be the fixed 30-second horizon")
        if self.tle_snapshot.collected_utc_ns > self.calibration_start_utc_ns:
            raise ValueError("joint correction TLE snapshot must be causal")
        if self.produced_utc_ns - self.tle_snapshot.collected_utc_ns > 86_400_000_000_000:
            raise ValueError("joint correction TLE snapshot exceeds the freshness policy")
        span_keys = tuple(
            (
                item.source_recording_fingerprint,
                item.source_stream_index,
                item.source_sample_start,
                item.source_sample_stop,
            )
            for item in self.calibration_source_spans
        )
        if span_keys != tuple(sorted(set(span_keys))):
            raise ValueError("joint calibration source spans must be unique and ordered")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.calibration_source_spans
        ):
            raise ValueError("joint correction source spans use the wrong authority")
        if any(
            item.start_utc_ns < self.calibration_start_utc_ns
            or item.end_utc_ns > self.calibration_end_utc_ns
            for item in self.calibration_source_spans
        ):
            raise ValueError("joint correction source span lies outside calibration")
        _validate_source_span_chronology(self.calibration_source_spans)
        members = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.verified_tle_members
        )
        if members != tuple(sorted(set(members))):
            raise ValueError("joint correction TLE membership must be unique and ordered")
        mode_digests = tuple(item.mode_digest for item in self.modes)
        association_mode_digests = tuple(item.association_mode_digest for item in self.modes)
        if len(set(mode_digests)) != len(mode_digests) or len(set(association_mode_digests)) != len(
            association_mode_digests
        ):
            raise ValueError("joint correction modes must be unique")
        if not math.isclose(
            math.fsum(item.posterior_probability for item in self.modes),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("joint correction mode probabilities must sum to one")
        used_members = {
            (state.catalog_number, state.selected_element_digest, state.element_epoch_utc_ns)
            for mode in self.modes
            for state in mode.satellite_states
        }
        if used_members != set(members):
            raise ValueError("joint correction verified members do not close over its states")
        has_eligible = any(
            item.navigation_eligible and item.posterior_probability > 0.0 for item in self.modes
        )
        if has_eligible != (self.status is StandardScientificStatus.COMPLETE):
            raise ValueError("joint correction status disagrees with eligible modes")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("joint correction product digest does not match content")
        return self


class KnownPositionJointCalibrationReceiptV1(ContractModel):
    """Access-controlled site/local-state receipt; never a solver input."""

    schema_version: Literal[1] = 1
    calibration_site: ObserverSiteV1
    calibration_site_authority_digest: Sha256Digest
    full_joint_state_digest: Sha256Digest
    receiver_local_state_digest: Sha256Digest
    joint_correction_product: JointSatelliteCorrectionProductV1
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_closed(self) -> Self:
        product = JointSatelliteCorrectionProductV1.model_validate(
            self.joint_correction_product.model_dump(mode="json")
        )
        if self.sealed_utc_ns < product.produced_utc_ns:
            raise ValueError("joint calibration receipt predates its product")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("joint calibration receipt digest does not match content")
        return self


def _validate_covariance(matrix: tuple[tuple[float, ...], ...], *, dimension: int) -> None:
    if len(matrix) != dimension or any(len(row) != dimension for row in matrix):
        raise ValueError("joint frequency covariance has the wrong dimensions")
    if dimension == 0:
        return
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ValueError("joint frequency covariance must be finite")
    for row in range(dimension):
        if matrix[row][row] < 0.0:
            raise ValueError("joint frequency covariance diagonal must be nonnegative")
        for column in range(row + 1, dimension):
            if not math.isclose(
                matrix[row][column],
                matrix[column][row],
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("joint frequency covariance must be symmetric")
    active = tuple(index for index in range(dimension) if matrix[index][index] > 0.0)
    for index in range(dimension):
        if matrix[index][index] == 0.0 and any(
            matrix[index][other] != 0.0 for other in range(dimension)
        ):
            raise ValueError("zero-variance joint covariance rows must be zero")
    correlation = tuple(
        tuple(
            matrix[left][right] / math.sqrt(matrix[left][left] * matrix[right][right])
            for right in active
        )
        for left in active
    )
    for size in range(1, len(active) + 1):
        for subset in itertools.combinations(range(len(active)), size):
            determinant = _determinant(
                tuple(tuple(correlation[row][column] for column in subset) for row in subset)
            )
            if determinant < -1e-10:
                raise ValueError("joint frequency covariance must be positive semidefinite")


def _determinant(matrix: tuple[tuple[float, ...], ...]) -> float:
    size = len(matrix)
    if size == 0:
        return 1.0
    result = 0.0
    for permutation in itertools.permutations(range(size)):
        inversions = sum(
            permutation[left] > permutation[right]
            for left in range(size)
            for right in range(left + 1, size)
        )
        product = math.prod(matrix[row][permutation[row]] for row in range(size))
        result += -product if inversions % 2 else product
    return result


def _validate_source_span_chronology(
    spans: tuple[CalibrationSourceSpanV1, ...],
) -> None:
    grouped: dict[tuple[str, int], list[CalibrationSourceSpanV1]] = {}
    for span in spans:
        grouped.setdefault(
            (span.source_recording_fingerprint, span.source_stream_index), []
        ).append(span)
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: item.source_sample_start)
        for left, right in zip(ordered, ordered[1:], strict=False):
            if left.source_sample_stop > right.source_sample_start:
                raise ValueError("joint calibration source spans overlap")
            if left.end_utc_ns > right.start_utc_ns:
                raise ValueError("joint calibration sample and UTC ordering disagree")
